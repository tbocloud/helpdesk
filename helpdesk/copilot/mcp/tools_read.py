# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Read tools for TBO staff. Each calls the hub's own permission-checked API as the caller."""

import frappe
from frappe import _

from helpdesk.copilot.mcp.registry import READ, register_tool
from helpdesk.copilot.mcp.shape import assignees, clip, plain, ticket_name, untrusted

TICKET = {"ticket": {"type": "string", "maxLength": 140, "description": "Ticket number, for example 0236"}}
MESSAGES_KEPT, NOTES_KEPT = 15, 15
MAX_ITEMS = 50


def my_work(caller, limit: int = 30) -> dict:
    from helpdesk.api.work import get_my_work

    work = get_my_work()
    keep = (
        "kind", "name", "title", "project_name", "customer", "status", "priority",
        "deadline", "is_overdue", "is_key", "hd_ticket", "hold_reason", "risks",
    )
    return {
        "counts": work.get("counts"),
        "items": [{k: item.get(k) for k in keep if item.get(k) not in (None, "", [])} for item in work["items"][:limit]],
        "done_in_last_30_days": len(work.get("done") or []),
    }


def get_ticket(caller, ticket: str) -> dict:
    from helpdesk.helpdesk.doctype.hd_ticket.api import get_one

    name = ticket_name(ticket)
    doc = get_one(name)
    messages = sorted(doc.get("communications") or [], key=lambda m: str(m.get("creation")))
    notes = sorted(doc.get("comments") or [], key=lambda c: str(c.get("creation")))
    return {
        "ticket": doc.get("name"),
        "subject": doc.get("subject"),
        "status": doc.get("status"),
        "priority": doc.get("priority"),
        "ticket_type": doc.get("ticket_type"),
        "customer": doc.get("customer"),
        "raised_by": doc.get("raised_by"),
        "team": doc.get("agent_group"),
        "assigned_to": assignees(doc.get("_assign")),
        "opened": doc.get("opening_date") or doc.get("creation"),
        "response_by": doc.get("response_by"),
        "resolution_by": doc.get("resolution_by"),
        "customer_site_ticket": doc.get("custom_client_ticket"),
        "copilot": {
            "run": doc.get("custom_copilot_run"),
            "stage": doc.get("custom_copilot_stage"),
            "root_cause": doc.get("custom_root_cause"),
        },
        "description": untrusted(plain(doc.get("description"), 6000)),
        "messages": [
            {
                "direction": "from customer" if m.get("sent_or_received") == "Received" else "to customer",
                "from": m.get("sender"),
                "at": m.get("creation"),
                "text": untrusted(plain(m.get("content"), 2500)),
            }
            for m in messages[-MESSAGES_KEPT:]
        ],
        "internal_notes": [
            {"by": c.get("commented_by"), "at": c.get("creation"), "text": untrusted(plain(c.get("content"), 1500))}
            for c in notes[-NOTES_KEPT:]
        ],
        "older_left_out": {
            "messages": max(0, len(messages) - MESSAGES_KEPT),
            "internal_notes": max(0, len(notes) - NOTES_KEPT),
        },
        "triage": _triage(name),
        "suggested_reply": _suggestion(name),
    }


def _triage(ticket: str) -> dict | None:
    from helpdesk.api.support_hub import get_triage

    triage = get_triage(ticket)
    if triage.get("status") != "Completed":
        return {"status": triage.get("status") or "Not run"}
    return {
        key: triage.get(key)
        for key in ("status", "category", "priority", "complexity", "summary", "recommended_track")
    }


def _suggestion(ticket: str) -> dict | None:
    from helpdesk.api.ai_suggestion import get_suggestion

    suggestion = get_suggestion(ticket)
    if not suggestion or not suggestion.get("status"):
        return None
    return {
        "status": suggestion.get("status"),
        "reply": plain(suggestion.get("reply"), 3000),
        "note": suggestion.get("note"),
    }


