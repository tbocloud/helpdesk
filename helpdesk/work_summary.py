"""Weekly work summary per customer, for the people who run that customer's work.

Every Monday, each customer with activity gets an HD Work Summary for the
previous 7 days: ticket and task counts, SLA breaches, overdue and held tasks,
what is due next week and per-project progress. The AI turns those numbers
into a short read for a project manager; when AI isn't configured or fails, a
plain summary is built from the same numbers. The managers, owners and leads
of the customer's projects and all Agent Managers are notified.
"""

import json

import frappe
from frappe import _
from frappe.utils import (
    add_days,
    escape_html,
    formatdate,
    get_datetime,
    getdate,
    now_datetime,
    nowdate,
)

from helpdesk.ai_engine import call_haiku
from helpdesk.api.ticket_ai import html_to_text, truncate
from helpdesk.work_reminders import get_project_managers, notify_users

PERIOD_DAYS = 7
DUE_NEXT_DAYS = 7
LIST_CAP = 10
AI_ITEM_CAP = 8
AI_TEXT_CHARS = 400
# Each customer's AI call runs in its own job, so one slow provider call only holds up that customer
SUMMARY_JOB_TIMEOUT = 600

CLOSED_PROJECT_STATUSES = ["Completed", "Cancelled"]
CLOSED_TASK_STATUSES = ["Completed", "Cancelled", "Template"]
OPEN_TICKET_CATEGORIES = ["Open", "Paused"]
KEY_TICKET_PRIORITIES = ("Urgent", "High")
ON_HOLD = "On Hold"

SYSTEM_PROMPT = """You write a short weekly status summary about one customer for a project manager.
Use only the facts in the JSON stats you are given. Never invent tickets, tasks, people, dates, numbers,
causes or plans that are not in the stats. If a list is empty, say nothing about it. Be brief and factual,
in plain English, with no greetings and no sign-off.
- overview: one or two sentences with the headline numbers for the period.
- highlights: what got done (completed tasks, resolved tickets, project progress).
- risks: overdue tasks, tasks on hold (with their reasons) and SLA-breached or urgent/high tickets.
- next_week: what is due in the next 7 days, key tasks first.
Each list item is one short plain-text sentence (no HTML, no markdown), at most 8 items per list.
Reply with JSON only: {"overview": "...", "highlights": ["..."], "risks": ["..."], "next_week": ["..."]}"""


def send_weekly_summaries():
    """Scheduler (Monday morning): one summary job per customer with activity in the last 7 days."""
    end = add_days(getdate(nowdate()), -1)
    start = add_days(end, -(PERIOD_DAYS - 1))
    for customer in sorted(get_active_customers(start, end)):
        try:
            frappe.enqueue(
                "helpdesk.work_summary.send_customer_summary",
                queue="long",
                timeout=SUMMARY_JOB_TIMEOUT,
                job_id=f"work-summary-{customer}-{end}",
                deduplicate=True,
                customer=customer,
                start=str(start),
                end=str(end),
            )
        except Exception:  # noqa: BLE001 - one customer must not stop the others
            frappe.log_error(
                title=f"Weekly summary not queued for {customer}",
                message=frappe.get_traceback(),
            )


def send_customer_summary(customer: str, start: str, end: str):
    """Background job: create one customer's summary and tell the people who run its work.

    A failure here is rolled back and logged by the job runner, and touches no other customer.
    """
    summary = create_summary(customer, start, end)
    notify_users(
        get_summary_recipients(customer),
        "HD Work Summary",
        summary.name,
        _("Weekly summary: {0}").format(customer),
    )
    return summary


def create_summary(customer: str, start, end):
    stats = collect_customer_stats(customer, start, end)
    text, used_ai = write_summary(customer, stats)
    return frappe.get_doc(
        {
            "doctype": "HD Work Summary",
            "customer": customer,
            "period_start": stats["period_start"],
            "period_end": stats["period_end"],
            "summary": text,
            "stats": json.dumps(stats, indent=1),
            "generated_by_ai": int(used_ai),
        }
    ).insert(ignore_permissions=True)


