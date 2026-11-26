# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""AI Models (Phase 31): how each AI model does, and which model each job uses.

Everything is read from HDS AI Usage Log, where every attempt is a row: TBO Support's own calls
(with their speed, and a Failed row with the error's kind when the provider refused) and the
Copilot worker's stages. Nothing here reads or returns a prompt or a customer's text.
"""

import contextlib
import re
import zlib

import frappe
from frappe import _
from frappe.utils import (
    add_days,
    add_to_date,
    cint,
    flt,
    getdate,
    now_datetime,
    nowdate,
)

from helpdesk import ai_engine, ai_gateway

LOG = "HDS AI Usage Log"
SETTINGS = "HDS Hub Settings"
PERIODS = (7, 30, 90)
# enough calls before an error rate says something about the model
MIN_CALLS = 20
DEGRADED_ERROR_RATE = 5.0
ERROR_LABELS = {
    "rate_limit": "Rate limit",
    "timeout": "Timeout",
    "server": "Server error (5xx)",
    "billing": "Billing or quota",
    "auth": "Key refused",
    "config": "Model not found",
    "bad_answer": "Bad answer format",
}
LATEST_ERRORS = 50
SLOWEST = 10


def period(days) -> int:
    days = cint(days) or 30
    return days if days in PERIODS else 30


def since(days: int) -> str:
    return str(add_days(getdate(nowdate()), -(days - 1)))


def percentile(values: list[int], share: float) -> float | None:
    """The value below which `share` of the calls finished, in seconds; None without calls."""
    values = sorted(v for v in values if v)
    if not values:
        return None
    index = min(len(values) - 1, max(0, round(share * (len(values) - 1))))
    return round(values[index] / 1000, 1)


def rate(part: int, whole: int) -> float | None:
    return round(part / whole * 100, 1) if whole else None


def error_label(kind: str | None) -> str:
    return _(ERROR_LABELS.get(kind or "", kind or "Other"))


def _rows(days: int, model: str | None = None) -> list:
    filters = {"creation": [">=", since(days)]}
    if model:
        filters["model"] = model
    return frappe.get_all(
        LOG,
        filters=filters,
        fields=[
            "name",
            "creation",
            "model",
            "provider",
            "job",
            "ticket",
            "source",
            "status",
            "fallback",
            "duration_ms",
            "error_class",
            "error_message",
            "estimated_cost_usd",
            "input_tokens",
            "output_tokens",
        ],
        order_by="creation asc",
        limit=0,
    )


def _figures(rows: list) -> dict:
    calls = len(rows)
    failed = [r for r in rows if r.status == "Failed"]
    times = [r.duration_ms for r in rows if r.status != "Failed"]
    return {
        "calls": calls,
        "failed": len(failed),
        "error_rate": rate(len(failed), calls),
        "as_fallback": sum(1 for r in rows if r.fallback),
        "fallback_rate": rate(sum(1 for r in rows if r.fallback), calls),
        "cost": round(sum(r.estimated_cost_usd or 0 for r in rows), 2),
        "tokens": sum((r.input_tokens or 0) + (r.output_tokens or 0) for r in rows),
        "p50": percentile(times, 0.5),
        "p95": percentile(times, 0.95),
    }


def job_plan(settings=None) -> list[dict]:
    """Each job's sections in the order it tries them, with the model of each."""
    settings = settings or ai_engine.get_hub_settings()
    providers = ai_engine.configured_providers(settings)
    plan = []
    for job in ai_engine.JOBS:
        models = ai_engine.job_models(job, settings)
        order = ai_engine.provider_order(settings, job)
        row = ai_engine.job_row(job, settings)
        steps = [
            {
                "section": slot,
                "model": models.get(slot) or _section_model(slot, settings, providers),
                "ready": bool(providers[slot]),
            }
            for slot in order
        ]
        plan.append(
            {
                "job": job,
                "primary": steps[0] if steps else None,
                "fallback": steps[1] if len(steps) > 1 else None,
                "primary_section": (row.get("primary_section") if row else "") or "",
                "allow_fallback": (row.get("allow_fallback") if row else "") or "",
                "openai_model": (row.get("openai_model") if row else "") or "",
                "anthropic_model": (row.get("anthropic_model") if row else "") or "",
            }
        )
    return plan


def _section_model(slot: str, settings, providers) -> str:
    """A section's model as set, also when the section has no key yet."""
    if providers[slot]:
        return providers[slot].model
    field = "openai_model" if slot == ai_engine.OPENAI_SLOT else "default_triage_model"
    return (settings.get(field) or "").strip()


def _used_for(plan: list[dict]) -> dict[str, dict]:
    used: dict[str, dict] = {}
    for job in plan:
        for role in ("primary", "fallback"):
            step = job[role]
            if step and step["model"]:
                used.setdefault(step["model"], {"primary": [], "fallback": []})[
                    role
                ].append(job["job"])
    return used


def _status(
    model: str, figures: dict, paused: set[str], candidate: bool = False
) -> str:
    if model in paused:
        return "Paused"
    if not figures["calls"]:
        return "Candidate" if candidate else "Not used"
    if (
        figures["calls"] >= MIN_CALLS
        and (figures["error_rate"] or 0) >= DEGRADED_ERROR_RATE
    ):
        return "Degraded"
    return "Healthy"


def _paused_models(settings) -> set[str]:
    """Models whose section, or own job model, the engine has paused after a failure."""
    paused = set()
    providers = ai_engine.configured_providers(settings)
    for job in ai_engine.JOBS:
        for provider in ai_engine.get_providers(job):
            if ai_engine.circuit_open(provider):
                paused.add(provider.model)
    for provider in providers.values():
        if provider and ai_engine.circuit_open(provider):
            paused.add(provider.model)
    return paused


def _hub_overview(days: int = 30) -> dict:
    """Every model side by side for the period, with the totals above them."""
    days = period(days)
    rows = _rows(days)
    settings = ai_engine.get_hub_settings()
    plan = job_plan(settings)
    used = _used_for(plan)
    paused = _paused_models(settings)
    by_model: dict[str, list] = {}
    for row in rows:
        by_model.setdefault(row.model or _("(no model)"), []).append(row)
    scores = latest_scores()
    waiting = candidate_names() - set(used)
    names = sorted(set(by_model) | set(used) | set(scores) | waiting)
    models = []
    for name in names:
        mine = by_model.get(name, [])
        figures = _figures(mine)
        models.append(
            {
                "model": name,
                "provider": (mine[-1].provider if mine else "")
                or _section_of(name, plan)
                or (candidate_section(name) if name in waiting else ""),
                "used_for": used.get(name, {"primary": [], "fallback": []}),
                **figures,
                "benchmark": scores.get(name),
                "status": _status(name, figures, paused, name in waiting),
            }
        )
    models.sort(key=lambda m: (-m["calls"], m["model"]))
    return {
        "days": days,
        "totals": _figures(rows),
        "budget_usd": frappe.db.get_single_value(
            "HDS Copilot Settings", "monthly_ai_budget_usd"
        )
        or 0,
        "models": models,
        "attention": [
            m["model"] for m in models if m["status"] in ("Paused", "Degraded")
        ],
        "recorded_since": _recorded_since(),
    }


def _section_of(model: str, plan: list[dict]) -> str:
    for job in plan:
        for role in ("primary", "fallback"):
            if job[role] and job[role]["model"] == model:
                return job[role]["section"]
    return ""


def _recorded_since() -> str:
    """The first day speed and errors were recorded: earlier rows have neither."""
    first = frappe.get_all(
        LOG,
        filters={"duration_ms": [">", 0]},
        fields=["creation"],
        order_by="creation asc",
        limit=1,
    )
    return str(getdate(first[0].creation)) if first else ""


def _hub_detail(model: str, days: int = 30) -> dict:
    """One model's performance and errors for the period."""
    days = period(days)
    rows = _rows(days, model)
    settings = ai_engine.get_hub_settings()
    plan = job_plan(settings)
    figures = _figures(rows)

    daily: dict[str, list] = {}
    for row in rows:
        daily.setdefault(str(getdate(row.creation)), []).append(row)
    start = getdate(since(days))
    series = []
    for i in range(days):
        day = str(add_days(start, i))
        f = _figures(daily.get(day, []))
        series.append(
            {
                "day": day,
                "calls": f["calls"],
                "failed": f["failed"],
                "error_rate": f["error_rate"] or 0,
                "cost": f["cost"],
                "p50": f["p50"],
            }
        )

    def grouped(key) -> list[dict]:
        groups: dict[str, list] = {}
        for row in rows:
            groups.setdefault(row.get(key) or _("(none)"), []).append(row)
        out = [{"name": name, **_figures(mine)} for name, mine in groups.items()]
        return sorted(out, key=lambda g: -g["calls"])

    failed = [r for r in rows if r.status == "Failed"]
    kinds: dict[str, int] = {}
    for row in failed:
        kinds[row.error_class or "other"] = kinds.get(row.error_class or "other", 0) + 1

    # the fallback's successful calls of the period, to say which failures were answered anyway
    rescues: dict[tuple, list] = {}
    for r in frappe.get_all(
        LOG,
        filters={"creation": [">=", since(days)], "fallback": 1, "status": "Success"},
        fields=["creation", "job", "ticket"],
        limit=0,
    ):
        rescues.setdefault((r.job, r.ticket), []).append(r.creation)

    def answered_after(row) -> bool:
        """Whether a fallback call for the same job and ticket followed within 5 minutes."""
        return any(
            0 <= (moment - row.creation).total_seconds() <= 300
            for moment in rescues.get((row.job, row.ticket), [])
        )

    latest = [
        {
            "when": str(row.creation)[:16],
            "job": row.job or "",
            "ticket": row.ticket or "",
            "kind": error_label(row.error_class),
            "message": row.error_message or "",
            "fallback_answered": answered_after(row),
        }
        for row in reversed(failed[-LATEST_ERRORS:])
    ]
    slowest = [
        {
            "when": str(row.creation)[:16],
            "job": row.job or "",
            "ticket": row.ticket or "",
            "seconds": round((row.duration_ms or 0) / 1000, 1),
        }
        for row in sorted(
            (r for r in rows if r.duration_ms and r.status != "Failed"),
            key=lambda r: -r.duration_ms,
        )[:SLOWEST]
    ]
    used = _used_for(plan).get(model, {"primary": [], "fallback": []})
    waiting = model in candidate_names() and not (used["primary"] or used["fallback"])
    return {
        "model": model,
        "days": days,
        "provider": (rows[-1].provider if rows else "")
        or _section_of(model, plan)
        or (candidate_section(model) if waiting else ""),
        "used_for": used,
        "status": _status(model, figures, _paused_models(settings), waiting),
        **figures,
        "series": series,
        "by_job": grouped("job"),
        "by_source": grouped("source"),
        "errors_by_kind": sorted(
            ({"kind": error_label(k), "count": n} for k, n in kinds.items()),
            key=lambda e: -e["count"],
        ),
        "errors_by_job": [g for g in grouped("job") if g["failed"]],
        "latest_errors": latest,
        "slowest": slowest,
        "recorded_since": _recorded_since(),
    }


def job_settings(days: int = 30) -> dict:
    """Model settings: each job's primary and fallback, with how it did in the period."""
    days = period(days)
    rows = _rows(days)
    settings = ai_engine.get_hub_settings()
    providers = ai_engine.configured_providers(settings)
    by_job: dict[str, list] = {}
    for row in rows:
        by_job.setdefault(row.job or "", []).append(row)
    scores = latest_scores()
    jobs = []
    for job in job_plan(settings):
        first = (job["primary"] or {}).get("model")
        jobs.append(
            {
                **job,
                **_figures(by_job.get(job["job"], [])),
                "score": scores.get(first),
            }
        )
    return {
        "days": days,
        "jobs": jobs,
        "sections": [
            {
                "section": slot,
                "ready": bool(providers[slot]),
                "model": _section_model(slot, settings, providers),
            }
            for slot in ai_engine.SLOTS
        ],
        "defaults": {
            "primary_section": settings.get("primary_ai_provider")
            or ai_engine.ANTHROPIC_SLOT,
            "failover": bool(settings.get("ai_failover")),
        },
        "models": sorted({r.model for r in rows if r.model} | candidate_names()),
        "candidates": candidates(),
        "alerts": alert_limits(settings),
        "guarded_jobs": list(GUARDED_JOBS),
        "can_change": can_change(),
        "gateway": ai_gateway.status(),
        "changes": frappe.get_all(
            "HDS Model Change",
            fields=[
                "creation",
                "job",
                "setting",
                "old_value",
                "new_value",
                "changed_by",
            ],
            order_by="creation desc",
            limit=20,
        ),
    }


def can_change(user: str | None = None) -> bool:
    """Only System Managers change which model a job uses."""
    user = user or frappe.session.user
    return user == "Administrator" or "System Manager" in frappe.get_roles(user)


JOB_SETTINGS = ("primary_section", "allow_fallback", "openai_model", "anthropic_model")
SETTING_LABELS = {
    "primary_section": "Primary section",
    "allow_fallback": "Fallback",
    "openai_model": "OpenAI model",
    "anthropic_model": "Anthropic-compatible model",
}


def _clean_job(job: str, values: dict) -> dict:
    if job not in ai_engine.JOBS:
        frappe.throw(_("Unknown AI job {0}").format(job))
    unknown = set(values) - set(JOB_SETTINGS)
    if unknown:
        frappe.throw(_("{0} cannot be changed here").format(", ".join(sorted(unknown))))
    clean = {k: str(v or "").strip() for k, v in values.items()}
    if clean.get("primary_section") not in (None, "", *ai_engine.SLOTS):
        frappe.throw(_("Unknown section {0}").format(clean["primary_section"]))
    if clean.get("allow_fallback") not in (None, "", "On", "Off"):
        frappe.throw(_("Fallback is On, Off or blank (as the settings say)"))
    return clean


def _apply_job(doc, job: str, clean: dict) -> list[tuple]:
    """Sets a job's choices on the settings document (not saved); returns what changed."""
    row = next((r for r in doc.get("ai_jobs") or [] if r.job == job), None)
    if not row:
        row = doc.append("ai_jobs", {"job": job})
    changes = []
    for field, value in clean.items():
        before = row.get(field) or ""
        if before != value:
            changes.append((field, before, value))
            row.set(field, value)
    return changes


def _first_model(settings, job: str) -> str:
    step = next(j for j in job_plan(settings) if j["job"] == job)["primary"]
    return (step or {}).get("model") or ""


def guard(job: str, values: dict) -> dict:
    """Before a Copilot job's model changes: the new first model's newest test-set score beside
    the current one's, and a warning when it has none or scores lower. Nothing is saved."""
    clean = _clean_job(job, values)
    doc = frappe.get_doc(SETTINGS)
    current = _first_model(doc, job)
    _apply_job(doc, job, clean)
    model = _first_model(doc, job)
    scores = latest_scores()
    mine, theirs = scores.get(model), scores.get(current)
    warning = ""
    if job in GUARDED_JOBS and model and model != current:
        if not mine:
            warning = _(
                "{0} has no run of the test set yet, so nothing says how well it does {1}."
            ).format(model, job)
        elif theirs and mine["accuracy"] < theirs["accuracy"]:
            warning = _(
                "{0} got {1}% of the test set right; {2}, which {3} uses now, got {4}%."
            ).format(model, mine["accuracy"], current, job, theirs["accuracy"])
    return {
        "job": job,
        "model": model,
        "score": mine,
        "current_model": current,
        "current_score": theirs,
        "changes_model": bool(model and model != current),
        "warning": warning,
    }


def save_job(job: str, values: dict) -> dict:
    """One job's first section, fallback and models; each change is written to the history."""
    if not can_change():
        frappe.throw(
            _("Only System Managers change which model a job uses."),
            frappe.PermissionError,
        )
    clean = _clean_job(job, values)
    doc = frappe.get_doc(SETTINGS)
    changes = _apply_job(doc, job, clean)
    if not changes:
        return job_settings()
    doc.save(ignore_permissions=True)
    for field, before, value in changes:
        frappe.get_doc(
            {
                "doctype": "HDS Model Change",
                "job": job,
                "setting": SETTING_LABELS[field],
                "old_value": before or _("(default)"),
                "new_value": value or _("(default)"),
                "changed_by": frappe.session.user,
            }
        ).insert(ignore_permissions=True)
    for model in (clean.get("openai_model"),):
        if model:
            ai_engine.ensure_model_pricing(model, ai_engine.OPENAI_SLOT)
    ai_engine.reset_provider_state()
    return job_settings()


def try_job(job: str) -> dict:
    """One tiny call with the job's first model: how long it took, or what the provider said."""
    if not can_change():
        frappe.throw(
            _("Only System Managers test a job's model."), frappe.PermissionError
        )
    if job not in ai_engine.JOBS:
        frappe.throw(_("Unknown AI job {0}").format(job))
    providers = ai_engine.get_providers(job)
    if not providers:
        return {
            "ok": False,
            "message": _("This job's section has no API key or model yet."),
        }
    provider = providers[0]
    from time import monotonic

    started = monotonic()
    try:
        ai_engine.complete(
            provider,
            "Reply with the single word OK.",
            "Connection test",
            budgets=(ai_engine.TEST_TOKEN_BUDGET,),
        )
    except ai_engine.AIProviderError as e:
        return {
            "ok": False,
            "model": provider.model,
            "message": _("{0} answered: {1}").format(provider.model, e.summary),
        }
    ai_engine.record_success(provider)
    return {
        "ok": True,
        "model": provider.model,
        "message": _("{0} answered in {1} s.").format(
            provider.model, round(monotonic() - started, 1)
        ),
    }


# --- candidates: models added to be tested before a job uses them --------------------------------

PRICING = "HDS Model Pricing"
# a wrong model here changes what Copilot tells a customer or writes as a fix
GUARDED_JOBS = ai_engine.WORKER_JOBS


def candidate_names() -> set[str]:
    return set(frappe.get_all(PRICING, filters={"candidate": 1}, pluck="name"))


def candidate_section(model: str) -> str:
    section = frappe.db.get_value(PRICING, model, "provider") or ""
    return ai_engine.ANTHROPIC_SLOT if section == "Anthropic" else section


def candidates() -> list[dict]:
    """The models added to be tested, with their prices and newest test-set score."""
    scores = latest_scores()
    used = _used_for(job_plan())
    rows = frappe.get_all(
        PRICING,
        filters={"candidate": 1},
        fields=[
            "name",
            "provider",
            "input_cost_per_1m",
            "output_cost_per_1m",
            "notes",
        ],
        order_by="creation desc",
    )
    return [
        {
            "model": r.name,
            "section": ai_engine.ANTHROPIC_SLOT
            if r.provider == "Anthropic"
            else r.provider,
            "input_price": r.input_cost_per_1m or 0,
            "output_price": r.output_cost_per_1m or 0,
            "note": r.notes or "",
            "benchmark": scores.get(r.name),
            "in_use": r.name in used,
        }
        for r in rows
    ]


def add_model(values: dict) -> dict:
    """A model to test before any job uses it: its name as the provider writes it, the section
    it is called through, and its prices per million tokens."""
    if not can_change():
        frappe.throw(_("Only System Managers add a model."), frappe.PermissionError)
    model = str(values.get("model") or "").strip()
    if not model:
        frappe.throw(_("Give the model's name as the provider writes it."))
    if len(model) > 140 or re.search(r"\s", model):
        frappe.throw(_("A model's name has no spaces and at most 140 characters."))
    section = str(values.get("section") or "").strip()
    if section not in ai_engine.SLOTS:
        frappe.throw(_("Choose the section this model is called through."))
    prices = {
        "input_cost_per_1m": flt(values.get("input_price")),
        "output_cost_per_1m": flt(values.get("output_price")),
    }
    if min(prices.values()) < 0:
        frappe.throw(_("A price cannot be below 0."))
    note = str(values.get("note") or "").strip()[:500]
    if frappe.db.exists(PRICING, model):
        doc = frappe.get_doc(PRICING, model)
        if doc.candidate:
            frappe.throw(_("{0} is already a candidate.").format(model))
        # a model TBO Support already knows keeps its section and a price it already has
        for field, price in prices.items():
            if price:
                doc.set(field, price)
        if note:
            doc.notes = note
    else:
        doc = frappe.new_doc(PRICING)
        doc.update(
            {
                "model_id": model,
                "display_name": model,
                "provider": section,
                "is_active": 1,
                "notes": note,
                **prices,
            }
        )
    doc.candidate = 1
    doc.save(ignore_permissions=True)
    return job_settings()


def remove_candidate(model: str) -> dict:
    """Takes a model off the candidates. Its price row goes too when nothing ever used it."""
    if not can_change():
        frappe.throw(
            _("Only System Managers remove a candidate."), frappe.PermissionError
        )
    if not frappe.db.get_value(PRICING, model, "candidate"):
        frappe.throw(_("{0} is not a candidate.").format(model))
    known = (
        model in _used_for(job_plan())
        or frappe.db.exists(LOG, {"model": model})
        or frappe.db.exists(EVAL_RUN, {"model": model})
    )
    if known:
        frappe.db.set_value(PRICING, model, "candidate", 0)
    else:
        frappe.delete_doc(PRICING, model, ignore_permissions=True)
    return job_settings()


# --- alerts: a model that fails, or a fallback that answers, more than the limit ------------------

ALERT_MIN_CALLS = 10
ALERT_QUIET_HOURS = 6
ALERT_KEY = "ai_models:alerted:{0}"
ALERT_FIELDS = {
    "error_rate": "model_alert_error_rate",
    "fallback_rate": "model_alert_fallback_rate",
}


def alert_limits(settings=None) -> dict:
    """The limits in percent; 0 switches that alert off."""
    settings = settings or ai_engine.get_hub_settings()
    return {key: cint(settings.get(field)) for key, field in ALERT_FIELDS.items()}


def save_alerts(values: dict) -> dict:
    if not can_change():
        frappe.throw(
            _("Only System Managers change the alert limits."), frappe.PermissionError
        )
    doc = frappe.get_doc(SETTINGS)
    for key, field in ALERT_FIELDS.items():
        if key not in values:
            continue
        limit = cint(values.get(key))
        if not 0 <= limit <= 100:
            frappe.throw(_("A limit is a percentage from 0 (off) to 100."))
        doc.set(field, limit)
    doc.save(ignore_permissions=True)
    return alert_limits(doc)


def send_alert(subject: str) -> None:
    """To the System and Agent Managers, in the app and in the team's chat channel."""
    from helpdesk.github_sync import admin_users
    from helpdesk.work_reminders import notify_users

    notify_users(
        admin_users(),
        SETTINGS,
        SETTINGS,
        subject,
        escalate=True,
        link="/ai-models",
        once=False,
    )


def _alert_once(key: str, subject: str, sent: list[str]) -> None:
    cache_key = ALERT_KEY.format(key)
    if frappe.cache.get_value(cache_key, expires=True):
        return
    send_alert(subject)
    frappe.cache.set_value(cache_key, 1, expires_in_sec=ALERT_QUIET_HOURS * 3600)
    sent.append(subject)


def watch() -> list[str]:
    """Hourly: tells the managers when a model failed, or the fallback answered, more often
    than the limit in the last hour. One alert per model in six hours. Never raises."""
    sent: list[str] = []
    try:
        limits = alert_limits()
        if not (limits["error_rate"] or limits["fallback_rate"]):
            return sent
        rows = frappe.get_all(
            LOG,
            filters={"creation": [">=", add_to_date(now_datetime(), hours=-1)]},
            fields=["model", "status", "fallback"],
            limit=0,
        )
        by_model: dict[str, list] = {}
        for row in rows:
            if row.model:
                by_model.setdefault(row.model, []).append(row)
        for model, mine in by_model.items():
            failed = sum(1 for r in mine if r.status == "Failed")
            share = rate(failed, len(mine)) or 0
            if (
                limits["error_rate"]
                and len(mine) >= ALERT_MIN_CALLS
                and share >= limits["error_rate"]
            ):
                _alert_once(
                    f"errors:{model}",
                    _(
                        "AI model {0}: {1}% of its calls failed in the last hour ({2} of {3}). See AI models."
                    ).format(model, share, failed, len(mine)),
                    sent,
                )
        answered = [r for r in rows if r.status != "Failed"]
        rescued = sum(1 for r in answered if r.fallback)
        share = rate(rescued, len(answered)) or 0
        if (
            limits["fallback_rate"]
            and len(answered) >= ALERT_MIN_CALLS
            and share >= limits["fallback_rate"]
        ):
            _alert_once(
                "fallback",
                _(
                    "AI fallback: the fallback model gave {0}% of the answers in the last hour ({1} of {2}). See AI models."
                ).format(share, rescued, len(answered)),
                sent,
            )
    except Exception:
        with contextlib.suppress(Exception):
            frappe.log_error(title="AI model alerts not checked")
    return sent


# --- benchmarks: our own test set, and public numbers beside it ---------------------------------

EVAL_RUN = "HDS Model Eval Run"
EVAL_REQUEST = "HDS Model Eval Request"
PUBLIC = "HDS Public Benchmark"


def store_eval(
    model: str,
    results: list,
    job: str = "investigate",
    source: str = "Worker",
    ran_on=None,
) -> str:
    """Keeps one run of the test set as scores per case number. A case's text, its expected
    answer and Copilot's own summary are dropped here: they never reach the hub's records."""
    model = str(model or "").strip()
    if not model:
        frappe.throw(_("The report names no model."))
    rows = []
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict):
            continue
        case = item.get("case")
        case_id = case.get("id") if isinstance(case, dict) else case
        if not case_id:
            continue
        found = item.get("filesFound", item.get("files_found"))
        rows.append(
            {
                "case_id": str(case_id)[:40],
                "right": 1 if item.get("right") else 0,
                "confidence": frappe.utils.flt(item.get("confidence")),
                "files_found": len(found) if isinstance(found, list) else cint(found),
                "tokens": cint(item.get("tokens")),
                "cost_usd": frappe.utils.flt(item.get("costUsd", item.get("cost_usd"))),
                "minutes": frappe.utils.flt(item.get("minutes")),
                "outcome": str(item.get("outcome") or "")[:140],
            }
        )
    if not rows:
        frappe.throw(_("The report has no cases."))
    right = sum(r["right"] for r in rows)
    doc = frappe.get_doc(
        {
            "doctype": EVAL_RUN,
            "model": model,
            "job": job if job in ai_engine.JOBS else "investigate",
            "ran_on": getdate(ran_on or nowdate()),
            "source": source,
            "cases_total": len(rows),
            "cases_right": right,
            "accuracy": round(right / len(rows) * 100, 1),
            "avg_minutes": round(sum(r["minutes"] for r in rows) / len(rows), 1),
            "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 2),
            "results": rows,
        }
    ).insert(ignore_permissions=True)
    return doc.name