def search_tickets(
    caller,
    query: str = "",
    status: str = "",
    priority: str = "",
    customer: str = "",
    assigned_to_me: bool = False,
    limit: int = 20,
) -> dict:
    filters = {}
    if status:
        filters["status"] = status
    if priority:
        filters["priority"] = priority
    if customer:
        filters["customer"] = customer
    if assigned_to_me:
        filters["_assign"] = ["like", f"%{frappe.session.user}%"]
    found = None
    if query:
        if len(query) < 2:
            frappe.throw(_("Search words need at least 2 characters."), frappe.ValidationError)
        found = _search_ticket_names(query)
        if not found:
            return {"tickets": [], "count": 0}
        filters["name"] = ["in", found]
    rows = frappe.get_list(
        "HD Ticket",
        filters=filters,
        fields=["name", "subject", "status", "priority", "customer", "modified", "_assign"],
        order_by="modified desc",
        limit_page_length=limit,
    )
    if found:
        rows.sort(key=lambda r: found.index(r.name))
    return {
        "tickets": [
            {
                "ticket": r.name,
                "subject": clip(r.subject, 200),
                "status": r.status,
                "priority": r.priority,
                "customer": r.customer,
                "assigned_to": assignees(r._assign),
                "modified": r.modified,
            }
            for r in rows
        ],
        "count": len(rows),
    }


def _search_ticket_names(query: str) -> list[str]:
    """Ticket names in the order the full-text search ranked them (their comments and emails count too)."""
    from helpdesk.api.search import search

    names = []
    for result in (search(query) or {}).get("results") or []:
        if result.get("doctype") == "HD Ticket":
            name = result.get("name")
        elif result.get("reference_ticket"):
            name = result.get("reference_ticket")
        elif result.get("reference_doctype") == "HD Ticket":
            name = result.get("reference_name")
        else:
            continue
        if name and name not in names:
            names.append(str(name))
    return names[:200]


def get_task(caller, task: str) -> dict:
    from helpdesk.tasky.api import get_task_detail

    detail = get_task_detail(task)
    keep = (
        "name", "subject", "status", "priority", "project", "category", "phase", "due_date", "exp_end_date",
        "assigned_to", "assignees", "assigned_by", "estimated_hours", "actual_hours", "hold_reason",
        "blocked", "depends_on_subject", "hd_ticket", "pull_requests",
    )
    result = {k: detail.get(k) for k in keep if detail.get(k) not in (None, "", [])}
    result["description"] = plain(detail.get("description"), 4000)
    return result


def list_projects(caller) -> dict:
    from helpdesk.tasky.api import get_projects

    keep = ("name", "project_name", "status", "customer", "percent_complete", "expected_end_date")
    projects = get_projects() or []
    return {"projects": [{k: p.get(k) for k in keep if p.get(k) not in (None, "")} for p in projects[:200]]}


def list_project_tasks(caller, project: str, status: str = "") -> dict:
    from helpdesk.tasky.api import get_kanban_tasks

    columns = (get_kanban_tasks(project) or {}).get("columns") or {}
    tasks = []
    for column, items in columns.items():
        if status and column != status:
            continue
        for t in items or []:
            tasks.append(
                {
                    "task": t.get("name"),
                    "subject": clip(t.get("subject"), 200),
                    "status": column,
                    "priority": t.get("priority"),
                    "due": t.get("exp_end_date"),
                    "assigned_to": assignees(t.get("_assign")) or t.get("assignees"),
                }
            )
    return {"project": project, "tasks": tasks[:100], "count": len(tasks)}


def search_knowledge_base(caller, query: str) -> dict:
    from helpdesk.api.article import search

    if len(query) < 2:
        frappe.throw(_("Search words need at least 2 characters."), frappe.ValidationError)
    return {
        "articles": [
            {
                "article": str(item.get("name") or "").split("#")[0],
                "title": item.get("subject"),
                "section": item.get("headings"),
                "excerpt": clip(item.get("description"), 400),
            }
            for item in (search(query) or [])[:10]
        ]
    }


def get_kb_article(caller, article: str) -> dict:
    from helpdesk.api.knowledge_base import get_article

    doc = get_article(article)
    return {
        "article": doc.get("name"),
        "title": doc.get("title"),
        "status": doc.get("status"),
        "category": doc.get("category_name"),
        "modified": doc.get("modified"),
        "content": plain(doc.get("content"), 20000),
    }


def get_fix_brief(caller, ticket: str) -> dict:
    from helpdesk.api.fix_brief import get_fix_brief as build

    brief = build(ticket_name(ticket))
    return {"filename": brief.get("filename"), "markdown": clip(brief.get("markdown"), 30000)}


def get_possible_duplicates(caller, ticket: str) -> dict:
    from helpdesk.api.duplicates import get_possible_duplicates as find

    return {"duplicates": find(ticket_name(ticket))}


