# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""What the customer hears from Copilot.

Stages ("Received", "Working on it", "Resolved", ...) go to the customer's own
ticket on their site through hub_api and are noted on the hub ticket.
Explanations and questions never go out by themselves: they land in the
agent's suggested-reply card, and the agent sends them. The customer's
"it's fixed" or "still broken" comes back here, from the portal or from
their site.
"""

import json
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import escape_html, now_datetime

from helpdesk import client_api
from helpdesk.automation import automation_user
from helpdesk.copilot import runs
from helpdesk.copilot import settings as copilot_settings
from helpdesk.ticket_puller import _close_ticket, _log_once
from helpdesk.work_reminders import notify_users

COPILOT_NAME = "TBO Copilot"
# what "Resolved" says after an explanation, by root cause
RESOLUTION_TEXT = {
    "question": "We have replied with the answer.",
    "not_allowed_request": "We have explained why this cannot be done and what to do instead.",
    "customer_mistake": "We have explained what happened and how to correct it.",
}


class _Blank(dict):
    def __missing__(self, key):
        return ""


def render(stage: str, context: dict | None = None) -> str:
    template = copilot_settings.template_for(stage)
    try:
        return template.format_map(_Blank(context or {})).strip()
    except (ValueError, IndexError):
        return template.strip()  # an edited template with a stray brace still reaches the customer


def latest_run(ticket: str):
    name = frappe.db.get_value("HD Ticket", ticket, "custom_copilot_run")
    return frappe.get_doc("HDS Copilot Run", name) if name else None


# --- stages -----------------------------------------------------------------


def send_stage(run, stage: str, context: dict | None = None) -> bool:
    """Shows `stage` on the customer's ticket, once per run, stage and text.

    Connected sites with hub_api get an update row (the raiser is notified
    there); every delivery is noted on the hub ticket and mirrored in
    `custom_copilot_stage`, whether or not the site could be reached.
    """
    text = render(stage, context)
    if _last_stage(run) == (stage, text):
        return False
    number = frappe.db.count("HDS Copilot Event", {"run": run.name, "event_type": "stage"}) + 1
    hub_ref = f"{run.name}:{stage}:{number}"
    pushed = _push_stage(run, hub_ref, stage, text)
    note = _("Copilot → customer: <b>{0}</b> — {1}").format(escape_html(_(stage)), escape_html(text))
    if not pushed:
        note += " <i>({0})</i>".format(_("not delivered to the customer's site"))
    comment(run.ticket, note)
    runs.add_event(
        run, "stage", {"stage": stage, "message": text, "hub_ref": hub_ref, "pushed": pushed}, runs.SYSTEM
    )
    runs.update_ticket(run, stage=stage)
    return True


def _last_stage(run) -> tuple | None:
    rows = frappe.get_all(
        "HDS Copilot Event",
        filters={"run": run.name, "event_type": "stage"},
        fields=["payload"],
        order_by="creation desc",
        limit=1,
    )
    if not rows:
        return None
    payload = json.loads(rows[0].payload or "{}")
    return (payload.get("stage"), payload.get("message"))


def _push_stage(run, hub_ref: str, stage: str, text: str) -> bool:
    info = frappe.db.get_value(
        "HD Ticket", run.ticket, ["custom_qcs_connection", "custom_client_ticket"], as_dict=True
    )
    if not (info and info.custom_qcs_connection and info.custom_client_ticket):
        return False
    conn = frappe.get_doc("HDS Support Connection", info.custom_qcs_connection)
    if not client_api.supports(conn, client_api.HUB_API):
        return False  # an older client: the status push still reaches it
    try:
        client_api.hub_api(
            conn,
            "add_update",
            {
                "name": info.custom_client_ticket,
                "hub_ref": hub_ref,
                "stage": stage,
                "message": text,
                "author_name": COPILOT_NAME,
                "kind": "Stage",
            },
        )
        return True
    except Exception:
        _log_once(
            f"Copilot stage not delivered to the customer site for {run.ticket}",
            f"hds_copilot_stage_push:{run.ticket}",
        )
        return False


def comment(ticket: str, html: str):
    """An internal note on the hub ticket, credited to the automation user, without notifications."""
    doc = frappe.get_doc(
        {
            "doctype": "HD Ticket Comment",
            "reference_ticket": ticket,
            "commented_by": automation_user(),
            "content": html,
        }
    )
    doc.flags.skip_notifications = True
    doc.insert(ignore_permissions=True)
    return doc


# --- the worker's result ----------------------------------------------------


def note_diagnosis(run, investigation: dict):
    """The diagnosis as an internal note: category, confidence, summary, evidence, proposal."""
    parts = [
        "<b>{0}</b> ({1}, {2}%)".format(
            _("Copilot diagnosis"),
            escape_html(run.root_cause_category or ""),
            int(round((investigation.get("confidence") or 0) * 100)),
        ),
        "<div>{0}</div>".format(escape_html(investigation.get("summary") or "")),
    ]
    evidence = investigation.get("evidence") or []
    if evidence:
        items = "".join(
            "<li>{0}</li>".format(
                escape_html(" ".join(str(v) for v in item.values() if v))
            )
            for item in evidence
        )
        parts.append(f"<ul>{items}</ul>")
    proposal = investigation.get("proposal") or {}
    if proposal:
        parts.append(
            "<div><b>{0}:</b> {1}</div>".format(
                _("Proposal"),
                escape_html(" ".join(str(v) for v in proposal.values() if v)),
            )
        )
    comment(run.ticket, "".join(parts))


def draft_explanation(run, text: str):
    """The explanation or question goes to the agent's suggested-reply card; the agent reads and sends it."""
    from helpdesk.ai_suggestion import store_suggestion

    store_suggestion(
        run.ticket,
        {
            "reply": as_html(text),
            "note": _("From Copilot run {0} ({1}): read it, edit if needed, send.").format(
                run.name, run.root_cause_category
            ),
        },
        [{"kind": "investigation", "name": run.name, "title": _("Copilot run {0}").format(run.name)}],
    )


