"""Boosting published posts from the content calendar (docs/meta-publishing.md, Phase 2).

Who sees what: `can_spend` (the project's managers and lead, the Digital Marketing Head,
System Managers) may start, approve, pause, resume and stop; anyone who may edit the post
may prepare a boost and ask for approval; Sales Employees see nothing. The server checks
every call. No function here returns a token."""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cstr, flt, get_fullname, getdate, today

from helpdesk.api.meta import (
    can_change_ad_cap,
    connection_summary,
    require_project_access,
)
from helpdesk.integrations.meta import ads, connect
from helpdesk.integrations.meta.graph import MetaError

BOOST, POST, CONNECTION = ads.BOOST, ads.POST, connect.CONNECTION
DEFAULT_BUDGET, DEFAULT_DAYS = 500, 5
BOOST_FIELDS = (
    "name",
    "post",
    "target",
    "goal",
    "status",
    "budget_type",
    "budget_amount",
    "total_budget",
    "currency",
    "start_date",
    "end_date",
    "days",
    "spend",
    "reach",
    "impressions",
    "clicks",
    "results",
    "cost_per_result",
    "failure_reason",
    "rejection_note",
    "meta_status",
    "requested_by",
    "approved_by",
    "last_synced",
)


def boost_payload(boost) -> dict:
    row = {f: boost.get(f) for f in BOOST_FIELDS}
    for key in ("start_date", "end_date", "last_synced"):
        row[key] = cstr(row[key]) if row[key] else None
    row["post_title"] = frappe.db.get_value(POST, boost.post, "title")
    row["requested_by_name"] = get_fullname(boost.requested_by)
    row["can_spend"] = ads.can_spend(boost.project)
    return row


def load_boost(boost: str):
    """A boost, once the person may spend on its project."""
    doc = frappe.get_doc(BOOST, boost)
    ads.require_spender(doc)
    return doc


def require_cap_editor():
    if frappe.session.user != "Administrator" and not can_change_ad_cap():
        frappe.throw(
            _(
                "Only a System Manager or the Digital Marketing Head can change the ad limit."
            ),
            frappe.PermissionError,
        )


# -------------------------------------------------------------- the post ----


@frappe.whitelist()
def get_boost_state(post: str) -> dict:
    """Everything the Boost section shows for one post, with no tokens."""
    doc = frappe.get_doc(POST, post)
    project = ads.require_view(doc)
    connection = ads.project_connection(project)
    blocker = ads.ads_blocker(connection)
    boosts = frappe.get_all(
        BOOST, filters={"post": post}, pluck="name", order_by="creation desc"
    )
    live = {
        r.target
        for r in doc.meta_publishes
        if r.status == "Published" and r.meta_post_id
    }
    return {
        "project": project,
        "can_spend": ads.can_spend(project),
        "blocked_reason": blocker,
        # the connection was made without the ads permissions: the page offers Reconnect
        "needs_reconnect": bool(
            connect.ads_enabled() and connection and not connection.ads_allowed
        ),
        "not_published": None
        if live
        else _("Boost is for posts that are live on Facebook or Instagram."),
        "targets": [t for t in ("Facebook", "Instagram") if t in live],
        "account": connection
        and connection.ad_account_id
        and {
            "name": connection.ad_account_name,
            "currency": connection.ad_account_currency,
            "status": connection.ad_account_status,
        },
        "spend": ads.spend_summary(connection)
        if connection and connection.ad_account_id
        else None,
        "boosts": [boost_payload(frappe.get_doc(BOOST, n)) for n in boosts],
        "goals": list(ads.GOALS),
    }


@frappe.whitelist()
def get_defaults(post: str) -> dict:
    """What the Boost dialog starts with: ₹500 a day for 5 days from tomorrow's start of
    day (today, if it is early enough), and the client's usual audience."""
    doc = frappe.get_doc(POST, post)
    project = ads.require_view(doc)
    connection = ads.project_connection(project)
    start = getdate(today())
    return {
        "budget_type": "Per day",
        "budget_amount": DEFAULT_BUDGET,
        "start_date": cstr(start),
        "end_date": cstr(start + timedelta(days=DEFAULT_DAYS - 1)),
        "audience": ads.default_audience(connection),
        "goal": "More reach",
    }


def post_connection(post: str):
    connection = ads.project_connection(ads.require_view(frappe.get_doc(POST, post)))
    if reason := ads.ads_blocker(connection):
        frappe.throw(reason)
    return connection


