"""AI time estimates for new tasks.

A task created without a due date gets one: the AI reads the task, the project
type (ERP implementation, mobile app, content calendar, ...) and how long
similar finished tasks took here, and answers with working days and hours.
The due date counts working days only (HD Work Settings' weekly off). When the
AI isn't configured or fails, typical durations per project type are used.
Due dates people set themselves are never touched.
"""

import statistics

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, formatdate, getdate, nowdate

from helpdesk.ai_engine import call_haiku

ESTIMATE_JOB_TIMEOUT = 120
HISTORY_LIMIT = 200
EXAMPLES = 12
DEFAULT_MAX_DAYS = 15
WEEKDAYS = {
    "Sunday": {6},
    "Friday": {4},
    "Saturday and Sunday": {5, 6},
    "Friday and Saturday": {4, 5},
}
# fallback working days when there's no AI and no history yet
TYPICAL_DAYS = {
    "ERP Implementation": 3,
    "Mobile App": 4,
    "Website": 3,
    "Content Calendar": 1,
    "Support": 1,
}
# creative and coordination work takes about as long whatever the project type
CATEGORY_TYPICAL_DAYS = {
    "Digital Marketing": 2,
    "Social Media": 1,
    "Content Writing": 1,
    "Graphic Design": 1,
    "Video": 3,
    "Motion Graphics": 3,
    "Coordination": 1,
}
PRIORITY_FACTOR = {"Urgent": 0.5, "High": 0.75}
HOURS_PER_DAY = 6

SYSTEM_PROMPT = """You estimate how long a task takes for TBO, an ERPNext implementation,
mobile app and digital marketing company. Answer with JSON only:
{"working_days": <whole number>, "estimated_hours": <number>, "reason": "<one short sentence>"}
working_days is the calendar span in working days from start to done for one person,
including reviews and waiting; estimated_hours is focused effort. Base it on the task text,
the project type and the reference durations of finished tasks. ERP configuration and
reports usually take 1-3 days, data migration and integrations longer; mobile app screens
and APIs 2-5 days; content posts and captions under a day; graphic designs about a day;
videos and motion graphics 2-4 days. Never exceed the maximum given."""


def get_settings():
    return frappe.get_cached_doc("HD Work Settings")


def weekly_off_days() -> set[int]:
    return WEEKDAYS.get(get_settings().weekly_off or "Sunday", {6})


def is_working_day(day) -> bool:
    from helpdesk.work_calendar import is_saturday_off

    day = getdate(day)
    return day.weekday() not in weekly_off_days() and not is_saturday_off(day)


def add_working_days(start, days: int):
    """The date `days` working days after `start` (start itself counts as day one)."""
    day = getdate(start)
    while not is_working_day(day):
        day = add_days(day, 1)
    counted = 1
    while counted < days:
        day = add_days(day, 1)
        if is_working_day(day):
            counted += 1
    return day


def should_estimate(task) -> bool:
    settings = get_settings()
    return bool(
        settings.ai_task_estimates
        and not task.exp_end_date
        and task.status not in ("Completed", "Cancelled", "Template")
    )


def queue_estimate(task):
    frappe.enqueue(
        "helpdesk.task_estimates.estimate_task",
        task=task.name,
        timeout=ESTIMATE_JOB_TIMEOUT,
        enqueue_after_commit=True,
        now=frappe.flags.in_test,
    )


def reference_durations(project_type: str | None) -> dict:
    """Median working-day spans of finished tasks, per category, plus a few examples."""
    project_filter = (
        {
            "project": (
                "in",
                frappe.get_all("Project", {"project_type": project_type}, pluck="name")
                or [""],
            )
        }
        if project_type
        else {}
    )
    finished = frappe.get_all(
        "Task",
        filters={
            "status": "Completed",
            "completed_on": ("is", "set"),
            **project_filter,
        },
        fields=[
            "subject",
            "custom_category",
            "creation",
            "exp_start_date",
            "completed_on",
        ],
        order_by="completed_on desc",
        limit=HISTORY_LIMIT,
    )
    spans = {}
    examples = []
    for task in finished:
        start = task.exp_start_date or getdate(task.creation)
        days = max(date_diff(task.completed_on, start) + 1, 1)
        spans.setdefault(task.custom_category or "Other", []).append(days)
        if len(examples) < EXAMPLES:
            examples.append({"task": task.subject, "days": days})
    medians = {cat: statistics.median(values) for cat, values in spans.items()}
    return {"median_days_by_category": medians, "examples": examples}


