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
    sbool,
)
from frappe.utils.password import get_decrypted_password

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
    """Each purpose's providers in the order it tries them, with the model of each: its own
    model and backup when it has them, else the sections in its order. A desktop level without
    a model, and a coming purpose, have none."""
    settings = settings or ai_engine.get_hub_settings()
    providers = ai_engine.configured_providers(settings)
    plan = []
    for job in ai_engine.JOBS:
        row = ai_engine.job_row(job, settings)
        coming = job in ai_engine.COMING_JOBS
        own = "" if coming else (row.get("model") if row else "") or ""
        if own:
            steps = [
                {
                    "section": model_section(model),
                    "model": model,
                    "ready": bool(
                        frappe.db.get_value(PRICING, model, "on_gateway")
                        if ai_gateway.for_all(settings)
                        else ai_engine.model_provider(model, settings)
                    ),
                }
                for model in (own, row.get("backup_model"))
                if model
            ]
        elif coming or job in ai_engine.OWN_MODEL_JOBS:
            steps = []
        else:
            models = ai_engine.job_models(job, settings)
            steps = [
                {
                    "section": slot,
                    "model": models.get(slot)
                    or _section_model(slot, settings, providers),
                    "ready": bool(providers[slot]),
                }
                for slot in ai_engine.provider_order(settings, job)
            ]
        plan.append(
            {
                "job": job,
                "application": ai_engine.application_of(job),
                "label": ai_engine.purpose_label(job),
                "gateway_name": ai_engine.DESKTOP_GATEWAY_NAMES.get(job, ""),
                "coming": coming,
                "own_only": job in ai_engine.OWN_MODEL_JOBS,
                "primary": steps[0] if steps else None,
                "fallback": steps[1] if len(steps) > 1 else None,
                "primary_section": (row.get("primary_section") if row else "") or "",
                "allow_fallback": (row.get("allow_fallback") if row else "") or "",
                "openai_model": (row.get("openai_model") if row else "") or "",
                "anthropic_model": (row.get("anthropic_model") if row else "") or "",
                "model": own,
                "backup_model": ""
                if coming
                else (row.get("backup_model") if row else "") or "",
            }
        )
    return plan


def _purpose_name(job: dict) -> str:
    """A purpose as the pages name it: TBO Support's and the worker's by their job, the others
    with their application, for example "Desktop app: Simple"."""
    if job["application"] in ("TBO Support", "Copilot worker"):
        return job["job"]
    return f"{job['application']}: {job['label']}"


