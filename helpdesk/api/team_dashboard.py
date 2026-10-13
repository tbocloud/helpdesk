"""The team dashboard (/helpdesk/team-dashboard), the Scoreboard.

Every agent sees all of it: every department, person, project, ranking,
champion, history and analysis, so the team can compete (the owner's decision).
That includes DM and ERP Employees: the department walls
(tasky.permissions.hidden_departments) don't apply here. Only System Managers and
Agent Managers may ask the AI to refresh the analysis. The numbers and the
scoring live in helpdesk.team_dashboard.
"""

import json

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Count, Sum
from frappe.utils import add_days, getdate, nowdate

from helpdesk import team_dashboard as td
from helpdesk.tasky.permissions import is_tasky_admin
from helpdesk.utils import agent_only

REFRESH_COOLDOWN_SECONDS = 60
NO_DEPARTMENT = ""


@frappe.whitelist()
@agent_only
def get_team_dashboard(
    period: str = "week",
    department: str | None = None,
    group: str | None = None,
    day: str | None = None,
) -> dict:
    """The numbers of the period `day` falls in (today by default; never a future
    day): summary, departments (with their groups), people, projects, champion,
    the previous period's champion, trend, the year's champions and the analysis,
    for the whole team, one department or one department group (a main department
    with its sub-departments). A closed period shows the champions stored when it
    closed. The year adds its twelve months side by side. Every agent sees all of
    it."""
    check_period(period)
    access = viewer_access(frappe.session.user)
    scope = scope_of(access, department, group)
    today = getdate(nowdate())
    anchor = anchor_day(day, today)
    start, end = td.period_bounds(period, anchor)
    closed = end < today
    c_start, c_end = td.comparison_bounds(period, start, end, today)
    # overdue is today's state: it only belongs to the period in progress
    data = td.collect(start, end, with_overdue=not closed, today=today)
    prev = td.collect(c_start, c_end, with_overdue=False, today=today)

    keep = td.scope_filter(scope.departments)
    by_department = td.tally(
        data, lambda r: (r["department"] or NO_DEPARTMENT) if keep(r) else None
    )
    by_group = td.tally(
        data, lambda r: access.group_of.get(r["department"]) if keep(r) else None
    )
    members = department_members(scope.departments)
    ranked = ranked_people(data, period, scope.departments, members)
    champions = Champions(period, start, closed)
    months = (
        year_months(period, start, today, scope, champions.of_month)
        if period == "year"
        else None
    )
    return {
        "period": {
            "key": period,
            "start": str(start),
            "end": str(end),
            "compare_start": str(c_start),
            "compare_end": str(c_end),
            "closed": closed,
            "current": start <= today <= end,
            "earliest": str(earliest_day(today)),
        },
        "access": {
            "departments": access.departments,
            "groups": [
                {"group": g, "departments": ds} for g, ds in access.groups.items()
            ],
            "can_refresh": access.can_refresh
            and period not in td.QUIET_PERIODS
            and not closed,
        },
        "department": scope.department,
        "group": scope.group,
        "summary": summary(data, prev, keep),
        "trend": td.trend(data, keep, start, end, period),
        "history": history(scope, anchor),
        "champion": champions.card(
            scope.group or scope.department, scope.group, ranked
        ),
        "previous_champion": previous_champion(period, start, scope),
        "people": people_rows(ranked, by_department, members, months),
        "departments": department_rows(
            data, prev, (by_department, by_group), members, access, scope, champions
        ),
        "projects": project_rows(data, keep, scope.departments),
        "analysis": current_analysis(period, start, scope, closed),
        "months": months and months["rows"],
        "rules": td.score_rules(period),
    }


