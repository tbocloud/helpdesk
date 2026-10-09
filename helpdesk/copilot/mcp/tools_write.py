# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Write tools for TBO staff. None of them sends anything to a customer.

Each repeats the guard of the screen it stands for, as the caller: an
internal note (like the comment box), a draft in the suggested-reply card
(like Regenerate), a task status (like the task board), a KB draft.
"""

import frappe
from frappe import _
from frappe.utils import md_to_html

from helpdesk.copilot.mcp.registry import WRITE, register_tool
from helpdesk.copilot.mcp.shape import paragraphs_html, ticket_name

TASK_STATUSES = ["Open", "Working", "On Hold", "Completed", "Cancelled"]
# the options of Task.hold_reason (test_copilot_mcp_write_tools checks they still match)
HOLD_REASONS = ["Laptop / system issue", "Leave", "Waiting on customer", "Waiting on another task", "Other"]


def add_ticket_comment(caller, ticket: str, text: str) -> dict:
    name = ticket_name(ticket)
    doc = frappe.get_doc("HD Ticket", name)
    doc.check_permission("read")  # what the comment box's run_doc_method checks
    doc.new_comment(paragraphs_html(text))
    created = frappe.get_all(
        "HD Ticket Comment",
        filters={"reference_ticket": name, "commented_by": frappe.session.user},
        order_by="creation desc",
        limit=1,
        pluck="name",
    )
    return {"ticket": name, "comment": created[0] if created else None, "visible_to_customer": False}


def draft_ticket_reply(caller, ticket: str, text: str) -> dict:
    from helpdesk.ai_suggestion import is_open_ticket, store_suggestion

    name = ticket_name(ticket)
    # the guard of regenerate_suggestion: an agent who may write the ticket, and an open ticket
    frappe.has_permission("HD Ticket", "write", name, throw=True)
    if not is_open_ticket(name):
        frappe.throw(_("Ticket {0} is closed; there is nothing to draft.").format(name), frappe.ValidationError)
    full_name = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
    store_suggestion(
        name,
        {
            "reply": paragraphs_html(text),
            "note": _("Drafted by {0} in TBO Copilot: read it, edit it, then send it.").format(full_name),
        },
        [],
    )
    return {"ticket": name, "saved_in": "the suggested-reply card", "sent_to_customer": False}


def update_task_status(
    caller, task: str, status: str, reason: str = "", hours_worked: float | None = None, notes: str = ""
) -> dict:
    from helpdesk.tasky.api import complete_task, hold_task, resume_task
    from helpdesk.tasky.api import update_task_status as set_status

    current = frappe.db.get_value("Task", task, "status")
    if current is None:
        frappe.throw(_("Task {0} not found").format(task), frappe.DoesNotExistError)
    if status == "On Hold":
        if not reason:
            frappe.throw(_("Say why the task is on hold (reason)."), frappe.ValidationError)
        hold_task(task, reason, notes)
    elif status == "Completed":
        # Completed may become Pending Review when the project wants approval
        complete_task(task, hours_worked, notes or None)
    else:
        if current == "On Hold":
            resume_task(task)
        if frappe.db.get_value("Task", task, "status") != status:
            set_status(task, status)
    return {"task": task, "status": frappe.db.get_value("Task", task, "status")}


def create_kb_article_draft(caller, title: str, content: str, ticket: str = "") -> dict:
    from helpdesk.api.knowledge_base import get_general_category

    values = {
        "doctype": "HD Article",
        "title": title,
        "content": md_to_html(content),
        "status": "Draft",
        "category": get_general_category(),
    }
    if ticket:
        name = ticket_name(ticket)
        frappe.has_permission("HD Ticket", "read", name, throw=True)
        values["source_ticket"] = name
    # as the caller, with their own create permission; never published here
    doc = frappe.get_doc(values).insert()
    return {"article": doc.name, "title": doc.title, "status": doc.status, "published": False}


TICKET = {"type": "string", "maxLength": 140, "description": "Ticket number, for example 0236"}

register_tool(
    "add_ticket_comment",
    kind=WRITE,
    description="Add an internal note to a ticket as me. Never shown to the customer.",
    handler=add_ticket_comment,
    properties={"ticket": TICKET, "text": {"type": "string", "maxLength": 20000}},
    required=["ticket", "text"],
)
register_tool(
    "draft_ticket_reply",
    kind=WRITE,
    description="Save a reply draft in the ticket's suggested-reply card for me to edit and send. Sends nothing.",
    handler=draft_ticket_reply,
    properties={"ticket": TICKET, "text": {"type": "string", "maxLength": 20000}},
    required=["ticket", "text"],
)
register_tool(
    "update_task_status",
    kind=WRITE,
    description="Change a task's status: Open, Working, On Hold (with a reason), Completed (hours_worked), Cancelled.",
    handler=update_task_status,
    properties={
        "task": {"type": "string", "maxLength": 140},
        "status": {"type": "string", "enum": TASK_STATUSES},
        "reason": {"type": "string", "enum": HOLD_REASONS, "description": "Why the task is on hold"},
        "hours_worked": {"type": "number"},
        "notes": {"type": "string", "maxLength": 2000},
    },
    required=["task", "status"],
)
register_tool(
    "create_kb_article_draft",
    kind=WRITE,
    description="Create a knowledge base article as a Draft (Markdown content), optionally from a ticket.",
    handler=create_kb_article_draft,
    properties={
        "title": {"type": "string", "maxLength": 200},
        "content": {"type": "string", "maxLength": 50000},
        "ticket": TICKET,
    },
    required=["title", "content"],
)
