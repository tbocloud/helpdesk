"""Boosting a published post as a paid ad (docs/meta-publishing.md, Phase 2).

A boost is a Marketing API Campaign > Ad Set > Ad that uses the post already on the Page
or Instagram account as its creative. Everything is created PAUSED and switched on only
after the money has been checked and a person allowed to spend has agreed. The hub never
spends more than the project's monthly cap, never touches payment, and writes every
spend action on the project's timeline."""

import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import (
    cint,
    flt,
    fmt_money,
    get_first_day,
    get_last_day,
    get_system_timezone,
    getdate,
    now_datetime,
    today,
)

from helpdesk.content_team import head_approvers, is_sales_employee
from helpdesk.helpdesk.doctype.hd_meta_boost.hd_meta_boost import (
    ACTIVE,
    COMPLETED,
    DRAFT,
    FAILED,
    LIVE,
    PAUSED,
    PENDING,
    REJECTED,
)
from helpdesk.helpdesk.doctype.hd_meta_connection.hd_meta_connection import (
    CONNECTED,
    EXPIRED,
)
from helpdesk.integrations.meta.connect import ads_enabled, app
from helpdesk.integrations.meta.graph import GraphClient, MetaError
from helpdesk.tasky.permissions import can_handle_credentials
from helpdesk.work_reminders import notify_users

BOOST = "HD Meta Boost"
CONNECTION = "HD Meta Connection"
POST = "HD Content Post"
PUBLISH = "HD Content Publish"

# Meta's outcome-based objectives (ODAX) and what each goal optimises for. `result` is the
# insight that counts as one result: a field of the insights row, or an action type.
GOALS = {
    "More reach": {
        "objective": "OUTCOME_AWARENESS",
        "optimization_goal": "REACH",
        "result": ("field", "reach"),
    },
    "More engagement": {
        "objective": "OUTCOME_ENGAGEMENT",
        "optimization_goal": "POST_ENGAGEMENT",
        "destination_type": "ON_POST",
        "result": ("action", "post_engagement"),
    },
    "More messages": {
        "objective": "OUTCOME_ENGAGEMENT",
        "optimization_goal": "CONVERSATIONS",
        "result": ("action", "onsite_conversion.messaging_conversation_started_7d"),
    },
    "More website visits": {
        "objective": "OUTCOME_TRAFFIC",
        "optimization_goal": "LINK_CLICKS",
        "destination_type": "WEBSITE",
        "result": ("action", "link_click"),
    },
}
# where a "More messages" ad opens the conversation
MESSAGE_DESTINATIONS = {"Facebook": "MESSENGER", "Instagram": "INSTAGRAM_DIRECT"}
# currencies Meta counts in whole units; every other one is in hundredths
ZERO_DECIMAL = {"JPY", "KRW", "VND", "CLP", "ISK", "PYG", "UGX", "XAF", "XOF"}
DEFAULT_COUNTRY = "IN"
MIN_AGE, MAX_AGE = 18, 65
MAX_PICKS = 10
# what Meta says about the ad, in words
META_STATUS = {
    "ACTIVE": "Running",
    "PAUSED": "Paused",
    "CAMPAIGN_PAUSED": "Paused",
    "ADSET_PAUSED": "Paused",
    "IN_PROCESS": "Meta is reviewing it",
    "PENDING_REVIEW": "Meta is reviewing it",
    "PREAPPROVED": "Meta is reviewing it",
    "PENDING_BILLING_INFO": "Waiting for a payment method on the ad account",
    "DISAPPROVED": "Meta didn't approve it",
    "WITH_ISSUES": "Running, with a warning from Meta",
    "ARCHIVED": "Stopped",
    "DELETED": "Stopped",
}
ACCESS_CODES = {10, 200, 270, 294}


# ------------------------------------------------------------------ who may --


def can_spend(project: str | None) -> bool:
    """Start, approve, pause, resume or stop a boost: whoever may handle the client's
    accounts (the project's managers and lead, the Digital Marketing Head, System
    Managers). Never a Sales Employee."""
    return can_handle_credentials(project)


def can_request(post, project: str | None) -> bool:
    """Prepare a boost and ask for approval: anyone who may edit the post, and those who
    can spend. Never a Sales Employee."""
    return not is_sales_employee() and (
        can_spend(project) or post.has_permission("write")
    )


