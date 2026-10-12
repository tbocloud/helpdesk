"""Calendar: Teams meetings, task due dates, holidays and leave in one place.

Everyone sees their own: meetings they scheduled or are invited to, the open
tasks assigned to them and their approved leave, plus the hub's holidays.
People who can see the overview (project managers, project leads, admins) can
switch to the whole team, which shows everyone's leave.
"""

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate

from helpdesk.api.content_board import user_full_names
from helpdesk.api.work import OPEN_TASK_FILTER, can_see_overview
from helpdesk.helpdesk.doctype.hd_meeting.hd_meeting import SCHEDULED
from helpdesk.utils import agent_only, assigned_to_filter
from helpdesk.work_calendar import holidays_between, leave_between, leave_today

MAX_RANGE_DAYS = 62
MAX_EVENTS = 500


@frappe.whitelist()
@agent_only
def get_calendar(start: str, end: str, team: int | str = 0) -> dict:
    """Meetings and due tasks between `start` and `end` (dates or datetimes)."""
    start_day, end_day = getdate(start), getdate(end)
    if end_day < start_day:
        frappe.throw(_("The end of the range is before its start."))
    if (end_day - start_day).days > MAX_RANGE_DAYS:
        frappe.throw(_("Pick a range of at most {0} days.").format(MAX_RANGE_DAYS))
    team = bool(frappe.utils.cint(team))
    if team and not can_see_overview():
        frappe.throw(
            _("Only project leads and managers can see the team's calendar."),
            frappe.PermissionError,
        )
    user = frappe.session.user
    return {
        "meetings": _meetings(start_day, end_day, None if team else user),
        "tasks": _tasks(start_day, end_day, None if team else user),
        "holidays": [
            {**row, "date": str(row["date"])}
            for row in holidays_between(start_day, end_day, weekly_off=False)
        ],
        "leave": _leave(start_day, end_day, None if team else user),
        "can_see_team": can_see_overview(),
    }


@frappe.whitelist()
@agent_only
def get_on_leave() -> dict:
    """{user: {to_date, half_day}} for everyone on leave today, for the assignee pickers
    and the team views. Every agent sees it, on purpose: whoever assigns work needs to
    know who is away. Only dates: the leave type stays in HD Leave, which only System
    Managers and Agent Managers can read."""
    return leave_today()


def _leave(start_day, end_day, user: str | None) -> list[dict]:
    """Approved leave in the range: the user's own, or everyone's for the team view."""
    rows = leave_between(start_day, end_day, [user] if user else None)
    names = user_full_names({row.user for row in rows})
    return [
        {
            "user": row.user,
            "full_name": names.get(row.user) or row.user,
            "from_date": str(row.from_date),
            "to_date": str(row.to_date),
            "half_day": bool(row.half_day),
        }
        for row in rows
    ]


def _meetings(start_day, end_day, user: str | None) -> list[dict]:
    Meeting = frappe.qb.DocType("HD Meeting")
    Attendee = frappe.qb.DocType("HD Meeting Attendee")
    query = (
        frappe.qb.from_(Meeting)
        .select(
            Meeting.name,
            Meeting.subject,
            Meeting.starts_on,
            Meeting.ends_on,
            Meeting.join_url,
            Meeting.reference_doctype,
            Meeting.reference_name,
            Meeting.customer,
            Meeting.scheduled_by,
        )
        .where(Meeting.status == SCHEDULED)
        .where(Meeting.starts_on < add_days(end_day, 1))
        .where(Meeting.ends_on >= start_day)
        .orderby(Meeting.starts_on)
        .limit(MAX_EVENTS)
    )
    if user:
        email = frappe.db.get_value("User", user, "email") or user
        invited = (
            frappe.qb.from_(Attendee)
            .select(Attendee.parent)
            .where(Attendee.parenttype == "HD Meeting")
            .where(Attendee.email == email.lower())
        )
        query = query.where((Meeting.scheduled_by == user) | Meeting.name.isin(invited))
    return [
        {
            **row,
            "starts_on": str(get_datetime(row.starts_on)),
            "ends_on": str(get_datetime(row.ends_on)),
        }
        for row in query.run(as_dict=True)
    ]


def _tasks(start_day, end_day, user: str | None) -> list[dict]:
    filters = {
        "status": OPEN_TASK_FILTER,
        "exp_end_date": ("between", [str(start_day), str(end_day)]),
    }
    if user:
        filters["name"] = assigned_to_filter("Task", user)
    # get_list: a team view still shows only the tasks the viewer may open
    tasks = frappe.get_list(
        "Task",
        filters=filters,
        fields=[
            "name",
            "subject",
            "project",
            "status",
            "exp_end_date",
            "is_key",
            "is_milestone",
        ],
        order_by="exp_end_date asc",
        limit_page_length=MAX_EVENTS,
    )
    projects = list({t.project for t in tasks if t.project})
    names = (
        dict(
            frappe.get_all(
                "Project",
                filters={"name": ("in", projects)},
                fields=["name", "project_name"],
                as_list=True,
            )
        )
        if projects
        else {}
    )
    return [
        {
            **task,
            "exp_end_date": str(task.exp_end_date),
            "project_name": names.get(task.project),
        }
        for task in tasks
    ]
