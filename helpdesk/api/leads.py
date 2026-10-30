"""The Leads page: sales leads read and written live in ERPNext on the CRM site, as the
signed-in person (docs/leads.md). Thin proxies to `tbo_smart.api.hub_leads`; the CRM
site decides what each person may see and do, and the API key never leaves the hub."""

import json

import frappe
from frappe import _
from frappe.utils import (
    add_days,
    add_months,
    cint,
    get_first_day,
    get_last_day,
    getdate,
    today,
)

from helpdesk.content_team import only_sales_team
from helpdesk.integrations.crm.leads import (
    LeadsError,
    LeadsUnavailableError,
    call,
    call_if_deployed,
    download,
    require_leads,
)

VIEWS = ("all", "mine", "call_today", "follow_up")
PERIODS = ("today", "yesterday", "week", "month", "quarter", "custom")
# a day is a custom range of that one day on the ERP site, which an older TBO Smart reads too
DAYS_AGO = {"today": 0, "yesterday": 1}
# the Business overview's periods: the financial year starts on 1 April (India)
BUSINESS_PERIODS = ("month", "last_month", "quarter", "fy", "custom")
FY_START_MONTH = 4
MESSAGE_CHANNELS = ("whatsapp", "email")
CALL_OUTCOMES = ("Connected", "No answer", "Busy", "Voicemail")
TELEPHONY = "tbo_smart.api.telephony"
# what the recording player may be handed back
AUDIO_TYPES = ("audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/ogg")
# what a lead photo may be handed back as: the ERP site only stores these
PHOTO_TYPES = ("image/jpeg", "image/png", "image/webp")
# a photo is at most 10 MB on the ERP site; as base64 a third more
MAX_PHOTO_BASE64 = 14 * 1024 * 1024
PHOTO_METHOD = "helpdesk.api.leads.lead_photo"
PHOTO_CACHE = "private, max-age=3600"
MAX_PAGE = 100
# the hub and the ERP site share one worker pool on Frappe Cloud, so a read that was just
# answered is kept per person for a short while instead of asked again (docs/leads.md)
CACHE_PREFIX = "hd_leads"
READ_TTL = 60
OPTIONS_TTL = 600
# a lead with no department, or a department without its own setting, goes quiet after this
DEFAULT_STALE_DAYS = 3


def cached_read(part: str, params: dict, ttl: int, fresh, read, keep=bool):
    """`read()`'s answer, from the signed-in person's cache while it is fresh enough.
    `fresh` skips the cache and renews it. A failed read caches nothing, nor does an
    answer `keep` refuses (an ERP site that doesn't have the part yet)."""
    key = f"{CACHE_PREFIX}:{frappe.session.user}:{part}:{json.dumps(params, sort_keys=True)}"
    if not cint(fresh):
        hit = frappe.cache.get_value(key, expires=True)
        if hit is not None:
            return hit
    result = read()
    if keep(result):
        frappe.cache.set_value(key, result, expires_in_sec=ttl)
    return result


def clear_cached_reads() -> None:
    """After a lead or proposal changes: the signed-in person's cached figures go, so
    their next Overview is read again. Other people's age out within `READ_TTL`."""
    frappe.cache.delete_keys(f"{CACHE_PREFIX}:{frappe.session.user}:")


@frappe.whitelist()
def get_options(fresh: int | str = 0) -> dict:
    """Stages, sources, segments, owners, territories and industries for the pickers,
    and whether the ERP site has the Daily report and can log a call made outside
    MyOperator (`has_daily_report`, `can_log_call`: both came with the same TBO Smart)."""
    require_leads()
    options = read_options(fresh)
    deployed = report_deployed()
    return {**options, "can_log_call": deployed, "has_daily_report": deployed}


def read_options(fresh: int | str = 0) -> dict:
    return cached_read(
        "options", {}, OPTIONS_TTL, fresh, lambda: call("get_options") or {}
    )