def _used_by(plan: list[dict]) -> dict[str, list[dict]]:
    """Per model, one entry per application: the purposes that use it first, and those it
    backs up."""
    out: dict[str, dict] = {}
    for job in plan:
        for role, step in (("first", job["primary"]), ("backup", job["fallback"])):
            if step and step["model"]:
                entry = out.setdefault(step["model"], {}).setdefault(
                    job["application"],
                    {"application": job["application"], "first": [], "backup": []},
                )
                entry[role].append(job["label"])
    return {model: list(apps.values()) for model, apps in out.items()}


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
                ].append(_purpose_name(job))
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
    waiting = listed_names() - set(used)
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
                or (model_section(name) if name in waiting else ""),
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
    waiting = model in listed_names() and not (used["primary"] or used["fallback"])
    return {
        "model": model,
        "days": days,
        "provider": (rows[-1].provider if rows else "")
        or _section_of(model, plan)
        or (model_section(model) if waiting else ""),
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
    plan = job_plan(settings)
    jobs = []
    for job in plan:
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
        "applications": [
            {
                "name": app["name"],
                "note": _(app["note"]),
                "coming": bool(app.get("coming")),
                "own_only": bool(app.get("own_models_only")),
            }
            for app in ai_engine.APPLICATIONS
        ],
        "providers": provider_list(settings),
        "catalog": catalog(plan),
        "presets": list(PRESETS),
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


JOB_SETTINGS = (
    "primary_section",
    "allow_fallback",
    "openai_model",
    "anthropic_model",
    "model",
    "backup_model",
)
SETTING_LABELS = {
    "primary_section": "Primary section",
    "allow_fallback": "Fallback",
    "openai_model": "OpenAI model",
    "anthropic_model": "Anthropic-compatible model",
    "model": "Model",
    "backup_model": "Backup",
}


def _clean_job(job: str, values: dict) -> dict:
    if job not in ai_engine.JOBS:
        frappe.throw(_("Unknown AI job {0}").format(job))
    if job in ai_engine.COMING_JOBS:
        frappe.throw(
            _("{0} comes with its phase; its model is chosen then.").format(
                ai_engine.purpose_label(job)
            )
        )
    allowed = (
        ("model", "backup_model") if job in ai_engine.OWN_MODEL_JOBS else JOB_SETTINGS
    )
    unknown = set(values) - set(allowed)
    if unknown:
        frappe.throw(_("{0} cannot be changed here").format(", ".join(sorted(unknown))))
    clean = {k: str(v or "").strip() for k, v in values.items()}
    if clean.get("primary_section") not in (None, "", *ai_engine.SLOTS):
        frappe.throw(_("Unknown section {0}").format(clean["primary_section"]))
    if clean.get("allow_fallback") not in (None, "", "On", "Off"):
        frappe.throw(_("Fallback is On, Off or blank (as the settings say)"))
    for field in ("model", "backup_model"):
        model = clean.get(field)
        if model and not frappe.db.get_value(PRICING, model, "listed"):
            frappe.throw(
                _("{0} isn't allowed for jobs. Tick it under Models first.").format(
                    model
                )
            )
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
    if "model" in clean and not row.get("model") and row.get("backup_model"):
        # back to the sections: a backup alone means nothing
        changes.append(("backup_model", row.backup_model, ""))
        row.backup_model = ""
    if row.get("backup_model") and not row.get("model"):
        frappe.throw(_("Choose the job's model before its backup."))
    if row.get("model") and row.get("model") == row.get("backup_model"):
        frappe.throw(_("The backup must be another model."))
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
    values = dict(values or {})
    # the guard compared against the job's model as it was then: someone may have changed it
    # since, and the manager saw a comparison that no longer holds
    expected = values.pop("expected_model", None)
    clean = _clean_job(job, values)
    doc = frappe.get_doc(SETTINGS)
    if job in GUARDED_JOBS and expected is not None:
        now = _first_model(doc, job) or ""
        if now != (expected or ""):
            frappe.throw(
                _(
                    "{0} now uses {1}, not the model you compared against. Look at the comparison again before saving."
                ).format(job, now or _("its section's default"))
            )
    # the level's models before the change, written back if the gateway refuses the new ones
    old = next((r for r in doc.get("ai_jobs") or [] if r.job == job), None)
    previous = (old.get("model"), old.get("backup_model")) if old else ()
    changes = _apply_job(doc, job, clean)
    if not changes:
        return job_settings()
    doc.save(ignore_permissions=True)
    if job in ai_engine.DESKTOP_GATEWAY_NAMES and admin_ready():
        write_level(job, previous)
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
    if job not in ai_engine.JOBS or job in ai_engine.COMING_JOBS:
        frappe.throw(_("Unknown AI job {0}").format(job))
    if job in ai_engine.OWN_MODEL_JOBS and not (ai_engine.job_row(job) or {}).get(
        "model"
    ):
        return {
            "ok": False,
            "message": _("Choose a model for {0} first.").format(
                ai_engine.purpose_label(job)
            ),
        }
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


# --- providers and the model list (plan addendum 31.8, docs/ai-models.md) ------------------------

PRICING = "HDS Model Pricing"
PROVIDER = "HDS AI Provider"
# a wrong model here changes what Copilot tells a customer or writes as a fix
GUARDED_JOBS = ai_engine.WORKER_JOBS
# no "AWS Bedrock": the owner turned Bedrock off on 2026-11-26 (DeepSeek goes through its own API)
STYLES = tuple(ai_engine.STYLE_KINDS)
# how the gateway names a provider's models (LiteLLM's prefixes)
LITELLM_PREFIX = {
    "OpenAI": "openai",
    "OpenAI-compatible": "openai",
    "Anthropic": "anthropic",
    "Anthropic-compatible": "anthropic",
}
# what "Add a provider" fills in, DeepSeek's own API first (the owner's choice, 26 Nov); the Copilot
# worker knows the same names (tbo-worker config.ts)
PRESETS = (
    {
        "name": "DeepSeek",
        "style": "OpenAI-compatible",
        "url": "https://api.deepseek.com",
        "note": "DeepSeek's own API: the data goes to DeepSeek's servers in China.",
    },
    {
        "name": "Qwen",
        "style": "OpenAI-compatible",
        "url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "note": "Alibaba Cloud's API: the data goes to its Singapore region. A key works only in its own region.",
    },
    {"name": "Claude", "style": "Anthropic", "url": "", "note": "Anthropic's own API."},
    {
        "name": "GPT",
        "style": "OpenAI",
        "url": ai_engine.OPENAI_BASE_URL,
        "note": "OpenAI's own API.",
    },
)
# HDS Model Pricing's older `provider` field (cost reports), from the account's API style
PRICING_PROVIDER = {
    "OpenAI": "OpenAI",
    "OpenAI-compatible": "OpenAI",
    "Anthropic": "Anthropic",
    "Anthropic-compatible": "Anthropic-compatible",
}
# today's two sections: the HDS Hub Settings fields behind each
SECTION_FIELDS = {
    ai_engine.OPENAI_SLOT: {
        "url": "openai_base_url",
        "key": "openai_api_key",
        "model": "openai_model",
    },
    ai_engine.ANTHROPIC_SLOT: {
        "url": "ai_base_url",
        "key": "anthropic_api_key",
        "model": "default_triage_model",
    },
}
SECTION_STYLES = {
    "Anthropic": "Anthropic",
    "Anthropic Compatible": "Anthropic-compatible",
    "OpenAI Compatible": "OpenAI-compatible",
}
MILLION = 1_000_000


def listed_names() -> set[str]:
    """The models allowed for jobs."""
    return set(frappe.get_all(PRICING, filters={"listed": 1}, pluck="name"))


def model_section(model: str) -> str:
    """The provider account a model of the list is called through."""
    return frappe.db.get_value(PRICING, model, "ai_provider") or ""


def _style(account: str, settings=None) -> str:
    if account == ai_engine.OPENAI_SLOT:
        return "OpenAI"
    if account == ai_engine.ANTHROPIC_SLOT:
        settings = settings or ai_engine.get_hub_settings()
        return SECTION_STYLES.get(
            settings.get("ai_provider") or "Anthropic", "Anthropic"
        )
    return frappe.db.get_value(PROVIDER, account, "api_style") or ""


def _only_system_managers(message: str) -> None:
    if not can_change():
        frappe.throw(message, frappe.PermissionError)


def provider_list(settings=None) -> list[dict]:
    """Today's two sections, then the provider accounts, with how many allowed models each
    has. Never a key: only whether one is saved."""
    settings = settings or ai_engine.get_hub_settings()
    ready = ai_engine.configured_providers(settings)
    listed = frappe.get_all(PRICING, filters={"listed": 1}, pluck="ai_provider")
    out = []
    for slot in ai_engine.SLOTS:
        fields = SECTION_FIELDS[slot]
        url = settings.get(fields["url"]) or ""
        if slot == ai_engine.OPENAI_SLOT:
            url = url or ai_engine.OPENAI_BASE_URL
        out.append(
            {
                "name": slot,
                "section": True,
                "style": _style(slot, settings),
                "url": url,
                "key_set": bool(
                    settings.get_password(fields["key"], raise_exception=False)
                ),
                "enabled": True,
                "ready": bool(ready[slot]),
                "json_mode": slot == ai_engine.OPENAI_SLOT,
                "default_model": _section_model(slot, settings, ready),
                "models": listed.count(slot),
                "note": "",
            }
        )
    through_gateway = ai_gateway.for_all(settings)
    for doc in frappe.get_all(
        PROVIDER,
        fields=[
            "name",
            "api_style",
            "base_url",
            "enabled",
            "json_mode",
            "notes",
            "key_on_gateway",
        ],
        order_by="creation asc",
    ):
        local_key = bool(
            get_decrypted_password(PROVIDER, doc.name, "api_key", raise_exception=False)
        )
        if through_gateway:
            ready = bool(doc.enabled and doc.key_on_gateway)
        else:
            ready = bool(doc.enabled and local_key)
        out.append(
            {
                "name": doc.name,
                "section": False,
                "style": doc.api_style,
                "url": doc.base_url or "",
                "key_set": local_key or bool(doc.key_on_gateway),
                "key_on_gateway": bool(doc.key_on_gateway),
                "enabled": bool(doc.enabled),
                "ready": ready,
                "json_mode": bool(doc.json_mode),
                "default_model": "",
                "models": listed.count(doc.name),
                "note": doc.notes or "",
            }
        )
    return out


def catalog(plan: list[dict] | None = None) -> list[dict]:
    """The model list: each model with a provider, its prices, whether jobs may use it, its
    monthly limit and this month's use, its newest test-set score and the jobs using it."""
    plan = plan or job_plan()
    used = _used_for(plan)
    used_by = _used_by(plan)
    scores = latest_scores()
    ready = {p["name"]: p["ready"] for p in provider_list()}
    rows = frappe.get_all(
        PRICING,
        filters={"ai_provider": ["is", "set"]},
        fields=[
            "name",
            "display_name",
            "ai_provider",
            "listed",
            "monthly_token_limit",
            "input_cost_per_1m",
            "output_cost_per_1m",
            "on_gateway",
        ],
        order_by="listed desc, ai_provider asc, name asc",
    )
    out = []
    for row in rows:
        jobs = used.get(row.name, {"primary": [], "fallback": []})
        out.append(
            {
                "model": row.name,
                "name": row.display_name or row.name,
                "provider": row.ai_provider,
                "provider_ready": bool(ready.get(row.ai_provider)),
                "listed": bool(row.listed),
                "limit_m": flt(row.monthly_token_limit),
                "used_m": round(ai_engine.month_tokens(row.name) / MILLION, 2),
                "input_price": row.input_cost_per_1m or 0,
                "output_price": row.output_cost_per_1m or 0,
                "benchmark": scores.get(row.name),
                "used_for": jobs,
                "used_by": used_by.get(row.name, []),
                "on_gateway": bool(row.on_gateway),
                "in_use": bool(jobs["primary"] or jobs["fallback"]),
            }
        )
    return out


def save_provider(values: dict) -> dict:
    """A provider account, or one of today's sections: its address, key and on/off. A key is
    sent only to replace the saved one; it never comes back."""
    _only_system_managers(_("Only System Managers change the AI providers."))
    name = str(values.get("name") or "").strip()
    url = str(values.get("url") or "").strip()
    key = str(values.get("key") or "").strip()
    if name in ai_engine.SLOTS:
        from helpdesk.api import ai_settings

        fields = SECTION_FIELDS[name]
        change = {fields["url"]: url}
        if "default_model" in values:
            change[fields["model"]] = str(values.get("default_model") or "").strip()
        if key:
            change[fields["key"]] = key
        ai_settings.save_settings(change)
        return job_settings()
    if not name or len(name) > 60:
        frappe.throw(_("Give the provider a name of at most 60 characters."))
    style = str(values.get("style") or "")
    if style not in STYLES:
        frappe.throw(_("Choose the provider's API style."))
    exists = frappe.db.exists(PROVIDER, name)
    if values.get("new") and exists:
        frappe.throw(_("{0} is already a provider.").format(name))
    doc = frappe.get_doc(PROVIDER, name) if exists else frappe.new_doc(PROVIDER)
    if not exists:
        doc.provider_name = name
    moved = exists and (doc.base_url or "") != url
    doc.api_style = style
    doc.base_url = url
    doc.enabled = 1 if sbool(values.get("enabled", True)) else 0
    doc.json_mode = 1 if sbool(values.get("json_mode", True)) else 0
    if "note" in values:
        doc.notes = str(values.get("note") or "").strip()[:500]
    # through the gateway a key lives only there (the owner's decision for Phase 37)
    to_gateway = ai_gateway.for_all()
    if to_gateway and not key and doc.key_on_gateway and moved:
        frappe.throw(_("Enter the key again: the gateway keeps it with the address."))
    if key and not to_gateway:
        doc.api_key = key
        doc.key_on_gateway = 0
    doc.save(ignore_permissions=True)
    if key and to_gateway:
        _key_to_gateway(doc.name, key, doc.base_url)
    return job_settings()


def _credential_values(key: str, url: str) -> dict:
    return {"api_key": key, **({"api_base": url} if url else {})}


def _key_to_gateway(account: str, key: str, url: str, forget: bool = True) -> None:
    """Writes an account's key to the gateway as a credential, and forgets it here (`forget`).
    A copy that isn't forgotten is for while TBO Support still calls the provider itself."""
    from frappe.utils.password import remove_encrypted_password

    try:
        ai_gateway.save_credential(account, _credential_values(key, url))
    except ai_gateway.GatewayError as e:
        frappe.throw(_("The gateway did not take the key: {0}").format(str(e)))
    if not forget:
        return
    remove_encrypted_password(PROVIDER, account, "api_key")
    frappe.db.set_value(PROVIDER, account, "key_on_gateway", 1, update_modified=False)


def gateway_params(model: str, account: str) -> dict:
    """How the gateway calls `model` of `account`: today's OpenAI section with the gateway's own
    OpenAI key, any other through its gateway credential."""
    if account == ai_engine.OPENAI_SLOT:
        return {"model": f"openai/{model}", "api_key": "os.environ/OPENAI_API_KEY"}
    if account == ai_engine.ANTHROPIC_SLOT:
        return {"model": f"anthropic/{model}", "litellm_credential_name": account}
    style = frappe.db.get_value(PROVIDER, account, "api_style") or ""
    prefix = LITELLM_PREFIX.get(style, "openai")
    return {"model": f"{prefix}/{model}", "litellm_credential_name": account}


def _section_credential() -> None:
    """Today's Anthropic-compatible section as a gateway credential, when it has a key."""
    settings = ai_engine.get_hub_settings()
    key = settings.get_password("anthropic_api_key", raise_exception=False)
    if key:
        ai_gateway.save_credential(
            ai_engine.ANTHROPIC_SLOT,
            _credential_values(key, (settings.get("ai_base_url") or "").strip()),
        )


def _served(name: str) -> dict | None:
    """How the gateway calls a model of the list now; None when it isn't on the gateway."""
    row = frappe.db.get_value(
        PRICING, name, ["listed", "ai_provider", "on_gateway"], as_dict=True
    )
    if not (row and row.on_gateway and row.listed and row.ai_provider):
        return None
    return gateway_params(name, row.ai_provider)


def _write_model(
    name: str, previous: dict | None = None, credential: bool = True
) -> None:
    """One model of the list into the gateway, or out of it when it is no longer allowed.
    `previous` (`_served` before the change) is written back if the gateway refuses the new
    one, so the model keeps answering; saving it again tries once more. `credential=False`:
    the caller has written the Anthropic-compatible section's credential already."""
    row = frappe.db.get_value(PRICING, name, ["listed", "ai_provider"], as_dict=True)
    try:
        if row and row.listed and row.ai_provider:
            if credential and row.ai_provider == ai_engine.ANTHROPIC_SLOT:
                _section_credential()
            ai_gateway.save_model(
                name, gateway_params(name, row.ai_provider), previous=previous
            )
            on = 1
        else:
            ai_gateway.delete_model(name)
            on = 0
    except ai_gateway.GatewayError as e:
        frappe.throw(_("The gateway did not take {0}: {1}").format(name, str(e)))
    if row:
        frappe.db.set_value(PRICING, name, "on_gateway", on, update_modified=False)


DESKTOP_SETTINGS = "TBO Desktop Settings"


def admin_ready() -> bool:
    """TBO Support may write into the gateway: it has its address and an admin key."""
    return bool(ai_gateway.base_url() and ai_gateway.admin_key())


def _ensure_credential(account: str) -> None:
    """The gateway can call `account`'s models: today's OpenAI section uses the gateway's own
    key; any other account's key is written as a credential when only
    TBO Support has it (it stays here too while TBO Support calls the providers itself)."""
    if account == ai_engine.ANTHROPIC_SLOT:
        _section_credential()
    if account in ai_engine.SLOTS:
        return
    doc = frappe.db.get_value(
        PROVIDER, account, ["api_style", "base_url", "key_on_gateway"], as_dict=True
    )
    if not doc or doc.key_on_gateway:
        return
    key = get_decrypted_password(PROVIDER, account, "api_key", raise_exception=False)
    if key:
        ai_gateway.save_credential(account, _credential_values(key, doc.base_url or ""))


def _level_to_gateway(name: str, models: list[str]) -> None:
    """A desktop level's models under its name, in order, in place of what it had."""
    for order in (1, 2):
        ai_gateway.delete_model(f"{name}:{order}")
    for order, model in enumerate(models, start=1):
        account = model_section(model)
        _ensure_credential(account)
        ai_gateway.save_model(
            name,
            {**gateway_params(model, account), "order": order},
            f"{name}:{order}",
        )


def write_level(job: str, previous: tuple = ()) -> None:
    """A desktop level on the gateway: one name (tbo-simple …) with the level's model first
    and its backup second, so a person's key needs only the level's name and the backup
    answers when the model can't. Without a model the name leaves the gateway. When the
    gateway refuses the change, the level's `previous` models are written back, so people's
    calls keep an answer; the settings are not saved (the error rolls them back)."""
    name = ai_engine.DESKTOP_GATEWAY_NAMES[job]
    row = ai_engine.job_row(job)
    chosen = [m for m in ((row.model, row.backup_model) if row else ()) if m]
    try:
        _level_to_gateway(name, chosen)
    except ai_gateway.GatewayError as e:
        message = _("The gateway did not take {0}: {1}").format(name, str(e))
        earlier = [m for m in previous if m]
        if earlier:
            try:
                _level_to_gateway(name, earlier)
                message += " " + _("It keeps the models it had.")
            except ai_gateway.GatewayError:
                # saving the same choice again changes nothing, so it can't repair the level
                message += " " + _(
                    "Its earlier models could not be written back either: use Write all to the gateway once it answers."
                )
        else:
            # a first save that failed half way: take off whatever got on, so the gateway
            # serves nothing the (rolled back) settings don't show
            with contextlib.suppress(ai_gateway.GatewayError):
                _level_to_gateway(name, [])
        frappe.throw(message)
    _desktop_names(name, add=bool(chosen))


def merged_names(text: str | None, name: str, add: bool) -> str | None:
    """TBO Desktop Settings' list of gateway names with `name` added or taken out; None when
    nothing changes. An empty list means tbo-default, as the desktop app module reads it."""
    names = [line.strip() for line in (text or "").splitlines() if line.strip()]
    names = names or ["tbo-default"]
    if add == (name in names):
        return None
    names = names + [name] if add else [n for n in names if n != name]
    return "\n".join(names)


def _desktop_names(name: str, add: bool) -> None:
    """The level's name in the list of names people's desktop keys may use, when the desktop
    app module is on this site (it updates the keys of everyone signed in)."""
    if not frappe.db.exists("DocType", DESKTOP_SETTINGS):
        return
    doc = frappe.get_single(DESKTOP_SETTINGS)
    names = merged_names(doc.get("models"), name, add)
    if names is not None:
        doc.models = names
        doc.save(ignore_permissions=True)


def write_all() -> dict:
    """Everything into the gateway: the accounts' keys, and every allowed model; a model no
    longer allowed leaves it. A key is forgotten here only while every call goes through the
    gateway (the owner's decision for Phase 37); before that switch is on, TBO Support still
    calls the providers itself, so the gateway gets a copy and the key stays here too."""
    _only_system_managers(_("Only System Managers set up the AI gateway."))
    if not (ai_gateway.base_url() and ai_gateway.admin_key()):
        frappe.throw(_("Set the gateway's address and its admin key first."))
    keys = _keys_to_gateway(forget=ai_gateway.for_all())
    models = frappe.get_all(
        PRICING, filters={"ai_provider": ["is", "set"]}, pluck="name"
    )
    if frappe.db.exists(
        PRICING, {"ai_provider": ai_engine.ANTHROPIC_SLOT, "listed": 1}
    ):
        # once for every model of the section, not once per model
        try:
            _section_credential()
        except ai_gateway.GatewayError as e:
            frappe.throw(_("The gateway did not take the key: {0}").format(str(e)))
    for name in models:
        # what the gateway serves now is written back if it refuses the replacement
        _write_model(name, _served(name), credential=False)
    for job in ai_engine.DESKTOP_GATEWAY_NAMES:
        # the level as it is saved is what the gateway serves: written back if the gateway
        # refuses part of it, never taken off as if it were a first save
        row = ai_engine.job_row(job)
        write_level(job, (row.model, row.backup_model) if row else ())
    return {**job_settings(), "written": {"keys": keys, "models": len(models)}}


def _keys_to_gateway(forget: bool) -> int:
    """Every key still kept here, written to the gateway as a credential; forgotten here when
    every call goes through the gateway (`forget`). How many were written."""
    keys = 0
    for account in frappe.get_all(PROVIDER, fields=["name", "base_url"]):
        key = get_decrypted_password(
            PROVIDER, account.name, "api_key", raise_exception=False
        )
        if key:
            _key_to_gateway(account.name, key, account.base_url or "", forget=forget)
            keys += 1
    return keys


def remove_provider(name: str) -> dict:
    """Takes a provider account away; its models stay in the list, no longer allowed."""
    _only_system_managers(_("Only System Managers change the AI providers."))
    if name in ai_engine.SLOTS:
        frappe.throw(_("Today's two sections stay. Remove their key instead."))
    if not frappe.db.exists(PROVIDER, name):
        frappe.throw(_("{0} isn't a provider.").format(name))
    models = frappe.get_all(PRICING, filters={"ai_provider": name}, pluck="name")
    for model in models:
        in_use = ai_engine.in_use_message(model)
        if in_use:
            frappe.throw(in_use)
    if ai_gateway.for_all():
        try:
            for model in models:
                ai_gateway.delete_model(model)
            ai_gateway.delete_credential(name)
        except ai_gateway.GatewayError as e:
            frappe.throw(_("The gateway did not let go of it: {0}").format(str(e)))
    elif admin_ready():
        # what "Write all" copied while the switch was off: no key of a removed provider stays
        # on the gateway (best effort: TBO Support doesn't need the gateway while it is off)
        with contextlib.suppress(ai_gateway.GatewayError):
            for model in models:
                ai_gateway.delete_model(model)
            ai_gateway.delete_credential(name)
    for model in models:
        frappe.db.set_value(
            PRICING,
            model,
            {"listed": 0, "ai_provider": "", "on_gateway": 0},
            update_modified=False,
        )
    frappe.delete_doc(PROVIDER, name, ignore_permissions=True)
    return job_settings()


def test_provider(name: str, model: str | None = None) -> dict:
    """One tiny call through a provider account, with its first allowed model (or `model`):
    how long it took, or what the provider said."""
    _only_system_managers(_("Only System Managers test a provider."))
    model = (model or "").strip()
    if not model:
        mine = frappe.get_all(
            PRICING,
            filters={"ai_provider": name},
            fields=["name"],
            order_by="listed desc, creation asc",
            limit=1,
        )
        if mine:
            model = mine[0].name
        elif name in ai_engine.SLOTS:
            settings = ai_engine.get_hub_settings()
            model = _section_model(
                name, settings, ai_engine.configured_providers(settings)
            )
    if not model:
        return {
            "ok": False,
            "message": _("Add a model for {0} first, then test it.").format(name),
        }
    through_gateway = ai_gateway.for_all()
    if through_gateway:
        # the gateway answers a model with its own account's key, so only one of this account's
        # models says whether this account works (a section's own model may be the gateway's)
        owner = model_section(model)
        if owner != name and (owner or name not in ai_engine.SLOTS):
            return {
                "ok": False,
                "message": _(
                    "{0} is not one of {1}'s models, so it can't test {1}."
                ).format(model, name),
            }
        provider = ai_engine.gateway_provider(model)
    else:
        provider = ai_engine.account_provider(name, model)
    if not provider:
        return {
            "ok": False,
            "message": _("{0} has no API key yet, or it is off.").format(name),
        }
    label = (
        _("{0} ({1}) through the TBO AI gateway").format(name, model)
        if through_gateway
        else provider.label
    )
    from time import perf_counter

    started = perf_counter()
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
            "message": _("{0} answered: {1}").format(label, e.summary),
        }
    ai_engine.record_success(provider)
    return {
        "ok": True,
        "message": _("{0} answered in {1} s.").format(
            label, round(perf_counter() - started, 1)
        ),
    }


