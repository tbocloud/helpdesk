"""Content calendar performance by employee.

A post counts for everyone on it: writer, designer and digital marketer. Each
post that is due gets a delivery score:

- published on or before its publish date: 100
- published after it: 60
- due and still not published: 0
- minus 10 for every time the client asked for changes (never below 0)

Posts not due yet, and cancelled posts, are listed but not scored. Who sees
whom follows helpdesk.api.performance.visible_employees.
"""

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, get_datetime, getdate, now_datetime

from helpdesk.api.performance import check_range, resolve_scope, sees_everyone

ROLES = ("writer", "designer", "marketer")
ON_TIME, LATE, MISSED = 100, 60, 0
CHANGE_PENALTY = 10
CHANGES_REQUESTED = "Changes Requested"


def period_posts(start, end) -> list[dict]:
    Post = frappe.qb.DocType("HD Content Post")
    return (
        frappe.qb.from_(Post)
        .select(
            Post.name,
            Post.title,
            Post.customer,
            Post.status,
            Post.format,
            Post.channel,
            Post.platforms,
            Post.publish_on,
            Post.published_on,
            Post.times_postponed,
            Post.writer,
            Post.designer,
            Post.marketer,
        )
        .where(Post.publish_on[f"{start} 00:00:00":f"{end} 23:59:59"])
        .where(Post.status != "Cancelled")
        .orderby(Post.publish_on)
        .run(as_dict=True)
    )


def change_requests(post_names: list[str]) -> dict[str, int]:
    """How many times each post was sent back by the client, from its change history."""
    if not post_names:
        return {}
    counts: dict[str, int] = defaultdict(int)
    for version in frappe.get_all(
        "Version",
        filters={
            "ref_doctype": "HD Content Post",
            "docname": ("in", post_names),
            "data": ("like", f"%{CHANGES_REQUESTED}%"),
        },
        fields=["docname", "data"],
    ):
        try:
            changed = json.loads(version.data or "{}").get("changed", [])
        except ValueError:
            continue
        if any(c[0] == "status" and c[2] == CHANGES_REQUESTED for c in changed):
            counts[version.docname] += 1
    return counts


def timing(post, now) -> str:
    if post.status == "Published":
        if post.published_on and getdate(post.published_on) > getdate(post.publish_on):
            return "Late"
        return "On time"
    return "Missed" if get_datetime(post.publish_on) < now else "Upcoming"


def score(timing_: str, changes: int) -> int | None:
    base = {"On time": ON_TIME, "Late": LATE, "Missed": MISSED}.get(timing_)
    if base is None:
        return None
    return max(base - CHANGE_PENALTY * changes, 0)


def platforms_of(post) -> list[str]:
    raw = [p.strip() for p in (post.platforms or "").split(",")]
    return [p for p in raw if p] or ([post.channel] if post.channel else [])


def avg(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values)) if values else None


def pct(part, whole) -> int | None:
    return round(part / whole * 100) if whole else None


def summarise(posts: list[dict]) -> dict:
    scored = [p for p in posts if p["score"] is not None]
    delivered = [p for p in posts if p["timing"] in ("On time", "Late")]
    return {
        "posts": len(posts),
        "published": len(delivered),
        "missed": sum(p["timing"] == "Missed" for p in posts),
        "upcoming": sum(p["timing"] == "Upcoming" for p in posts),
        "on_time": sum(p["timing"] == "On time" for p in posts),
        "on_time_pct": pct(
            sum(p["timing"] == "On time" for p in posts), len(delivered)
        ),
        "avg_score": avg(p["score"] for p in scored),
        "change_requests": sum(p["changes"] for p in posts),
        "postponed": sum(1 for p in posts if p["times_postponed"]),
    }


def scored_posts(start, end) -> list[dict]:
    now = now_datetime()
    raw = period_posts(start, end)
    changes = change_requests([p.name for p in raw])
    posts = []
    for p in raw:
        t = timing(p, now)
        n = changes.get(p.name, 0)
        posts.append(
            {
                "name": p.name,
                "title": p.title,
                "customer": p.customer,
                "status": p.status,
                "format": p.format,
                "platforms": platforms_of(p),
                "publish_on": str(p.publish_on),
                "timing": t,
                "changes": n,
                "times_postponed": p.times_postponed or 0,
                "score": score(t, n),
                "team": {r: p.get(r) for r in ROLES},
            }
        )
    return posts


@frappe.whitelist()
def get_content_performance(
    from_date: str,
    to_date: str,
    employee: str | None = None,
    department: str | None = None,
) -> dict:
    start, end = check_range(from_date, to_date)
    people = resolve_scope(None, department)
    if employee and employee not in {p.employee for p in people}:
        frappe.throw(
            _("You can't view this employee's performance."), frappe.PermissionError
        )

    posts = scored_posts(start, end)

    by_user = defaultdict(list)
    for post in posts:
        for user in {u for u in post["team"].values() if u}:
            by_user[user].append(post)

    team = []
    for person in people:
        mine = by_user.get(person.user_id, [])
        if not mine:
            continue
        team.append(
            {
                "employee": person.employee,
                "employee_name": person.employee_name,
                "image": person.image,
                "designation": person.designation,
                **summarise(mine),
            }
        )
    # ranked by average score; people with nothing scored yet go last
    team.sort(
        key=lambda r: (r["avg_score"] is None, -(r["avg_score"] or 0), -r["posts"])
    )
    for rank, row in enumerate(team, start=1):
        row["rank"] = rank

    # the team's posts, each once, however many of the team worked on it
    user_of = {p.employee: p.user_id for p in people}
    team_posts = {
        post["name"]: post
        for row in team
        for post in by_user.get(user_of[row["employee"]], [])
    }
    team_summary = summarise(list(team_posts.values()))

    selected = employee or (team[0]["employee"] if team else None)
    detail = None
    if selected:
        person = next(p for p in people if p.employee == selected)
        mine = by_user.get(person.user_id, [])
        row = next((r for r in team if r["employee"] == selected), None)
        detail = {
            "employee": person.employee,
            "employee_name": person.employee_name,
            "image": person.image,
            "designation": person.designation,
            "rank": row["rank"] if row else None,
            "ranked_of": len(team),
            "summary": summarise(mine),
            "posts": [
                {**p, "roles": [r for r in ROLES if p["team"][r] == person.user_id]}
                for p in mine
            ],
            "channels": channel_mix(mine),
        }

    return {
        "from_date": str(start),
        "to_date": str(end),
        "team": team,
        "team_summary": team_summary,
        "detail": detail,
    }


