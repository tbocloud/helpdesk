"""Competition on the Scoreboard, for the TBO Smart app: ranks and how they moved,
streaks, personal bests, badges, the weekly challenge and how to move up.

Every view here is derived from the Scoreboard's own numbers (helpdesk.team_dashboard:
collect, tally, rank and score) and the tasks' due dates; there is no second scoring
formula. Badges are awarded when a period closes (team_dashboard.close_period) and
kept in HD Badge Award, so the history never shifts. docs/tbo-smart-api.md
(Competition) has the rules.
"""

from collections import defaultdict
from collections.abc import Callable

import frappe
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import add_days, flt, formatdate, getdate

from helpdesk import team_dashboard as td
from helpdesk.recurrence import working_day_checker
from helpdesk.utils import assigned_names_query
from helpdesk.work_reminders import notify_users

BADGE = "HD Badge Award"
# under the Scoreboard's prefix, so td.clear_cache() drops it with the numbers
DUE_CACHE_PREFIX = f"{td.CACHE_PREFIX}:due"
STREAK_LOOKBACK_DAYS = 90
STREAK_BADGE_DAYS = 5
KEY_CLOSER_MIN = 2
ZERO_OVERDUE_MIN_DUE = 3
PODIUM_SIZE = 3
PODIUM_LOOKBACK_WEEKS = 26
BEST_WEEKS = 26
BADGE_LIST_LIMIT = 20
MOVE_UP_ACTIONS = 3
# a task due on a non-working day counts on the next one; never further than this
MAX_DAYS_OFF_IN_A_ROW = 14
# how a task due on a day stands
ON_TIME, LATE, PENDING, WAITING = "on_time", "late", "pending", "waiting"
# held work and work in review wait on someone else (as "Overdue now" leaves them out)
WAITING_STATUSES = ("On Hold", "Pending Review")
DEFAULT_CHALLENGE = "Key tasks due this week"
# the champion is already told "You're the … champion"; the badge needn't tell them again
SILENT_BADGES = ("champion_week", "champion_month")
PERIOD_BADGES = {"Week": "champion_week", "Month": "champion_month"}


def badge_catalog() -> dict[str, dict]:
    """Every badge with its rule, in the order the app shows them."""
    return {
        "on_time_streak": {
            "label": _("On-time streak {0}").format(STREAK_BADGE_DAYS),
            "rule": _(
                "{0} working days in a row with everything you had due done on time. Days with nothing due neither count nor break it."
            ).format(STREAK_BADGE_DAYS),
        },
        "key_closer": {
            "label": _("Key task closer"),
            "rule": _(
                "{0} or more key tasks or milestones completed on time in one week."
            ).format(KEY_CLOSER_MIN),
        },
        "zero_overdue_week": {
            "label": _("Zero overdue week"),
            "rule": _(
                "At least {0} tasks due in the week, every one done on time, and nothing overdue when the week closed."
            ).format(ZERO_OVERDUE_MIN_DUE),
        },
        "podium": {
            "label": _("Department top {0}").format(PODIUM_SIZE),
            "rule": _(
                "In the top {0} of a department's Scoreboard for the week, with the week's minimum activity."
            ).format(PODIUM_SIZE),
        },
        "champion_week": {
            "label": _("Champion of the week"),
            "rule": _("The week's champion of the whole team or of a department."),
        },
        "champion_month": {
            "label": _("Champion of the month"),
            "rule": _("The month's champion of the whole team or of a department."),
        },
    }


def challenges() -> dict[str, tuple[str, Callable[[dict], bool]]]:
    """HD Follow Up Settings' weekly challenge choice → (its goal, the tasks it counts)."""
    return {
        "Key tasks due this week": (
            _("Close every key task due this week"),
            lambda row: row["key"],
        ),
        "Every task due this week": (
            _("Finish every task due this week on time"),
            lambda row: True,
        ),
    }


# --- tasks by due date ---------------------------------------------------------