def require_view(post) -> str | None:
    """The post's project, once the signed-in person may take part in boosts at all."""
    from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
        content_project_for,
    )

    post.check_permission("read")
    project = content_project_for(post.customer)
    if not (project and can_request(post, project)):
        frappe.throw(
            _("You can't boost this post. Ask the Digital Marketing Head."),
            frappe.PermissionError,
        )
    return project


def require_spender(boost):
    if not can_spend(boost.project):
        frappe.throw(
            _(
                "Only the project's managers and the Digital Marketing Head can start or change a boost."
            ),
            frappe.PermissionError,
        )


# --------------------------------------------------------------- connection --


def ads_blocker(connection) -> str | None:
    """Why ads can't be used on this connection right now, or None. Plain words."""
    if not ads_enabled():
        return _(
            "Boosting is switched off. A System Manager turns it on in Settings → Meta."
        )
    if not connection or connection.status == "Pending":
        return _("Connect Meta on the project first.")
    if connection.status != CONNECTED:
        return _("Reconnect Meta to allow ads: the connection needs attention.")
    if not (connection.ads_allowed and connection.user_token()):
        return _("Reconnect Meta to allow ads.")
    if not connection.ad_account_id:
        return _("Pick the client's ad account on the project's Meta tab.")
    if connection.ad_account_status != "Active":
        return _(
            "The client's ad account is {0}. Ask the client to fix it in Meta."
        ).format(_(connection.ad_account_status or "not available"))
    return None


def ads_graph(connection) -> GraphClient:
    """Ads act through the signed-in person's long-lived token (the Page token is for posting)."""
    _app_id, secret = app()
    return GraphClient(connection.user_token(), secret)


def project_connection(project: str):
    return (
        frappe.get_doc(CONNECTION, project)
        if frappe.db.exists(CONNECTION, project)
        else None
    )


def plain_error(error: MetaError) -> str:
    """Meta's refusal, as something staff can act on."""
    text = error.user_message.lower()
    if error.token_expired:
        return error.user_message
    if error.code in ACCESS_CODES or "permission" in text:
        return _(
            "TBO can't use this ad account. Ask the client to add TBO's business as a partner on it, or connect Meta as a person with an advertiser role on the account."
        )
    if any(w in text for w in ("payment", "billing", "funding")):
        return _(
            "The client's ad account has no working payment method. The client adds one in Meta Business Settings, then the boost can start."
        )
    return error.user_message


# -------------------------------------------------------------- audience -----


def default_audience(connection) -> dict:
    """Where to show the ad by default: Kerala for Indian clients, else the client's own
    country (the UAE for UAE clients). Falls back to the whole country when Meta can't say."""
    country = DEFAULT_COUNTRY
    if connection and connection.customer:
        name = frappe.db.get_value("HD Customer", connection.customer, "country")
        code = name and frappe.db.get_value("Country", name, "code")
        country = (code or DEFAULT_COUNTRY).upper()
    place = {
        "type": "country",
        "key": country,
        "name": frappe.db.get_value("Country", {"code": country.lower()}, "name")
        or country,
    }
    if country == "IN" and connection and connection.ad_account_id:
        try:
            found = search_locations(connection, "Kerala", ["region"])
            kerala = next((p for p in found if p["name"] == "Kerala"), None)
            place = kerala or place
        except MetaError:
            pass
    return {
        "locations": [place],
        "age_min": 18,
        "age_max": 55,
        "interests": [],
        "advantage_audience": True,
    }


def search_locations(connection, query: str, types=("country", "region", "city")):
    data = ads_graph(connection).get(
        "search",
        type="adgeolocation",
        q=query,
        location_types=json.dumps(list(types)),
        limit=8,
    )
    return [
        {
            "type": p.get("type"),
            "key": str(p.get("key")),
            "name": p.get("name"),
            "detail": ", ".join(
                x for x in (p.get("region"), p.get("country_name")) if x
            ),
        }
        for p in data.get("data", [])
    ]


def search_interests(connection, query: str):
    data = ads_graph(connection).get("search", type="adinterest", q=query, limit=8)
    return [
        {"id": str(i["id"]), "name": i["name"]}
        for i in data.get("data", [])
        if i.get("id")
    ]