@frappe.whitelist()
def search_locations(post: str, q: str) -> list[dict]:
    try:
        return (
            ads.search_locations(post_connection(post), q) if len(q or "") > 1 else []
        )
    except MetaError as e:
        frappe.throw(ads.plain_error(e))


@frappe.whitelist()
def search_interests(post: str, q: str) -> list[dict]:
    try:
        return (
            ads.search_interests(post_connection(post), q) if len(q or "") > 1 else []
        )
    except MetaError as e:
        frappe.throw(ads.plain_error(e))


@frappe.whitelist(methods=["POST"])
def preview(post: str, values: dict | str) -> dict:
    """The plain summary of a boost, Meta's reach estimate when it has one, and whether the
    month's limit allows it. Nothing is created."""
    values = frappe.parse_json(values)
    connection = post_connection(post)
    audience = ads.clean_audience(values.get("audience"))
    values = {**values, "audience": audience}
    estimate = ads.estimate_reach(
        connection, audience, values.get("goal") or "More reach"
    )
    days = (getdate(values["end_date"]) - getdate(values["start_date"])).days + 1
    total = (
        flt(values["budget_amount"]) * days
        if values.get("budget_type") == "Per day"
        else flt(values["budget_amount"])
    )
    room = flt(connection.monthly_ad_cap) - ads.planned_this_month(
        connection.project, values["start_date"]
    )
    return {
        "summary": ads.summary_line(values, connection.ad_account_currency, estimate),
        "total": total,
        "days": days,
        "left": max(room, 0),
        "over_cap": total > room + 1e-9,
        "currency": connection.ad_account_currency,
    }


@frappe.whitelist(methods=["POST"])
def submit(post: str, values: dict | str) -> dict:
    """Boost this post. Someone who may spend starts it; an editor's goes to the Digital
    Marketing Head for approval."""
    return boost_payload(ads.submit_boost(post, frappe.parse_json(values)))


# ------------------------------------------------------------ a boost ----


@frappe.whitelist(methods=["POST"])
def approve(boost: str) -> dict:
    load_boost(boost)
    return boost_payload(ads.start_boost(boost))


@frappe.whitelist(methods=["POST"])
def reject(boost: str, note: str | None = None) -> dict:
    return boost_payload(ads.reject_boost(boost, note))


@frappe.whitelist(methods=["POST"])
def pause(boost: str) -> dict:
    return boost_payload(ads.pause_boost(boost))


@frappe.whitelist(methods=["POST"])
def resume(boost: str) -> dict:
    return boost_payload(ads.resume_boost(boost))


@frappe.whitelist(methods=["POST"])
def stop(boost: str) -> dict:
    return boost_payload(ads.stop_boost(boost))


# ------------------------------------------------------------- project ----


@frappe.whitelist()
def get_project_ads(project: str) -> dict:
    """The Ads tab: boosts of the project, and this month's spend against the limit."""
    require_project_access(project)
    connection = ads.project_connection(project)
    names = frappe.get_all(
        BOOST,
        filters={"project": project},
        pluck="name",
        order_by="creation desc",
        limit=200,
    )
    return {
        "enabled": connect.ads_enabled(),
        "blocked_reason": ads.ads_blocker(connection),
        "needs_reconnect": bool(
            connect.ads_enabled() and connection and not connection.ads_allowed
        ),
        "account": connection
        and connection.ad_account_id
        and {
            "name": connection.ad_account_name,
            "currency": connection.ad_account_currency,
            "status": connection.ad_account_status,
        },
        "spend": ads.spend_summary(connection)
        if connection and connection.ad_account_id
        else None,
        "boosts": [boost_payload(frappe.get_doc(BOOST, n)) for n in names],
    }


@frappe.whitelist()
def list_ad_accounts(project: str) -> list[dict]:
    require_project_access(project)
    try:
        return connect.list_ad_accounts(project)
    except MetaError as e:
        frappe.throw(ads.plain_error(e))


@frappe.whitelist(methods=["POST"])
def select_ad_account(project: str, account_id: str) -> dict:
    require_project_access(project)
    try:
        connect.select_ad_account(project, account_id)
    except MetaError as e:
        frappe.throw(ads.plain_error(e))
    return connection_summary(project)


@frappe.whitelist(methods=["POST"])
def set_monthly_cap(project: str, amount: float | str) -> dict:
    """The most the project's boosts may plan to spend in a month."""
    require_project_access(project)
    require_cap_editor()
    if flt(amount) < 0:
        frappe.throw(_("The limit can't be below zero."))
    frappe.db.set_value(CONNECTION, project, "monthly_ad_cap", flt(amount))
    return connection_summary(project)