def get_session_replay(caller, ticket: str) -> dict:
    from helpdesk.api.session_replay import get_session_replay as replay

    data = replay(ticket_name(ticket))
    if not data.get("available"):
        return {"available": False}
    return {
        "available": True,
        "summary": clip(data.get("summary"), 4000),
        "timeline": clip(data.get("timeline"), 12000),
    }


def get_calendar(caller, start: str, end: str, team: bool = False) -> dict:
    from helpdesk.api.calendar import get_calendar as calendar

    data = calendar(start, end, 1 if team else 0)
    return {"meetings": (data.get("meetings") or [])[:100], "tasks": (data.get("tasks") or [])[:100]}


def get_copilot_run(caller, ticket: str) -> dict:
    from helpdesk.api.copilot import get_run

    return get_run(ticket_name(ticket))


register_tool(
    "my_work",
    kind=READ,
    description="My open tickets and tasks, overdue first: status, priority, deadline, risks.",
    handler=my_work,
    properties={"limit": {"type": "integer", "minimum": 1, "maximum": MAX_ITEMS}},
)
register_tool(
    "get_ticket",
    kind=READ,
    description="One ticket: details, customer conversation, internal notes, AI triage and suggested reply.",
    handler=get_ticket,
    properties=TICKET,
    required=["ticket"],
)
register_tool(
    "search_tickets",
    kind=READ,
    description="Find tickets by words and/or status, priority, customer, assigned to me; newest first.",
    handler=search_tickets,
    properties={
        "query": {"type": "string", "maxLength": 200, "description": "Words to find in tickets, their emails and notes"},
        "status": {"type": "string", "maxLength": 60},
        "priority": {"type": "string", "maxLength": 60},
        "customer": {"type": "string", "maxLength": 140},
        "assigned_to_me": {"type": "boolean"},
        "limit": {"type": "integer", "minimum": 1, "maximum": MAX_ITEMS},
    },
)
register_tool(
    "get_task",
    kind=READ,
    description="One task: status, project, assignees, due date, hours, hold, linked ticket and pull requests.",
    handler=get_task,
    properties={"task": {"type": "string", "maxLength": 140, "description": "Task name, for example TASK-2026-00012"}},
    required=["task"],
)
register_tool(
    "list_projects",
    kind=READ,
    description="Projects I can see, with status and customer.",
    handler=list_projects,
)
register_tool(
    "list_project_tasks",
    kind=READ,
    description="Tasks of one project, optionally one status (Open, Working, Pending Review, On Hold, Completed).",
    handler=list_project_tasks,
    properties={
        "project": {"type": "string", "maxLength": 140},
        "status": {"type": "string", "maxLength": 60},
    },
    required=["project"],
)
register_tool(
    "search_knowledge_base",
    kind=READ,
    description="Search published knowledge base articles; up to 5 matches with a short excerpt.",
    handler=search_knowledge_base,
    properties={"query": {"type": "string", "maxLength": 200}},
    required=["query"],
)
register_tool(
    "get_kb_article",
    kind=READ,
    description="One knowledge base article as plain text.",
    handler=get_kb_article,
    properties={"article": {"type": "string", "maxLength": 140}},
    required=["article"],
)
register_tool(
    "get_fix_brief",
    kind=READ,
    description="The developer fix brief of a ticket in Markdown: problem, evidence, what done looks like.",
    handler=get_fix_brief,
    properties=TICKET,
    required=["ticket"],
)
register_tool(
    "get_possible_duplicates",
    kind=READ,
    description="Open tickets that look like duplicates of this ticket (up to 3).",
    handler=get_possible_duplicates,
    properties=TICKET,
    required=["ticket"],
)
register_tool(
    "get_session_replay",
    kind=READ,
    description="What the customer did before raising the ticket: replay summary and timeline.",
    handler=get_session_replay,
    properties=TICKET,
    required=["ticket"],
)
register_tool(
    "get_calendar",
    kind=READ,
    description="My meetings and due tasks between two dates (YYYY-MM-DD); team view for leads.",
    handler=get_calendar,
    properties={
        "start": {"type": "string", "maxLength": 30},
        "end": {"type": "string", "maxLength": 30},
        "team": {"type": "boolean"},
    },
    required=["start", "end"],
)
register_tool(
    "get_copilot_run",
    kind=READ,
    description="Copilot's run on a ticket: state, root cause, stage the customer sees, evidence, events.",
    handler=get_copilot_run,
    properties=TICKET,
    required=["ticket"],
)
