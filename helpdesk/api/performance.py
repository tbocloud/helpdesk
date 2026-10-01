"""Employee performance: hours logged, task progress and content delivery.

Every query here reads across doctypes the viewer may not have permission on,
so access is decided once, in `visible_employees`, and nothing leaves this
module for an employee outside that set:

- System Managers, Agent Managers and HR see everyone
- Project Managers see the members of the projects they manage, and themselves
- everyone else sees only themselves
"""

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import add_days, date_diff, flt, get_datetime, getdate, nowdate
from pypika import functions as fn

from helpdesk.tasky.permissions import get_managed_projects, is_tasky_admin

TEAM_ROLES = ("System Manager", "Agent Manager", "HR Manager", "HR User")
OPEN_TASK = ("Open", "Working", "Pending Review", "Overdue")
CLOSED_POST = ("Published", "Cancelled")
CONTENT_ROLES = ("writer", "designer", "marketer")
TOP_ACTIVITIES = 5
MAX_RANGE_DAYS = 366


# ------------------------------------------------------------------ scope --


def sees_everyone(user: str) -> bool:
    return is_tasky_admin(user) or bool(set(TEAM_ROLES) & set(frappe.get_roles(user)))


def visible_employees(user: str | None = None) -> list[dict]:
    """The active employees (with a login) this user may see."""
    user = user or frappe.session.user
    Employee = frappe.qb.DocType("Employee")
    query = (
        frappe.qb.from_(Employee)
        .select(
            Employee.name.as_("employee"),
            Employee.employee_name,
            Employee.user_id,
            Employee.department,
            Employee.designation,
            Employee.image,
        )
        .where(Employee.status == "Active")
        .where(Employee.user_id.isnotnull() & (Employee.user_id != ""))
        .orderby(Employee.employee_name)
    )
    if not sees_everyone(user):
        users = {user}
        projects = get_managed_projects(user)
        if projects:
            users |= set(
                frappe.get_all(
                    "Project User",
                    filters={"parenttype": "Project", "parent": ("in", projects)},
                    pluck="user",
                )
            )
        query = query.where(Employee.user_id.isin(list(users)))
    return query.run(as_dict=True)


def resolve_scope(employee: str | None, department: str | None) -> list[dict]:
    people = visible_employees()
    if employee:
        people = [p for p in people if p.employee == employee]
        if not people:
            frappe.throw(
                _("You can't view this employee's performance."), frappe.PermissionError
            )
    elif department:
        people = [p for p in people if p.department == department]
    return people


def check_range(from_date: str, to_date: str):
    start, end = getdate(from_date), getdate(to_date)
    if end < start:
        frappe.throw(_("The end date is before the start date."))
    if date_diff(end, start) > MAX_RANGE_DAYS:
        frappe.throw(_("Pick a period of up to a year."))
    return start, end


# ------------------------------------------------------------------- data --


def logged_hours(employees: list[str], start, end) -> list[dict]:
    """One row per employee, day, activity and project; drafts count, cancelled sheets don't."""
    if not employees:
        return []
    Detail = frappe.qb.DocType("Timesheet Detail")
    Sheet = frappe.qb.DocType("Timesheet")
    day = fn.Date(Detail.from_time)
    return (
        frappe.qb.from_(Detail)
        .join(Sheet)
        .on(Sheet.name == Detail.parent)
        .select(
            Sheet.employee,
            day.as_("day"),
            Detail.activity_type,
            Detail.project,
            Detail.task,
            Sum(Detail.hours).as_("hours"),
        )
        .where(Sheet.docstatus < 2)
        .where(Sheet.employee.isin(employees))
        .where(Detail.from_time >= f"{start} 00:00:00")
        .where(Detail.from_time <= f"{end} 23:59:59")
        .groupby(Sheet.employee, day, Detail.activity_type, Detail.project, Detail.task)
        .run(as_dict=True)
    )


