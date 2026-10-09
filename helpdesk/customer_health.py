"""Customer health: one status per customer (Healthy, Watch, At risk) and the reasons.

Eight signals, each judged ok, watch or at risk by a fixed rule, or skipped when
the customer has no data for it (a skipped signal never counts against them):

- tickets: new tickets in the last 30 days against the 30 days before
- sla: tickets raised in the last 30 days whose first reply or resolution was late
- waiting: open tickets waiting on us for more than WAITING_DAYS days
- rating: the customers' average rating over the last 90 days
- work: overdue tasks and key tasks at risk in the customer's open projects
- contract: support hours used against the time gone in the current period
- signoff: sign-offs that need clarification or have escalated items
- erp: the customer's ERP connection in Error or Disconnected

A watch signal scores its weight and an at-risk one twice its weight; the
total decides the status. Everything is computed for all customers at once
(a handful of grouped queries, no query per customer) and cached for
CACHE_SECONDS. See docs/customer-health.md.
"""

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Avg, Coalesce, Count, Sum
from frappe.utils import add_days, flt, getdate, now_datetime, nowdate

from helpdesk.support_contracts import contract_usage, current_contracts, shown_period

HEALTHY = "healthy"
WATCH = "watch"
AT_RISK = "at_risk"
# every signal skipped: nothing to judge the customer on yet
NO_DATA = "no_data"
STATUSES = (AT_RISK, WATCH, HEALTHY, NO_DATA)

OK = "ok"
SKIPPED = "skipped"
STATE_FACTOR = {OK: 0, SKIPPED: 0, WATCH: 1, AT_RISK: 2}

# how much each signal counts, in the order the Health section lists them
WEIGHTS = {
    "sla": 3,
    "waiting": 2,
    "tickets": 1,
    "rating": 2,
    "work": 2,
    "contract": 2,
    "signoff": 2,
    "erp": 1,
}
AT_RISK_POINTS = 6
WATCH_POINTS = 2

TICKET_DAYS = 30
RATING_DAYS = 90
WAITING_DAYS = 3
# new tickets: watch at TREND_WATCH or more and TREND_WATCH_RATIO times the
# 30 days before; at risk at TREND_RISK or more and TREND_RISK_RATIO times
TREND_WATCH, TREND_WATCH_RATIO = 5, 1.5
TREND_RISK, TREND_RISK_RATIO = 10, 2.0
SLA_WATCH, SLA_RISK = 1, 3
WAITING_WATCH, WAITING_RISK = 1, 3
# average stars out of 5 below which the rating is watch / at risk
RATING_WATCH, RATING_RISK = 4.0, 3.0
WORK_RISK_OVERDUE = 3
# support hours burning fast: at least BURN_MIN % used and BURN_MARGIN points
# ahead of the share of the period that has gone
BURN_MIN, BURN_MARGIN = 50, 20

SLA_FAILED = "Failed"
OPEN_SIGNOFF_STATUSES = (
    "Sent",
    "In progress",
    "Needs clarification",
    "Ready to sign",
    "Reopened",
)
NEEDS_CLARIFICATION = "Needs clarification"
ESCALATED = "Escalated"

CACHE_KEY = "helpdesk:customer_health"
CACHE_SECONDS = 600


# --- cache ---


def all_health() -> dict[str, dict]:
    """{customer: health} for every customer, from the cache when it's fresh."""
    # expires=True: otherwise a miss is kept as None in the request's local
    # cache and every later call in the same request recomputes
    cached = frappe.cache.get_value(CACHE_KEY, expires=True)
    if cached is None:
        cached = compute_all_health()
        frappe.cache.set_value(CACHE_KEY, cached, expires_in_sec=CACHE_SECONDS)
    return cached


def clear_health_cache(*args, **kwargs):
    """doc_events (any signature, after_rename passes more): a contract, sign-off,
    connection or customer changed."""
    frappe.cache.delete_value(CACHE_KEY)


def readable(customers) -> list[str]:
    """The customers the session user may read."""
    names = [c for c in customers if c]
    if not names:
        return []
    return frappe.get_list(
        "HD Customer",
        filters={"name": ("in", names)},
        pluck="name",
        limit_page_length=0,
    )


# --- computing ---


