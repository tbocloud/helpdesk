"""The sales dashboards (docs/sales-dashboard.md): a salesperson's own day (Sales → Dashboard)
and the team's (Sales → Team dashboard). Every figure is read live from the ERP site through
the Leads proxies; nothing is stored here. Each page is one request that reads its parts one
after another, as the Leads Overview does: the hub and the ERP site share one worker pool,
so parallel requests would wait on each other (docs/leads.md, "How the Overview loads")."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, today

from helpdesk.api import call_batches, leads
from helpdesk.content_team import manages_sales, only_sales_team
from helpdesk.integrations.crm.leads import LeadsError, call_if_deployed, require_leads

TEAM_PERIODS = ("today", "week", "month")
# a day that has ended no longer changes, so its calls are kept for an hour
CLOSED_DAY_TTL = 3600
FOLLOW_UP_ROWS = 3


@frappe.whitelist()
def get_my_dashboard(fresh: int | str = 0) -> dict:
    """The signed-in person's own figures: `calls` (Today's calls, never cached), `month`
    (their own leads this month: totals, pipeline, the AI's plan), `week` (called and
    contacted each day since Monday) and `follow_ups` (counts and the first few due). Each
    part is optional: one that fails is null with its message in `errors`."""
    require_leads()
    if manages_sales():
        frappe.throw(
            _(
                "The Dashboard is a salesperson's own day. Sales Heads and Sales Managers follow the team on the Team dashboard."
            ),
            frappe.PermissionError,
        )
    user = frappe.session.user
    page = {"calls": None, "month": None, "week": None, "follow_ups": None}
    page["errors"] = read_parts(
        page,
        (
            ("calls", call_batches.get_my_calls),
            ("month", lambda: own_month(user, fresh)),
            ("week", lambda: week_calls(user, fresh, own=True)),
            ("follow_ups", lambda: own_follow_ups(user, fresh)),
        ),
    )
    return page


@frappe.whitelist()
def get_team_dashboard(
    period: str = "today", owner: str | None = None, fresh: int | str = 0
) -> dict:
    """The team's figures for `period` (today, week or month), everyone's or one person's:
    `overview` (the Leads Overview's totals, pipeline, funnel and AI counts), `people` (each
    salesperson's calls in the period), `week` (each one's calls per day since Monday) and
    `handed_out` (today's call batches by slot). The overview is required; the rest are
    optional, with their messages in `errors`. Not for BDs."""
    require_leads()
    leads.refuse_bd()
    if period not in TEAM_PERIODS:
        frappe.throw(_("Pick today, this week or this month."))
    owner = owner or None
    page = {
        "period": period,
        "overview": team_overview(period, owner, fresh),
        "people": None,
        "week": None,
        "handed_out": None,
    }
    page["errors"] = read_parts(
        page,
        (
            ("people", lambda: team_calls(period, owner, fresh)),
            ("week", lambda: week_calls(owner, fresh)),
            ("handed_out", handed_out_today),
        ),
    )
    return page


def read_parts(page: dict, parts) -> dict:
    """Fills `page` with each part's answer; a part the ERP site refuses stays null and
    its message is returned by part, for the card's own error state."""
    errors = {}
    for part, read in parts:
        try:
            page[part] = read()
        except LeadsError as e:
            # frappe.throw queued the message for a toast; the card shows it in place
            frappe.clear_last_message()
            errors[part] = str(e)
    return errors


def own_month(user: str, fresh) -> dict:
    """The person's own leads this month, as the ERP site's overview counts them."""
    overview = leads.read_overview("month", None, None, user, fresh)
    ai = overview.get("ai") or {}
    return {
        "from_date": overview.get("from_date"),
        "to_date": overview.get("to_date"),
        "totals": overview.get("totals") or {},
        "pipeline": overview.get("pipeline") or [],
        "plan": ((ai.get("plan") or {}).get("rows") or []) if ai.get("enabled") else [],
    }


def own_follow_ups(user: str, fresh) -> dict:
    """How many of the person's follow-ups are due when, and the first few to make."""
    counts = leads.get_follow_up_counts(owner=user, fresh=fresh)
    rows = leads.list_leads(view="follow_up", owner=user, page_length=FOLLOW_UP_ROWS)
    return {
        "counts": counts,
        "rows": rows.get("rows") or [],
        "total": cint(rows.get("total")),
    }


def team_overview(period: str, owner: str | None, fresh) -> dict:
    """The Overview's figures for the period, with the owner picker cut to the sales team."""
    overview = leads.read_overview(period, None, None, owner, fresh)
    ai = overview.get("ai") or {}
    people, _empty = only_sales_team(overview.get("people") or [], keep=(owner,))
    return {
        "from_date": overview.get("from_date"),
        "to_date": overview.get("to_date"),
        "stale_days": overview.get("stale_days"),
        "totals": overview.get("totals") or {},
        "pipeline": overview.get("pipeline") or [],
        "funnel": overview.get("funnel") or [],
        "ai": {
            key: ai.get(key)
            for key in ("enabled", "high_intent", "unhappy", "stage_suggested")
        },
        "people": people,
    }


def team_calls(period: str, owner: str | None, fresh) -> list[dict] | None:
    """Each salesperson's calls in the period: handed out (`given`), `called` and
    `contacted` (someone answered). None while the ERP site is older than this."""
    analysis = leads.read_lead_analysis(period, None, None, owner, fresh)
    if not analysis.get("available"):
        return None
    rows, _empty = only_sales_team(analysis.get("calling") or [], keep=(owner,))
    return [calling_row(row) for row in rows]


def week_calls(owner: str | None, fresh, own: bool = False) -> dict | None:
    """Called and contacted per person for each day from Monday to today, counted as Today's
    calls counts them (the ERP site's calling analysis, one day at a time). `own` keeps only
    the signed-in person; otherwise the sales team. None while the ERP site is older."""
    day = getdate(today())
    days = [add_days(day, -offset) for offset in range(day.weekday(), -1, -1)]
    people: dict[str, dict] = {}
    for index, date in enumerate(days):
        answer = day_analysis(date, owner, fresh if date == day else 0)
        if answer is None:
            return None
        rows = answer.get("calling") or []
        if own:
            rows = [r for r in rows if r.get("user") == frappe.session.user]
        else:
            rows, _empty = only_sales_team(rows, keep=(owner,))
        for row in rows:
            person = people.setdefault(
                row["user"],
                {
                    "user": row["user"],
                    "full_name": row.get("full_name") or row["user"],
                    "called": [0] * len(days),
                    "contacted": [0] * len(days),
                },
            )
            person["called"][index] = cint(row.get("called"))
            person["contacted"][index] = cint(row.get("reached"))
    return {"days": [str(d) for d in days], "people": list(people.values())}


def day_analysis(date, owner: str | None, fresh) -> dict | None:
    """The ERP site's calling analysis for one day; a day that has ended is kept an hour."""
    ttl = leads.READ_TTL if date == getdate(today()) else CLOSED_DAY_TTL
    params = {"period": "custom", "from_date": str(date), "to_date": str(date)}
    return leads.cached_read(
        "analysis_day",
        {**params, "owner": owner},
        ttl,
        fresh,
        lambda: call_if_deployed("get_lead_analysis", **params, owner=owner),
        keep=lambda answer: answer is not None,
    )


def calling_row(row: dict) -> dict:
    return {
        "user": row.get("user"),
        "full_name": row.get("full_name") or row.get("user"),
        "given": cint(row.get("given")),
        "called": cint(row.get("called")),
        "contacted": cint(row.get("reached")),
    }


def handed_out_today() -> list[dict] | None:
    """Today's call batches by slot and department, in the order the slots start: the leads
    handed out and how many were called. None while the ERP site is older than this."""
    report = call_batches.get_call_batches_report()
    if not report.get("available"):
        return None
    slots: dict[tuple, dict] = {}
    for person in report.get("people") or []:
        for batch in person.get("batches") or []:
            key = (batch.get("slot"), person.get("department"))
            slot = slots.setdefault(
                key,
                {
                    "slot": key[0],
                    "department": key[1],
                    "starts_at": str(batch.get("starts_at") or ""),
                    "size": 0,
                    "called": 0,
                },
            )
            slot["size"] += cint(batch.get("size"))
            slot["called"] += cint(batch.get("called"))
            starts = [slot["starts_at"], str(batch.get("starts_at") or "")]
            slot["starts_at"] = min(filter(None, starts), default="")
    return sorted(slots.values(), key=lambda s: (s["starts_at"], s["department"] or ""))