def due_tasks(start, end, today) -> list[dict]:
    """Tasks due between `start` and `end` (not cancelled), with their assignees and
    department; cached briefly, like the Scoreboard's numbers."""
    key = f"{DUE_CACHE_PREFIX}:{start}:{end}:{getdate(today)}"
    cached = frappe.cache.get_value(key, expires=True)
    if cached is not None:
        return cached
    task = frappe.qb.DocType("Task")
    project = frappe.qb.DocType("Project")
    rows = (
        frappe.qb.from_(task)
        .left_join(project)
        .on(project.name == task.project)
        .select(
            task.name,
            task.subject,
            task.project,
            task["_assign"],
            task.exp_end_date,
            task.status,
            task.completed_on,
            task.is_key,
            task.is_milestone,
            project.custom_department.as_("department"),
        )
        .where(
            task.exp_end_date.between(getdate(start), getdate(end))
            & task.status.notin(["Cancelled", "Template"])
        )
        .run(as_dict=True)
    )
    data = [
        {
            "name": r.name,
            "subject": r.subject,
            "project": r.project,
            "department": r.department,
            "users": td.assignees(r._assign),
            "due": getdate(r.exp_end_date),
            "status": r.status,
            "completed_on": getdate(r.completed_on) if r.completed_on else None,
            "key": bool(r.is_key or r.is_milestone),
        }
        for r in rows
    ]
    frappe.cache.set_value(key, data, expires_in_sec=td.CACHE_SECONDS)
    return data


def outcome(row: dict, as_of) -> str:
    """On time (completed by its due date), late (completed after it, or still open
    past it on `as_of`), pending (open and not due yet) or waiting on someone else."""
    if row["status"] == "Completed":
        on_time = row["completed_on"] and row["completed_on"] <= row["due"]
        return ON_TIME if on_time else LATE
    if row["status"] in WAITING_STATUSES:
        return WAITING
    return LATE if row["due"] < getdate(as_of) else PENDING


def working_day_of(day, is_working):
    """The day itself when it is worked, else the next working day."""
    day = getdate(day)
    for _i in range(MAX_DAYS_OFF_IN_A_ROW):
        if is_working(day):
            break
        day = getdate(add_days(day, 1))
    return day


def outcomes_by_day(rows: list[dict], as_of, is_working) -> dict:
    """{user: {working day: [outcome of each task due then]}}; waiting work is left out."""
    found = defaultdict(lambda: defaultdict(list))
    for row in rows:
        result = outcome(row, as_of)
        if result == WAITING:
            continue
        day = working_day_of(row["due"], is_working)
        for user in row["users"]:
            found[user][day].append(result)
    return found


def streak_run(days: dict, start, last, as_of, is_working) -> tuple[int, int, object]:
    """(current, longest, last counted day) of the on-time streak from `start` to
    `last`: a working day counts when everything due on it was done on time, breaks
    it when something was late, and is skipped when nothing was due. On `as_of`
    (today) work that is still pending doesn't break it yet: the day isn't over."""
    run = best = 0
    counted = None
    day, last, as_of = getdate(start), getdate(last), getdate(as_of)
    while day <= last:
        results = days.get(day) if is_working(day) else None
        if results:
            if all(r == ON_TIME for r in results):
                run += 1
                best = max(best, run)
                counted = day
            elif day != as_of or LATE in results:
                run = 0
        day = getdate(add_days(day, 1))
    return run, best, counted


# --- one person ----------------------------------------------------------------


def my_streaks(user: str, today) -> dict:
    """The user's on-time streak (working days) and department top-3 streak (weeks)."""
    start = getdate(add_days(today, -STREAK_LOOKBACK_DAYS))
    is_working = working_day_checker(start, add_days(today, MAX_DAYS_OFF_IN_A_ROW))
    days = outcomes_by_day(due_tasks(start, today, today), today, is_working)
    current, best, _counted = streak_run(
        days.get(user, {}), start, today, today, is_working
    )
    return {
        "on_time_days": current,
        "best_on_time_days": best,
        "podium_weeks": podium_streak(user, today),
        "lookback_days": STREAK_LOOKBACK_DAYS,
    }


def podium_streak(user: str, today) -> int:
    """Closed weeks in a row, up to last week, in a department's top 3 (the badge)."""
    monday = td.period_bounds("week", today)[0]
    badge = frappe.qb.DocType(BADGE)
    weeks = {
        getdate(d)
        for d in frappe.qb.from_(badge)
        .select(badge.period_start)
        .where(
            (badge.user == user)
            & (badge.badge == "podium")
            & (badge.period_start >= add_days(monday, -7 * PODIUM_LOOKBACK_WEEKS))
        )
        .run(pluck=True)
    }

    def week_before(start):
        # weeks are clipped to their month, so the one before isn't always 7 days back
        return td.period_bounds("week", add_days(start, -1))[0]

    count = 0
    week = week_before(monday)
    while week in weeks:
        count += 1
        week = week_before(week)
    return count