def compute_all_health() -> dict[str, dict]:
    customers = frappe.get_all("HD Customer", pluck="name")
    if not customers:
        return {}
    today = getdate(nowdate())
    tickets = ticket_facts()
    ratings = rating_facts()
    work = work_facts()
    contracts = contract_facts(today)
    signoffs = signoff_facts()
    connections = erp_facts(customers)
    result = {}
    for customer in customers:
        t = tickets.get(customer, {})
        result[customer] = combine(
            [
                judge_sla(t.get("failed", 0), t.get("tracked", 0)),
                judge_waiting(t.get("waiting", 0), t.get("open", 0)),
                judge_tickets(t.get("new", 0), t.get("previous", 0)),
                judge_rating(**ratings.get(customer, {})),
                judge_work(**work.get(customer, {})),
                judge_contract(contracts.get(customer)),
                judge_signoff(**signoffs.get(customer, {})),
                judge_erp(connections.get(customer)),
            ]
        )
    return result


def ticket_facts() -> dict[str, dict]:
    """Per customer: new tickets in the last and previous 30 days, SLA tracked and
    failed among the new ones, open tickets and how many of those wait on us."""
    Ticket = frappe.qb.DocType("HD Ticket")
    now = now_datetime()
    since = add_days(now, -TICKET_DAYS)
    before = add_days(now, -2 * TICKET_DAYS)
    is_new = Ticket.creation >= since
    is_open = Ticket.status_category == "Open"
    waiting_since = Coalesce(Ticket.last_customer_response, Ticket.creation)

    def count(condition):
        return Sum(Case().when(condition, 1).else_(0))

    rows = (
        frappe.qb.from_(Ticket)
        .select(
            Ticket.customer,
            count(is_new).as_("new"),
            count((Ticket.creation >= before) & (Ticket.creation < since)).as_(
                "previous"
            ),
            count(is_new & Ticket.sla.notnull() & (Ticket.sla != "")).as_("tracked"),
            count(is_new & (Ticket.agreement_status == SLA_FAILED)).as_("failed"),
            count(is_open).as_("open"),
            count(is_open & (waiting_since < add_days(now, -WAITING_DAYS))).as_(
                "waiting"
            ),
        )
        .where(Ticket.customer.notnull() & (Ticket.customer != ""))
        .where((Ticket.creation >= before) | is_open)
        .groupby(Ticket.customer)
        .run(as_dict=True)
    )
    return {
        r.customer: {
            key: int(r[key] or 0)
            for key in ("new", "previous", "tracked", "failed", "open", "waiting")
        }
        for r in rows
    }


def rating_facts() -> dict[str, dict]:
    """Per customer: how many tickets resolved in the last 90 days were rated, and the average stars."""
    Ticket = frappe.qb.DocType("HD Ticket")
    rows = (
        frappe.qb.from_(Ticket)
        .select(
            Ticket.customer,
            Count(Ticket.name).as_("count"),
            Avg(Ticket.feedback_rating).as_("average"),
        )
        .where(Ticket.customer.notnull() & (Ticket.customer != ""))
        .where(Ticket.feedback_rating > 0)
        .where(Ticket.resolution_date >= add_days(now_datetime(), -RATING_DAYS))
        .groupby(Ticket.customer)
        .run(as_dict=True)
    )
    # ratings are stored as 0-1
    return {
        r.customer: {"count": r.count, "average": round(flt(r.average) * 5, 1)}
        for r in rows
    }


def work_facts() -> dict[str, dict]:
    """Per customer: open tasks in its open projects, judged like the Overview's
    overdue and at-risk buckets (helpdesk.api.work)."""
    from helpdesk.api.directory import CLOSED_PROJECT_STATUSES
    from helpdesk.api.work import (
        OPEN_TASK_FILTER,
        TASK_FIELDS,
        _open_dependencies,
        _task_item,
    )

    projects = dict(
        frappe.get_all(
            "Project",
            filters={"customer": ("is", "set"), "status": CLOSED_PROJECT_STATUSES},
            fields=["name", "customer"],
            as_list=True,
        )
    )
    if not projects:
        return {}
    tasks = frappe.get_all(
        "Task",
        filters={"project": ("in", list(projects)), "status": OPEN_TASK_FILTER},
        fields=TASK_FIELDS,
        limit_page_length=0,
    )
    waiting = _open_dependencies(tasks)
    facts: dict[str, dict] = {}
    for task in tasks:
        item = _task_item(task, {}, waiting)
        row = facts.setdefault(
            projects[task.project],
            {"open_tasks": 0, "overdue": 0, "overdue_key": 0, "key_at_risk": 0},
        )
        row["open_tasks"] += 1
        row["overdue"] += item["is_overdue"]
        row["overdue_key"] += item["is_overdue"] and item["is_key"]
        row["key_at_risk"] += bool(item["is_key"] and item["risks"])
    return facts