def get_active_customers(start, end) -> set[str]:
    """Customers with an open project or ticket, or a ticket or task touched in the period."""
    period = ("between", [str(start), str(end)])
    customers = set(
        frappe.get_all(
            "Project",
            filters={"status": ("not in", CLOSED_PROJECT_STATUSES)},
            pluck="customer",
        )
    )
    customers |= set(
        frappe.get_all(
            "HD Ticket",
            filters={"status_category": ("in", OPEN_TICKET_CATEGORIES)},
            pluck="customer",
            distinct=True,
        )
    )
    customers |= set(
        frappe.get_all(
            "HD Ticket", filters={"modified": period}, pluck="customer", distinct=True
        )
    )
    touched_projects = frappe.get_all(
        "Task",
        filters={"modified": period, "project": ("is", "set")},
        pluck="project",
        distinct=True,
    )
    if touched_projects:
        customers |= set(
            frappe.get_all(
                "Project",
                filters={"name": ("in", touched_projects)},
                pluck="customer",
            )
        )
    return {c for c in customers if c}


def get_summary_recipients(customer: str) -> list[str]:
    """Managers, owners and leads of the customer's open projects, plus enabled Agent Managers."""
    projects = frappe.get_all(
        "Project",
        filters={"customer": customer, "status": ("not in", CLOSED_PROJECT_STATUSES)},
        fields=["name", "project_lead"],
    )
    users = set()
    for project in projects:
        users.update(get_project_managers(project.name))
        if project.project_lead:
            users.add(project.project_lead)
    users.update(get_agent_managers())
    return sorted(u for u in users if u)


def get_agent_managers() -> list[str]:
    managers = frappe.get_all(
        "Has Role",
        filters={"role": "Agent Manager", "parenttype": "User"},
        pluck="parent",
    )
    if not managers:
        return []
    return frappe.get_all(
        "User", filters={"name": ("in", managers), "enabled": 1}, pluck="name"
    )


# --- stats ---


def collect_customer_stats(customer: str, start, end) -> dict:
    """Facts about one customer's tickets, tasks and projects for the period (lists capped)."""
    start, end = getdate(start), getdate(end)
    today = getdate(nowdate())
    projects = frappe.get_all(
        "Project",
        filters={"customer": customer, "status": ("!=", "Cancelled")},
        fields=["name", "project_name", "status"],
        order_by="project_name asc",
    )
    tasks = (
        frappe.get_all(
            "Task",
            filters={
                "project": ("in", [p.name for p in projects]),
                "status": ("!=", "Template"),
            },
            fields=[
                "name",
                "subject",
                "project",
                "status",
                "exp_end_date",
                "is_key",
                "hold_reason",
                "hold_since",
                "modified",
            ],
            order_by="exp_end_date asc",
        )
        if projects
        else []
    )
    return {
        "customer": customer,
        "period_start": str(start),
        "period_end": str(end),
        "as_of": str(today),
        "tickets": ticket_stats(customer, start, end),
        "tasks": task_stats(tasks, projects, start, end, today),
        "projects": project_progress(tasks, projects),
    }


def ticket_stats(customer: str, start, end) -> dict:
    period = ("between", [str(start), str(end)])
    opened = frappe.get_all(
        "HD Ticket", filters={"customer": customer, "creation": period}, pluck="name"
    )
    resolved = frappe.get_all(
        "HD Ticket",
        filters={
            "customer": customer,
            "status_category": "Resolved",
            "resolution_date": period,
        },
        fields=["name", "agreement_status"],
    )
    still_open = frappe.get_all(
        "HD Ticket",
        filters={
            "customer": customer,
            "status_category": ("in", OPEN_TICKET_CATEGORIES),
        },
        fields=["name", "subject", "priority", "resolution_by", "agreement_status"],
        order_by="resolution_by asc",
    )
    now = now_datetime()
    breached_open = [
        t
        for t in still_open
        if t.agreement_status == "Failed"
        or (t.resolution_by and get_datetime(t.resolution_by) < now)
    ]
    breached_resolved = [t for t in resolved if t.agreement_status == "Failed"]
    key_open = [t for t in still_open if t.priority in KEY_TICKET_PRIORITIES]
    return {
        "opened": len(opened),
        "resolved": len(resolved),
        "open": len(still_open),
        "sla_breached": len(breached_open) + len(breached_resolved),
        "sla_breached_open": [ticket_item(t) for t in breached_open[:LIST_CAP]],
        "urgent_high_open": len(key_open),
        "urgent_high_open_list": [ticket_item(t) for t in key_open[:LIST_CAP]],
    }