@frappe.whitelist()
def list_leads(
    search: str | None = None,
    stage: str | None = None,
    owner: str | None = None,
    segment: str | None = None,
    view: str = "all",
    start: int | str = 0,
    page_length: int | str = 20,
    source: str | None = None,
    temperature: str | None = None,
    metric: str | None = None,
    period: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    department: str | None = None,
) -> dict:
    """A page of leads. `metric` with its period keeps the leads one number of the
    Overview counts (the ERP site picks them). `department` keeps one lead department's
    leads; the ERP site still shows only what the person may see."""
    require_leads()
    if view not in VIEWS:
        frappe.throw(_("Pick All, Mine, Call today or Follow-up."))
    if period:
        check_period(period, from_date, to_date, dates_required=bool(metric))
    when = {"period": None, "from_date": None, "to_date": None}
    if metric:
        when = {
            "period": period or None,
            "from_date": from_date or None,
            "to_date": to_date or None,
        }
        if period in DAYS_AGO:
            when = erp_period(period, from_date, to_date)
    result = call(
        "list_leads",
        search=(search or "").strip() or None,
        stage=stage or None,
        owner=owner or None,
        segment=segment or None,
        source=source or None,
        temperature=temperature or None,
        department=department or None,
        metric=metric or None,
        **when,
        view=view,
        # cint: a malformed number is 0, never a server error
        start=max(cint(start), 0),
        page_length=min(max(cint(page_length) or 20, 1), MAX_PAGE),
    )
    return result or {"rows": [], "total": 0}


@frappe.whitelist()
def get_overview(
    period: str = "month",
    from_date: str | None = None,
    to_date: str | None = None,
    owner: str | None = None,
    fresh: int | str = 0,
) -> dict:
    """The Overview: the pipeline, the funnel and the period's figures for the
    leads the signed-in person may see (theirs, their team's or everyone's)."""
    require_leads()
    check_period(period, from_date, to_date)
    return read_overview(period, from_date, to_date, owner, fresh)


def read_overview(period, from_date, to_date, owner, fresh) -> dict:
    when = erp_period(period, from_date, to_date)
    return cached_read(
        "overview",
        {**when, "owner": owner or None},
        READ_TTL,
        fresh,
        lambda: call("get_overview", **when, owner=owner or None) or {},
    )


@frappe.whitelist()
def get_lead_intake(fresh: int | str = 0) -> dict:
    """New leads each salesperson took today and yesterday (imports left out), with the
    daily target from HD CRM Settings (0: none). `available` is false while the ERP
    site's TBO Smart is older than this, so the page leaves the strip out."""
    require_leads()
    return read_lead_intake(fresh)


def read_lead_intake(fresh) -> dict:
    day = getdate(today())
    result = cached_read(
        "intake",
        {"day": str(day)},
        READ_TTL,
        fresh,
        lambda: call_if_deployed(
            "get_lead_intake", from_date=str(add_days(day, -1)), to_date=str(day)
        ),
        # None: an older ERP site, asked again next time so a deploy shows at once
        keep=lambda answer: answer is not None,
    )
    if result is None:
        return {"available": False}
    # the target is the hub's own setting, so it is read live
    target = frappe.db.get_single_value("HD CRM Settings", "daily_lead_target")
    # the ERP site lists everyone with a sales role; the strip is the sales team only, and
    # each day's total is the sum of the rows shown so the numbers match the chips
    people, team_empty = only_sales_team(result.get("people") or [])
    team = {p.get("user") for p in people}
    days = []
    for day in result.get("days") or []:
        rows = [r for r in day.get("by_owner") or [] if r.get("user") in team]
        days.append(
            {**day, "by_owner": rows, "total": sum(cint(r.get("count")) for r in rows)}
        )
    return {
        **result,
        "days": days,
        "people": people,
        "team_empty": team_empty,
        "available": True,
        "target": max(cint(target), 0),
    }


@frappe.whitelist()
def get_proposal_money(
    period: str = "month",
    from_date: str | None = None,
    to_date: str | None = None,
    owner: str | None = None,
    fresh: int | str = 0,
) -> dict:
    """The Overview's "Proposals & money": proposals sent, won, advances received in the
    period, and every payment split still to come in. `available` is false while the
    ERP site's TBO Smart is older than this."""
    require_leads()
    check_period(period, from_date, to_date)
    return read_proposal_money(period, from_date, to_date, owner, fresh)


def read_proposal_money(period, from_date, to_date, owner, fresh) -> dict:
    when = erp_period(period, from_date, to_date)
    result = cached_read(
        "money",
        {**when, "owner": owner or None},
        READ_TTL,
        fresh,
        lambda: call_if_deployed("get_proposal_money", **when, owner=owner or None),
        keep=lambda answer: answer is not None,
    )
    return {**result, "available": True} if result is not None else {"available": False}