def clean_audience(audience: dict | str | None) -> dict:
    """The audience as the person set it, checked and cut down to what the hub sends."""
    audience = frappe.parse_json(audience) if isinstance(audience, str) else audience
    audience = audience or {}
    places = [
        {
            "type": p["type"],
            "key": str(p["key"]),
            "name": p.get("name") or str(p["key"]),
        }
        for p in audience.get("locations") or []
        if p.get("type") in ("country", "region", "city") and p.get("key")
    ][:MAX_PICKS]
    if not places:
        frappe.throw(_("Pick at least one place to show the ad in."))
    age_min = cint(audience.get("age_min") or MIN_AGE)
    age_max = cint(audience.get("age_max") or MAX_AGE)
    if not (MIN_AGE <= age_min <= age_max <= MAX_AGE):
        frappe.throw(
            _("Ages must be between {0} and {1}, youngest first.").format(
                MIN_AGE, MAX_AGE
            )
        )
    return {
        "locations": places,
        "age_min": age_min,
        "age_max": age_max,
        "interests": [
            {"id": str(i["id"]), "name": i.get("name") or ""}
            for i in audience.get("interests") or []
            if i.get("id")
        ][:MAX_PICKS],
        "advantage_audience": bool(audience.get("advantage_audience", True)),
    }


def targeting_spec(audience: dict) -> dict:
    """Meta's targeting for this audience. Placements are left out: Meta chooses them."""
    geo: dict = {}
    for place in audience["locations"]:
        if place["type"] == "country":
            geo.setdefault("countries", []).append(place["key"])
        elif place["type"] == "region":
            geo.setdefault("regions", []).append({"key": place["key"]})
        else:
            geo.setdefault("cities", []).append(
                {"key": place["key"], "radius": 10, "distance_unit": "kilometer"}
            )
    spec = {
        "geo_locations": geo,
        "age_min": audience["age_min"],
        "age_max": audience["age_max"],
        "targeting_automation": {
            "advantage_audience": int(audience["advantage_audience"])
        },
    }
    if audience["interests"]:
        spec["flexible_spec"] = [
            {
                "interests": [
                    {"id": i["id"], "name": i["name"]} for i in audience["interests"]
                ]
            }
        ]
    return spec


def where_text(audience: dict) -> str:
    return ", ".join(p["name"] for p in audience["locations"])


def estimate_reach(connection, audience: dict, goal: str) -> str | None:
    """Meta's estimate of the people the audience holds, in words; None when it can't say
    (the preview then simply leaves it out)."""
    try:
        data = ads_graph(connection).get(
            f"{connection.ad_account_id}/delivery_estimate",
            targeting_spec=json.dumps(targeting_spec(audience)),
            optimization_goal=GOALS[goal]["optimization_goal"],
        )
        row = (data.get("data") or [{}])[0]
        low, high = row.get("estimate_mau_lower_bound"), row.get(
            "estimate_mau_upper_bound"
        )
    except MetaError:
        return None
    if not (low or high):
        return None
    return _("{0} to {1} people a month").format(f"{cint(low):,}", f"{cint(high):,}")


def summary_line(values: dict, currency: str, estimate: str | None) -> str:
    """'₹2,500 total · 5 days · Kerala, 18–55 · estimated reach …'"""
    days = (getdate(values["end_date"]) - getdate(values["start_date"])).days + 1
    amount = flt(values["budget_amount"])
    total = amount * days if values["budget_type"] == "Per day" else amount
    audience = clean_audience(values.get("audience"))
    parts = [
        _("{0} total").format(fmt_money(total, currency=currency)),
        _("{0} days").format(days) if days != 1 else _("1 day"),
        f"{where_text(audience)}, {audience['age_min']}–{audience['age_max']}",
    ]
    if estimate:
        parts.append(_("estimated reach {0}").format(estimate))
    return " · ".join(parts)


# ------------------------------------------------------------------ the cap --


def planned_this_month(project: str, day=None, exclude: str | None = None) -> float:
    """What boosts starting in this month can spend: a live boost at its full budget, a
    finished one at what it really spent."""
    day = getdate(day or today())
    Boost = frappe.qb.DocType(BOOST)
    query = (
        frappe.qb.from_(Boost)
        .select(Boost.status, Boost.total_budget, Boost.spend)
        .where(Boost.project == project)
        .where(Boost.status.isin([*LIVE, COMPLETED]))
        .where(Boost.start_date >= get_first_day(day))
        .where(Boost.start_date <= get_last_day(day))
    )
    if exclude:
        query = query.where(Boost.name != exclude)
    return sum(
        flt(r.spend) if r.status == COMPLETED else flt(r.total_budget)
        for r in query.run(as_dict=True)
    )


