"""Teams meetings scheduled from a ticket or a task (see helpdesk.teams_meetings)."""

import json

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, now_datetime

from helpdesk import teams_meetings
from helpdesk.helpdesk.doctype.hd_meeting.hd_meeting import (
    CANCELLED,
    REFERENCE_DOCTYPES,
    SCHEDULED,
)
from helpdesk.utils import agent_only, is_chat_placeholder_email
from helpdesk.work_reminders import _assignees

PAST_MEETINGS = 5
MAX_SUGGESTIONS = 10
# addresses that can never receive an invitation (RFC 2606 test names, chat stand-ins)
UNDELIVERABLE_DOMAINS = ("example.com", "example.org", "example.net", "localhost")
UNDELIVERABLE_SUFFIXES = (".test", ".invalid", ".localhost")
MIN_DURATION = 5
MAX_DURATION = 8 * 60


@frappe.whitelist()
@agent_only
def get_meetings(reference_doctype: str, reference_name: str | int) -> dict:
    """Upcoming meetings first, then the last few past or cancelled ones."""
    reference = _reference(reference_doctype, reference_name)
    rows = frappe.get_all(
        "HD Meeting",
        filters={
            "reference_doctype": reference.doctype,
            "reference_name": str(reference.name),
        },
        fields=[
            "name",
            "subject",
            "starts_on",
            "ends_on",
            "status",
            "join_url",
            "organizer",
            "scheduled_by",
        ],
        order_by="starts_on asc",
    )
    now = now_datetime()
    upcoming = [
        r for r in rows if r.status == SCHEDULED and get_datetime(r.ends_on) >= now
    ]
    earlier = [r for r in rows if r not in upcoming][-PAST_MEETINGS:][::-1]
    for row in upcoming + earlier:
        replies = frappe.get_all(
            "HD Meeting Attendee",
            filters={"parent": row.name, "parenttype": "HD Meeting"},
            pluck="response",
        )
        row["attendee_count"] = len(replies)
        row["accepted"] = replies.count("Accepted")
        row["declined"] = replies.count("Declined")
        row["can_cancel"] = row.status == SCHEDULED and _can_change(row)
    return {
        "enabled": teams_meetings.is_enabled(),
        "upcoming": upcoming,
        "earlier": earlier,
    }


@frappe.whitelist()
@agent_only
def meetings_enabled() -> bool:
    """Whether to offer Schedule meeting (the ticket header asks before showing its button)."""
    return teams_meetings.is_enabled()


@frappe.whitelist()
@agent_only
def get_meeting_defaults(reference_doctype: str, reference_name: str | int) -> dict:
    """Subject, attendees and length to start the Schedule meeting dialog with."""
    reference = _reference(reference_doctype, reference_name)
    settings = teams_meetings.get_settings()
    attendees = _default_attendees(reference)
    invited = {a["email"] for a in attendees}
    return {
        "subject": _default_subject(reference),
        "attendees": attendees,
        "suggestions": [
            s for s in _suggestions(reference) if s["email"] not in invited
        ][:MAX_SUGGESTIONS],
        "duration": cint(settings.default_duration) or 30,
        "organizer": teams_meetings.organizer_mailbox(),
    }


@frappe.whitelist(methods=["POST"])
@agent_only
def schedule_meeting(
    reference_doctype: str,
    reference_name: str | int,
    subject: str,
    starts_on: str,
    duration: int | str,
    attendees: str | list,
    agenda: str | None = None,
) -> dict:
    """Creates the Teams meeting in Outlook (invitations go out) and records it."""
    start = get_datetime(starts_on)
    if start < add_to_date(now_datetime(), minutes=-5):
        frappe.throw(_("Pick a time in the future."))
    return _create_meeting(
        reference_doctype, reference_name, subject, start, duration, attendees, agenda
    )


@frappe.whitelist(methods=["POST"])
@agent_only
def start_meeting_now(
    reference_doctype: str,
    reference_name: str | int,
    attendees: str | list,
    duration: int | str = 30,
    subject: str | None = None,
) -> dict:
    """Meet now: a Teams meeting from this minute, so the link can go to the customer straight away."""
    start = now_datetime().replace(second=0, microsecond=0)
    return _create_meeting(
        reference_doctype,
        reference_name,
        subject or "",
        start,
        duration,
        attendees,
        None,
    )