def _eval_runs(model: str | None = None) -> list:
    return frappe.get_all(
        EVAL_RUN,
        filters={"model": model} if model else {},
        fields=[
            "name",
            "model",
            "job",
            "ran_on",
            "source",
            "cases_total",
            "cases_right",
            "accuracy",
            "avg_minutes",
            "total_cost_usd",
        ],
        order_by="ran_on desc, creation desc",
        limit=50,
    )


def _cases(run: str) -> list[dict]:
    rows = frappe.get_all(
        "HDS Model Eval Result",
        filters={"parent": run, "parenttype": EVAL_RUN},
        fields=["case_id", "right", "minutes", "cost_usd"],
        order_by="idx asc",
    )
    return [
        {"case": r.case_id, "right": bool(r.right), "minutes": r.minutes} for r in rows
    ]


def latest_scores() -> dict[str, dict]:
    """Each model's newest run: {model: {accuracy, ran_on}}."""
    scores: dict[str, dict] = {}
    for run in _eval_runs():
        scores.setdefault(
            run.model, {"accuracy": run.accuracy, "ran_on": str(run.ran_on)}
        )
    return scores


def benchmarks(model: str, against: str | None = None) -> dict:
    """One model's runs of our test set, case by case for the newest, head to head with
    another model's newest run, and the public numbers a manager added."""
    runs = _eval_runs(model)
    for run in runs:
        run["cost_per_right_case"] = (
            round(run.total_cost_usd / run.cases_right, 2) if run.cases_right else None
        )
        run["ran_on"] = str(run.ran_on)
    others = sorted({r.model for r in _eval_runs() if r.model != model})
    against = against if against in others else (others[0] if others else "")
    theirs = _eval_runs(against)[:1] if against else []
    return {
        "model": model,
        "runs": runs,
        "cases": _cases(runs[0].name) if runs else [],
        "others": others,
        "against": against,
        "against_cases": _cases(theirs[0].name) if theirs else [],
        "against_accuracy": theirs[0].accuracy if theirs else None,
        "public": frappe.get_all(
            PUBLIC,
            filters={"model": model},
            fields=["name", "benchmark", "score", "measured_on", "source_url", "note"],
            order_by="measured_on desc",
        ),
        "requests": frappe.get_all(
            EVAL_REQUEST,
            filters={"model": model, "status": ["in", ["Queued", "Running", "Failed"]]},
            fields=["name", "status", "requested_by", "creation", "error"],
            order_by="creation desc",
            limit=5,
        ),
        "can_change": can_change(),
    }