def save_model(values: dict) -> dict:
    """A model of the list: added, or its name, provider, prices, tick or monthly limit
    changed. A model a job uses can't be unticked (HDSModelPricing.validate)."""
    _only_system_managers(_("Only System Managers change the model list."))
    model = str(values.get("model") or "").strip()
    if not model or len(model) > 140 or re.search(r"\s", model):
        frappe.throw(
            _("Give the model's name as the provider writes it, without spaces.")
        )
    exists = frappe.db.exists(PRICING, model)
    if (
        values.get("new")
        and exists
        and frappe.db.get_value(PRICING, model, "ai_provider")
    ):
        frappe.throw(_("{0} is already in the list.").format(model))
    doc = frappe.get_doc(PRICING, model) if exists else frappe.new_doc(PRICING)
    # what the gateway serves now, to write back if it refuses the change
    previous = _served(model) if exists else None
    if not exists:
        doc.update({"model_id": model, "display_name": model, "is_active": 1})
    if "name" in values:
        doc.display_name = str(values.get("name") or "").strip()[:140] or model
    if "provider" in values:
        account = str(values.get("provider") or "").strip()
        if account not in ai_engine.SLOTS and not frappe.db.exists(PROVIDER, account):
            frappe.throw(_("Choose the provider this model is called through."))
        doc.ai_provider = account
        doc.provider = PRICING_PROVIDER.get(_style(account), "OpenAI")
    if not doc.ai_provider:
        frappe.throw(_("Choose the provider this model is called through."))
    for field, key in (
        ("input_cost_per_1m", "input_price"),
        ("output_cost_per_1m", "output_price"),
    ):
        if key in values:
            price = flt(values.get(key))
            if price < 0:
                frappe.throw(_("A price cannot be below 0."))
            doc.set(field, price)
    if "limit_m" in values:
        doc.monthly_token_limit = flt(values.get("limit_m"))
    if "listed" in values:
        doc.listed = 1 if sbool(values.get("listed")) else 0
    doc.save(ignore_permissions=True)
    if ai_gateway.for_all():
        _write_model(doc.name, previous)
    return job_settings()