def contract_facts(today) -> dict[str, dict]:
    """Per customer: today's support contract period and how much of it has gone.

    Active contracts can't overlap, so a customer has at most one running today.
    """
    contracts = current_contracts(today)
    usage = contract_usage(contracts, today)
    facts = {}
    for contract in contracts:
        period = shown_period(usage[contract.name])
        if not period:
            continue
        start, end = getdate(period["start"]), getdate(period["end"])
        facts[contract.customer] = {
            "contract": contract.name,
            "percent": period["percent"],
            "used": period["used"],
            "allowance": period["allowance"],
            "remaining": period["remaining"],
            "elapsed": round(
                100 * ((today - start).days + 1) / ((end - start).days + 1)
            ),
        }
    return facts


def signoff_facts() -> dict[str, dict]:
    """Per customer: sign-offs in progress, those needing clarification, escalated
    items, and the projects with a sign-off that needs us."""
    Signoff = frappe.qb.DocType("HD Project Signoff")
    Item = frappe.qb.DocType("HD Project Signoff Item")
    rows = (
        frappe.qb.from_(Signoff)
        .left_join(Item)
        .on(
            (Item.parent == Signoff.name)
            & (Item.parenttype == "HD Project Signoff")
            & (Item.response == ESCALATED)
        )
        .select(
            Signoff.customer,
            Signoff.project,
            Signoff.status,
            Count(Item.name).as_("escalated"),
        )
        .where(Signoff.customer.notnull() & (Signoff.customer != ""))
        .where(Signoff.status.isin(OPEN_SIGNOFF_STATUSES))
        .groupby(Signoff.name)
        .run(as_dict=True)
    )
    facts: dict[str, dict] = {}
    for r in rows:
        row = facts.setdefault(
            r.customer,
            {
                "in_progress": 0,
                "needs_clarification": 0,
                "escalated": 0,
                "projects": [],
            },
        )
        row["in_progress"] += 1
        row["needs_clarification"] += r.status == NEEDS_CLARIFICATION
        row["escalated"] += r.escalated
        if (r.status == NEEDS_CLARIFICATION or r.escalated) and r.project not in row[
            "projects"
        ]:
            row["projects"].append(r.project)
    return facts


def erp_facts(customers: list[str]) -> dict[str, str]:
    """Per customer: the status of its latest ERP connection."""
    from helpdesk.api.directory import connection_status

    return {
        customer: connection["status"]
        for customer, connection in connection_status(
            customers, ignore_permissions=True
        ).items()
    }


# --- rules ---


def signal(key: str, state: str, **facts) -> dict:
    return {"key": key, "state": state, "facts": facts}


def judge_tickets(new: int, previous: int) -> dict:
    if not new and not previous:
        return signal("tickets", SKIPPED)
    state = OK
    if new >= TREND_RISK and new >= previous * TREND_RISK_RATIO:
        state = AT_RISK
    elif new >= TREND_WATCH and new >= previous * TREND_WATCH_RATIO:
        state = WATCH
    return signal("tickets", state, new=new, previous=previous)


def judge_sla(failed: int, tracked: int) -> dict:
    if not tracked:
        return signal("sla", SKIPPED)
    return signal(
        "sla", by_count(failed, SLA_WATCH, SLA_RISK), failed=failed, tracked=tracked
    )


def judge_waiting(waiting: int, open_tickets: int) -> dict:
    if not open_tickets:
        return signal("waiting", SKIPPED)
    return signal(
        "waiting",
        by_count(waiting, WAITING_WATCH, WAITING_RISK),
        waiting=waiting,
        open=open_tickets,
    )


def judge_rating(count: int = 0, average: float | None = None) -> dict:
    if not count:
        return signal("rating", SKIPPED)
    state = OK
    if average < RATING_RISK:
        state = AT_RISK
    elif average < RATING_WATCH:
        state = WATCH
    return signal("rating", state, count=count, average=average)


def judge_work(
    open_tasks: int = 0, overdue: int = 0, overdue_key: int = 0, key_at_risk: int = 0
) -> dict:
    if not open_tasks:
        return signal("work", SKIPPED)
    state = OK
    if overdue >= WORK_RISK_OVERDUE or overdue_key:
        state = AT_RISK
    elif overdue or key_at_risk:
        state = WATCH
    return signal(
        "work",
        state,
        open_tasks=open_tasks,
        overdue=overdue,
        overdue_key=overdue_key,
        key_at_risk=key_at_risk,
    )