def ticket_item(ticket) -> dict:
    return {
        "name": str(ticket.name),
        "subject": ticket.subject,
        "priority": ticket.priority,
        "resolution_by": str(ticket.resolution_by) if ticket.resolution_by else None,
    }


def task_stats(tasks, projects, start, end, today) -> dict:
    names = {p.name: p.project_name or p.name for p in projects}
    period_start, period_end = get_datetime(start), get_datetime(add_days(end, 1))
    completed = [
        t
        for t in tasks
        if t.status == "Completed" and period_start <= t.modified < period_end
    ]
    still_open = [t for t in tasks if t.status not in CLOSED_TASK_STATUSES]
    # a held task's due date moves when it resumes, so it isn't counted as overdue
    active = [t for t in still_open if t.status != ON_HOLD]
    overdue = [t for t in active if t.exp_end_date and getdate(t.exp_end_date) < today]
    due_soon = [
        t
        for t in active
        if t.exp_end_date
        and today <= getdate(t.exp_end_date) <= add_days(today, DUE_NEXT_DAYS)
    ]
    on_hold = [t for t in still_open if t.status == ON_HOLD]
    key_open = [t for t in still_open if t.is_key]

    def items(rows, **extra):
        return [task_item(t, names, **extra) for t in rows[:LIST_CAP]]

    return {
        "completed": len(completed),
        "completed_list": items(completed),
        "open": len(still_open),
        "overdue": len(overdue),
        "overdue_list": items(overdue),
        "on_hold": len(on_hold),
        "on_hold_list": items(on_hold, with_hold=True),
        "key_open": len(key_open),
        "key_open_list": items(key_open),
        "due_next_7_days": len(due_soon),
        "due_next_7_days_list": items(due_soon),
    }


def task_item(task, project_names: dict, with_hold: bool = False) -> dict:
    item = {
        "subject": task.subject,
        "project": project_names.get(task.project, task.project),
        "status": task.status,
        "due": str(task.exp_end_date) if task.exp_end_date else None,
        "is_key": bool(task.is_key),
    }
    if with_hold:
        item["hold_reason"] = task.hold_reason
        item["hold_since"] = str(task.hold_since) if task.hold_since else None
    return item


def project_progress(tasks, projects) -> list[dict]:
    rows = []
    for project in projects:
        counted = [
            t for t in tasks if t.project == project.name and t.status != "Cancelled"
        ]
        done = sum(1 for t in counted if t.status == "Completed")
        rows.append(
            {
                "project": project.project_name or project.name,
                "status": project.status,
                "tasks": len(counted),
                "completed": done,
                "progress": round(done * 100 / len(counted)) if counted else 0,
            }
        )
    # open projects first: those are the ones a manager acts on
    rows.sort(key=lambda r: r["status"] in CLOSED_PROJECT_STATUSES)
    return rows[:LIST_CAP]


# --- summary text ---


def write_summary(customer: str, stats: dict) -> tuple[str, bool]:
    """Summary HTML and whether the AI wrote it; falls back to a plain summary of the stats."""
    try:
        result = call_haiku(SYSTEM_PROMPT, build_prompt(customer, stats))
    except Exception:  # noqa: BLE001 - provider errors vary; the plain summary still goes out
        frappe.log_error(
            title="Weekly summary with AI failed", message=frappe.get_traceback()
        )
        return render_summary(*fallback_summary(stats)), False

    response = result.get("response") or {}
    sections = ai_sections(response) if isinstance(response, dict) else None
    if not sections:
        return render_summary(*fallback_summary(stats)), False
    return render_summary(*sections), True


def build_prompt(customer: str, stats: dict) -> str:
    return f"Customer: {customer}\n\nStats (JSON):\n{json.dumps(stats, indent=1)}"