def remove_model(model: str) -> dict:
    """Takes a model off the list. Its price row is deleted when nothing ever used it; a model
    with calls or test-set runs keeps its prices for the cost reports."""
    _only_system_managers(_("Only System Managers change the model list."))
    if not frappe.db.exists(PRICING, model):
        frappe.throw(_("{0} isn't in the list.").format(model))
    in_use = ai_engine.in_use_message(model)
    if in_use:
        frappe.throw(in_use)
    if ai_gateway.for_all():
        try:
            ai_gateway.delete_model(model)
        except ai_gateway.GatewayError as e:
            frappe.throw(
                _("The gateway did not let go of {0}: {1}").format(model, str(e))
            )
    elif admin_ready() and frappe.db.get_value(PRICING, model, "on_gateway"):
        # a copy "Write all" made while the switch was off: once the model leaves the list,
        # Write all no longer sees it, so it goes now (best effort)
        with contextlib.suppress(ai_gateway.GatewayError):
            ai_gateway.delete_model(model)
    known = frappe.db.exists(LOG, {"model": model}) or frappe.db.exists(
        EVAL_RUN, {"model": model}
    )
    if known:
        frappe.db.set_value(
            PRICING,
            model,
            {"listed": 0, "ai_provider": "", "on_gateway": 0},
            update_modified=False,
        )
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