def judge_contract(period: dict | None) -> dict:
    if not period:
        return signal("contract", SKIPPED)
    state = OK
    if period["percent"] >= 100:
        state = AT_RISK
    elif (
        period["percent"] >= BURN_MIN
        and period["percent"] - period["elapsed"] >= BURN_MARGIN
    ):
        state = WATCH
    return signal("contract", state, **period)


def judge_signoff(
    in_progress: int = 0,
    needs_clarification: int = 0,
    escalated: int = 0,
    projects: list | None = None,
) -> dict:
    if not in_progress:
        return signal("signoff", SKIPPED)
    state = OK
    if escalated:
        state = AT_RISK
    elif needs_clarification:
        state = WATCH
    return signal(
        "signoff",
        state,
        in_progress=in_progress,
        needs_clarification=needs_clarification,
        escalated=escalated,
        projects=projects or [],
    )


def judge_erp(status: str | None) -> dict:
    if not status:
        return signal("erp", SKIPPED)
    state = {"Error": AT_RISK, "Disconnected": WATCH}.get(status, OK)
    return signal("erp", state, status=status)


def by_count(count: int, watch_at: int, risk_at: int) -> str:
    if count >= risk_at:
        return AT_RISK
    if count >= watch_at:
        return WATCH
    return OK


def combine(signals: list[dict]) -> dict:
    """The customer's status from its signals' points."""
    for s in signals:
        s["weight"] = WEIGHTS[s["key"]]
        s["points"] = s["weight"] * STATE_FACTOR[s["state"]]
    points = sum(s["points"] for s in signals)
    if all(s["state"] == SKIPPED for s in signals):
        status = NO_DATA
    elif points >= AT_RISK_POINTS:
        status = AT_RISK
    elif points >= WATCH_POINTS:
        status = WATCH
    else:
        status = HEALTHY
    return {"status": status, "points": points, "signals": signals}


def reasons(health: dict) -> list[str]:
    """The signals that count against the customer, worst first, as their labels."""
    flagged = sorted(
        (s for s in health["signals"] if s["points"]),
        key=lambda s: -s["points"],
    )
    return [signal_label(s["key"]) for s in flagged]


def brief(health: dict | None) -> dict | None:
    """What a list row shows: the status, its points and the reasons."""
    if not health:
        return None
    return {
        "status": health["status"],
        "points": health["points"],
        "reasons": reasons(health),
    }


def sort_key(health: dict | None):
    """Worst first: at risk, watch, healthy, no data; more points first within each."""
    status = health["status"] if health else NO_DATA
    return (STATUSES.index(status), -(health["points"] if health else 0))


# --- wording (built per request, so it follows the reader's language) ---


def signal_label(key: str) -> str:
    return {
        "sla": _("SLA breaches"),
        "waiting": _("Waiting on us"),
        "tickets": _("New tickets"),
        "rating": _("Customer rating"),
        "work": _("Project work"),
        "contract": _("Support hours"),
        "signoff": _("Sign-offs"),
        "erp": _("ERP connection"),
    }[key]


def signal_rule(key: str) -> str:
    return {
        "sla": _(
            "Tickets raised in the last {0} days whose first reply or resolution was late. Watch at {1}, at risk at {2} or more."
        ).format(TICKET_DAYS, SLA_WATCH, SLA_RISK),
        "waiting": _(
            "Open tickets whose last customer message (or opening) is over {0} days old. Watch at {1}, at risk at {2} or more."
        ).format(WAITING_DAYS, WAITING_WATCH, WAITING_RISK),
        "tickets": _(
            "New tickets in the last {0} days against the {0} before. Watch at {1} or more and {2}× as many; at risk at {3} or more and {4}× as many."
        ).format(
            TICKET_DAYS,
            TREND_WATCH,
            f"{TREND_WATCH_RATIO:g}",
            TREND_RISK,
            f"{TREND_RISK_RATIO:g}",
        ),
        "rating": _(
            "Average rating of tickets resolved in the last {0} days. Watch below {1}, at risk below {2}."
        ).format(RATING_DAYS, f"{RATING_WATCH:g}", f"{RATING_RISK:g}"),
        "work": _(
            "Open tasks in the customer's open projects. Watch at an overdue task or a key task at risk; at risk at {0} overdue or an overdue key task."
        ).format(WORK_RISK_OVERDUE),
        "contract": _(
            "Hours used in the current period against the time gone. Watch at {0}% used and {1} points ahead of the time; at risk when used up."
        ).format(BURN_MIN, BURN_MARGIN),
        "signoff": _(
            "Sign-offs in progress. Watch when one needs clarification; at risk when an item is escalated."
        ),
        "erp": _("At risk when the connection is in Error; watch when Disconnected."),
    }[key]