@frappe.whitelist()
def get_business_overview(
    period: str = "month",
    from_date: str | None = None,
    to_date: str | None = None,
    department: str | None = None,
    include_profit: int | str = 0,
    fresh: int | str = 0,
) -> dict:
    """The management-only Business overview (docs/leads.md): company-wide pipeline,
    proposals, onboardings and revenue. Who may see it is decided on the ERP site
    (System Manager or its TBO Management role) and nowhere else: a refusal there is a
    403 here. `available` is false while the ERP site's TBO Smart is older than this."""
    require_leads()
    start, end = business_range(period, from_date, to_date)
    params = {
        "from_date": str(start),
        "to_date": str(end),
        "department": department or None,
        "include_profit": 1 if cint(include_profit) else 0,
    }
    result = cached_read(
        "business",
        params,
        READ_TTL,
        fresh,
        lambda: call_if_deployed(
            "get_business_overview",
            permission_message=_("Only management can see the Business overview."),
            **params,
        ),
        keep=lambda answer: answer is not None,
    )
    return (
        {**result, "available": True, "period": period}
        if result is not None
        else {"available": False}
    )


def business_range(period: str, from_date: str | None, to_date: str | None) -> tuple:
    """(from, to) of this month, last month, this quarter or financial year to date, or
    the dates picked."""
    if period not in BUSINESS_PERIODS:
        frappe.throw(
            _("Pick this month, last month, this quarter, this year or your own dates.")
        )
    now = getdate(today())
    if period == "custom":
        if not (from_date and to_date):
            frappe.throw(_("Pick both dates for your own period."))
        start, end = getdate(from_date), getdate(to_date)
        if end < start:
            frappe.throw(_("The to date is before the from date."))
        return start, end
    if period == "month":
        return getdate(get_first_day(now)), now
    if period == "last_month":
        first = getdate(add_months(get_first_day(now), -1))
        return first, getdate(get_last_day(first))
    if period == "quarter":
        return getdate(f"{now.year}-{3 * ((now.month - 1) // 3) + 1:02d}-01"), now
    year = now.year if now.month >= FY_START_MONTH else now.year - 1
    return getdate(f"{year}-{FY_START_MONTH:02d}-01"), now


@frappe.whitelist()
def get_overview_page(
    period: str = "month",
    from_date: str | None = None,
    to_date: str | None = None,
    owner: str | None = None,
    fresh: int | str = 0,
) -> dict:
    """Everything the Overview shows, in one request: `overview`, `money` and `intake`.
    The ERP site shares the hub's worker pool, so the reads go one after another here
    instead of as parallel requests that wait on each other. Money and intake are
    optional: one that fails leaves the overview whole and says why in `errors`."""
    require_leads()
    check_period(period, from_date, to_date)
    page = {
        "overview": read_overview(period, from_date, to_date, owner, fresh),
        "money": None,
        "intake": None,
        "errors": {},
    }
    for part, read in (
        (
            "money",
            lambda: read_proposal_money(period, from_date, to_date, owner, fresh),
        ),
        ("intake", lambda: read_lead_intake(fresh)),
    ):
        try:
            page[part] = read()
        except LeadsError as e:
            # frappe.throw queued the message for a toast; the page shows it in place
            frappe.clear_last_message()
            page["errors"][part] = str(e)
    return page


@frappe.whitelist()
def get_daily_report(
    date: str | None = None, owner: str | None = None, fresh: int | str = 0
) -> dict:
    """The Daily Sales Performance Report for one day (default today): one row per
    salesperson the signed-in person may see, or just `owner`. The hub adds the targets,
    each person's pace against them and the text to paste into WhatsApp. `available` is
    false while the ERP site's TBO Smart is older than this, so the tab stays out."""
    from helpdesk.daily_sales_report import prepare

    require_leads()
    day = getdate(date) if date else getdate(today())
    result = cached_read(
        "daily_report",
        {"date": str(day), "owner": owner or None},
        READ_TTL,
        fresh,
        lambda: call_if_deployed(
            "get_daily_report", date=str(day), owner=owner or None
        ),
        keep=lambda answer: answer is not None,
    )
    if result is None:
        return {"available": False}
    return {**prepare(result, owner=owner), "available": True}


def report_deployed() -> bool:
    """Whether the ERP site has the daily report and `log_call`, which ship together. Asked
    through the signed-in person's own report, remembered for ten minutes once it is
    there; any failure is "not now", never an error on the lead page."""
    require_leads()
    day = str(getdate(today()))
    try:
        return bool(
            cached_read(
                "report_deployed",
                {},
                OPTIONS_TTL,
                0,
                lambda: call_if_deployed(
                    "get_daily_report", date=day, owner=frappe.session.user
                )
                is not None,
            )
        )
    except LeadsError:
        frappe.clear_last_message()
        return False