def _alert_once(
    key: str, subject: str, sent: list[str], hours: int = ALERT_QUIET_HOURS
) -> None:
    cache_key = ALERT_KEY.format(key)
    if frappe.cache.get_value(cache_key, expires=True):
        return
    send_alert(subject)
    frappe.cache.set_value(cache_key, 1, expires_in_sec=hours * 3600)
    sent.append(subject)


# a model's monthly token limit: told at these shares of it, once each a month
LIMIT_LEVELS = (100, 80)


def watch() -> list[str]:
    """Hourly: tells the managers when a model failed, or the fallback answered, more often
    than the limit in the last hour (one alert per model in six hours), and when a model
    reaches 80% and 100% of its monthly token limit (once each a month). Never raises."""
    sent: list[str] = []
    try:
        limits = alert_limits()
        if limits["error_rate"] or limits["fallback_rate"]:
            _watch_calls(limits, sent)
        _watch_month_limits(sent)
    except Exception:
        with contextlib.suppress(Exception):
            frappe.log_error(title="AI model alerts not checked")
    return sent


def _watch_month_limits(sent: list[str]) -> None:
    month = nowdate()[:7]
    for row in frappe.get_all(
        PRICING,
        filters={"monthly_token_limit": [">", 0]},
        fields=["name", "monthly_token_limit"],
    ):
        used = ai_engine.month_tokens(row.name)
        share = used / (row.monthly_token_limit * MILLION) * 100
        level = next((n for n in LIMIT_LEVELS if share >= n), None)
        if not level:
            continue
        figures = (row.name, round(used / MILLION, 1), flt(row.monthly_token_limit))
        if level == 100:
            subject = _(
                "AI model {0} has used its monthly token limit ({1} of {2} million tokens). Jobs that use it first wait until next month, or until the limit is raised in AI models."
            ).format(*figures)
        else:
            subject = _(
                "AI model {0} has used {3}% of its monthly token limit ({1} of {2} million tokens). At 100% the jobs that use it first stop until next month."
            ).format(*figures, round(share))
        _alert_once(f"limit:{row.name}:{month}:{level}", subject, sent, hours=32 * 24)