def add_public_benchmark(model: str, values: dict) -> dict:
    """A public number for a model, with its date and where it came from."""
    if not can_change():
        frappe.throw(
            _("Only System Managers add public benchmarks."), frappe.PermissionError
        )
    benchmark = str(values.get("benchmark") or "").strip()
    score = str(values.get("score") or "").strip()
    if not (benchmark and score):
        frappe.throw(_("Give the benchmark's name and the score."))
    url = str(values.get("source_url") or "").strip()
    if url and not url.startswith(("https://", "http://")):
        frappe.throw(_("The source must be a web address."))
    frappe.get_doc(
        {
            "doctype": PUBLIC,
            "model": model,
            "benchmark": benchmark[:140],
            "score": score[:140],
            "measured_on": values.get("measured_on") or None,
            "source_url": url[:500],
            "note": str(values.get("note") or "").strip()[:500],
        }
    ).insert(ignore_permissions=True)
    return benchmarks(model)


def remove_public_benchmark(name: str) -> dict:
    if not can_change():
        frappe.throw(
            _("Only System Managers remove public benchmarks."), frappe.PermissionError
        )
    model = frappe.db.get_value(PUBLIC, name, "model")
    frappe.delete_doc(PUBLIC, name, ignore_permissions=True)
    return benchmarks(model)