@frappe.whitelist(methods=["POST"])
@agent_only
def refresh_analysis(
    period: str = "week", department: str | None = None, group: str | None = None
) -> dict:
    """Ask the AI to read the period's numbers again (System and Agent Managers)."""
    check_period(period)
    access = viewer_access(frappe.session.user)
    if not access.can_refresh:
        frappe.throw(
            _("Only managers can refresh the analysis."), frappe.PermissionError
        )
    scope = scope_of(access, department, group)
    today = getdate(nowdate())
    start, end = td.period_bounds(period, today)
    name = scope.group or scope.department or ""
    key = td.analysis_cache_key(period, start, name, bool(scope.group))
    lock = f"{key}:refresh"
    if frappe.cache.get_value(lock, expires=True):
        frappe.throw(_("The analysis was refreshed less than a minute ago."))
    frappe.cache.set_value(lock, 1, expires_in_sec=REFRESH_COOLDOWN_SECONDS)

    data = td.collect(start, end, with_overdue=True, today=today)
    keep = td.scope_filter(scope.departments)
    ranked = td.rank(td.tally(data, lambda r: True if keep(r) else None)[True], period)
    facts = td.analysis_facts(
        td.scope_title(name, bool(scope.group)),
        td.period_label(period, start, end),
        ranked,
        td.totals(data, keep),
    )
    analysis = td.write_analysis(facts)
    if analysis["status"] == "ready":
        frappe.cache.set_value(key, analysis, expires_in_sec=td.ANALYSIS_SECONDS)
    return {**analysis, "period_start": str(start), "current": True}


# --- who sees what -----------------------------------------------------------


def viewer_access(user: str) -> frappe._dict:
    """The departments and department groups the viewer may pick (every active
    one, past the department walls, so DM and ERP can compete) and whether they
    may refresh the analysis (System and Agent Managers). `group_of` maps each
    department in a group to the group."""
    groups = td.department_groups()
    return frappe._dict(
        departments=td.active_departments(),
        groups=groups,
        group_of={d: g for g, ds in groups.items() for d in ds},
        can_refresh=is_tasky_admin(user),
    )


def scope_department(access, department: str | None) -> str | None:
    if department and department not in access.departments:
        frappe.throw(_("{0} isn't an active department.").format(department))
    return department or None


def scope_of(access, department: str | None, group: str | None) -> frappe._dict:
    """What the page shows: the whole team, one department, or one department
    group. `departments` lists the departments in it (None for the whole team)."""
    if department and group:
        frappe.throw(_("Pick a department or a department group, not both."))
    if group:
        if group not in access.groups:
            frappe.throw(_("{0} isn't a department group.").format(group))
        return frappe._dict(
            department=None, group=group, departments=access.groups[group]
        )
    department = scope_department(access, department)
    return frappe._dict(
        department=department,
        group=None,
        departments=[department] if department else None,
    )


def check_period(period: str):
    if period not in td.PERIODS:
        frappe.throw(_("Unknown period: {0}").format(period))


def ranked_people(data: dict, period: str, departments: list | None, members: dict):
    """Everyone in scope scored, best first, as the People view ranks them: whoever
    has work in the scope, then its members (`department_members`) with nothing."""
    keep = td.scope_filter(departments)
    ranked = td.rank(td.tally(data, lambda r: True if keep(r) else None)[True], period)
    for person in sorted(set().union(*members.values()) - {r["user"] for r in ranked}):
        ranked.extend(td.rank({person: td.blank()}, period))
    return ranked


def department_is(department: str):
    """Rows of one department; NO_DEPARTMENT for projects without one."""
    return lambda r: (r["department"] or NO_DEPARTMENT) == department


# --- the parts of the page ---------------------------------------------------


def summary(data: dict, prev: dict, keep) -> dict:
    now, before = td.totals(data, keep), td.totals(prev, keep)
    return {
        **now,
        "previous": {
            k: before[k] for k in ("tasks", "weight", "on_time_pct", "hours", "posts")
        },
    }


def champion_card(champion: dict | None) -> dict | None:
    """Who, the score, the reasons and the breakdown."""
    if not champion:
        return None
    info = td.people_info([champion["user"]]).get(champion["user"], {})
    return {
        "user": champion["user"],
        "name": info.get("name") or champion["user"],
        "image": info.get("image"),
        "score": champion["score"],
        "reasons": champion["reasons"],
        "breakdown": champion["breakdown"],
    }