def _watch_calls(limits: dict, sent: list[str]) -> None:
    """A model failing, or the fallback answering, at least the limit in the last hour."""
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
    """Each model's newest run: {model: {accuracy, ran_on}}. Every run is read (a few per
    model), not the newest 50 the history shows: many runs of one model must not hide another
    model's only one."""
    scores: dict[str, dict] = {}
    for run in frappe.get_all(
        EVAL_RUN,
        fields=["model", "accuracy", "ran_on"],
        order_by="ran_on desc, creation desc",
        limit=0,
    ):
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
    others = sorted(m for m in latest_scores() if m != model)
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


def close_requests(model: str, eval_run: str, job: str | None = None) -> None:
    """A run of the test set arrived: the model's waiting requests (for `job`, when given)
    are answered."""
    filters = {"model": model, "status": ["in", ["Queued", "Running"]]}
    if job:
        filters["job"] = job
    for name in frappe.get_all(EVAL_REQUEST, filters=filters, pluck="name"):
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
    # the worker sends a list; anything else counts as nothing missing, never as a refusal
    listed = references.get("missing")
    missing = [
        {
            "kind": str(m.get("kind") or "")[:40],
            "value": str(m.get("value") or "")[:200],
        }
        for m in (listed if isinstance(listed, list) else [])
        if isinstance(m, dict) and m.get("value")
    ][:50]
    checked = cint(references.get("checked"))
    frappe.db.set_value(
        "HDS Copilot Run",
        run,
        {
            "references_checked": checked,
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
    compare with what the agent sends. A redraft of a waiting draft by the same model is the
    same draft; by another model it is a new one, so what the agent sends counts for the model
    that made it, and the replaced draft stays unused."""
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
        if not waiting or (waiting.get("model") or "") != (model or ""):
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
    """What customers said after Copilot worked on their ticket: fixed, or still broken. A
    ticket keeps only its newest answer, and a new fix asks again, so the answer is about the
    ticket's own run (`custom_copilot_run`, else its newest): it counts for that run's model
    only, not for every model that once worked on the ticket."""
    counts = {"Confirmed": 0, "Reopened": 0}
    tickets = sorted({r.ticket for r in runs if r.ticket})
    if not tickets or not frappe.db.has_column(
        "HD Ticket", "custom_customer_confirmation"
    ):
        return counts
    linked = frappe.db.has_column("HD Ticket", "custom_copilot_run")
    answers = frappe.get_all(
        "HD Ticket",
        filters={
            "name": ["in", tickets],
            "custom_customer_confirmation": ["in", list(counts)],
        },
        fields=[
            "name",
            "custom_customer_confirmation",
            *(["custom_copilot_run"] if linked else []),
        ],
        limit=0,
    )
    if not answers:
        return counts
    known: set[str] = set()
    newest: dict[str, str] = {}
    for run in frappe.get_all(
        "HDS Copilot Run",
        filters={"ticket": ["in", [a.name for a in answers]]},
        fields=["name", "ticket"],
        order_by="creation asc",
        limit=0,
    ):
        known.add(run.name)
        newest[run.ticket] = run.name
    # `runs` are this model's runs in the period: an answer counts only when the run it is
    # about is one of them, never for a run of another model or from before the period
    in_period = {r.name for r in runs}
    for answer in answers:
        run = answer.get("custom_copilot_run")
        about = run if run in known else newest.get(answer.name)
        if about in in_period:
            counts[answer.custom_customer_confirmation] += 1
    return counts


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
    """TBO Support's figures with the gateway's (`more`) as one: counts and cost add up; the
    speed stays the first's. Only TBO Support's own log says which calls a fallback answered,
    so the fallback rate stays the share of its calls (`hub_calls`), never of the gateway's."""
    calls = figures["calls"] + more["calls"]
    failed = figures["failed"] + more["failed"]
    hub_calls = figures.get("hub_calls", figures["calls"])
    return {
        **figures,
        "calls": calls,
        "failed": failed,
        "error_rate": rate(failed, calls),
        "hub_calls": hub_calls,
        "fallback_rate": rate(figures["as_fallback"], hub_calls),
        "cost": round(figures["cost"] + more["cost"], 2),
        "p50": figures["p50"] if figures["p50"] is not None else more["p50"],
        "p95": figures["p95"] if figures["p95"] is not None else more["p95"],
    }


def _merged_status(status: str, figures: dict) -> str:
    """A model's status again once the gateway's calls are added: from all its calls, as for
    TBO Support's alone. A pause stays."""
    if status == "Paused" or not figures["calls"]:
        return status
    return _status("", figures, set())


def overview(days: int = 30) -> dict:
    """Every model side by side: TBO Support's and the Copilot worker's, and the gateway's."""
    result = _hub_overview(days)
    by_model: dict[str, list] = {}
    for row in ai_gateway.day_rows(result["days"]):
        by_model.setdefault(row.model, []).append(row)
    if not by_model:
        return result
    known = {m["model"]: m for m in result["models"]}
    scores = latest_scores()
    for name, rows in by_model.items():
        figures = _gateway_figures(rows)
        aliases = sorted({r.gateway_alias for r in rows if r.gateway_alias})
        if name in known:
            known[name].update(_add(known[name], figures))
            known[name]["gateway_aliases"] = aliases
            known[name]["status"] = _merged_status(known[name]["status"], known[name])
        else:
            result["models"].append(
                {
                    "model": name,
                    "provider": GATEWAY_SOURCE,
                    "gateway_aliases": aliases,
                    "used_for": {"primary": [], "fallback": []},
                    **figures,
                    "benchmark": scores.get(name),
                    "status": _merged_status("Not used", figures),
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
    result["gateway_aliases"] = sorted(
        {r.gateway_alias for r in rows if r.gateway_alias}
    )
    if not result["provider"]:
        result["provider"] = GATEWAY_SOURCE
    result["status"] = _merged_status(result["status"], result)
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


def _keys_only_on_gateway(settings) -> dict[str, list[str]]:
    """Provider accounts whose key lives only in the gateway, with the jobs of TBO Support and
    the Copilot worker that call their models. Straight to the providers, those models have no
    key. A desktop level isn't one: the desktop app always calls the gateway."""
    found: dict[str, list[str]] = {}
    for row in settings.get("ai_jobs") or []:
        if not row.get("model") or row.job in ai_engine.OWN_MODEL_JOBS:
            continue
        for model in (row.get("model"), row.get("backup_model")):
            account = model_section(model) if model else ""
            if (
                account
                and account not in ai_engine.SLOTS
                and frappe.db.get_value(PROVIDER, account, "key_on_gateway")
                and not get_decrypted_password(
                    PROVIDER, account, "api_key", raise_exception=False
                )
            ):
                jobs = found.setdefault(account, [])
                if row.job not in jobs:
                    jobs.append(row.job)
    return found


def save_gateway(values: dict) -> dict:
    """The gateway's address, its keys, whether to read its usage and whether every call goes
    through it. While every call goes through it, a new address or call key is checked like
    the switch itself; the switch goes off only when no job needs a key that lives only in the
    gateway."""
    if not can_change():
        frappe.throw(
            _("Only System Managers set up the AI gateway."), frappe.PermissionError
        )
    doc = frappe.get_doc(SETTINGS)
    # whether every call went through the gateway until now (the switch, its address and key)
    was_on = ai_gateway.for_all(doc)
    old_url = (doc.gateway_url or "").strip()
    if "url" in values:
        doc.gateway_url = str(values.get("url") or "").strip()
    if "on" in values:
        doc.gateway_sync = 1 if frappe.utils.sbool(values.get("on")) else 0
    if values.get("key") is not None:
        doc.gateway_viewer_key = str(values.get("key")).strip()
    if values.get("call_key") is not None:
        doc.gateway_key = str(values.get("call_key")).strip()
    if values.get("admin_key") is not None:
        doc.gateway_admin_key = str(values.get("admin_key")).strip()
    if "for_all" in values:
        doc.gateway_for_all = 1 if frappe.utils.sbool(values.get("for_all")) else 0
    if was_on and not doc.gateway_for_all:
        # keys saved while every call went through the gateway live only there (the owner's
        # decision for Phase 37), and the gateway never gives a key back
        stranded = _keys_only_on_gateway(doc)
        if stranded:
            frappe.throw(
                _(
                    "The keys of {0} live only in the gateway, and {1} use their models. Choose other models for those jobs first; once the switch is off, enter those keys again. Every call keeps going through the gateway."
                ).format(
                    ", ".join(sorted(stranded)),
                    ", ".join(sorted({j for jobs in stranded.values() for j in jobs})),
                )
            )
    moved = (doc.gateway_url or "").strip() != old_url or values.get(
        "call_key"
    ) is not None
    # turning it on, or a new address or key while it is on: checked before calls go there
    probe = bool(doc.gateway_for_all) and (not was_on or moved)
    doc.save(ignore_permissions=True)
    if probe and not ai_gateway.call_key() and ai_gateway.admin_key():
        # TBO Support makes its own gateway key: nobody copies one by hand
        try:
            doc.gateway_key = ai_gateway.make_call_key()
        except ai_gateway.GatewayError as e:
            frappe.throw(
                _("The gateway did not make TBO Support's key: {0}").format(str(e))
            )
        doc.save(ignore_permissions=True)
    if probe:
        # every call goes through it only once it answers and takes TBO Support's key
        frappe.cache.delete_value([ai_gateway.ALIVE_KEY, ai_gateway.KEY_WORKS_KEY])
        problem = ""
        if not ai_gateway.for_all():
            problem = _(
                "Give the gateway's address and TBO Support's gateway key first."
            )
        elif not ai_gateway.alive(fresh=True):
            problem = _("The gateway does not answer at {0}.").format(
                ai_gateway.base_url()
            )
        elif not ai_gateway.key_works():
            problem = _("The gateway refused TBO Support's key.")
        if problem:
            # the error rolls the save back, so the earlier settings stay; the flags just
            # written are about the refused address or key, so they go too, and the next call
            # checks the gateway it really uses
            frappe.cache.delete_value([ai_gateway.ALIVE_KEY, ai_gateway.KEY_WORKS_KEY])
            frappe.throw(
                problem
                + " "
                + (
                    _(
                        "Nothing was changed: every call keeps going through the gateway."
                    )
                    if was_on
                    else _("Every call keeps going straight to the providers.")
                )
            )
    if probe and not was_on:
        # switching on writes everything the gateway must serve: the keys still kept here (then
        # forgotten here), every allowed model and the desktop levels, as they are now; a
        # refusal rolls the switch back
        if not admin_ready():
            frappe.throw(
                _(
                    "Set the gateway's admin key first: the providers' keys and the models move to the gateway when every call goes through it."
                )
            )
        write_all()
    ai_engine.reset_provider_state()
    return ai_gateway.status()


def sync_gateway() -> dict:
    if not can_change():
        frappe.throw(
            _("Only System Managers read the AI gateway now."), frappe.PermissionError
        )
    result = ai_gateway.sync()
    return {**ai_gateway.status(), "ok": result["ok"], "note": result["note"]}