def close_requests(model: str, eval_run: str) -> None:
    """A run of the test set arrived: the model's waiting requests are answered."""
    for name in frappe.get_all(
        EVAL_REQUEST,
        filters={"model": model, "status": ["in", ["Queued", "Running"]]},
        pluck="name",
    ):
        frappe.db.set_value(
            EVAL_REQUEST, name, {"status": "Done", "eval_run": eval_run}
        )


def withdraw_eval_request(name: str) -> dict:
    """Takes back a request nobody has run yet."""
    if not can_change():
        frappe.throw(
            _("Only System Managers take back a request."), frappe.PermissionError
        )
    request = frappe.db.get_value(EVAL_REQUEST, name, ["model", "status"], as_dict=True)
    if not request:
        frappe.throw(_("This request is gone."))
    if request.status == "Done":
        frappe.throw(_("This request was already answered."))
    frappe.delete_doc(EVAL_REQUEST, name, ignore_permissions=True)
    return benchmarks(request.model)


def request_eval(model: str, job: str = "investigate") -> dict:
    """Asks for a run of the test set on a model; one waiting request per model. The cases
    live on the test hub, so a person runs the worker's `eval` there and brings the scores in."""
    if not can_change():
        frappe.throw(
            _("Only System Managers run the test set."), frappe.PermissionError
        )
    model = str(model or "").strip()
    if not model:
        frappe.throw(_("Choose a model."))
    if frappe.db.exists(
        EVAL_REQUEST, {"model": model, "status": ["in", ["Queued", "Running"]]}
    ):
        frappe.throw(
            _("A run of the test set on {0} is already waiting.").format(model)
        )
    frappe.get_doc(
        {
            "doctype": EVAL_REQUEST,
            "model": model,
            "job": job if job in ai_engine.WORKER_JOBS else "investigate",
            "requested_by": frappe.session.user,
        }
    ).insert(ignore_permissions=True)
    return benchmarks(model)