def signal_value(s: dict) -> str:
    f = s["facts"]
    if s["state"] == SKIPPED:
        return {
            "sla": _("No tickets with an SLA in the last {0} days").format(TICKET_DAYS),
            "waiting": _("No open tickets"),
            "tickets": _("No tickets in the last {0} days").format(2 * TICKET_DAYS),
            "rating": _("No ratings in the last {0} days").format(RATING_DAYS),
            "work": _("No open tasks in open projects"),
            "contract": _("No support contract running"),
            "signoff": _("No sign-off in progress"),
            "erp": _("No ERP connection"),
        }[s["key"]]
    key = s["key"]
    if key == "sla":
        return _("{0} of {1} tickets late").format(f["failed"], f["tracked"])
    if key == "waiting":
        return _("{0} of {1} open tickets waiting over {2} days").format(
            f["waiting"], f["open"], WAITING_DAYS
        )
    if key == "tickets":
        return _("{0} new, {1} in the {2} days before").format(
            f["new"], f["previous"], TICKET_DAYS
        )
    if key == "rating":
        return _("{0} out of 5 from {1} ratings").format(f["average"], f["count"])
    if key == "work":
        return _("{0} overdue, {1} key at risk, of {2} open tasks").format(
            f["overdue"], f["key_at_risk"], f["open_tasks"]
        )
    if key == "contract":
        if f["remaining"] < 0:
            return _("{0}% used, {1} h over").format(f["percent"], -f["remaining"])
        return _("{0}% used with {1}% of the period gone").format(
            f["percent"], f["elapsed"]
        )
    if key == "signoff":
        return _("{0} need clarification, {1} items escalated, of {2} open").format(
            f["needs_clarification"], f["escalated"], f["in_progress"]
        )
    return {
        "Error": _("Error"),
        "Disconnected": _("Disconnected"),
        "Connected": _("Connected"),
        "Pending": _("Pending"),
    }.get(f["status"], f["status"])


def signal_link(s: dict, customer: str) -> dict | None:
    """Where the signal's records are: a tickets filter, the customer's tabs, the Overview or a project's sign-offs."""
    key, f = s["key"], s["facts"]
    now = now_datetime()
    by_customer = ["customer", "=", customer]
    if key == "tickets":
        since = add_days(now, -TICKET_DAYS)
        return tickets_link([by_customer, ["creation", ">=", str(since)]])
    if key == "sla":
        since = add_days(now, -TICKET_DAYS)
        return tickets_link(
            [
                by_customer,
                ["creation", ">=", str(since)],
                ["agreement_status", "=", SLA_FAILED],
            ]
        )
    if key == "waiting":
        return tickets_link([by_customer, ["status_category", "=", "Open"]])
    if key == "rating":
        since = add_days(now, -RATING_DAYS)
        return tickets_link(
            [
                by_customer,
                ["feedback_rating", ">", 0],
                ["resolution_date", ">=", str(since)],
            ]
        )
    if key == "work":
        return {"kind": "work"}
    if key == "contract":
        return {"kind": "tab", "hash": "support-hours"}
    if key == "signoff":
        projects = f.get("projects") or []
        if len(projects) == 1:
            return {"kind": "signoff", "project": projects[0]}
        return {"kind": "tab", "hash": "projects"}
    return None


def tickets_link(filters: list) -> dict:
    return {"kind": "tickets", "filters": filters}


def present(health: dict, customer: str) -> dict:
    """A customer's health with every signal's label, value, rule and link."""
    return {
        "status": health["status"],
        "points": health["points"],
        "reasons": reasons(health),
        "thresholds": {"watch": WATCH_POINTS, "at_risk": AT_RISK_POINTS},
        "signals": [
            {
                "key": s["key"],
                "state": s["state"],
                "weight": s["weight"],
                "points": s["points"],
                "label": signal_label(s["key"]),
                "value": signal_value(s),
                "rule": signal_rule(s["key"]),
                "link": signal_link(s, customer) if s["state"] != SKIPPED else None,
            }
            for s in health["signals"]
        ],
    }