def personal_bests(user: str, today, longest_streak: int) -> dict:
    """The user's best weeks of the last BEST_WEEKS weeks, longest on-time streak and
    champion titles (weeks and longer)."""
    first = getdate(add_days(td.period_bounds("week", today)[0], -7 * (BEST_WEEKS - 1)))
    task = frappe.qb.DocType("Task")
    rows = (
        frappe.qb.from_(task)
        .select(task.completed_on, task.exp_end_date, task.is_key, task.is_milestone)
        .where(
            (task.status == "Completed")
            & task.completed_on.between(first, getdate(today))
            & task.name.isin(assigned_names_query("Task", user))
        )
        .run(as_dict=True)
    )
    weeks = defaultdict(lambda: {"done": 0, "on_time": 0, "key": 0})
    for r in rows:
        done = getdate(r.completed_on)
        week = weeks[td.period_bounds("week", done)[0]]
        week["done"] += 1
        week["on_time"] += bool(r.exp_end_date and done <= getdate(r.exp_end_date))
        week["key"] += bool(r.is_key or r.is_milestone)

    def best(field: str) -> dict | None:
        top = max(weeks.items(), key=lambda kv: (kv[1][field], kv[0]), default=None)
        if not top or not top[1][field]:
            return None
        return {"value": top[1][field], "week_start": str(top[0])}

    champion = frappe.qb.DocType("HD Team Champion")
    titles = (
        frappe.qb.from_(champion)
        .select(Count("*"))
        .where((champion.user == user) & (champion.period_type != "Day"))
        .run()[0][0]
    )
    return {
        "most_on_time_in_a_week": best("on_time"),
        "most_done_in_a_week": best("done"),
        "most_key_in_a_week": best("key"),
        "longest_on_time_streak": longest_streak,
        "champion_titles": titles,
        "weeks_looked_at": BEST_WEEKS,
    }


def earned_badges(user: str) -> dict:
    """The user's latest badges, and every badge with its rule and how often they
    earned it."""
    catalog = badge_catalog()
    badge = frappe.qb.DocType(BADGE)
    rows = (
        frappe.qb.from_(badge)
        .select(
            badge.name,
            badge.badge,
            badge.period_type,
            badge.period_start,
            badge.period_end,
            badge.department,
            badge.detail,
            badge.earned_on,
        )
        .where(badge.user == user)
        .orderby(badge.earned_on, order=frappe.qb.desc)
        .orderby(badge.period_start, order=frappe.qb.desc)
        .limit(BADGE_LIST_LIMIT)
        .run(as_dict=True)
    )
    counts = dict(
        frappe.qb.from_(badge)
        .select(badge.badge, Count("*"))
        .where(badge.user == user)
        .groupby(badge.badge)
        .run()
    )
    return {
        "earned": [
            {
                "name": r.name,
                "badge": r.badge,
                "label": catalog.get(r.badge, {}).get("label", r.badge),
                "period_type": r.period_type,
                "start": str(r.period_start),
                "end": str(r.period_end),
                "department": r.department,
                "detail": r.detail,
                "earned_on": str(r.earned_on),
            }
            for r in rows
        ],
        "catalog": [
            {"badge": key, **info, "count": counts.get(key, 0)}
            for key, info in catalog.items()
        ],
    }


# --- the weekly challenge --------------------------------------------------------


def challenge_choice() -> str:
    from helpdesk.follow_ups import get_settings

    # a Single's new field has no stored value until the settings are saved
    return get_settings().get("weekly_challenge") or DEFAULT_CHALLENGE


def weekly_challenge(user: str, today) -> dict | None:
    """This week's team goal (Settings → Follow-ups), its progress and who completed
    their part: everyone with tasks in it who did all of them on time. None when off."""
    choice = challenge_choice()
    if choice not in challenges():
        return None
    title, counts = challenges()[choice]
    start, end = td.period_bounds("week", today)
    rows = [r for r in due_tasks(start, end, today) if counts(r)]
    people = defaultdict(lambda: {"done": 0, "total": 0})
    done = 0
    for row in rows:
        on_time = outcome(row, today) == ON_TIME
        done += on_time
        for person in row["users"]:
            people[person]["total"] += 1
            people[person]["done"] += on_time
    finished = sorted(u for u, p in people.items() if p["done"] == p["total"])
    info = td.people_info(finished)
    return {
        "key": choice,
        "title": title,
        "week": {"start": str(start), "end": str(end)},
        "goal": len(rows),
        "done": done,
        "pct": td.pct(done, len(rows)),
        "complete": bool(rows) and done == len(rows),
        "mine": dict(people[user]) if user in people else None,
        "completed_by": sorted(
            (
                {"user": u, "full_name": info[u]["name"], "image": info[u]["image"]}
                for u in finished
                if info.get(u, {}).get("enabled")
            ),
            key=lambda p: p["full_name"],
        ),
    }