def check_cap(connection, boost):
    """Refuse a boost that would take the month past the project's cap. The connection
    row is locked so two boosts started together can't both slip under it."""
    frappe.db.get_value(CONNECTION, connection.name, "name", for_update=True)
    cap = flt(connection.monthly_ad_cap)
    planned = planned_this_month(boost.project, boost.start_date, exclude=boost.name)
    room = cap - planned
    if flt(boost.total_budget) <= room + 1e-9:
        return
    currency = connection.ad_account_currency
    if room <= 0:
        frappe.throw(
            _(
                "This month's ad limit of {0} is already planned. Ask the Digital Marketing Head to raise the limit, or start this boost next month."
            ).format(fmt_money(cap, currency=currency))
        )
    frappe.throw(
        _(
            "This boost could spend up to {0}, but only {1} is left of this month's {2} limit. Lower the budget to {1} or less, or ask the Digital Marketing Head to raise the limit."
        ).format(
            fmt_money(boost.total_budget, currency=currency),
            fmt_money(room, currency=currency),
            fmt_money(cap, currency=currency),
        )
    )


def spend_summary(connection) -> dict:
    cap = flt(connection.monthly_ad_cap)
    planned = planned_this_month(connection.project)
    return {
        "currency": connection.ad_account_currency,
        "cap": cap,
        "planned": planned,
        "left": max(cap - planned, 0),
    }


# ----------------------------------------------------------------- creating --


def published_target(post, target: str):
    """The post's Published row for this target, which holds the id of the live post."""
    row = next(
        (
            r
            for r in post.meta_publishes
            if r.target == target and r.status == "Published" and r.meta_post_id
        ),
        None,
    )
    if not row:
        frappe.throw(
            _("Only a post that is live on {0} can be boosted there.").format(_(target))
        )
    return row


def create_boost(post_name: str, values: dict):
    """A Draft boost for a published post, checked in full but nothing sent to Meta yet."""
    post = frappe.get_doc(POST, post_name)
    project = require_view(post)
    connection = project_connection(project)
    if reason := ads_blocker(connection):
        frappe.throw(reason)
    target = values.get("target")
    row = published_target(post, target)
    goal = values.get("goal")
    if goal not in GOALS:
        frappe.throw(_("Pick what the boost should achieve."))
    if goal == "More website visits" and not row.link:
        frappe.throw(
            _("This post has no website link to send people to. Pick another goal.")
        )
    busy = frappe.db.exists(
        BOOST,
        {"post": post.name, "target": target, "status": ["in", [PENDING, *LIVE]]},
    )
    if busy:
        frappe.throw(
            _(
                "{0} is already being boosted or waiting for approval. Stop it first."
            ).format(busy)
        )
    boost = frappe.get_doc(
        {
            "doctype": BOOST,
            "project": project,
            "customer": post.customer,
            "post": post.name,
            "target": target,
            "meta_post_id": row.meta_post_id,
            "goal": goal,
            "budget_type": values.get("budget_type") or "Per day",
            "budget_amount": flt(values.get("budget_amount")),
            "currency": connection.ad_account_currency,
            "start_date": values.get("start_date") or today(),
            "end_date": values.get("end_date"),
            "audience": json.dumps(clean_audience(values.get("audience"))),
            "ad_account_id": connection.ad_account_id,
            "requested_by": frappe.session.user,
            "status": DRAFT,
        }
    )
    boost.insert(ignore_permissions=True)
    check_cap(connection, boost)
    return boost


def submit_boost(post_name: str, values: dict):
    """The dialog's one button. Someone who may spend starts the boost; an editor's goes
    to the Digital Marketing Head for approval."""
    boost = create_boost(post_name, values)
    if can_spend(boost.project):
        return start_boost(boost.name)
    return request_approval(boost.name)


def request_approval(boost_name: str):
    boost = frappe.get_doc(BOOST, boost_name)
    if boost.status != DRAFT:
        frappe.throw(_("This boost is already {0}.").format(_(boost.status)))
    boost.db_set("status", PENDING)
    boost.status = PENDING
    post = frappe.get_doc(POST, boost.post)
    log(
        boost,
        _("{0} asked to boost {1} on {2} for up to {3}.").format(
            frappe.utils.get_fullname(), post.label, _(boost.target), money(boost)
        ),
    )
    notify_users(
        [u for u in head_approvers() if u != frappe.session.user],
        BOOST,
        boost.name,
        _("{0} asked to boost {1} on {2} for up to {3}. Approve or reject it.").format(
            frappe.utils.get_fullname(), post.label, _(boost.target), money(boost)
        ),
        link=ads_path(boost.project),
    )
    return boost