def people_rows(
    ranked: list, by_department: dict, members: dict, months: dict | None = None
) -> list[dict]:
    """Everyone ranked, with their numbers; in the year, each person's twelve
    months too (`months`, from year_months)."""
    info = td.people_info([r["user"] for r in ranked])
    rows = []
    for position, r in enumerate(ranked, start=1):
        person = info.get(r["user"])
        if not person or (not person["enabled"] and not r["score"]):
            continue
        s = r["stats"]
        rows.append(
            {
                "user": r["user"],
                "name": person["name"],
                "image": person["image"],
                "department": main_department(r["user"], by_department, members),
                "rank": position,
                "score": r["score"],
                "eligible": r["eligible"],
                "breakdown": r["breakdown"],
                "reasons": r["reasons"],
                "tasks": s["tasks"],
                "weight": round(s["weight"], 1),
                "key": s["key"],
                "self_made": s["self_made"],
                "on_time_pct": td.pct(s["on_time"], s["dated"]),
                "dated": s["dated"],
                "hours": round(s["hours"], 1),
                "overdue": s["overdue"],
                "slips": s["slips"],
                "excellent": s["excellent"],
                "good": s["good"],
                "rework": s["rework"],
                "sent_back": s["sent_back"],
                "came_back": s["came_back"],
                "posts_on_time": s["posts_on_time"],
                "posts_late": s["posts_late"],
                "posts_missed": s["posts_missed"],
                "months": months["people"].get(r["user"]) if months else None,
            }
        )
    return rows


def main_department(user: str, by_department: dict, members: dict) -> str | None:
    """Where the person did the most tasks in the period, else a department they're
    a member of."""
    done = {
        d: people[user]["tasks"]
        for d, people in by_department.items()
        if user in people
    }
    best = max(done, key=done.get, default=None) if any(done.values()) else None
    if best:
        return best
    return next((d for d, users in members.items() if user in users and d), None)


def department_rows(data, prev, tallies, members, access, scope, champions):
    """One row per department in scope, each group (a main department with its
    sub-departments) first as a row of its own with its departments under it
    (`parent`), then the departments in no group and No department."""
    by_department, by_group = tallies

    def row(name, stats, keep, people, parent=None, is_group=False):
        active = {u for u, s in stats.items() if td.delivered(s) or s["overdue"]}
        return {
            "department": name or None,
            "kind": "group" if is_group else "department",
            "parent": parent,
            "people": len(active | people),
            **summary(data, prev, keep),
            "champion": (
                champions.card(name, is_group, td.rank(stats, champions.period))
                if name
                else None
            ),
        }

    def department(d, parent=None):
        return row(
            d,
            by_department.get(d, {}),
            department_is(d),
            members.get(d, set()),
            parent,
        )

    def group(g):
        ds = access.groups[g]
        people = set().union(*(members.get(d, set()) for d in ds))
        return [
            row(g, by_group.get(g, {}), td.scope_filter(ds), people, is_group=True),
            *(department(d, g) for d in ds),
        ]

    if scope.group:
        return group(scope.group)
    if scope.department:
        return [department(scope.department, access.group_of.get(scope.department))]
    rows = []
    for d in access.departments:
        if d in access.groups:
            rows.extend(group(d))
        elif d not in access.group_of:
            rows.append(department(d))
    no_department = by_department.get(NO_DEPARTMENT, {})
    if any(td.delivered(s) or s["overdue"] for s in no_department.values()):
        rows.append(department(NO_DEPARTMENT))
    return rows


def department_members(departments: list[str] | None) -> dict[str, set]:
    """Who belongs to each department in scope: the members of its open projects.
    With no department picked, every active agent is listed too."""
    project = frappe.qb.DocType("Project")
    member = frappe.qb.DocType("Project User")
    query = (
        frappe.qb.from_(member)
        .join(project)
        .on(project.name == member.parent)
        .select(project.custom_department, member.user)
        .distinct()
        .where(
            (member.parenttype == "Project")
            & (project.status == "Open")
            & project.custom_department.isnotnull()
        )
    )
    if departments:
        query = query.where(project.custom_department.isin(departments))
    out: dict[str, set] = {}
    for dept, user in query.run():
        out.setdefault(dept, set()).add(user)
    if not departments:
        agent = frappe.qb.DocType("HD Agent")
        out[NO_DEPARTMENT] = set(
            frappe.qb.from_(agent)
            .select(agent.user)
            .where(agent.is_active == 1)
            .run(pluck=True)
        ) - set().union(*out.values())
    return out