def as_html(text: str) -> str:
    paragraphs = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
    return "".join(
        "<p>{0}</p>".format(escape_html(p).replace("\n", "<br>")) for p in paragraphs
    )


# --- hand-over to a person --------------------------------------------------


def hand_over(run, reason: str) -> str | None:
    """A Task for the customer's developer in the customer's project (else the hand-over project).

    Without a project, or a developer, the Agent Managers are told instead.
    Returns the task name.
    """
    ticket = frappe.get_doc("HD Ticket", run.ticket)
    developer = (
        frappe.db.get_value("HD Customer", ticket.customer, "custom_assigned_developer")
        if ticket.customer
        else None
    )
    project = project_for(ticket.customer)
    task = _create_task(ticket, project, developer, run, reason) if project else None
    run.db_set({"task": task, "handed_over_to": developer}, update_modified=False)
    subject = _("Copilot handed ticket {0} over: {1}").format(ticket.name, reason[:120])
    if developer:
        notify_users([developer], "HD Ticket", ticket.name, subject, escalate=not task)
    else:
        runs.tell_people(run, subject)
    return task


def project_for(customer: str | None) -> str | None:
    project = (
        frappe.db.get_value(
            "Project", {"customer": customer, "status": "Open"}, "name", order_by="modified desc"
        )
        if customer
        else None
    )
    return project or copilot_settings.get_settings().handover_project


def _create_task(ticket, project: str, developer: str | None, run, reason: str) -> str | None:
    from helpdesk.api.work import create_task_from_ticket
    from helpdesk.tasky.api import _is_project_member

    assignee = developer if developer and _is_project_member(project, developer) else ""
    description = "<p>{0}</p><p>{1}</p>".format(
        escape_html(reason), _("Copilot run {0}; see the diagnosis on the ticket.").format(run.name)
    )
    with as_automation_user():
        if not frappe.has_permission("HD Ticket", "write", ticket.name):
            frappe.log_error(
                title=f"Copilot could not hand over {ticket.name}",
                message=f"{frappe.session.user} may not write the ticket; no task created",
            )
            return None
        result = create_task_from_ticket(
            ticket.name,
            project,
            task_name=_("Copilot hand-over: {0}").format(ticket.subject or ticket.name)[:140],
            description=description,
            assigned_to=assignee,
            pause_ticket=False,
        )
    task = result.get("task")
    return task.get("name") if isinstance(task, dict) else task