def reject_boost(boost_name: str, note: str | None = None):
    boost = frappe.get_doc(BOOST, boost_name)
    require_spender(boost)
    if boost.status not in (DRAFT, PENDING):
        frappe.throw(_("This boost is already {0}.").format(_(boost.status)))
    boost.db_set({"status": REJECTED, "rejection_note": note})
    boost.status = REJECTED
    log(
        boost,
        _("{0} rejected the boost. {1}").format(
            frappe.utils.get_fullname(), note or ""
        ),
    )
    tell_requester(boost, _("Your boost was rejected. {0}").format(note or ""))
    return boost


# --------------------------------------------------------------- going live --


def start_boost(boost_name: str):
    """Approve and start: build everything PAUSED on Meta, then switch it on. The cap is
    checked again just before, under a lock."""
    frappe.db.get_value(BOOST, boost_name, "name", for_update=True)
    boost = frappe.get_doc(BOOST, boost_name)
    require_spender(boost)
    if boost.status not in (DRAFT, PENDING):
        frappe.throw(_("This boost is already {0}.").format(_(boost.status)))
    connection = project_connection(boost.project)
    if reason := ads_blocker(connection):
        frappe.throw(reason)
    if getdate(boost.end_date) < getdate():
        frappe.throw(_("The dates have passed. Make a new boost."))
    check_cap(connection, boost)
    boost.db_set(
        {
            "approved_by": frappe.session.user,
            "approved_on": now_datetime(),
        }
    )
    graph = ads_graph(connection)
    try:
        build_paused(graph, boost, connection)
        switch_on(graph, boost)
    except MetaError as e:
        fail(boost, connection, e)
        return boost
    boost.db_set({"status": ACTIVE, "failure_reason": None, "meta_status": "Running"})
    boost.status = ACTIVE
    frappe.db.set_value(POST, boost.post, "meta_boosted", 1, update_modified=False)
    log(
        boost,
        _("{0} started a boost of {1} on {2}: up to {3}, {4} to {5}.").format(
            frappe.utils.get_fullname(),
            frappe.db.get_value(POST, boost.post, "title"),
            _(boost.target),
            money(boost),
            boost.start_date,
            boost.end_date,
        ),
    )
    if boost.requested_by != frappe.session.user:
        tell_requester(boost, _("Your boost is live."))
    return boost


def to_minor(amount: float, currency: str) -> int:
    """Meta counts money in the currency's smallest unit (paise, fils, cents)."""
    return round(flt(amount) * (1 if currency in ZERO_DECIMAL else 100))


def meta_time(day, at: time) -> str:
    zone = ZoneInfo(get_system_timezone())
    return datetime.combine(getdate(day), at, tzinfo=zone).isoformat()


def start_time(boost) -> str:
    """Today's boosts start in five minutes (Meta refuses a start in the past)."""
    if getdate(boost.start_date) <= getdate():
        return (
            datetime.now(ZoneInfo(get_system_timezone())) + timedelta(minutes=5)
        ).isoformat()
    return meta_time(boost.start_date, time(0, 0))


def creative_for(boost, connection) -> dict:
    """The existing post is the ad: no new image or copy is made."""
    if boost.target == "Instagram":
        return {
            "source_instagram_media_id": boost.meta_post_id,
            "instagram_user_id": connection.instagram_user_id,
        }
    return {"object_story_id": boost.meta_post_id}