def project_rows(data, keep, departments: list[str] | None) -> list[dict]:
    """Projects with more than one member, in scope, that are open or had work in
    the period: progress, hours and who contributed what."""
    active = {
        r["project"]
        for key in ("tasks", "hours", "overdue")
        for r in data[key]
        if keep(r)
    }
    project = frappe.qb.DocType("Project")
    member = frappe.qb.DocType("Project User")
    query = (
        frappe.qb.from_(project)
        .join(member)
        .on((member.parent == project.name) & (member.parenttype == "Project"))
        .select(
            project.name,
            project.project_name,
            project.customer,
            project.status,
            project.custom_department.as_("department"),
            Count(member.user).distinct().as_("members"),
        )
        .groupby(project.name)
        .having(Count(member.user).distinct() > 1)
    )
    if departments:
        query = query.where(project.custom_department.isin(departments))
    projects = [
        p for p in query.run(as_dict=True) if p.status == "Open" or p.name in active
    ]
    if not projects:
        return []
    names = {p.name for p in projects}
    progress = task_progress(list(names))
    contributions = td.tally(
        data, lambda r: r["project"] if r["project"] in names else None
    )
    info = td.people_info([u for people in contributions.values() for u in people])
    rows = []
    for p in projects:
        people = contributions.get(p.name, {})
        done, total = progress.get(p.name, (0, 0))
        rows.append(
            {
                "project": p.name,
                "project_name": p.project_name or p.name,
                "customer": p.customer,
                "department": p.department,
                "status": p.status,
                "members": p.members,
                "done": done,
                "total": total,
                "tasks": sum(1 for t in data["tasks"] if t["project"] == p.name),
                "hours": round(sum(s["hours"] for s in people.values()), 1),
                "overdue": sum(1 for t in data["overdue"] if t["project"] == p.name),
                "contributors": sorted(
                    (
                        {
                            "user": u,
                            "name": info.get(u, {}).get("name") or u,
                            "image": info.get(u, {}).get("image"),
                            "tasks": s["tasks"],
                            "weight": round(s["weight"], 1),
                            "hours": round(s["hours"], 1),
                            "overdue": s["overdue"],
                        }
                        for u, s in people.items()
                    ),
                    key=lambda c: (-c["tasks"], -c["hours"], c["name"]),
                ),
            }
        )
    rows.sort(key=lambda r: (-r["tasks"], -r["overdue"], r["project_name"].lower()))
    return rows


def task_progress(projects: list[str]) -> dict[str, tuple[int, int]]:
    """(completed, total) tasks per project, cancelled and template tasks left out."""
    task = frappe.qb.DocType("Task")
    done = Sum(Case().when(task.status == "Completed", 1).else_(0))
    rows = (
        frappe.qb.from_(task)
        .select(task.project, done, Count("*"))
        .where(
            task.project.isin(projects) & task.status.notin(["Cancelled", "Template"])
        )
        .groupby(task.project)
        .run()
    )
    return {project: (int(d or 0), int(t)) for project, d, t in rows}


def history(scope, day) -> list[dict]:
    """The champions of `day`'s year (weeks and longer) of the department, the
    group or the whole team, newest first. Stored when each period closed, so
    they never shift."""
    champion = frappe.qb.DocType("HD Team Champion")
    query = (
        frappe.qb.from_(champion)
        .select(
            champion.name,
            champion.period_type,
            champion.period_start,
            champion.period_end,
            champion.user,
            champion.score,
        )
        .where(
            (champion.period_type != "Day")
            & (champion.period_start >= f"{getdate(day).year}-01-01")
            & (champion.period_start <= f"{getdate(day).year}-12-31")
            & champion.user.isnotnull()
        )
        .orderby(champion.period_end, order=frappe.qb.desc)
        .orderby(champion.period_start, order=frappe.qb.desc)
    )
    query = stored_scope(query, champion, scope)
    rows = query.run(as_dict=True)
    info = td.people_info([r.user for r in rows])
    return [
        {
            "period_type": r.period_type,
            "start": str(r.period_start),
            "end": str(r.period_end),
            "user": r.user,
            "name": info.get(r.user, {}).get("name") or r.user,
            "image": info.get(r.user, {}).get("image"),
            "score": r.score,
        }
        for r in rows
    ]