def channel_mix(posts: list[dict]) -> list[dict]:
    mix = defaultdict(list)
    for post in posts:
        for platform in post["platforms"]:
            mix[platform].append(post["score"])
    return sorted(
        (
            {"channel": c, "posts": len(scores), "avg_score": avg(scores)}
            for c, scores in mix.items()
        ),
        key=lambda r: (-r["posts"], -(r["avg_score"] or 0)),
    )


# ------------------------------------------------------------- by customer --


@frappe.whitelist()
def get_customer_performance(
    from_date: str,
    to_date: str,
    customer: str | None = None,
    department: str | None = None,
) -> dict:
    """Content delivery per customer, and who on the team worked on each."""
    start, end = check_range(from_date, to_date)
    people = resolve_scope(None, department)
    person_of = {p.user_id: p for p in people}
    posts = scored_posts(start, end)
    # people who see everyone also see posts nobody is on yet
    if department or not sees_everyone(frappe.session.user):
        posts = [p for p in posts if set(p["team"].values()) & person_of.keys()]

    by_customer = defaultdict(list)
    for post in posts:
        by_customer[post["customer"] or ""].append(post)

    customers = sorted(
        (
            {
                "customer": name,
                **summarise(mine),
                "people": len(contributors(mine, person_of)),
            }
            for name, mine in by_customer.items()
        ),
        key=lambda r: (-r["posts"], r["avg_score"] is None, -(r["avg_score"] or 0)),
    )

    selected = customer if customer in by_customer else None
    if selected is None and customers and customer is None:
        selected = customers[0]["customer"]
    detail = None
    if selected is not None:
        mine = by_customer[selected]
        detail = {
            "customer": selected,
            "summary": summarise(mine),
            "people": people_on(mine, person_of),
            "posts": [
                {**p, "team": {r: team_member(p["team"][r], person_of) for r in ROLES}}
                for p in mine
            ],
            "channels": channel_mix(mine),
            "formats": format_mix(mine),
        }

    return {
        "from_date": str(start),
        "to_date": str(end),
        "summary": {**summarise(posts), "customers": len(customers)},
        "customers": customers,
        "trend": trend(posts, start, end),
        "detail": detail,
    }


def contributors(posts: list[dict], person_of: dict) -> set[str]:
    return {u for p in posts for u in p["team"].values() if u in person_of}


def people_on(posts: list[dict], person_of: dict) -> list[dict]:
    """Each team member on these posts: what they did and how it went."""
    rows = []
    for user in contributors(posts, person_of):
        person = person_of[user]
        theirs = [p for p in posts if user in p["team"].values()]
        rows.append(
            {
                "employee": person.employee,
                "employee_name": person.employee_name,
                "image": person.image,
                "designation": person.designation,
                "roles": {
                    r: sum(p["team"][r] == user for p in theirs) for r in ROLES
                },
                **summarise(theirs),
            }
        )
    return sorted(
        rows,
        key=lambda r: (r["avg_score"] is None, -(r["avg_score"] or 0), -r["posts"]),
    )


def team_member(user: str | None, person_of: dict) -> dict | None:
    if not user:
        return None
    person = person_of.get(user)
    return {
        "user": user,
        "name": person.employee_name if person else frappe.utils.get_fullname(user),
        "employee": person.employee if person else None,
    }


def format_mix(posts: list[dict]) -> list[dict]:
    counts = defaultdict(int)
    for post in posts:
        counts[post["format"] or _("Other")] += 1
    return sorted(
        ({"format": f, "posts": n} for f, n in counts.items()),
        key=lambda r: -r["posts"],
    )


def trend(posts: list[dict], start, end) -> dict:
    """Posts due per day (per week for periods over a month), split by how they went."""
    weekly = date_diff(end, start) > 31
    bucket_of = (
        (lambda d: add_days(d, -d.weekday())) if weekly else (lambda d: d)
    )
    buckets = []
    day = bucket_of(start)
    while day <= end:
        buckets.append(day)
        day = add_days(day, 7 if weekly else 1)
    counts = {b: defaultdict(int) for b in buckets}
    for post in posts:
        b = bucket_of(getdate(post["publish_on"]))
        if b in counts:
            counts[b][post["timing"]] += 1
    timings = ("On time", "Late", "Missed", "Upcoming")
    return {
        "bucket": "week" if weekly else "day",
        "dates": [str(b) for b in buckets],
        "series": {t: [counts[b][t] for b in buckets] for t in timings},
    }