# --- quality: what people and checks say about a model's work -----------------------------------

EVENT = "HDS AI Quality Event"
EVENT_KINDS = (
    "Unsupported answer",
    "Safety cut",
    "Bad answer format",
    "Missing reference",
    "Hand-over",
    "Answered",
    "Draft made",
    "Draft used",
    "Draft changed",
)


def record_event(kind: str, model: str | None = None, **more) -> None:
    """One quality signal. Never raises and never blocks the caller: a lost event is better
    than a reply that fails. `detail` is a short code or a file or field name, never a
    customer's text."""
    try:
        if kind not in EVENT_KINDS:
            return
        frappe.get_doc(
            {
                "doctype": EVENT,
                "kind": kind,
                "model": (model or "")[:140],
                "job": more.get("job"),
                "ticket": more.get("ticket"),
                "copilot_run": more.get("copilot_run"),
                "value": more.get("value"),
                "detail": str(more.get("detail") or "")[:140],
            }
        ).insert(ignore_permissions=True)
    except Exception:
        # not even a failing error log may reach the caller
        with contextlib.suppress(Exception):
            frappe.log_error(title="AI quality event not recorded")


def record_references(run: str, references) -> None:
    """What the worker's reference check found for a run: how many cited files, functions,
    doctypes and fields it checked, and which do not exist."""
    if not isinstance(references, dict):
        return
    missing = [
        {
            "kind": str(m.get("kind") or "")[:40],
            "value": str(m.get("value") or "")[:200],
        }
        for m in references.get("missing") or []
        if isinstance(m, dict) and m.get("value")
    ][:50]
    frappe.db.set_value(
        "HDS Copilot Run",
        run,
        {
            "references_checked": cint(references.get("checked")),
            "references_missing": len(missing),
            "missing_references": frappe.as_json(missing) if missing else None,
        },
        update_modified=False,
    )
    model = frappe.db.get_value("HDS Copilot Run", run, "model_used")
    for item in missing:
        record_event(
            "Missing reference",
            model,
            job="investigate",
            copilot_run=run,
            detail=f"{item['kind']}: {item['value']}",
        )