def current_analysis(period: str, start, scope, closed: bool = False) -> dict:
    """A closed period's own analysis (stored with its champion). For the period
    in progress: its analysis when someone refreshed it, else the last closed
    period's, else none yet."""
    cached = (
        None
        if closed
        else frappe.cache.get_value(
            td.analysis_cache_key(
                period, start, scope.group or scope.department, bool(scope.group)
            ),
            expires=True,
        )
    )
    if cached:
        return {**cached, "period_start": str(start), "current": True}
    champion = frappe.qb.DocType("HD Team Champion")
    query = (
        frappe.qb.from_(champion)
        .select(champion.analysis, champion.period_start, champion.period_end)
        .where(
            (champion.period_type == td.PERIODS[period][0])
            & (
                (champion.period_start == start)
                if closed
                else (champion.period_end < start)
            )
            & champion.analysis.isnotnull()
        )
        .orderby(champion.period_start, order=frappe.qb.desc)
        .limit(1)
    )
    query = stored_scope(query, champion, scope)
    row = next(iter(query.run(as_dict=True)), None)
    stored = json.loads(row.analysis) if row else None
    if not stored or stored.get("status") != "ready":
        return {"status": "none"}
    return {
        **stored,
        "period_start": str(row.period_start),
        "period_end": str(row.period_end),
        "current": False,
    }


def stored_scope(query, champion, scope):
    """HD Team Champion records of the scope: the group, the department, or the
    whole team (no department)."""
    name = scope.group or scope.department
    if not name:
        return query.where(champion.department.isnull())
    return query.where(
        (champion.department == name) & (champion.is_group == int(bool(scope.group)))
    )


# --- months, and champions of closed periods ------------------------------------


def earliest_day(today):
    """The first day the month picker offers: the start of last year."""
    return getdate(today).replace(year=getdate(today).year - 1, month=1, day=1)


def anchor_day(day: str | None, today):
    """The day whose period the page shows: today, or a past day picked on the
    page. A future day has no numbers yet, so it is refused."""
    if not day:
        return today
    try:
        anchor = getdate(day)
    except Exception:  # noqa: BLE001 - getdate raises several kinds on bad text
        frappe.throw(_("Pick a day as YYYY-MM-DD."))
    if anchor > today:
        frappe.throw(
            _("{0} hasn't happened yet. Pick today or an earlier day.").format(
                frappe.utils.formatdate(anchor)
            )
        )
    return anchor


def stored_champions(period_type: str, start, end=None) -> list:
    """HD Team Champion records of the period type starting on `start` (or from
    `start` to `end`), with a champion."""
    champion = frappe.qb.DocType("HD Team Champion")
    query = (
        frappe.qb.from_(champion)
        .select(
            champion.period_start,
            champion.period_end,
            champion.department,
            champion.is_group,
            champion.user,
            champion.score,
            champion.breakdown,
        )
        .where((champion.period_type == period_type) & champion.user.isnotnull())
    )
    if end:
        query = query.where(champion.period_start.between(start, end))
    else:
        query = query.where(champion.period_start == getdate(start))
    return query.run(as_dict=True)


def stored_card(row) -> dict:
    """A stored champion as the page's champion card, with the reasons it was
    stored with (its three biggest positive parts)."""
    info = td.people_info([row.user]).get(row.user, {})
    try:
        breakdown = json.loads(row.breakdown or "[]")
    except ValueError:
        breakdown = []
    reasons = [
        b.get("detail")
        for b in sorted(breakdown, key=lambda b: -(b.get("points") or 0))
        if (b.get("points") or 0) > 0 and b.get("key") != "hours"
    ][:3]
    return {
        "user": row.user,
        "name": info.get("name") or row.user,
        "image": info.get("image"),
        "score": row.score,
        "reasons": reasons,
        "breakdown": breakdown,
        "stored": True,
        "start": str(row.period_start),
        "end": str(row.period_end),
    }


