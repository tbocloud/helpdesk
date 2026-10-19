"""Sales on the Scoreboard: salespeople scored on their CRM activity.

Leads live in ERPNext on the CRM site (docs/leads.md), so the activity is read
from there (TBO Smart's `hub_leads.get_sales_activity`, counts per person, no
lead named) and counted in the **CRM** department, under **Sales**. The points
below join the task score in `helpdesk.team_dashboard.score()`, so a person with
project tasks and sales work has one score, one rank and can be champion like
anyone else. When the CRM site can't be reached the Scoreboard still works; the
Sales rows say why their numbers are missing. See docs/team-dashboard.md, Sales.
"""

import frappe
from frappe import _

from helpdesk.integrations.crm.client import CRMClient, CRMError
from helpdesk.integrations.crm.leads import API, friendly_error, leads_on

# where the activity counts: CRM, a sub-department of Sales (DEFAULT_GROUPS)
SALES_DEPARTMENT = "CRM"
OK, OFF, UNAVAILABLE = "ok", "off", "unavailable"
# under the Scoreboard's prefix, so its clear_cache() drops these too
CACHE_PREFIX = "team_dashboard:sales"
CACHE_SECONDS = 300
# a failure is asked again sooner, so the Sales rows come back once the site does
FAILURE_CACHE_SECONDS = 60
LAKH = 100000

# what the CRM site counts per person -> the person's stats on the Scoreboard
FIELDS = {
    "contacted": "sales_contacted",
    "moms_submitted": "sales_meetings",
    "quotations_sent": "sales_proposals",
    "follow_ups_done": "sales_follow_ups",
    "follow_ups_on_time": "sales_follow_ups_on_time",
    "won": "sales_won",
    "won_value": "sales_won_value",
    "new": "sales_new",
    # today's state: only for the period in progress
    "mom_pending": "sales_mom_pending",
    "follow_ups_overdue": "sales_follow_ups_overdue",
}
NOW_FIELDS = ("mom_pending", "follow_ups_overdue")

# Points, in the spirit of the task score: what moves a deal forward is worth
# most, a lead contacted a little, a win most; minutes not written and
# follow-ups let slip cost points, as overdue tasks do.
WEIGHTS = {
    "contacted": 0.25,
    "follow_up_on_time": 0.25,
    "meeting": 1.5,
    "proposal": 1.5,
    "won": 4.0,
    # the deal's size: +1 per lakh won, at most +4 a won lead
    "won_per_lakh": 1.0,
    "won_value_cap": 4.0,
    "mom_pending": -0.5,
    "follow_up_overdue": -0.5,
}


def blank() -> dict:
    return dict.fromkeys(FIELDS.values(), 0)


def activity(start, end, with_overdue: bool = True) -> dict:
    """{status, message, currency, rows}: each person's activity in the period as
    Scoreboard rows (department CRM). `status` is off while Leads aren't set up,
    unavailable (with the reason) when the CRM site can't answer. Cached briefly."""
    if not leads_on():
        return {"status": OFF, "message": None, "currency": None, "rows": []}
    key = f"{CACHE_PREFIX}:{start}:{end}"
    found = frappe.cache.get_value(key, expires=True)
    if found is None:
        found = fetch(start, end)
        frappe.cache.set_value(
            key,
            found,
            expires_in_sec=CACHE_SECONDS
            if found["status"] == OK
            else FAILURE_CACHE_SECONDS,
        )
    rows = [
        {
            "department": SALES_DEPARTMENT,
            "project": None,
            "user": person["user"],
            **{
                stat: (person.get(field) or 0)
                if with_overdue or field not in NOW_FIELDS
                else 0
                for field, stat in FIELDS.items()
            },
        }
        for person in found["people"]
        if person.get("user")
    ]
    return {
        "status": found["status"],
        "message": found["message"],
        "currency": found["currency"],
        "rows": rows,
    }