def _create_meeting(
    reference_doctype, reference_name, subject, start, duration, attendees, agenda
) -> dict:
    if not teams_meetings.is_enabled():
        frappe.throw(
            _(
                "Teams meetings are not set up. Ask an admin to fill in HD Meeting Settings."
            )
        )
    reference = _reference(reference_doctype, reference_name)
    minutes = cint(duration)
    if not MIN_DURATION <= minutes <= MAX_DURATION:
        frappe.throw(
            _("A meeting is {0} to {1} minutes long.").format(
                MIN_DURATION, MAX_DURATION
            )
        )

    meeting = frappe.get_doc(
        {
            "doctype": "HD Meeting",
            "subject": (subject or "").strip() or _default_subject(reference),
            "starts_on": start,
            "ends_on": add_to_date(start, minutes=minutes),
            "reference_doctype": reference.doctype,
            "reference_name": str(reference.name),
            "organizer": teams_meetings.organizer_mailbox(),
            "scheduled_by": frappe.session.user,
            "agenda": (agenda or "").strip(),
            "attendees": [
                {"email": a.get("email"), "full_name": a.get("full_name")}
                for a in _parse_attendees(attendees)
            ],
        }
    )
    meeting.insert(ignore_permissions=True)
    try:
        meeting.schedule_in_teams()
    except teams_meetings.GraphError as e:
        frappe.throw(str(e), title=_("Meeting not created"))
    meeting.save(ignore_permissions=True)
    meeting.note_on_reference(
        _("Teams meeting scheduled for {0}: {1}. Join: {2}").format(
            meeting.when_label(), meeting.subject, meeting.join_url
        )
    )
    return {"name": meeting.name, "join_url": meeting.join_url}


@frappe.whitelist(methods=["POST"])
@agent_only
def cancel_meeting(meeting: str, reason: str | None = None) -> dict:
    """Cancels in Outlook (attendees are told) and marks the meeting cancelled."""
    doc = frappe.get_doc("HD Meeting", meeting)
    _reference(doc.reference_doctype, doc.reference_name)
    if not _can_change(doc):
        frappe.throw(
            _(
                "Only the person who scheduled it or an Agent Manager can cancel this meeting."
            ),
            frappe.PermissionError,
        )
    reason = (reason or "").strip()
    try:
        doc.cancel_in_teams(reason)
    except teams_meetings.GraphError as e:
        frappe.throw(str(e), title=_("Meeting not cancelled"))
    doc.save(ignore_permissions=True)
    doc.note_on_reference(
        _("Teams meeting on {0} cancelled: {1}").format(doc.when_label(), doc.subject)
        + (f" ({reason})" if reason else "")
    )
    return {"name": doc.name, "status": CANCELLED}


@frappe.whitelist(methods=["POST"])
def test_connection() -> dict:
    """HD Meeting Settings button: proves the app can reach the organizer's calendar."""
    # only_for is skipped in tests, so check the role directly
    if "System Manager" not in frappe.get_roles():
        frappe.throw(
            _("Only System Managers can test the connection."), frappe.PermissionError
        )
    settings = teams_meetings.get_settings()
    if not settings.connected_app:
        frappe.throw(_("Choose the Microsoft App first and save."))
    # a test right after granting a permission must not reuse the old sign-in
    teams_meetings.forget_token()
    try:
        return teams_meetings.check_connection(teams_meetings.organizer_mailbox())
    except teams_meetings.GraphError as e:
        frappe.throw(str(e), title=_("Connection failed"))


def _reference(doctype: str, name):
    if doctype not in REFERENCE_DOCTYPES:
        frappe.throw(_("Meetings can be scheduled from tickets and tasks only."))
    doc = frappe.get_doc(doctype, str(name))
    doc.check_permission("read")
    return doc


def _can_change(meeting) -> bool:
    user = frappe.session.user
    return meeting.scheduled_by == user or bool(
        {"Agent Manager", "System Manager"} & set(frappe.get_roles(user))
    )