def relevant_tasks(start, end) -> list[dict]:
    """Tasks due or completed in the period, plus everything open and already late."""
    Task = frappe.qb.DocType("Task")
    today = getdate(nowdate())
    fields = [
        Task.name,
        Task.subject,
        Task.project,
        Task.status,
        Task.exp_end_date,
        Task.completed_on,
        Task.expected_time,
        Task.actual_time,
        Task._assign,
    ]
    if frappe.get_meta("Task").has_field("custom_assigned_employee"):
        fields.append(Task.custom_assigned_employee)
    due = Task.exp_end_date[start:end]
    done = Task.completed_on[start:end]
    late = Task.status.isin(OPEN_TASK) & (Task.exp_end_date < today)
    return (
        frappe.qb.from_(Task)
        .select(*fields)
        .where(Task.status != "Template")
        .where(due | done | late)
        .run(as_dict=True)
    )


def tasks_for(tasks: list[dict], user: str, employee: str) -> list[dict]:
    mine = []
    for task in tasks:
        try:
            assignees = json.loads(task._assign or "[]")
        except (TypeError, ValueError):
            assignees = []
        if user in assignees or task.get("custom_assigned_employee") == employee:
            mine.append(task)
    return mine


def task_metrics(tasks: list[dict], start, end) -> dict:
    today = getdate(nowdate())
    completed = [
        t
        for t in tasks
        if t.status == "Completed"
        and t.completed_on
        and start <= getdate(t.completed_on) <= end
    ]
    on_time = [
        t
        for t in completed
        if not t.exp_end_date or getdate(t.completed_on) <= getdate(t.exp_end_date)
    ]
    overdue = [
        t
        for t in tasks
        if t.status in OPEN_TASK and t.exp_end_date and getdate(t.exp_end_date) < today
    ]
    due = [
        t for t in tasks if t.exp_end_date and start <= getdate(t.exp_end_date) <= end
    ]
    return {
        "tasks_due": len(due),
        "tasks_completed": len(completed),
        "tasks_on_time": len(on_time),
        "tasks_overdue": len(overdue),
        "estimated_hours": round(sum(flt(t.expected_time) for t in completed), 1),
    }


def relevant_posts(start, end) -> list[dict]:
    Post = frappe.qb.DocType("HD Content Post")
    return (
        frappe.qb.from_(Post)
        .select(
            Post.name,
            Post.title,
            Post.customer,
            Post.status,
            Post.publish_on,
            Post.published_on,
            Post.writer,
            Post.designer,
            Post.marketer,
        )
        .where(Post.publish_on[f"{start} 00:00:00":f"{end} 23:59:59"])
        .where(Post.status != "Cancelled")
        .run(as_dict=True)
    )


def post_metrics(posts: list[dict], user: str) -> dict:
    now = get_datetime()
    mine = [p for p in posts if user in (p.writer, p.designer, p.marketer)]
    published = [p for p in mine if p.status == "Published"]
    on_time = [
        p
        for p in published
        if p.published_on and getdate(p.published_on) <= getdate(p.publish_on)
    ]
    missed = [
        p
        for p in mine
        if p.status not in CLOSED_POST and get_datetime(p.publish_on) < now
    ]
    return {
        "posts": len(mine),
        "posts_published": len(published),
        "posts_on_time": len(on_time),
        "posts_missed": len(missed),
    }


def expected_hours(employee: str, start, end, hours_per_day: float) -> float:
    """Working days in the period (the employee's holiday list, else Mon-Fri) x a working day."""
    end = min(end, getdate(nowdate()))
    if end < start:
        return 0
    days = date_diff(end, start) + 1
    try:
        from hrms.hr.utils import get_holidays_for_employee

        holidays = len(
            get_holidays_for_employee(employee, start, end, raise_exception=False)
        )
    except ImportError:
        holidays = sum(
            1 for i in range(days) if add_days(start, i).weekday() >= 5  # Sat, Sun
        )
    return round(max(days - holidays, 0) * hours_per_day, 1)


def hours_per_day() -> float:
    try:
        return (
            flt(frappe.db.get_single_value("HR Settings", "standard_working_hours"))
            or 8
        )
    except Exception:  # noqa: BLE001 - HRMS not installed
        return 8