def build_paused(graph: GraphClient, boost, connection):
    """Campaign, ad set and ad, all PAUSED. Ids are saved as soon as Meta gives them."""
    goal = GOALS[boost.goal]
    account = boost.ad_account_id
    name = f"{boost.post} · {boost.goal} · {boost.name}"
    if not boost.campaign_id:
        boost.campaign_id = graph.post(
            f"{account}/campaigns",
            name=name,
            objective=goal["objective"],
            status="PAUSED",
            special_ad_categories=json.dumps([]),
            is_adset_budget_sharing_enabled="false",
        )["id"]
        boost.db_set("campaign_id", boost.campaign_id)
    if not boost.adset_id:
        budget = to_minor(boost.budget_amount, boost.currency)
        params = {
            "name": name,
            "campaign_id": boost.campaign_id,
            "status": "PAUSED",
            "billing_event": "IMPRESSIONS",
            "optimization_goal": goal["optimization_goal"],
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "start_time": start_time(boost),
            "end_time": meta_time(boost.end_date, time(23, 59)),
            "targeting": json.dumps(targeting_spec(json.loads(boost.audience))),
            "daily_budget"
            if boost.budget_type == "Per day"
            else "lifetime_budget": budget,
        }
        destination = goal.get("destination_type") or MESSAGE_DESTINATIONS.get(
            boost.target
        )
        if destination:
            params["destination_type"] = destination
        if boost.goal in ("More engagement", "More messages"):
            params["promoted_object"] = json.dumps(
                {"page_id": connection.facebook_page_id}
            )
        boost.adset_id = graph.post(f"{account}/adsets", **params)["id"]
        boost.db_set("adset_id", boost.adset_id)
    if not boost.ad_id:
        boost.ad_id = graph.post(
            f"{account}/ads",
            name=name,
            adset_id=boost.adset_id,
            creative=json.dumps(creative_for(boost, connection)),
            status="PAUSED",
        )["id"]
        boost.db_set("ad_id", boost.ad_id)


def switch_on(graph: GraphClient, boost):
    """Nothing spends until all three are on; the campaign goes last."""
    for object_id in (boost.ad_id, boost.adset_id, boost.campaign_id):
        graph.post(object_id, status="ACTIVE")


def set_campaign(boost, status: str):
    connection = project_connection(boost.project)
    ads_graph(connection).post(boost.campaign_id, status=status)


def fail(boost, connection, error: MetaError):
    """The boost didn't start. What was built stays PAUSED on Meta (it costs nothing);
    staff see why, in plain words."""
    reason = plain_error(error)
    boost.db_set({"status": FAILED, "failure_reason": reason})
    boost.status = FAILED
    if error.token_expired and connection:
        connection.mark(EXPIRED, error.user_message)
    log(boost, _("The boost didn't start: {0}").format(reason))
    tell_requester(boost, _("The boost didn't start: {0}").format(reason))


# ------------------------------------------------------------- pause, stop --


def pause_boost(boost_name: str):
    boost = frappe.get_doc(BOOST, boost_name)
    require_spender(boost)
    if boost.status != ACTIVE:
        frappe.throw(_("Only a running boost can be paused."))
    change_campaign(boost, "PAUSED", PAUSED, _("paused"))
    return boost


def resume_boost(boost_name: str):
    """Turning a paused boost back on adds no money: it was counted when it started."""
    boost = frappe.get_doc(BOOST, boost_name)
    require_spender(boost)
    if boost.status != PAUSED:
        frappe.throw(_("Only a paused boost can be resumed."))
    if getdate(boost.end_date) < getdate():
        frappe.throw(_("The dates have passed. Make a new boost."))
    connection = project_connection(boost.project)
    if reason := ads_blocker(connection):
        frappe.throw(reason)
    change_campaign(boost, "ACTIVE", ACTIVE, _("resumed"))
    return boost


def stop_boost(boost_name: str):
    """Ends the boost for good: the campaign is archived on Meta, so it can't be turned
    on again from there either."""
    boost = frappe.get_doc(BOOST, boost_name)
    require_spender(boost)
    if boost.status not in LIVE:
        frappe.throw(_("Only a running or paused boost can be stopped."))
    change_campaign(boost, "ARCHIVED", COMPLETED, _("stopped"))
    boost.db_set("meta_status", "Stopped")
    sync_boost(boost.name)
    return frappe.get_doc(BOOST, boost_name)


def change_campaign(boost, meta_status: str, status: str, verb: str):
    connection = project_connection(boost.project)
    try:
        set_campaign(boost, meta_status)
    except MetaError as e:
        if e.token_expired and connection:
            connection.mark(EXPIRED, e.user_message)
        frappe.throw(plain_error(e))
    boost.db_set("status", status)
    boost.status = status
    log(
        boost,
        _("{0} {1} the boost of {2} on {3}.").format(
            frappe.utils.get_fullname(),
            verb,
            frappe.db.get_value(POST, boost.post, "title"),
            _(boost.target),
        ),
    )


# ---------------------------------------------------------------- insights ---


def result_count(goal: str, row: dict) -> int:
    kind, key = GOALS[goal]["result"]
    if kind == "field":
        return cint(row.get(key))
    return sum(
        cint(a.get("value"))
        for a in row.get("actions") or []
        if a.get("action_type") == key
    )