# --- ranks and moving up -----------------------------------------------------------


def previous_positions(prev_people: dict, period: str) -> dict[str, int]:
    """Where each person who delivered something in the comparison period stood
    then. Nobody else has a previous rank (their rank_delta is null): ranks among
    people with nothing only follow the alphabet."""
    active = {u: s for u, s in prev_people.items() if td.delivered(s)}
    return {r["user"]: i for i, r in enumerate(td.rank(active, period), start=1)}


def leaderboard(data, prev, period, scope, by_department, limit, user):
    """One scope's board (the whole team, a department or a department group, as
    team_dashboard.scope_of gives it), ranked as the web Scoreboard's People view,
    with each person's rank change since the comparison period; and the ranked
    rows."""
    from helpdesk.api.team_dashboard import (
        department_members,
        people_rows,
        ranked_people,
    )

    departments = scope.departments
    keep = td.scope_filter(departments)
    members = department_members(departments)
    ranked = ranked_people(data, period, departments, members)
    champion = td.champion_of(ranked)
    prev_people = td.tally(prev, lambda r: True if keep(r) else None)[True]
    before = previous_positions(prev_people, period)
    rows = [
        {
            "user": p["user"],
            "full_name": p["name"],
            "image": p["image"],
            "department": p["department"],
            "rank": p["rank"],
            "score": p["score"],
            "rank_delta": before[p["user"]] - p["rank"]
            if p["user"] in before
            else None,
            "is_champion": bool(champion and champion["user"] == p["user"]),
            "tasks_done": p["tasks"],
            "weighted_work": p["weight"],
            "on_time_pct": p["on_time_pct"],
            "overdue": p["overdue"],
        }
        for p in people_rows(ranked, by_department, members)
    ]
    board = {
        "department": scope.department,
        "group": scope.group,
        "champion": champion and champion["user"],
        "of": len(rows),
        "leaders": rows[:limit],
        "me": next((r for r in rows if r["user"] == user), None),
    }
    return board, ranked


def task_gain(stats: dict, task: dict, period: str, today, user: str) -> dict | None:
    """What finishing one open task now adds to the user's score: score() with the
    task done minus score() as it is. Held or in-review work can't be finished now."""
    if task["status"] in WAITING_STATUSES:
        return None
    due = getdate(task["exp_end_date"]) if task.get("exp_end_date") else None
    key = bool(task.get("is_key") or task.get("is_milestone"))
    # an open task has no rating or comebacks yet: quality 1, its weight alone
    weight = td.task_weight(
        {
            "key": key,
            "estimate": flt(task.get("expected_hours")),
            "priority": task.get("priority"),
            "self_made": (task.get("assigned_by") or {}).get("user") == user,
        }
    )["weight"]
    on_time = bool(due and due >= getdate(today))
    overdue = bool(due and not on_time and task["status"] in td.OPEN_STATUSES)
    after = dict(stats)
    after["tasks"] += 1
    after["key"] += key
    after["weight"] += weight
    after["value"] += weight
    after["dated"] += bool(due)
    if on_time:
        after["on_time"] += 1
        after["weight_on_time"] += weight
        after["value_on_time"] += weight
    if overdue and after["overdue"]:
        after["overdue"] -= 1
    points = round(
        td.score(after, period)["score"] - td.score(stats, period)["score"], 1
    )
    if overdue:
        text = _("Finish overdue “{0}”: +{1}")
    elif on_time:
        text = _("Finish “{0}” on time: +{1}")
    else:
        text = _("Finish “{0}” (no due date, so half credit): +{1}")
    return {
        "task": task["name"],
        "subject": task["subject"],
        "due": str(due) if due else None,
        "points": points,
        "text": text.format(task["subject"], points),
    }