def build_prompt(task, project, history: dict, max_days: int) -> str:
    return frappe.as_json(
        {
            "task": {
                "subject": task.subject,
                "description": frappe.utils.strip_html(task.description or "")[:1500],
                "category": task.get("custom_category"),
                "phase": task.get("custom_phase"),
                "priority": task.priority,
                "key_task": bool(task.is_key),
                "milestone": bool(task.is_milestone),
            },
            "project": {
                "type": project.get("project_type") or "not set",
                "name": project.get("project_name"),
            },
            "reference_durations": history,
            "maximum_working_days": max_days,
        }
    )


def fallback_estimate(task, project_type: str | None, history: dict) -> dict:
    medians = history.get("median_days_by_category") or {}
    category = task.get("custom_category") or "Other"
    if medians.get(category):
        base, source = medians[category], _("similar finished tasks")
    elif category in CATEGORY_TYPICAL_DAYS:
        base = CATEGORY_TYPICAL_DAYS[category]
        source = _("typical time for this kind of task")
    else:
        base = TYPICAL_DAYS.get(project_type or "", 2)
        source = _("typical time for this project type")
    days = max(round(base * PRIORITY_FACTOR.get(task.priority, 1)), 1)
    return {
        "working_days": days,
        "estimated_hours": days * HOURS_PER_DAY,
        "reason": _("Based on {0}.").format(source),
        "used_ai": False,
    }


def ai_estimate(task, project, history: dict, max_days: int) -> dict | None:
    try:
        result = call_haiku(
            SYSTEM_PROMPT, build_prompt(task, project, history, max_days)
        )
    except Exception:  # noqa: BLE001 - provider errors vary; the fallback still sets a date
        frappe.log_error(
            title="AI task estimate failed", message=frappe.get_traceback()
        )
        return None
    response = result.get("response") if isinstance(result, dict) else None
    days = cint(response.get("working_days")) if isinstance(response, dict) else 0
    if days < 1:
        frappe.log_error(
            title="AI task estimate not usable", message=str(response)[:3000]
        )
        return None
    reason = frappe.utils.strip_html(str(response.get("reason") or ""))[:300]
    return {
        "working_days": days,
        "estimated_hours": max(flt(response.get("estimated_hours")), 0),
        "reason": reason,
        "used_ai": True,
    }


def estimate_task(task: str):
    """Background job: fill in the due date (and hours) of a task created without one."""
    doc = frappe.get_doc("Task", task)
    if not should_estimate(doc):
        return
    project = (
        frappe.db.get_value(
            "Project", doc.project, ["project_type", "project_name"], as_dict=True
        )
        if doc.project
        else None
    ) or frappe._dict()
    max_days = cint(get_settings().max_task_days) or DEFAULT_MAX_DAYS
    history = reference_durations(project.get("project_type"))
    estimate = ai_estimate(doc, project, history, max_days) or fallback_estimate(
        doc, project.get("project_type"), history
    )
    days = min(estimate["working_days"], max_days)

    start = doc.exp_start_date or nowdate()
    doc.exp_start_date = start
    doc.exp_end_date = add_working_days(start, days)
    if not doc.get("custom_estimated_hours") and estimate["estimated_hours"]:
        doc.custom_estimated_hours = round(estimate["estimated_hours"], 1)
    doc.ai_estimated = 1
    doc.estimate_note = estimate["reason"]
    doc.save(ignore_permissions=True)

    by = _("AI estimate") if estimate["used_ai"] else _("standard estimate")
    doc.add_comment(
        "Info",
        frappe.utils.escape_html(
            _("Due date set to {0}: {1} working day(s), {2}. {3}").format(
                formatdate(doc.exp_end_date), days, by, estimate["reason"]
            )
        ),
    )