def pct(part, whole) -> float | None:
    return round(part / whole * 100) if whole else None


def project_names(names) -> dict:
    names = [n for n in names if n]
    if not names:
        return {}
    return dict(
        frappe.get_all(
            "Project",
            filters={"name": ("in", names)},
            fields=["name", "project_name"],
            as_list=True,
        )
    )


# ------------------------------------------------------------- endpoints --


@frappe.whitelist()
def get_scope():
    """Who the viewer can see, for the page's pickers."""
    people = visible_employees()
    me = frappe.db.get_value(
        "Employee", {"user_id": frappe.session.user, "status": "Active"}, "name"
    )
    return {
        "sees_team": len(people) > 1 or sees_everyone(frappe.session.user),
        "me": me,
        "employees": people,
        "departments": sorted({p.department for p in people if p.department}),
    }


@frappe.whitelist()
def get_team_performance(
    from_date: str, to_date: str, department: str | None = None
) -> dict:
    start, end = check_range(from_date, to_date)
    people = resolve_scope(None, department)
    by_id = {p.employee: p for p in people}
    rows_hours = logged_hours(list(by_id), start, end)
    tasks = relevant_tasks(start, end)
    posts = relevant_posts(start, end)
    per_day = hours_per_day()

    hours = defaultdict(float)
    active_days = defaultdict(set)
    activity_by_person = defaultdict(lambda: defaultdict(float))
    activity_total = defaultdict(float)
    daily = defaultdict(float)
    for r in rows_hours:
        h = flt(r.hours)
        activity = r.activity_type or _("Not set")
        hours[r.employee] += h
        active_days[r.employee].add(str(r.day))
        activity_by_person[r.employee][activity] += h
        activity_total[activity] += h
        daily[str(r.day)] += h

    top = [a for a, _h in sorted(activity_total.items(), key=lambda kv: -kv[1])][
        :TOP_ACTIVITIES
    ]
    rows = []
    for p in people:
        expected = expected_hours(p.employee, start, end, per_day)
        mix = activity_by_person[p.employee]
        row = {
            **p,
            "hours": round(hours[p.employee], 1),
            "expected_hours": expected,
            "utilisation": pct(hours[p.employee], expected),
            "active_days": len(active_days[p.employee]),
            "activities": {a: round(mix.get(a, 0), 1) for a in top}
            | {"Other": round(sum(v for a, v in mix.items() if a not in top), 1)},
            **task_metrics(tasks_for(tasks, p.user_id, p.employee), start, end),
            **post_metrics(posts, p.user_id),
        }
        row["on_time_pct"] = pct(row["tasks_on_time"], row["tasks_completed"])
        row["posts_on_time_pct"] = pct(row["posts_on_time"], row["posts_published"])
        rows.append(row)
    # people who don't log time or own work (HR, accounts...) would only drag the team down
    idle = [
        r
        for r in rows
        if not (
            r["hours"]
            or r["tasks_due"]
            or r["tasks_completed"]
            or r["posts"]
            or r["tasks_overdue"]
        )
    ]
    rows = [r for r in rows if r not in idle]
    rows.sort(key=lambda r: -r["hours"])

    total = lambda key: sum(r[key] for r in rows)  # noqa: E731
    return {
        "from_date": str(start),
        "to_date": str(end),
        "hours_per_day": per_day,
        "activities": top,
        "rows": rows,
        "daily": [
            {
                "day": str(add_days(start, i)),
                "hours": round(daily.get(str(add_days(start, i)), 0), 1),
            }
            for i in range(date_diff(end, start) + 1)
        ],
        "totals": {
            "people": len(rows),
            "idle_people": len(idle),
            "hours": round(total("hours"), 1),
            "expected_hours": round(total("expected_hours"), 1),
            "utilisation": pct(total("hours"), total("expected_hours")),
            "tasks_completed": total("tasks_completed"),
            "tasks_on_time": total("tasks_on_time"),
            "on_time_pct": pct(total("tasks_on_time"), total("tasks_completed")),
            "tasks_overdue": total("tasks_overdue"),
            "posts_published": total("posts_published"),
            "posts_missed": total("posts_missed"),
        },
    }