def move_up(ranked: list[dict], user: str, tasks: list[dict], period: str, today):
    """The gap to the person ranked just above, and up to MOVE_UP_ACTIONS of the
    user's own open tasks that gain the most points, each saying whether it alone
    would close the gap."""
    position = next((i for i, r in enumerate(ranked) if r["user"] == user), None)
    if position is None:
        return None
    me = ranked[position]
    ahead = ranked[position - 1] if position else None
    gap = round(ahead["score"] - me["score"], 1) if ahead else None
    gains = (task_gain(me["stats"], t, period, today, user) for t in tasks)
    actions = sorted(
        (g for g in gains if g and g["points"] > 0),
        key=lambda g: (-g["points"], g["due"] or "9999-12-31"),
    )[:MOVE_UP_ACTIONS]
    for action in actions:
        action["passes"] = gap is not None and action["points"] > gap
    info = td.people_info([ahead["user"]]) if ahead else {}
    return {
        "leader": ahead is None,
        "next": {
            "user": ahead["user"],
            "full_name": info.get(ahead["user"], {}).get("name") or ahead["user"],
            "score": ahead["score"],
        }
        if ahead
        else None,
        "gap": gap,
        "actions": actions,
    }


def competition(
    user: str, period: str, limit: int, today, tasks: list[dict], day=None
) -> dict:
    """Everything the app's Compete screen shows. The boards are public, as on the
    web Scoreboard (every active department, past the DM/ERP walls); streaks, bests,
    badges and how to move up are the user's own. `tasks` are the user's open tasks.

    `day` picks a past period (the one it falls in): its boards then show the
    champions stored when it closed, and there is no moving up in it."""
    from helpdesk.api.team_dashboard import (
        NO_DEPARTMENT,
        Champions,
        previous_champion,
        scope_of,
        viewer_access,
    )

    access = viewer_access(user)
    start, end = td.period_bounds(period, day or today)
    closed = end < getdate(today)
    c_start, c_end = td.comparison_bounds(period, start, end, today)
    data = td.collect(start, end, with_overdue=not closed, today=today)
    prev = td.collect(c_start, c_end, with_overdue=False, today=today)
    by_department = td.tally(data, lambda r: r["department"] or NO_DEPARTMENT)
    champions = Champions(period, start, closed)

    def board(department=None, group=None):
        scope = scope_of(access, department, group)
        found, ranked = leaderboard(
            data, prev, period, scope, by_department, limit, user
        )
        if closed:
            card = champions.card(scope.group or scope.department, scope.group, ranked)
            found["champion"] = card and card["user"]
            for row in [*found["leaders"], found["me"]]:
                if row:
                    row["is_champion"] = row["user"] == found["champion"]
        return found, ranked

    team, ranked = board()
    streaks = my_streaks(user, today)
    return {
        "period": period,
        "period_label": td.period_label(period, start, end),
        "range": {"start": str(start), "end": str(end)},
        "compare": {"start": str(c_start), "end": str(c_end)},
        "closed": closed,
        "previous_champion": previous_champion(
            period, start, scope_of(access, None, None)
        ),
        "me": team["me"],
        "team": team,
        "groups": [board(group=g)[0] for g in access.groups],
        "departments": [board(d)[0] for d in access.departments],
        "streaks": streaks,
        "personal_bests": personal_bests(user, today, streaks["best_on_time_days"]),
        "badges": earned_badges(user),
        "challenge": weekly_challenge(user, today),
        "move_up": None if closed else move_up(ranked, user, tasks, period, today),
    }


# --- badges at period close ------------------------------------------------------


def award_badges(period: str, start, end, data: dict) -> None:
    """The badges earned in a period that just closed (close_period's numbers), each
    stored and told once. Days bring streaks; weeks bring key task closers, zero
    overdue weeks, department top 3s and champions; months bring champions."""
    start, end = getdate(start), getdate(end)
    if period == "today":
        found = streak_awards(end)
    elif period == "week":
        found = [
            *key_closer_awards(data),
            *zero_overdue_awards(start, end, data),
            *podium_awards(data),
            *champion_awards("Week", start),
        ]
    elif period == "month":
        found = champion_awards("Month", start)
    else:
        return
    period_type = td.PERIODS[period][0]
    for user, badge, department, detail in found:
        award(user, badge, period_type, start, end, department, detail)


