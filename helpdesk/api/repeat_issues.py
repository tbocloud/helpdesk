"""Repeat issues on the Scoreboard (/helpdesk/team-dashboard?view=repeats).

Everyone who sees the Scoreboard sees them, with the Scoreboard's own rules for
departments (`viewer_access`, `scope_department`: every active department, past
the DM/ERP walls). The actions follow permissions:

- "Not a repeat" and "Create root-cause task": System and Agent Managers,
  department heads and Project Managers (`can_act`); the task itself only in a
  project of the cluster's customer that the person manages or leads, or whose
  department they head.
- "Draft KB article": anyone who may create HD Articles (agents), with AI set up.

Detection lives in helpdesk.repeat_issues; docs/team-dashboard.md (Repeat issues).
"""

import frappe
from frappe import _
from frappe.utils import escape_html, getdate, nowdate

from helpdesk import repeat_issues as ri
from helpdesk.api.team_dashboard import check_period, scope_department, viewer_access
from helpdesk.api.ticket_ai import truncate
from helpdesk.tasky.permissions import (
    can_manage_project,
    can_manage_team,
    departments_headed,
    is_project_manager,
)
from helpdesk.utils import agent_only

DRAFT_COOLDOWN_SECONDS = 60
TASK_SUBJECT_CHARS = 140


@frappe.whitelist()
@agent_only
def get_repeat_issues(period: str = "week", department: str | None = None) -> dict:
    """The period's repeat issues, by customer, with what the viewer may do."""
    check_period(period)
    department = scope_department(viewer_access(frappe.session.user), department)
    data = ri.repeat_issues(period, department, getdate(nowdate()))
    return {
        **data,
        "department": department,
        "access": {
            "can_act": can_act(frappe.session.user),
            "can_draft_kb": bool(frappe.has_permission("HD Article", "create")),
        },
    }


@frappe.whitelist(methods=["POST"])
@agent_only
def dismiss_repeat_issue(
    period: str, cluster: str, department: str | None = None
) -> dict:
    """ "Not a repeat": the cluster stops showing, for everyone."""
    check_can_act()
    found = find(period, cluster, department)
    doc = ri.save_decision(found, "Dismissed")
    return {"issue": doc.name}


@frappe.whitelist(methods=["POST"])
@agent_only
def restore_repeat_issue(issue: str) -> dict:
    """Undo "Not a repeat"."""
    check_can_act()
    doc = frappe.get_doc("HD Repeat Issue", issue)
    if doc.status != "Dismissed":
        frappe.throw(_("Only a dismissed repeat issue can be brought back."))
    doc.status = "Open"
    doc.decided_by = frappe.session.user
    doc.save(ignore_permissions=True)
    return {"issue": doc.name}


@frappe.whitelist(methods=["POST"])
@agent_only
def create_root_cause_task(
    period: str, cluster: str, project: str, department: str | None = None
) -> dict:
    """A key task in the customer's project to fix what keeps coming back, listing
    the cluster's tickets and tasks."""
    check_can_act()
    found = find(period, cluster, department)
    check_project(project, found["customer"])
    # two managers (or a double click) must not both create one: the second waits
    # for the first to commit, then finds its task
    ri.lock_customer(found["customer"])
    record = ri.decision_for(found, ri.decisions([found["customer"]]))
    if record and record["status"] == "Root-cause task" and record["task"]:
        frappe.throw(
            _("This repeat issue already has a root-cause task: {0}.").format(
                record["task"]
            )
        )
    title = (ri.cached_label(found["id"]) or {}).get("title") or found["subject"]
    task = frappe.get_doc(
        {
            "doctype": "Task",
            "subject": truncate(_("Root cause: {0}").format(title), TASK_SUBJECT_CHARS),
            "project": project,
            "status": "Open",
            "priority": "High",
            "is_key": 1,
            "custom_category": "Support",
            "description": task_description(found),
        }
    ).insert(ignore_permissions=True)
    doc = ri.save_decision(found, "Root-cause task", task=task.name)
    return {"task": task.name, "project": project, "issue": doc.name}