def fetch(start, end) -> dict:
    """The CRM site's answer, or why there is none. The hub asks as its own API
    user: the Scoreboard is open to everyone and closes periods at night."""
    try:
        client = CRMClient.from_settings()
    except CRMError:
        return unavailable(
            _("The ERP site isn't connected. Ask an admin to set up Settings → CRM.")
        )
    try:
        result = client.call(
            f"{API}.get_sales_activity", from_date=str(start), to_date=str(end)
        )
    except CRMError as e:
        return unavailable(str(friendly_error(e, client.base)))
    result = result if isinstance(result, dict) else {}
    return {
        "status": OK,
        "message": None,
        "currency": result.get("currency"),
        "people": [p for p in result.get("people") or [] if isinstance(p, dict)],
    }


def unavailable(message: str) -> dict:
    return {"status": UNAVAILABLE, "message": message, "currency": None, "people": []}


def add(stats: dict, row: dict):
    """Adds one activity row to a person's stats (team_dashboard.tally)."""
    for stat in FIELDS.values():
        stats[stat] += row.get(stat) or 0


def delivered(stats: dict) -> int:
    """Sales work done: leads contacted, meetings with minutes, proposals sent,
    leads won."""
    return (
        stats["sales_contacted"]
        + stats["sales_meetings"]
        + stats["sales_proposals"]
        + stats["sales_won"]
    )


def weighted(stats: dict) -> float:
    """Sales work by its weight, for the champion's minimum (like weighted work)."""
    w = WEIGHTS
    return (
        stats["sales_contacted"] * w["contacted"]
        + stats["sales_follow_ups_on_time"] * w["follow_up_on_time"]
        + stats["sales_meetings"] * w["meeting"]
        + stats["sales_proposals"] * w["proposal"]
        + stats["sales_won"] * w["won"]
    )


def parts(stats: dict) -> dict:
    """The score's sales parts."""
    w = WEIGHTS
    value_bonus = min(
        stats["sales_won_value"] / LAKH * w["won_per_lakh"],
        stats["sales_won"] * w["won_value_cap"],
    )
    return {
        "sales_activity": stats["sales_contacted"] * w["contacted"]
        + stats["sales_follow_ups_on_time"] * w["follow_up_on_time"],
        "sales_meetings": stats["sales_meetings"] * w["meeting"],
        "sales_proposals": stats["sales_proposals"] * w["proposal"],
        "sales_won": stats["sales_won"] * w["won"] + value_bonus,
        "sales_slips": stats["sales_mom_pending"] * w["mom_pending"]
        + stats["sales_follow_ups_overdue"] * w["follow_up_overdue"],
    }


def detail(key: str, s: dict) -> str:
    """What one sales part of the score stands for, in words."""
    if key == "sales_activity":
        return _("Leads contacted: {0}, follow-ups on time {1} of {2}").format(
            s["sales_contacted"], s["sales_follow_ups_on_time"], s["sales_follow_ups"]
        )
    if key == "sales_meetings":
        return _("Meetings with minutes: {0}").format(s["sales_meetings"])
    if key == "sales_proposals":
        return _("Proposals sent: {0}").format(s["sales_proposals"])
    if key == "sales_won":
        return _("Leads won: {0}, worth {1}").format(
            s["sales_won"], frappe.utils.fmt_money(s["sales_won_value"], precision=0)
        )
    return _("Minutes pending: {0}, follow-ups overdue: {1}").format(
        s["sales_mom_pending"], s["sales_follow_ups_overdue"]
    )


def figures(stats: dict) -> dict | None:
    """A person's or a scope's sales numbers for the page; None without any."""
    if not any(stats[stat] for stat in FIELDS.values()):
        return None
    return {field: stats[stat] for field, stat in FIELDS.items()} | {
        "conversion": round(stats["sales_won"] / stats["sales_new"] * 100)
        if stats["sales_new"]
        else None
    }
