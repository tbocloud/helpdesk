# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""AI Models (Phase 31): how each AI model does, and which model each job uses.

Everything is read from HDS AI Usage Log, where every attempt is a row: TBO Support's own calls
(with their speed, and a Failed row with the error's kind when the provider refused) and the
Copilot worker's stages. Nothing here reads or returns a prompt or a customer's text.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, nowdate

from helpdesk import ai_engine

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


def _status(model: str, figures: dict, paused: set[str]) -> str:
    if model in paused:
        return "Paused"
    if not figures["calls"]:
        return "Not used"
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


def overview(days: int = 30) -> dict:
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
    names = sorted(set(by_model) | set(used))
    models = []
    for name in names:
        mine = by_model.get(name, [])
        figures = _figures(mine)
        models.append(
            {
                "model": name,
                "provider": (mine[-1].provider if mine else "")
                or _section_of(name, plan),
                "used_for": used.get(name, {"primary": [], "fallback": []}),
                **figures,
                "status": _status(name, figures, paused),
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


def detail(model: str, days: int = 30) -> dict:
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
    return {
        "model": model,
        "days": days,
        "provider": (rows[-1].provider if rows else "") or _section_of(model, plan),
        "used_for": used,
        "status": _status(model, figures, _paused_models(settings)),
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
    jobs = []
    for job in job_plan(settings):
        jobs.append({**job, **_figures(by_job.get(job["job"], []))})
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
        "models": sorted({r.model for r in rows if r.model}),
        "can_change": can_change(),
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


def save_job(job: str, values: dict) -> dict:
    """One job's first section, fallback and models; each change is written to the history."""
    if not can_change():
        frappe.throw(
            _("Only System Managers change which model a job uses."),
            frappe.PermissionError,
        )
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

    doc = frappe.get_doc(SETTINGS)
    row = next((r for r in doc.get("ai_jobs") or [] if r.job == job), None)
    if not row:
        row = doc.append("ai_jobs", {"job": job})
    changes = []
    for field, value in clean.items():
        before = row.get(field) or ""
        if before != value:
            changes.append((field, before, value))
            row.set(field, value)
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