def award(user, badge, period_type, start, end, department, detail):
    """Store one badge and tell its owner, unless it was awarded already."""
    from helpdesk.helpdesk.doctype.hd_badge_award.hd_badge_award import HDBadgeAward

    name = HDBadgeAward.record_name(badge, user, start, department)
    if frappe.db.exists(BADGE, name) or not frappe.db.exists("User", user):
        return None
    try:
        doc = frappe.get_doc(
            {
                "doctype": BADGE,
                "user": user,
                "badge": badge,
                "period_type": period_type,
                "period_start": start,
                "period_end": end,
                "department": department,
                "detail": detail,
                "earned_on": add_days(end, 1),
            }
        ).insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        # an overlapping run of the same close awarded it first
        return None
    if badge not in SILENT_BADGES:
        notify_users(
            [user],
            BADGE,
            doc.name,
            _("You earned “{0}”: {1}").format(badge_catalog()[badge]["label"], detail),
            link="/team-dashboard",
        )
    return doc


def streak_awards(day) -> list[tuple]:
    """Whoever's on-time streak reached STREAK_BADGE_DAYS on `day`."""
    start = getdate(add_days(day, -STREAK_LOOKBACK_DAYS))
    is_working = working_day_checker(start, add_days(day, MAX_DAYS_OFF_IN_A_ROW))
    if not is_working(getdate(day)):
        return []
    # the day is over: anything due on it and still open is late
    as_of = add_days(day, 1)
    found = []
    for user, days in outcomes_by_day(
        due_tasks(start, day, as_of), as_of, is_working
    ).items():
        run, _best, counted = streak_run(days, start, day, as_of, is_working)
        if counted == getdate(day) and run == STREAK_BADGE_DAYS:
            found.append(
                (
                    user,
                    "on_time_streak",
                    None,
                    _(
                        "{0} working days in a row with everything due done on time, to {1}"
                    ).format(run, formatdate(day, "d MMM yyyy")),
                )
            )
    return found


def key_closer_awards(data: dict) -> list[tuple]:
    counts = defaultdict(int)
    for t in data["tasks"]:
        if t["key"] and t["on_time"]:
            for user in t["users"]:
                counts[user] += 1
    return [
        (
            user,
            "key_closer",
            None,
            _("{0} key tasks or milestones done on time in the week").format(n),
        )
        for user, n in counts.items()
        if n >= KEY_CLOSER_MIN
    ]


def zero_overdue_awards(start, end, data: dict) -> list[tuple]:
    """Everything due in the week done on time, at least ZERO_OVERDUE_MIN_DUE tasks,
    and nothing overdue when it closed (close_period counts overdue the day after)."""
    as_of = add_days(end, 1)
    late_now = {u for t in data["overdue"] for u in t["users"]}
    results = defaultdict(list)
    for row in due_tasks(start, end, as_of):
        result = outcome(row, as_of)
        if result != WAITING:
            for user in row["users"]:
                results[user].append(result)
    return [
        (
            user,
            "zero_overdue_week",
            None,
            _("All {0} tasks due in the week done on time, nothing overdue").format(
                len(found)
            ),
        )
        for user, found in results.items()
        if len(found) >= ZERO_OVERDUE_MIN_DUE
        and all(r == ON_TIME for r in found)
        and user not in late_now
    ]


def podium_awards(data: dict) -> list[tuple]:
    """The top PODIUM_SIZE of each active department who reached the week's minimum
    activity, ranked by score() as the champion is."""
    by_department = td.tally(data, lambda r: r["department"])
    found = []
    for department in td.active_departments():
        ranked = td.rank(by_department.get(department, {}), "week")
        top = [r for r in ranked if r["eligible"]][:PODIUM_SIZE]
        for place, row in enumerate(top, start=1):
            found.append(
                (
                    row["user"],
                    "podium",
                    department,
                    _("No. {0} in {1} with {2} points").format(
                        place, department, row["score"]
                    ),
                )
            )
    return found


def champion_awards(period_type: str, start) -> list[tuple]:
    """The period's stored champions (HD Team Champion), one badge per person."""
    champion = frappe.qb.DocType("HD Team Champion")
    scopes = defaultdict(list)
    for user, department in (
        frappe.qb.from_(champion)
        .select(champion.user, champion.department)
        .where(
            (champion.period_type == period_type)
            & (champion.period_start == getdate(start))
            & champion.user.isnotnull()
        )
        .run()
    ):
        scopes[user].append(department or _("the whole team"))
    return [
        (
            user,
            PERIOD_BADGES[period_type],
            None,
            _("Champion of {0}").format(", ".join(sorted(found))),
        )
        for user, found in scopes.items()
    ]