def ai_sections(response: dict) -> tuple[str, list] | None:
    """The model's answer as (overview, sections) of plain text, or None when it is unusable."""

    def clean(value) -> str:
        if not isinstance(value, str):
            return ""
        return truncate(html_to_text(value), AI_TEXT_CHARS)

    def clean_list(value) -> list[str]:
        if not isinstance(value, list):
            return []
        texts = (clean(item) for item in value[:AI_ITEM_CAP])
        return [text for text in texts if text]

    overview = clean(response.get("overview"))
    highlights = clean_list(response.get("highlights"))
    risks = clean_list(response.get("risks"))
    next_week = clean_list(response.get("next_week"))
    if not (overview or highlights or risks or next_week):
        return None
    return overview, section_list(highlights, risks, next_week)


def section_list(highlights: list, risks: list, next_week: list) -> list:
    return [
        (_("Highlights"), highlights, _("Nothing completed this period.")),
        (_("Risks"), risks, _("No risks flagged.")),
        (_("Due next week"), next_week, _("Nothing due in the next 7 days.")),
    ]


def fallback_summary(stats: dict) -> tuple[str, list]:
    """A plain (overview, sections) built only from the stats, for when AI is unavailable."""
    tickets, tasks = stats["tickets"], stats["tasks"]
    overview = _(
        "{0} to {1}: {2} tickets opened, {3} resolved, {4} still open ({5} with a breached SLA). "
        "{6} tasks completed, {7} open ({8} overdue, {9} on hold)."
    ).format(
        formatdate(stats["period_start"]),
        formatdate(stats["period_end"]),
        tickets["opened"],
        tickets["resolved"],
        tickets["open"],
        tickets["sla_breached"],
        tasks["completed"],
        tasks["open"],
        tasks["overdue"],
        tasks["on_hold"],
    )

    highlights = [
        _("Completed: {0} ({1})").format(t["subject"], t["project"])
        for t in tasks["completed_list"]
    ]
    if tickets["resolved"]:
        highlights.append(_("{0} tickets resolved").format(tickets["resolved"]))
    highlights += [
        _("{0}: {1}% complete ({2} of {3} tasks)").format(
            p["project"], p["progress"], p["completed"], p["tasks"]
        )
        for p in stats["projects"]
        if p["tasks"] and p["status"] not in CLOSED_PROJECT_STATUSES
    ]

    risks = [
        _("Overdue since {0}: {1} ({2})").format(
            formatdate(t["due"]), key_label(t), t["project"]
        )
        for t in tasks["overdue_list"]
    ]
    risks += [
        _("On hold since {0} ({1}): {2} ({3})").format(
            formatdate(t["hold_since"]) if t["hold_since"] else "-",
            t["hold_reason"] or _("no reason given"),
            key_label(t),
            t["project"],
        )
        for t in tasks["on_hold_list"]
    ]
    risks += [
        _("SLA breached: ticket #{0} {1}").format(t["name"], t["subject"])
        for t in tickets["sla_breached_open"]
    ]
    breached = {t["name"] for t in tickets["sla_breached_open"]}
    risks += [
        _("{0} priority ticket open: #{1} {2}").format(
            t["priority"], t["name"], t["subject"]
        )
        for t in tickets["urgent_high_open_list"]
        if t["name"] not in breached
    ]

    next_week = [
        _("Due {0}: {1} ({2})").format(formatdate(t["due"]), key_label(t), t["project"])
        for t in tasks["due_next_7_days_list"]
    ]
    return overview, section_list(highlights, risks, next_week)


def key_label(task: dict) -> str:
    return (
        _("Key task: {0}").format(task["subject"])
        if task["is_key"]
        else task["subject"]
    )


def render_summary(overview: str, sections: list) -> str:
    """Simple HTML (p/ul/li/strong); every piece of text is escaped here."""
    parts = [f"<p>{escape_html(overview)}</p>"] if overview else []
    for title, items, empty_text in sections:
        parts.append(f"<p><strong>{escape_html(title)}</strong></p>")
        if items:
            rows = "".join(f"<li>{escape_html(item)}</li>" for item in items)
            parts.append(f"<ul>{rows}</ul>")
        else:
            parts.append(f"<p>{escape_html(empty_text)}</p>")
    return "".join(parts)