@frappe.whitelist()
def get_employee_performance(employee: str, from_date: str, to_date: str) -> dict:
    start, end = check_range(from_date, to_date)
    [person] = resolve_scope(employee, None)
    per_day = hours_per_day()
    rows_hours = logged_hours([person.employee], start, end)
    tasks = tasks_for(relevant_tasks(start, end), person.user_id, person.employee)
    posts = relevant_posts(start, end)

    daily = defaultdict(float)
    by_activity = defaultdict(float)
    by_project = defaultdict(float)
    by_task = defaultdict(float)
    for r in rows_hours:
        h = flt(r.hours)
        daily[str(r.day)] += h
        by_activity[r.activity_type or _("Not set")] += h
        by_project[r.project or ""] += h
        if r.task:
            by_task[r.task] += h
    names = project_names(by_project.keys() | {t.project for t in tasks})
    total_hours = sum(daily.values())
    expected = expected_hours(person.employee, start, end, per_day)

    today = getdate(nowdate())

    def task_state(t):
        if t.status == "Completed":
            if (
                t.exp_end_date
                and t.completed_on
                and getdate(t.completed_on) > getdate(t.exp_end_date)
            ):
                return "Completed late"
            return "Completed"
        if t.status in OPEN_TASK and t.exp_end_date and getdate(t.exp_end_date) < today:
            return "Overdue"
        return t.status

    task_rows = sorted(
        (
            {
                "name": t.name,
                "subject": t.subject,
                "project": names.get(t.project) or t.project,
                "state": task_state(t),
                "due": str(t.exp_end_date) if t.exp_end_date else None,
                "completed_on": str(t.completed_on) if t.completed_on else None,
                "estimated": flt(t.expected_time),
                "logged": round(by_task.get(t.name, 0), 1),
            }
            for t in tasks
        ),
        key=lambda t: ({"Overdue": 0}.get(t["state"], 1), t["due"] or "9999"),
    )
    mine = [p for p in posts if person.user_id in (p.writer, p.designer, p.marketer)]
    now = get_datetime()

    metrics = task_metrics(tasks, start, end) | post_metrics(posts, person.user_id)
    return {
        "person": person,
        "from_date": str(start),
        "to_date": str(end),
        "hours_per_day": per_day,
        "summary": {
            "hours": round(total_hours, 1),
            "expected_hours": expected,
            "utilisation": pct(total_hours, expected),
            "active_days": len([d for d, h in daily.items() if h]),
            **metrics,
            "on_time_pct": pct(metrics["tasks_on_time"], metrics["tasks_completed"]),
            "posts_on_time_pct": pct(
                metrics["posts_on_time"], metrics["posts_published"]
            ),
        },
        "daily": [
            {
                "day": str(add_days(start, i)),
                "hours": round(daily.get(str(add_days(start, i)), 0), 1),
            }
            for i in range(date_diff(end, start) + 1)
        ],
        "by_activity": [
            {"activity": a, "hours": round(h, 1)}
            for a, h in sorted(by_activity.items(), key=lambda kv: -kv[1])
        ],
        "by_project": [
            {"project": names.get(p) or p or _("No project"), "hours": round(h, 1)}
            for p, h in sorted(by_project.items(), key=lambda kv: -kv[1])
        ],
        "tasks": task_rows[:100],
        "posts": [
            {
                "name": p.name,
                "title": p.title,
                "customer": p.customer,
                "role": ", ".join(
                    _(r.title()) for r in CONTENT_ROLES if p.get(r) == person.user_id
                ),
                "publish_on": str(p.publish_on),
                "state": (
                    "Published on time"
                    if p.status == "Published"
                    and p.published_on
                    and getdate(p.published_on) <= getdate(p.publish_on)
                    else (
                        "Published late"
                        if p.status == "Published"
                        else "Missed" if get_datetime(p.publish_on) < now else p.status
                    )
                ),
            }
            for p in sorted(mine, key=lambda p: p.publish_on)
        ],
    }
