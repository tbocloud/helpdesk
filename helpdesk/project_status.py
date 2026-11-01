"""Project status report: where each open project stands, in one table.

A coordinator used to write this by hand every week. Now a person (or the AI, from a
spoken or pasted update) writes one HD Project Status Update per project: its stage, who
it waits on and a few lines. Everything else on the report is worked out from the tasks,
so it cannot go out of date or be mistyped: tasks done and overdue, tasks on hold and
why, the next milestone, days waiting on the client, and where the written status
contradicts the work. Updates are never edited, so the history is the project's story.

Every Friday 17:00 the report goes to its recipients (`send_weekly_report`), and a project
whose update is more than a week old reminds its lead and coordinators through
helpdesk.follow_ups. See docs/project-status-report.md.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Max
from frappe.utils import (
    date_diff,
    formatdate,
    get_datetime,
    get_fullname,
    getdate,
    nowdate,
)

from helpdesk.api.work import ON_HOLD, PORTFOLIO_TASK_FIELDS, is_task_overdue
from helpdesk.tasky.permissions import (
    COORDINATOR_PROJECT_ROLE,
    get_coordinated_projects,
    get_led_projects,
    get_managed_projects,
    is_tasky_admin,
)

DOCTYPE = "HD Project Status Update"
SETTINGS = "HD Work Settings"
PAGE_PATH = "/project-status"
# a project is on the report while it is running or paused, not once it is closed
REPORT_PROJECT_STATUSES = ("Open", "On hold")
# an update older than this many days is stale and its lead is reminded
STALE_DAYS = 7
LIVE_STAGES = ("Live", "Support")
ON_HOLD_STAGE = "On hold"
NOTHING = "Nothing"
CLIENT = "Client"
# Task.hold_reason for a task held until the customer answers
CLIENT_HOLD_REASON = "Waiting on customer"
UPDATE_FIELDS = [
    "name",
    "project",
    "stage",
    "waiting_on",
    "waiting_since",
    "update_text",
    "next_step",
    "next_step_date",
    "written_by",
    "source",
    "creation",
]
PROJECT_FIELDS = [
    "name",
    "project_name",
    "customer",
    "project_lead",
    "custom_department",
    "status",
    "creation",
]
TASK_FIELDS = [*PORTFOLIO_TASK_FIELDS, "hold_reason", "hold_since", "modified"]
HISTORY_LIMIT = 50


def select_options(fieldname: str) -> list[str]:
    """The choices of one of HD Project Status Update's Select fields: the doctype is
    the single list of stages, waiting-on choices and sources."""
    options = frappe.get_meta(DOCTYPE).get_field(fieldname).options or ""
    return [option for option in options.split("\n") if option]


# --- who may write -------------------------------------------------------------


def writable_projects(user: str, projects: list[str]) -> set[str]:
    """Which of `projects` `user` may write updates for: the same people as
    `can_coordinate_project` (admins, the project's managers and lead, its coordinators),
    worked out for many projects at once."""
    if is_tasky_admin(user):
        return set(projects)
    allowed = (
        set(get_managed_projects(user))
        | set(get_led_projects(user))
        | set(get_coordinated_projects(user))
    )
    return allowed & set(projects)


# --- reading -------------------------------------------------------------------


def latest_updates(projects: list[str]) -> dict[str, dict]:
    """{project: its newest update}, in one query."""
    if not projects:
        return {}
    update = frappe.qb.DocType(DOCTYPE)
    newest = (
        frappe.qb.from_(update)
        .select(update.project, Max(update.creation).as_("at"))
        .where(update.project.isin(projects))
        .groupby(update.project)
        .as_("newest")
    )
    rows = (
        frappe.qb.from_(update)
        .join(newest)
        .on((update.project == newest.project) & (update.creation == newest.at))
        .select(*[update[field] for field in UPDATE_FIELDS])
        .orderby(update.creation)
        .run(as_dict=True)
    )
    return {row.project: row for row in rows}


def read_tasks(projects: list[str]) -> dict[str, list]:
    """{project: its tasks} without templates and cancelled work. Counts only, so every
    task is read whoever asks: a member's report is as true as a manager's."""
    if not projects:
        return {}
    tasks = frappe.qb.get_query(
        "Task",
        fields=TASK_FIELDS,
        filters={
            "project": ("in", projects),
            "status": ("not in", ("Template", "Cancelled")),
        },
    ).run(as_dict=True)
    by_project = {}
    for task in tasks:
        by_project.setdefault(task.project, []).append(task)
    return by_project


def task_facts(tasks: list, today) -> dict:
    """What the tasks say about a project: done and total, overdue, held (with the
    reason and for how long), the next open milestone and the last change."""
    facts = {
        "done": 0,
        "total": len(tasks),
        "overdue": 0,
        "held": [],
        "next_milestone": None,
        "last_activity": None,
    }
    for task in tasks:
        changed = get_datetime(task.modified).date()
        if not facts["last_activity"] or changed > facts["last_activity"]:
            facts["last_activity"] = changed
        if task.status == "Completed":
            facts["done"] += 1
            continue
        deadline = getdate(task.exp_end_date) if task.exp_end_date else None
        is_overdue = is_task_overdue(task, deadline, today)
        facts["overdue"] += is_overdue
        if task.status == ON_HOLD:
            facts["held"].append(
                {
                    "task": task.name,
                    "subject": task.subject,
                    "reason": task.hold_reason,
                    "since": task.hold_since,
                    "days": date_diff(today, task.hold_since) if task.hold_since else 0,
                }
            )
        milestone = facts["next_milestone"]
        if task.is_milestone and (
            not milestone
            or (deadline and (not milestone["due"] or deadline < milestone["due"]))
        ):
            facts["next_milestone"] = {
                "task": task.name,
                "subject": task.subject,
                "due": deadline,
                "is_overdue": is_overdue,
            }
    facts["held"].sort(key=lambda held: -held["days"])
    return facts


def client_wait_days(update: dict | None, held: list[dict], today) -> int | None:
    """Days the project has waited on the client: from the day the update says the wait
    began, else from its oldest task held for the client."""
    if update and update.waiting_on == CLIENT and update.waiting_since:
        return max(date_diff(today, update.waiting_since), 0)
    since = [
        h["since"] for h in held if h["reason"] == CLIENT_HOLD_REASON and h["since"]
    ]
    return max(date_diff(today, min(since)), 0) if since else None


def contradictions(
    project, update: dict | None, facts: dict, stage: str | None
) -> list[dict]:
    """Where what is written does not match the work. Each is {code, text}."""
    found = []
    if stage in LIVE_STAGES and facts["overdue"]:
        found.append(
            {
                "code": "live_with_overdue",
                "text": _("Marked {0}, but {1} task(s) are overdue").format(
                    stage, facts["overdue"]
                ),
            }
        )
    client_held = [h for h in facts["held"] if h["reason"] == CLIENT_HOLD_REASON]
    if update and update.waiting_on == NOTHING and client_held:
        found.append(
            {
                "code": "client_hold_not_waiting",
                "text": _(
                    "Waiting on nothing, but {0} task(s) are held for the client"
                ).format(len(client_held)),
            }
        )
    if update and project.status == "On hold" and update.stage != ON_HOLD_STAGE:
        found.append(
            {
                "code": "project_on_hold",
                "text": _("The project is on hold, but the stage says {0}").format(
                    update.stage
                ),
            }
        )
    return found


def update_age(update: dict | None, today) -> int | None:
    """Days since the project's last update; None when it never had one."""
    if not update:
        return None
    return date_diff(today, get_datetime(update.creation).date())


def needs_update(age: int | None, stage: str | None) -> bool:
    """Whether the update is old enough to be written again. A paused project has
    nothing new to say; a project that never had an update needs one."""
    return stage != ON_HOLD_STAGE and (age is None or age > STALE_DAYS)


def project_row(project, update: dict | None, facts: dict, today) -> dict:
    """One line of the report: the written status beside the facts and the flags."""
    stage = update.stage if update else None
    if not stage and project.status == "On hold":
        stage = ON_HOLD_STAGE
    age = update_age(update, today)
    flags = contradictions(project, update, facts, stage)
    return {
        "project": project.name,
        "project_name": project.project_name or project.name,
        "customer": project.customer,
        "lead": project.project_lead,
        "lead_name": get_fullname(project.project_lead)
        if project.project_lead
        else None,
        "department": project.custom_department,
        "project_status": project.status,
        "stage": stage,
        "waiting_on": update.waiting_on if update else None,
        "waiting_since": update.waiting_since if update else None,
        "update_text": update.update_text if update else None,
        "next_step": update.next_step if update else None,
        "next_step_date": update.next_step_date if update else None,
        "written_by": update.written_by if update else None,
        "written_by_name": get_fullname(update.written_by)
        if update and update.written_by
        else None,
        "update_age": age,
        "stale": needs_update(age, stage),
        "facts": {
            **facts,
            "client_wait_days": client_wait_days(update, facts["held"], today),
        },
        "flags": flags,
    }


def attention_key(row: dict) -> tuple:
    """Sort key: what needs a person first. Contradictions and overdue work, then
    stale or missing updates, then waiting on the client, then the rest; paused
    projects last."""
    waiting = row["waiting_on"] not in (None, NOTHING)
    return (
        row["stage"] == ON_HOLD_STAGE,
        not (row["flags"] or row["facts"]["overdue"]),
        not row["stale"],
        not waiting,
        -row["facts"]["overdue"],
        row["project_name"].lower(),
    )


def project_rows(user: str | None = None) -> list[dict]:
    """The report's rows for the projects `user` may see, most pressing first. Each row
    says whether `user` may write its update (`can_write`)."""
    user = user or frappe.session.user
    projects = frappe.get_list(
        "Project",
        filters={"status": ("in", REPORT_PROJECT_STATUSES)},
        fields=PROJECT_FIELDS,
        limit_page_length=0,
    )
    names = [p.name for p in projects]
    updates = latest_updates(names)
    tasks = read_tasks(names)
    today = getdate(nowdate())
    writable = writable_projects(user, names)
    rows = []
    for project in projects:
        row = project_row(
            project,
            updates.get(project.name),
            task_facts(tasks.get(project.name, []), today),
            today,
        )
        row["can_write"] = project.name in writable
        rows.append(row)
    return sorted(rows, key=attention_key)


def history(project: str) -> list[dict]:
    """A project's updates, newest first. The caller has checked `project` is readable."""
    update = frappe.qb.DocType(DOCTYPE)
    rows = (
        frappe.qb.from_(update)
        .select(*[update[field] for field in UPDATE_FIELDS])
        .where(update.project == project)
        .orderby(update.creation, order=frappe.qb.desc)
        .limit(HISTORY_LIMIT)
        .run(as_dict=True)
    )
    for row in rows:
        row["written_by_name"] = (
            get_fullname(row.written_by) if row.written_by else None
        )
    return rows


# --- writing -------------------------------------------------------------------


def save_updates(updates: list[dict]) -> list[str]:
    """Inserts one update per item as the signed-in user, who must be allowed to write
    each project's (the doctype's permission hook decides). All are saved or none."""
    names = []
    for item in updates:
        doc = frappe.get_doc({"doctype": DOCTYPE, **item})
        doc.insert()
        names.append(doc.name)
    return names


# --- the stale reminder --------------------------------------------------------


def stale_projects(today) -> list[dict]:
    """Open projects whose last update is more than STALE_DAYS old, counting from the
    project's start when it never had one: [{name, project_name, days}]."""
    projects = frappe.qb.get_query(
        "Project",
        fields=["name", "project_name", "creation"],
        filters={"status": "Open"},
    ).run(as_dict=True)
    updates = latest_updates([p.name for p in projects])
    stale = []
    for project in projects:
        update = updates.get(project.name)
        since = update.creation if update else project.creation
        days = date_diff(today, get_datetime(since).date())
        stage = update.stage if update else None
        if needs_update(days, stage):
            stale.append(
                {
                    "name": project.name,
                    "project_name": project.project_name or project.name,
                    "days": days,
                }
            )
    return stale


# --- the Friday report ---------------------------------------------------------


def report_recipients() -> list[str]:
    """Who gets the Friday report: the people listed in HD Work Settings, else the
    System Managers and the project coordinators. Enabled users only."""
    from helpdesk.work_reminders import enabled_users

    listed = [
        row.user for row in frappe.get_cached_doc(SETTINGS).status_report_recipients
    ]
    return enabled_users(listed or default_recipients())


def default_recipients() -> list[str]:
    roles = frappe.qb.DocType("Has Role")
    managers = (
        frappe.qb.from_(roles)
        .select(roles.parent)
        .where((roles.role == "System Manager") & (roles.parenttype == "User"))
        .run(pluck=True)
    )
    member = frappe.qb.DocType("Project User")
    coordinators = (
        frappe.qb.from_(member)
        .select(member.user)
        .where(
            (member.parenttype == "Project")
            & (member.custom_role == COORDINATOR_PROJECT_ROLE)
        )
        .run(pluck=True)
    )
    return [*managers, *coordinators]


def report_sections(rows: list[dict]) -> list[tuple[str, list[tuple[str, str]]]]:
    """The report as a message: what needs attention first, then the rest, one line per
    project with its number as in the table."""
    needs, rest = [], []
    for number, row in enumerate(rows, 1):
        line = (
            f"{number}. {summary_line(row)}",
            f"{PAGE_PATH}?project={row['project']}",
        )
        attention = row["flags"] or row["facts"]["overdue"] or row["stale"]
        (needs if attention else rest).append(line)
    return [
        (heading.format(len(lines)), lines)
        for heading, lines in (
            (_("Needs attention ({0})"), needs),
            (_("Other projects ({0})"), rest),
        )
        if lines
    ]


def summary_line(row: dict) -> str:
    parts = [row["project_name"], row["stage"] or _("No update yet")]
    if row["waiting_on"] not in (None, NOTHING):
        waited = row["facts"]["client_wait_days"]
        wait = _("waiting on {0}").format(row["waiting_on"])
        parts.append(
            f"{wait} {_('{0} day(s)').format(waited)}"
            if row["waiting_on"] == CLIENT and waited
            else wait
        )
    if row["facts"]["overdue"]:
        parts.append(_("{0} overdue").format(row["facts"]["overdue"]))
    parts.extend(flag["text"] for flag in row["flags"])
    if row["stale"]:
        parts.append(
            _("update is {0} days old").format(row["update_age"])
            if row["update_age"] is not None
            else _("no update yet")
        )
    text = " · ".join(parts)
    first = (row["update_text"] or "").strip().splitlines()
    return f"{text}: {first[0]}" if first else text


def send_weekly_report():
    """Friday 17:00 (hooks.py): the report to each recipient, by chat or email. As the
    scheduler runs as Administrator, every open project is on it."""
    from helpdesk.follow_ups import deliver_digest

    recipients = report_recipients()
    sections = report_sections(project_rows())
    if not recipients or not sections:
        return
    subject = _("Project status report · {0}").format(
        formatdate(nowdate(), "dd MMM yyyy")
    )
    for user in recipients:
        try:
            deliver_digest(user, subject, sections)
        except Exception:  # noqa: BLE001 - one person's message must not stop the rest
            frappe.log_error(title=f"Project status report not sent to {user}")