# --- drafts: whether the agent sent the AI's draft reply as written, changed, or not at all -------

DRAFT_KEY = "ai_models:draft:{0}:{1}"
DRAFT_HOURS = 24
DRAFT_USED = 0.9
DRAFT_CHANGED = 0.4
MAX_SHINGLES = 3000


def shingles(text: str | None) -> set[int]:
    """A text as checksums of its runs of three words: enough to say how much of one text is
    in another, and nothing a person could read back."""
    words = re.findall(r"\w+", frappe.utils.strip_html(text or "").lower())
    if not words:
        return set()
    runs = [" ".join(words[i : i + 3]) for i in range(max(1, len(words) - 2))]
    return {zlib.crc32(run.encode()) for run in runs[:MAX_SHINGLES]}


def note_draft(ticket: str, model: str | None, reply: str) -> None:
    """An AI draft reply was made for the agent. Only its checksums are kept, for a day, to
    compare with what the agent sends. A redraft of a waiting draft is the same draft."""
    try:
        marks = shingles(reply)
        if not marks:
            return
        key = DRAFT_KEY.format(ticket, frappe.session.user)
        waiting = frappe.cache.get_value(key, expires=True)
        frappe.cache.set_value(
            key,
            {"model": model or "", "marks": sorted(marks)},
            expires_in_sec=DRAFT_HOURS * 3600,
        )
        if not waiting:
            record_event("Draft made", model, job="draft", ticket=ticket)
    except Exception:
        with contextlib.suppress(Exception):
            frappe.log_error(title="AI draft not noted")