@frappe.whitelist(methods=["POST"])
def log_call(lead: str, outcome: str, note: str | None = None) -> dict:
    """A call made outside MyOperator, logged on the lead as the signed-in person; it
    counts in today's report, so their cached reads go."""
    require_leads()
    if outcome not in CALL_OUTCOMES:
        frappe.throw(_("Pick Connected, No answer, Busy or Voicemail."))
    logged = call_if_deployed(
        "log_call",
        post=True,
        lead=lead,
        outcome=outcome,
        note=(note or "").strip() or None,
    )
    if logged is None:
        frappe.throw(
            _("The ERP site can't log calls yet. It needs the latest TBO Smart."),
            LeadsUnavailableError,
        )
    clear_cached_reads()
    return logged


def check_period(
    period: str,
    from_date: str | None,
    to_date: str | None,
    dates_required: bool = True,
) -> None:
    if period not in PERIODS:
        frappe.throw(
            _("Pick today, yesterday, a week, a month, a quarter or your own dates.")
        )
    if dates_required and period == "custom" and not (from_date and to_date):
        frappe.throw(_("Pick both dates for your own period."))


def erp_period(period: str, from_date: str | None, to_date: str | None) -> dict:
    """The period as the ERP site takes it: today and yesterday as a one-day custom range;
    dates only for a custom period."""
    if period in DAYS_AGO:
        day = str(add_days(getdate(today()), -DAYS_AGO[period]))
        return {"period": "custom", "from_date": day, "to_date": day}
    custom = period == "custom"
    return {
        "period": period,
        "from_date": from_date if custom else None,
        "to_date": to_date if custom else None,
    }


@frappe.whitelist()
def get_lead(name: str) -> dict:
    """The lead, its timeline, its quotations and the stages it may move to."""
    require_leads()
    return call("get_lead", name=name) or {}


@frappe.whitelist()
def get_lead_departments(fresh: int | str = 0) -> dict:
    """Every lead department with its heads and members, for Settings → CRM.
    `available` is false while the ERP site's TBO Smart is older than departments, so
    the section stays out."""
    require_leads()
    result = cached_read(
        "departments",
        {},
        READ_TTL,
        fresh,
        lambda: call_if_deployed("get_lead_departments"),
        keep=lambda answer: answer is not None,
    )
    if result is None:
        return {"available": False, "departments": []}
    return {"available": True, "departments": result}


@frappe.whitelist(methods=["POST"])
def save_lead_department(values: dict | str, name: str | None = None) -> dict:
    """Adds a lead department (or edits `name`): `department_name`, `lead_type`,
    `is_active`, `heads` and `members` (users). Only System Managers and Sales Managers
    on the ERP site may; it says so when it refuses."""
    require_leads()
    return change_department(
        "save_lead_department", values=parse_data(values), name=name or None
    )


@frappe.whitelist(methods=["POST"])
def set_lead_department_active(name: str, active: int | str = 1) -> dict:
    """Turns a lead department on or off; its leads stay where they are."""
    require_leads()
    return change_department(
        "set_lead_department_active", name=name, active=1 if cint(active) else 0
    )


def change_department(method: str, **params) -> dict:
    """A department write on the ERP site; the signed-in person's cached reads go, as the
    departments (and what they may see) changed."""
    saved = call_if_deployed(
        method,
        post=True,
        permission_message=_(
            "Only a System Manager or Sales Manager on the ERP site can manage lead departments."
        ),
        **params,
    )
    if saved is None:
        frappe.throw(
            _(
                "The ERP site can't manage lead departments yet. It needs the latest TBO Smart."
            ),
            LeadsUnavailableError,
        )
    clear_cached_reads()
    return saved


@frappe.whitelist()
def find_duplicate_leads(
    email: str | None = None,
    phone: str | None = None,
    company: str | None = None,
    exclude: str | None = None,
) -> dict:
    """Leads the signed-in person can see that share the email, phone or company typed on
    the lead form (`exclude`: the lead being edited), each with what it matched on.
    `available` is false while the ERP site's TBO Smart is older than this, so the
    form skips the check."""
    require_leads()
    email, phone, company = ((value or "").strip() for value in (email, phone, company))
    if not (email or phone or company):
        return {"available": True, "matches": []}
    matches = call_if_deployed(
        "find_duplicate_leads",
        email=email or None,
        phone=phone or None,
        company=company or None,
        exclude=(exclude or "").strip() or None,
    )
    if matches is None:
        return {"available": False, "matches": []}
    return {"available": True, "matches": matches}