def _default_subject(reference) -> str:
    if reference.doctype == "HD Ticket":
        return _("Ticket #{0}: {1}").format(reference.name, reference.subject)
    return reference.subject


def _default_attendees(reference) -> list[dict]:
    """The customer who raised the ticket (and its contact's email), the people
    assigned to it, and me; addresses that can't receive an invitation are left out."""
    emails = []
    if reference.doctype == "HD Ticket":
        emails.append(reference.raised_by)
        if reference.get("contact"):
            emails.append(frappe.db.get_value("Contact", reference.contact, "email_id"))
    emails += _assignees(reference.get("_assign"))
    emails.append(frappe.session.user)
    attendees, seen = [], set()
    for value in emails:
        email = (frappe.db.get_value("User", value, "email") or value or "").lower()
        if not email or email in seen or not is_deliverable(email):
            continue
        seen.add(email)
        attendees.append(
            {
                "email": email,
                "full_name": frappe.db.get_value("User", {"email": email}, "full_name")
                or "",
            }
        )
    return attendees


def _suggestions(reference) -> list[dict]:
    """People to add with one click: a task's project team first (internal calls),
    then the customer's contacts."""
    people = _project_team(reference) if reference.doctype == "Task" else []
    seen = {p["email"] for p in people}
    return people + [c for c in _customer_contacts(reference) if c["email"] not in seen]


def _project_team(task) -> list[dict]:
    """The project lead and members of the task's project, as active users."""
    if not task.get("project"):
        return []
    users = [frappe.db.get_value("Project", task.project, "project_lead")]
    users += frappe.get_all(
        "Project User",
        filters={"parenttype": "Project", "parent": task.project},
        pluck="user",
    )
    rows = frappe.get_all(
        "User",
        filters={"name": ("in", [u for u in users if u]), "enabled": 1},
        fields=["email", "full_name"],
    )
    team, seen = [], set()
    for row in sorted(rows, key=lambda r: (r.full_name or r.email or "").lower()):
        email = (row.email or "").lower()
        if (
            email
            and email not in seen
            and email != _my_email()
            and is_deliverable(email)
        ):
            seen.add(email)
            team.append({"email": email, "full_name": row.full_name or ""})
    return team


def _my_email() -> str:
    return (frappe.db.get_value("User", frappe.session.user, "email") or "").lower()


def _customer_contacts(reference) -> list[dict]:
    """The customer's contacts with a usable email, primary first, to add with one click."""
    customer = reference.get("customer")
    if reference.doctype == "Task" and reference.get("project"):
        customer = frappe.db.get_value("Project", reference.project, "customer")
    if not customer or not frappe.db.exists("HD Customer", customer):
        return []
    doc = frappe.get_doc("HD Customer", customer)
    names = [row.contact_name for row in doc.contacts if row.contact_name]
    rows = (
        frappe.get_all(
            "Contact",
            filters={"name": ("in", names), "email_id": ("is", "set")},
            fields=["name", "full_name", "email_id"],
        )
        if names
        else []
    )
    rows.sort(
        key=lambda r: (r.name != doc.primary_contact, (r.full_name or "").lower())
    )
    contacts, seen = [], set()
    for row in rows:
        email = (row.email_id or "").strip().lower()
        if email and email not in seen and is_deliverable(email):
            seen.add(email)
            contacts.append({"email": email, "full_name": row.full_name or ""})
    return contacts


def is_deliverable(email: str) -> bool:
    """False for chat stand-ins and reserved test domains: an invitation there only bounces."""
    domain = email.rpartition("@")[2].lower()
    if not domain or is_chat_placeholder_email(email):
        return False
    return domain not in UNDELIVERABLE_DOMAINS and not domain.endswith(
        UNDELIVERABLE_SUFFIXES
    )


def _parse_attendees(attendees) -> list[dict]:
    if isinstance(attendees, str):
        try:
            attendees = json.loads(attendees)
        except ValueError:
            attendees = [{"email": e} for e in attendees.replace(";", ",").split(",")]
    rows = []
    for item in attendees or []:
        if isinstance(item, str):
            item = {"email": item}
        if isinstance(item, dict) and (item.get("email") or "").strip():
            rows.append(item)
    return rows