def plain_rejection(feedback: dict | None) -> str:
    """Why Meta didn't approve the ad, from its review feedback, as a sentence."""
    reasons = []
    for group in (feedback or {}).values():
        if isinstance(group, dict):
            reasons += [str(k).replace("_", " ").strip().lower() for k in group]
    reasons = sorted(set(reasons))
    if not reasons:
        return _(
            "Meta didn't approve this ad. Check the post against Meta's ad policies, then boost again."
        )
    return _(
        "Meta didn't approve this ad because of: {0}. Change the post to follow Meta's ad policies, then boost again."
    ).format(", ".join(reasons))


def sync_boost(boost_name: str):
    """Read the ad's status and numbers from Meta into the boost."""
    boost = frappe.get_doc(BOOST, boost_name)
    connection = project_connection(boost.project)
    if not (boost.ad_id and connection and connection.user_token()):
        return boost
    graph = ads_graph(connection)
    try:
        ad = graph.get(boost.ad_id, fields="effective_status,ad_review_feedback")
        rows = graph.get(
            f"{boost.ad_id}/insights",
            fields="spend,reach,impressions,clicks,actions",
            date_preset="maximum",
        ).get("data")
    except MetaError as e:
        if e.token_expired:
            connection.mark(EXPIRED, e.user_message)
        raise
    row = (rows or [{}])[0]
    spend = flt(row.get("spend"))
    results = result_count(boost.goal, row)
    values = {
        "spend": spend,
        "reach": cint(row.get("reach")),
        "impressions": cint(row.get("impressions")),
        "clicks": cint(row.get("clicks")),
        "results": results,
        "cost_per_result": spend / results if results else 0,
        "last_synced": now_datetime(),
    }
    effective = ad.get("effective_status")
    if boost.meta_status != "Stopped":
        values["meta_status"] = META_STATUS.get(effective, effective)
    boost.db_set(values)
    boost.update(values)
    move_with_meta(boost, effective, ad.get("ad_review_feedback"))
    return boost


def move_with_meta(boost, effective: str | None, feedback: dict | None):
    """Follow what Meta says: a rejection, a pause made in Ads Manager, or the end date."""
    if boost.status not in LIVE:
        return
    if effective == "DISAPPROVED":
        reason = plain_rejection(feedback)
        boost.db_set({"status": FAILED, "failure_reason": reason})
        boost.status = FAILED
        log(boost, _("Meta didn't approve the ad. {0}").format(reason))
        tell_requester(boost, reason)
    elif effective in ("ARCHIVED", "DELETED") or getdate(today()) > getdate(
        boost.end_date
    ):
        boost.db_set("status", COMPLETED)
        boost.status = COMPLETED
        log(boost, _("The boost has ended."))
    elif (
        effective in ("PAUSED", "CAMPAIGN_PAUSED", "ADSET_PAUSED")
        and boost.status == ACTIVE
    ):
        boost.db_set("status", PAUSED)
        boost.status = PAUSED
    elif effective == "ACTIVE" and boost.status == PAUSED:
        boost.db_set("status", ACTIVE)
        boost.status = ACTIVE


def sync_active_boosts():
    """Scheduler, every hour: refresh the numbers of every running or paused boost."""
    names = frappe.get_all(BOOST, filters={"status": ["in", list(LIVE)]}, pluck="name")
    for name in names:
        try:
            sync_boost(name)
        except Exception:  # noqa: BLE001 - one bad boost must not stop the others
            frappe.log_error(title=f"Meta boost sync failed for {name}")


# ----------------------------------------------------------- notes and news --


def money(boost) -> str:
    return fmt_money(boost.total_budget, currency=boost.currency)


def ads_path(project: str) -> str:
    return f"/projects/{project}/ads"


def log(boost, text: str):
    """Every spend action, on the project's timeline."""
    frappe.get_doc("Project", boost.project).add_comment(
        "Info", f"{text} ({boost.name})"
    )


def tell_requester(boost, message: str):
    people = {boost.requested_by, *head_approvers()}
    post = frappe.db.get_value(POST, boost.post, "title")
    notify_users(
        sorted(u for u in people if u and u != frappe.session.user),
        BOOST,
        boost.name,
        f"{post}: {message}",
        link=ads_path(boost.project),
        once=False,
    )