def scope_key(name: str | None, is_group) -> tuple:
    return (name or None, bool(is_group) and bool(name))


class Champions:
    """Who is champion of each scope (the whole team, a group, a department) of the
    page's period. A closed period shows the records stored when it closed (HD
    Team Champion), never a recomputation, so its history doesn't shift when the
    formula or old tasks change; nobody stored means no champion. The period in
    progress is worked out now."""

    def __init__(self, period: str, start, closed: bool):
        self.period = period
        self.closed = closed
        self.stored = (
            {
                scope_key(r.department, r.is_group): r
                for r in stored_champions(td.PERIODS[period][0], start)
            }
            if closed
            else {}
        )

    def card(self, name: str | None, is_group, ranked: list) -> dict | None:
        if not self.closed:
            return champion_card(td.champion_of(ranked))
        row = self.stored.get(scope_key(name, is_group))
        return stored_card(row) if row else None

    @staticmethod
    def of_month(rows: list, scope) -> dict:
        """{month start: stored row} of the scope, from a year's Month records."""
        key = scope_key(scope.group or scope.department, scope.group)
        return {
            getdate(r.period_start): r
            for r in rows
            if scope_key(r.department, r.is_group) == key
        }


def previous_champion(period: str, start, scope) -> dict | None:
    """The champion of the period before (last month, last week, yesterday) as
    stored when it closed, for the scope; None when nobody was stored."""
    prev_start = td.period_bounds(period, add_days(start, -1))[0]
    key = scope_key(scope.group or scope.department, scope.group)
    row = next(
        (
            r
            for r in stored_champions(td.PERIODS[period][0], prev_start)
            if scope_key(r.department, r.is_group) == key
        ),
        None,
    )
    return stored_card(row) if row else None


def year_months(period: str, start, today, scope, of_month) -> dict:
    """The year's twelve months side by side for the scope: weighted work, tasks,
    on time, quality and champion (stored for a closed month, worked out for the
    month in progress, none for a month to come), and each person's month by
    month (`people`: {user: [12 entries or None]})."""
    year = getdate(start).year
    keep = td.scope_filter(scope.departments)
    stored = of_month(
        stored_champions("Month", f"{year}-01-01", f"{year}-12-31"), scope
    )
    rows, people = [], {}
    for month in range(1, 13):
        m_start, m_end = td.period_bounds("month", f"{year}-{month:02d}-01")
        row = {"month": str(m_start), "end": str(m_end)}
        if m_start > today:
            rows.append({**row, "future": True})
            for entries in people.values():
                entries.append(None)
            continue
        data = td.collect(m_start, m_end, with_overdue=False, today=today)
        figures = td.totals(data, keep)
        ranked = td.rank(
            td.tally(data, lambda r: True if keep(r) else None)[True], "month"
        )
        if m_end < today:
            champion = stored.get(m_start)
            champion = stored_card(champion) if champion else None
        else:
            champion = champion_card(td.champion_of(ranked))
        rows.append(
            {
                **row,
                "future": False,
                "tasks": figures["tasks"],
                "weight": figures["weight"],
                "on_time_pct": figures["on_time_pct"],
                "quality": figures["quality"],
                "champion": champion,
            }
        )
        by_user = {r["user"]: r for r in ranked}
        for user in by_user:
            people.setdefault(user, [None] * (month - 1))
        for user, entries in people.items():
            stats = by_user.get(user)
            entries.append(
                {
                    "month": str(m_start),
                    "score": stats["score"] if stats else 0,
                    "tasks": stats["stats"]["tasks"] if stats else 0,
                    "weight": round(stats["stats"]["weight"], 1) if stats else 0,
                }
            )
    return {"rows": rows, "people": people}