@contextmanager
def as_automation_user():
    """Runs a block as the hub's own user, so a customer's action can do what an agent would."""
    previous_user, previous_form = frappe.session.user, frappe.local.form_dict
    frappe.set_user(automation_user())
    try:
        yield
    finally:
        frappe.set_user(previous_user)
        frappe.local.form_dict = previous_form


# --- the agent's reply, the customer's reply ----------------------------------


def on_communication_insert(doc, method=None):
    """Communication after_insert: an agent's reply answers an Explaining run; a customer's
    message after a question starts a follow-up run."""
    if doc.reference_doctype != "HD Ticket" or not doc.reference_name:
        return
    if doc.communication_type != "Communication":
        return
    run = latest_run(doc.reference_name)
    if not run:
        return
    try:
        if doc.sent_or_received == "Sent":
            on_agent_reply(run)
        elif doc.sent_or_received == "Received":
            on_customer_message(run)
    except Exception:
        frappe.log_error(
            title=f"Copilot could not follow the conversation on {doc.reference_name}",
            message=frappe.get_traceback(),
        )


def on_agent_reply(run):
    if run.state != "Explaining":
        return
    waiting = run.root_cause_category == "unclear"
    run = runs.transition(run, "Answered", runs.SYSTEM, note="the agent sent the reply")
    if waiting:
        send_stage(run, "Waiting for you")
    else:
        send_stage(run, "Resolved", {"resolution": RESOLUTION_TEXT.get(run.root_cause_category, "")})


def on_customer_message(run):
    """The customer answered Copilot's question: a follow-up run picks the ticket up again."""
    stage = frappe.db.get_value("HD Ticket", run.ticket, "custom_copilot_stage")
    if run.state == "Answered" and stage == "Waiting for you":
        runs.start_run(run.ticket, kind="followup")


def on_customer_comment(ticket: str):
    """The same, for a comment relayed from the customer's site."""
    run = latest_run(ticket)
    if run:
        on_customer_message(run)


# --- confirm and reopen -------------------------------------------------------


def decide_resolution(ticket: str, confirmed: bool, note: str = "", actor: str = runs.CUSTOMER) -> dict:
    """Confirmed closes the ticket and the run; Reopened sends the ticket to a person."""
    doc = frappe.get_doc("HD Ticket", ticket)
    run = latest_run(ticket)
    note = (note or "").strip()[:1000]
    if confirmed:
        frappe.db.set_value("HD Ticket", ticket, "custom_customer_confirmation", "Confirmed", update_modified=False)
        if run:
            _close_run(run, actor, note)
        with as_automation_user():  # the hub closes on the customer's behalf; no feedback form
            _close_ticket(ticket)
        comment(ticket, _("The customer confirmed the fix.") + (f" <i>{escape_html(note)}</i>" if note else ""))
        return {"confirmation": "Confirmed", "run": run.name if run else None, "task": None}

    if not note:
        frappe.throw(_("Please say what is still wrong."))
    frappe.db.set_value("HD Ticket", ticket, "custom_customer_confirmation", "Reopened", update_modified=False)
    with as_automation_user():
        _reopen_ticket(doc)
    comment(ticket, _("The customer reopened the ticket:") + f" <i>{escape_html(note)}</i>")
    task = None
    if run:
        if (run.state, "Escalated") in runs.TRANSITIONS:
            run = runs.transition(run, "Escalated", actor, note=f"reopened: {note}"[:140])
        task = hand_over(run, _("The customer says it is still broken: {0}").format(note))
        send_stage(run, "With our team")
    return {"confirmation": "Reopened", "run": run.name if run else None, "task": task}


def _close_run(run, actor: str, note: str):
    if (run.state, "Closed") in runs.TRANSITIONS:
        runs.transition(run, "Closed", actor, note=f"confirmed: {note}"[:140])
    elif run.state in runs.CANCELLABLE:
        runs.transition(run, "Cancelled", runs.SYSTEM, note="the customer says the ticket is solved")


def _reopen_ticket(doc):
    if doc.status_category != "Resolved":
        return  # still open: nothing to reopen, the note is on the ticket
    doc.status = doc.ticket_reopen_status or doc.default_open_status
    doc.save(ignore_permissions=True)