@frappe.whitelist(methods=["POST"])
@agent_only
def draft_kb_article(period: str, cluster: str, department: str | None = None) -> dict:
    """A draft KB article from the cluster's latest resolved ticket, through the
    existing KB draft feature (helpdesk.kb_drafts); an article already written
    from one of its tickets is returned instead."""
    from helpdesk import kb_drafts
    from helpdesk.ai_suggestion import is_ai_configured

    frappe.has_permission("HD Article", "create", throw=True)
    found = find(period, cluster, department)
    tickets = [i["name"] for i in found["items"] if i["kind"] == "ticket"]
    existing = ri.linked_articles(tickets)
    if existing:
        return {**next(iter(existing.values())), "existing": True}
    if not is_ai_configured():
        frappe.throw(_("AI isn't set up on this hub, so it can't draft an article."))
    source = answered_ticket(tickets)
    if not source:
        frappe.throw(
            _(
                "None of these tickets is resolved with a reply from the team yet, so there's no answer to write up."
            )
        )
    lock = f"{ri.CACHE_PREFIX}_draft:{found['id']}"
    if frappe.cache.get_value(lock, expires=True):
        frappe.throw(_("An article was asked for less than a minute ago."))
    frappe.cache.set_value(lock, 1, expires_in_sec=DRAFT_COOLDOWN_SECONDS)
    article = kb_drafts.draft_article(source)
    if not article:
        frappe.throw(
            _(
                "The AI didn't write a draft: an article may already cover it, or the answer wasn't clear enough."
            )
        )
    return {
        "name": article.name,
        "title": article.title,
        "status": article.status,
        "existing": False,
    }


# --- checks and helpers --------------------------------------------------------


def can_act(user: str) -> bool:
    """May dismiss repeat issues and create root-cause tasks: admins, department
    heads and Project Managers."""
    return can_manage_team(user) or is_project_manager(user)


def check_can_act():
    if not can_act(frappe.session.user):
        frappe.throw(
            _("Only managers and department heads can act on repeat issues."),
            frappe.PermissionError,
        )


def find(period: str, cluster: str, department: str | None) -> dict:
    check_period(period)
    department = scope_department(viewer_access(frappe.session.user), department)
    return ri.find_cluster(period, department, cluster, getdate(nowdate()))


def check_project(project: str, customer: str):
    """The task goes to an open project of the cluster's customer that the user
    manages or leads, or whose department they head."""
    row = frappe.db.get_value(
        "Project",
        project,
        ["customer", "status", "custom_department"],
        as_dict=True,
    )
    if not row or row.customer != customer or row.status != "Open":
        frappe.throw(_("Pick an open project of {0}.").format(customer))
    user = frappe.session.user
    if not (
        can_manage_project(project, user)
        or (row.custom_department and row.custom_department in departments_headed(user))
    ):
        frappe.throw(
            _(
                "Only the project's managers, its lead or its department's heads can add this task."
            ),
            frappe.PermissionError,
        )


def task_description(found: dict) -> str:
    """The cluster in words, and every ticket and task in it."""
    label = ri.cached_label(found["id"]) or {}
    lines = [
        "<p>"
        + escape_html(
            _(
                "{0} raised this {1} times in the last {2} days ({3} this period). Fix the cause so it stops coming back."
            ).format(
                found["customer"],
                found["total"],
                ri.LOOKBACK_DAYS,
                found["in_period"],
            )
        )
        + "</p>"
    ]
    if label.get("cause"):
        lines.append(
            f"<p>{escape_html(_('Likely cause: {0}').format(label['cause']))}</p>"
        )
    if label.get("fix"):
        lines.append(
            f"<p>{escape_html(_('Suggested fix: {0}').format(label['fix']))}</p>"
        )
    items = []
    for i in found["items"]:
        text = escape_html(f"{i['date']} · {i['subject']}")
        if i["kind"] == "ticket":
            items.append(
                f'<li><a href="/helpdesk/tickets/{escape_html(i["name"])}">#{escape_html(i["name"])}</a> {text}</li>'
            )
        else:
            items.append(f"<li>{escape_html(i['name'])} {text}</li>")
    lines.append(f"<ul>{''.join(items)}</ul>")
    return "".join(lines)


def answered_ticket(tickets: list[str]) -> str | None:
    """The most recently resolved of the tickets that the team answered."""
    from helpdesk.kb_drafts import has_team_answer

    if not tickets:
        return None
    ticket = frappe.qb.DocType("HD Ticket")
    resolved = (
        frappe.qb.from_(ticket)
        .select(ticket.name)
        .where(ticket.name.isin(tickets) & (ticket.status_category == "Resolved"))
        .orderby(ticket.modified, order=frappe.qb.desc)
        .run(pluck=True)
    )
    return next((str(t) for t in resolved if has_team_answer(str(t))), None)