@frappe.whitelist()
def get_stale_leads(fresh: int | str = 0) -> dict:
    """The signed-in person's leads with no activity for longer than their department
    allows, for the "No activity" chip on the list. `available` is false while the ERP
    site's TBO Smart is older than this."""
    require_leads()
    rows = cached_read(
        "stale",
        {},
        READ_TTL,
        fresh,
        lambda: read_stale_leads(read_options(fresh).get("departments") or []),
        keep=lambda answer: answer is not None,
    )
    if rows is None:
        return {"available": False, "leads": []}
    return {"available": True, "leads": rows}


def stale_days(department: str | None, departments: list[dict]) -> int:
    """How many idle days make a lead in `department` stale: the department's own
    `stale_after_days`, else the default."""
    for row in departments:
        if row.get("name") == department and cint(row.get("stale_after_days")) > 0:
            return cint(row["stale_after_days"])
    return DEFAULT_STALE_DAYS


def read_stale_leads(departments: list[dict], acting_user: str | None = None):
    """The stale leads the acting user (default: the signed-in person) may see, each kept
    only once idle for its own department's days; None while the ERP site's TBO Smart is
    older than `get_stale_leads`. The ERP site is asked for the shortest of the
    departments' days, so every department's threshold can be applied here."""
    days = min(
        [DEFAULT_STALE_DAYS]
        + [
            cint(d.get("stale_after_days"))
            for d in departments
            if cint(d.get("stale_after_days")) > 0
        ]
    )
    rows = call_if_deployed("get_stale_leads", acting_user=acting_user, days=days)
    if rows is None:
        return None
    return [
        row
        for row in rows
        if cint(row.get("idle_days"))
        >= stale_days(row.get("tbo_department"), departments)
    ]


@frappe.whitelist(methods=["POST"])
def create_lead(data: dict | str, allow_duplicate: int | str = 0) -> dict:
    """A new lead. The ERP site refuses one whose email or phone another lead already
    has, until the person confirms with `allow_duplicate`."""
    require_leads()
    extra = {"allow_duplicate": 1} if cint(allow_duplicate) else {}
    result = call("create_lead", post=True, data=parse_data(data), **extra) or {}
    clear_cached_reads()
    return result


@frappe.whitelist(methods=["POST"])
def update_lead(name: str, data: dict | str) -> dict:
    require_leads()
    result = call("update_lead", post=True, name=name, data=parse_data(data)) or {}
    clear_cached_reads()
    return result


@frappe.whitelist(methods=["POST"])
def set_stage(name: str, stage: str, note: str | None = None) -> dict:
    require_leads()
    result = (
        call(
            "set_stage",
            post=True,
            name=name,
            stage=stage,
            note=(note or "").strip() or None,
        )
        or {}
    )
    clear_cached_reads()
    return result


@frappe.whitelist(methods=["POST"])
def add_note(name: str, note: str) -> dict:
    require_leads()
    note = (note or "").strip()
    if not note:
        frappe.throw(_("Write the note first."))
    return call("add_note", post=True, name=name, note=note) or {}


# --- AI runs leads: the AI proposes, a person decides and sends -----------------


@frappe.whitelist()
def get_lead_ai(name: str) -> dict:
    """The lead's "AI suggests": summary, sentiment, intent, next best action, a
    stage to suggest and a draft, its health and likely duplicates."""
    require_leads()
    return call("get_lead_ai", name=name) or {}


@frappe.whitelist(methods=["POST"])
def refresh_lead_ai(name: str) -> dict:
    require_leads()
    return call("refresh_lead_ai", post=True, name=name) or {}


@frappe.whitelist(methods=["POST"])
def apply_ai_stage(name: str) -> dict:
    """Moves the lead to the stage the AI suggested, as the signed-in person."""
    require_leads()
    return call("apply_ai_stage", post=True, name=name) or {}


@frappe.whitelist(methods=["POST"])
def dismiss_ai_stage(name: str) -> dict:
    require_leads()
    return call("dismiss_ai_stage", post=True, name=name) or {}


@frappe.whitelist(methods=["POST"])
def draft_lead_message(name: str, channel: str, language: str = "en") -> dict:
    """A WhatsApp or email text to edit and send from the person's own app; the
    ERP site sends nothing."""
    require_leads()
    if channel not in MESSAGE_CHANNELS:
        frappe.throw(_("Pick WhatsApp or email."))
    return (
        call(
            "draft_lead_message",
            post=True,
            name=name,
            channel=channel,
            language=language if language in ("en", "ml") else "en",
        )
        or {}
    )


