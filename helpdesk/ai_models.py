# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""AI Models (Phase 31): how each AI model does, and which model each job uses.

Everything is read from HDS AI Usage Log, where every attempt is a row: TBO Support's own calls
(with their speed, and a Failed row with the error's kind when the provider refused) and the
Copilot worker's stages. Nothing here reads or returns a prompt or a customer's text.
"""

import contextlib

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
    scores = latest_scores()
    names = sorted(set(by_model) | set(used) | set(scores))
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
                "benchmark": scores.get(name),
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


def request_eval(model: str, job: str = "investigate") -> dict:
    """Queues a run of the test set on a model for the Copilot worker; one at a time per model."""
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