def on_communication_insert(doc, method=None):
    """Communication after_insert: an agent's sent reply is compared with the AI draft made
    for it. Never blocks the reply."""
    try:
        if doc.reference_doctype != "HD Ticket" or not doc.reference_name:
            return
        if doc.communication_type != "Communication" or doc.sent_or_received != "Sent":
            return
        key = DRAFT_KEY.format(doc.reference_name, frappe.session.user)
        draft = frappe.cache.get_value(key, expires=True)
        if not draft:
            return
        frappe.cache.delete_value(key)
        marks = set(draft.get("marks") or [])
        kept = len(marks & shingles(doc.content)) / len(marks) if marks else 0
        if kept >= DRAFT_USED:
            kind = "Draft used"
        elif kept >= DRAFT_CHANGED:
            kind = "Draft changed"
        else:
            return
        record_event(
            kind,
            draft.get("model"),
            job="draft",
            ticket=doc.reference_name,
            value=round(kept * 100),
        )
    except Exception:
        with contextlib.suppress(Exception):
            frappe.log_error(title="AI draft not compared with the reply")


def _customer_answers(runs: list) -> dict:
    """What customers said after Copilot worked on their ticket: fixed, or still broken."""
    tickets = sorted({r.ticket for r in runs if r.ticket})
    if not tickets or not frappe.db.has_column(
        "HD Ticket", "custom_customer_confirmation"
    ):
        return {"Confirmed": 0, "Reopened": 0}
    answers = frappe.get_all(
        "HD Ticket",
        filters={
            "name": ["in", tickets],
            "custom_customer_confirmation": ["in", ["Confirmed", "Reopened"]],
        },
        pluck="custom_customer_confirmation",
        limit=0,
    )
    return {kind: answers.count(kind) for kind in ("Confirmed", "Reopened")}


def quality(model: str, days: int = 30) -> dict:
    """One model's quality for the period: Copilot's outcomes, the chat's, and the two
    hallucination checks, each on its own."""
    days = period(days)
    start = since(days)
    runs = frappe.get_all(
        "HDS Copilot Run",
        filters={"model_used": model, "creation": [">=", start]},
        fields=[
            "name",
            "ticket",
            "state",
            "review_verdict",
            "explanation_edited",
            "references_checked",
            "references_missing",
        ],
        limit=0,
    )
    names = [r.name for r in runs]
    approvals = (
        frappe.get_all(
            "HDS Copilot Approval",
            filters={
                "run": ["in", names],
                "status": ["in", ["Approved", "Merged", "Rejected"]],
            },
            fields=["status"],
            limit=0,
        )
        if names
        else []
    )
    approved = sum(1 for a in approvals if a.status != "Rejected")
    reviewed = [r for r in runs if r.review_verdict]
    edited = [r.explanation_edited for r in runs if r.explanation_edited is not None]
    checked = [r for r in runs if r.references_checked]
    events: dict[str, int] = {}
    for row in frappe.get_all(
        EVENT,
        filters={"model": model, "creation": [">=", start]},
        fields=["kind"],
        limit=0,
    ):
        events[row.kind] = events.get(row.kind, 0) + 1
    chat = (
        events.get("Answered", 0)
        + events.get("Unsupported answer", 0)
        + events.get("Hand-over", 0)
    )
    answers = _customer_answers(runs)
    answered = answers["Confirmed"] + answers["Reopened"]
    drafts = max(
        events.get("Draft made", 0),
        events.get("Draft used", 0) + events.get("Draft changed", 0),
    )
    return {
        "model": model,
        "days": days,
        "copilot": {
            "runs": len(runs),
            "failed": sum(1 for r in runs if r.state == "Failed"),
            "approvals": len(approvals),
            "approval_rate": rate(approved, len(approvals)),
            "reviewed": len(reviewed),
            "right_rate": rate(
                sum(1 for r in reviewed if r.review_verdict == "Right"), len(reviewed)
            ),
            "wrong_rate": rate(
                sum(1 for r in reviewed if r.review_verdict == "Wrong"), len(reviewed)
            ),
            "avg_edited": round(sum(edited) / len(edited), 1) if edited else None,
            "customer_answers": answered,
            "still_broken": answers["Reopened"],
            "still_broken_rate": rate(answers["Reopened"], answered),
        },
        "drafts": {
            "made": drafts,
            "used": events.get("Draft used", 0),
            "changed": events.get("Draft changed", 0),
            "not_used": drafts
            - events.get("Draft used", 0)
            - events.get("Draft changed", 0),
            "used_rate": rate(events.get("Draft used", 0), drafts),
            "changed_rate": rate(events.get("Draft changed", 0), drafts),
        },
        "chat": {
            "replies": chat,
            "answered_rate": rate(events.get("Answered", 0), chat),
            "handover_rate": rate(events.get("Hand-over", 0), chat),
        },
        "hallucination": {
            "runs_checked": len(checked),
            "missing_reference_rate": rate(
                sum(1 for r in checked if r.references_missing), len(checked)
            ),
            "missing_references": events.get("Missing reference", 0),
            "unsupported_rate": rate(events.get("Unsupported answer", 0), chat),
            "unsupported": events.get("Unsupported answer", 0),
            "safety_cuts": events.get("Safety cut", 0),
            "bad_format": events.get("Bad answer format", 0),
        },
    }