@frappe.whitelist(methods=["POST"])
def log_message_sent(name: str, channel: str, text: str) -> dict:
    """The person sent the message from their own WhatsApp or mail: put it on the
    lead's timeline as theirs."""
    require_leads()
    if channel not in MESSAGE_CHANNELS:
        frappe.throw(_("Pick WhatsApp or email."))
    text = (text or "").strip()
    if not text:
        frappe.throw(_("Write the message first."))
    return (
        call("log_message_sent", post=True, name=name, channel=channel, text=text) or {}
    )


# --- calls through MyOperator (TBO Smart's docs/telephony-myoperator.md) ----------


@frappe.whitelist(methods=["POST"])
def click_to_call(name: str, number: str | None = None) -> dict:
    """MyOperator rings the signed-in person's phone, then the lead (`number`: one of
    the lead's own numbers; default its mobile)."""
    require_leads()
    return (
        call(
            "click_to_call",
            post=True,
            api=TELEPHONY,
            lead=name,
            number=(number or "").strip() or None,
        )
        or {}
    )


@frappe.whitelist()
def call_recording(call: str) -> None:
    """A call's recording, streamed from the ERP site, which plays it only to people
    who may read the lead."""
    require_leads()
    content, content_type = download(
        "call_recording", api=TELEPHONY, call=(call or "").strip()
    )
    frappe.local.response.filename = f"call-{call}.mp3"
    frappe.local.response.filecontent = content
    frappe.local.response.content_type = (
        content_type if content_type in AUDIO_TYPES else "audio/mpeg"
    )
    frappe.local.response.display_content_as = "inline"
    frappe.local.response.type = "download"


# --- place and photos (docs/leads.md) ----------------------------------------------


@frappe.whitelist()
def get_lead_photos(lead: str) -> dict:
    """{available, photos}: the lead's photos newest first. `available` is false while the
    ERP site's TBO Smart is older than lead photos, so the card stays out."""
    require_leads()
    photos = call_if_deployed("get_lead_photos", lead=lead)
    if photos is None:
        return {"available": False, "photos": []}
    return {"available": True, "photos": photos}


@frappe.whitelist(methods=["POST"])
def upload_lead_photo(
    lead: str, filename: str, content: str, caption: str | None = None
) -> dict:
    """A photo on the lead as the signed-in person (`content` base64; the ERP site checks
    it is a PNG, JPEG or WebP of at most 10 MB and that the lead has room)."""
    require_leads()
    if not content or len(content) > MAX_PHOTO_BASE64:
        frappe.throw(_("Choose a photo of at most 10 MB."))
    return (
        call(
            "upload_lead_photo",
            post=True,
            lead=lead,
            filename=(filename or "").strip()[:120] or "photo",
            content=content,
            caption=(caption or "").strip()[:140] or None,
        )
        or {}
    )


@frappe.whitelist(methods=["POST"])
def delete_lead_photo(lead: str, file: str) -> dict:
    require_leads()
    return call("delete_lead_photo", post=True, lead=lead, file=file) or {}


@frappe.whitelist()
def lead_photo(lead: str, file: str, thumb: int | str = 0) -> None:
    """A lead photo's image (`thumb` 1: a small one), streamed from the ERP site, which
    shows it only to people who may read the lead."""
    require_leads()
    content, content_type = download(
        "get_lead_photo", lead=lead, file=file, thumb=1 if cint(thumb) else 0
    )
    if content_type not in PHOTO_TYPES:
        frappe.throw(_("That photo isn't available."), frappe.DoesNotExistError)
    frappe.local.response.filename = f"{file}.{content_type.split('/')[1]}"
    frappe.local.response.filecontent = content
    frappe.local.response.content_type = content_type
    frappe.local.response.display_content_as = "inline"
    frappe.local.response.type = "download"


def cache_lead_photo(response, request) -> None:
    """after_request hook: a photo is the same bytes every time (its file never changes), so
    the browser keeps it for an hour, for that person only."""
    if request.path.endswith(PHOTO_METHOD) and response.status_code == 200:
        response.headers["Cache-Control"] = PHOTO_CACHE


def parse_data(data: dict | str) -> dict:
    data = frappe.parse_json(data) if isinstance(data, str) else data
    if not isinstance(data, dict):
        frappe.throw(_("The lead's details must be a set of fields."))
    return data