# --- the AI gateway's models (the desktop app), beside TBO Support's own ------------------------

GATEWAY_SOURCE = "Desktop app (AI gateway)"


def _gateway_figures(days_rows: list) -> dict:
    """Figures from the gateway's daily totals. The speed is the request-weighted middle of
    the days' medians, and the slow end the slowest day's: close, not exact."""
    calls = sum(r.requests or 0 for r in days_rows)
    failed = sum(r.failures or 0 for r in days_rows)
    weighted = [
        (r.p50_ms, (r.requests or 0) - (r.failures or 0)) for r in days_rows if r.p50_ms
    ]
    weight = sum(w for _ms, w in weighted)
    p50 = (
        round(sum(ms * w for ms, w in weighted) / weight / 1000, 1) if weight else None
    )
    slow = [r.p95_ms for r in days_rows if r.p95_ms]
    return {
        "calls": calls,
        "failed": failed,
        "error_rate": rate(failed, calls),
        "as_fallback": 0,
        "fallback_rate": None,
        "cost": round(sum(r.spend_usd or 0 for r in days_rows), 2),
        "tokens": 0,
        "p50": p50,
        "p95": round(max(slow) / 1000, 1) if slow else None,
    }


def _add(figures: dict, more: dict) -> dict:
    """Two sources' figures as one: counts and cost add up; the speed stays the first's."""
    calls = figures["calls"] + more["calls"]
    failed = figures["failed"] + more["failed"]
    return {
        **figures,
        "calls": calls,
        "failed": failed,
        "error_rate": rate(failed, calls),
        "fallback_rate": rate(figures["as_fallback"], calls),
        "cost": round(figures["cost"] + more["cost"], 2),
        "p50": figures["p50"] if figures["p50"] is not None else more["p50"],
        "p95": figures["p95"] if figures["p95"] is not None else more["p95"],
    }


def overview(days: int = 30) -> dict:
    """Every model side by side: TBO Support's and the Copilot worker's, and the gateway's."""
    result = _hub_overview(days)
    by_model: dict[str, list] = {}
    for row in ai_gateway.day_rows(result["days"]):
        by_model.setdefault(row.model, []).append(row)
    if not by_model:
        return result
    known = {m["model"]: m for m in result["models"]}
    for name, rows in by_model.items():
        figures = _gateway_figures(rows)
        if name in known:
            known[name].update(_add(known[name], figures))
            if known[name]["status"] in ("Not used", "Candidate"):
                known[name]["status"] = "Healthy"
        else:
            result["models"].append(
                {
                    "model": name,
                    "provider": GATEWAY_SOURCE,
                    "used_for": {"primary": [], "fallback": []},
                    **figures,
                    "benchmark": latest_scores().get(name),
                    "status": "Degraded"
                    if figures["calls"] >= MIN_CALLS
                    and (figures["error_rate"] or 0) >= DEGRADED_ERROR_RATE
                    else "Healthy",
                }
            )
        result["totals"] = _add(result["totals"], figures)
    result["models"].sort(key=lambda m: (-m["calls"], m["model"]))
    result["attention"] = [
        m["model"] for m in result["models"] if m["status"] in ("Paused", "Degraded")
    ]
    return result


def detail(model: str, days: int = 30) -> dict:
    """One model's performance and errors, with the gateway's share when it has one."""
    result = _hub_detail(model, days)
    rows = ai_gateway.day_rows(result["days"], model)
    result["by_person"] = []
    if not rows:
        return result
    figures = _gateway_figures(rows)
    hub = {k: result[k] for k in figures}
    result.update(_add(hub, figures))
    if not result["provider"]:
        result["provider"] = GATEWAY_SOURCE
    if result["status"] in ("Not used", "Candidate"):
        result["status"] = "Healthy"
    by_day: dict[str, list] = {}
    for row in rows:
        by_day.setdefault(str(row.day), []).append(row)
    for point in result["series"]:
        mine = by_day.get(point["day"])
        if mine:
            f = _gateway_figures(mine)
            point["calls"] += f["calls"]
            point["failed"] += f["failed"]
            point["cost"] = round(point["cost"] + f["cost"], 2)
            point["error_rate"] = rate(point["failed"], point["calls"]) or 0
    result["by_source"].append({"name": GATEWAY_SOURCE, **figures})
    kinds = {e["kind"]: e["count"] for e in result["errors_by_kind"]}
    for row in rows:
        for kind, count in (frappe.parse_json(row.error_classes) or {}).items():
            kinds[kind] = kinds.get(kind, 0) + cint(count)
    result["errors_by_kind"] = sorted(
        ({"kind": k, "count": n} for k, n in kinds.items()), key=lambda e: -e["count"]
    )
    people: dict[str, list] = {}
    for row in rows:
        people.setdefault(row.gateway_user or _("(no name)"), []).append(row)
    result["by_person"] = sorted(
        ({"name": name, **_gateway_figures(mine)} for name, mine in people.items()),
        key=lambda g: -g["cost"],
    )
    return result


def save_gateway(values: dict) -> dict:
    """The gateway's address, its read-only key and whether to read it."""
    if not can_change():
        frappe.throw(
            _("Only System Managers set up the AI gateway."), frappe.PermissionError
        )
    doc = frappe.get_doc(SETTINGS)
    if "url" in values:
        doc.gateway_url = str(values.get("url") or "").strip()
    if "on" in values:
        doc.gateway_sync = 1 if frappe.utils.sbool(values.get("on")) else 0
    if values.get("key") is not None:
        doc.gateway_viewer_key = str(values.get("key")).strip()
    doc.save(ignore_permissions=True)
    return ai_gateway.status()


def sync_gateway() -> dict:
    if not can_change():
        frappe.throw(
            _("Only System Managers read the AI gateway now."), frappe.PermissionError
        )
    result = ai_gateway.sync()
    return {**ai_gateway.status(), "ok": result["ok"], "note": result["note"]}
