"""Sales → Lead report (docs/weekly-lead-report.md): the KSA division's sheet of each
salesperson's leads, read live from the division's ERP site.

A row is a lead created or updated in the week, under its owner. Every column is the lead's
own: the KSA site's Lead has the sheet's fields (conversion possibility, visits this week,
follow-up plan; remarks are its Comment). The hub keeps nothing.
"""

from collections import defaultdict
from datetime import timedelta

import frappe
from frappe.core.utils import html2text
from frappe.utils import add_days, cint, escape_html, flt, getdate

from helpdesk.divisions import (
    DIVISION,
    active_division,
    division_client,
    division_without_site,
    is_super_admin,
    leads_closed_by_site,
    memberships,
    overview_divisions,
)
from helpdesk.integrations.crm.leads import can_use_leads

# the KSA site's Lead fields (Custom Fields made there on 2026-11-25) and the ones it had
CONVERSION_FIELD = "custom_conversion_possibility"
VISITS_FIELD = "custom_visits_this_week"
FOLLOW_UP_FIELD = "custom_follow_up_plan"
REMARKS_FIELD = "custom_comment"
SEGMENT_FIELD = "custom_lead_segment"
DESIGNATION_FIELD = "job_title"
CONVERSIONS = ("High", "Medium", "Low", "Not Possible")
FOLLOW_UPS = ("Yes", "No")
MAX_VISITS = 99
MAX_REMARKS = 1000
MAX_DESIGNATION = 140

LEAD_FIELDS = [
    "name",
    "lead_owner",
    "company_name",
    "lead_name",
    DESIGNATION_FIELD,
    "mobile_no",
    "phone",
    "email_id",
    "industry",
    "tbo_business_type",
    "tbo_lead_type",
    "modified",
    SEGMENT_FIELD,
    CONVERSION_FIELD,
    VISITS_FIELD,
    FOLLOW_UP_FIELD,
    REMARKS_FIELD,
]
# the KSA site's Lead Segment, in the words of the template's Requirement column
SEGMENT_LABELS = {"Erpnext": "ERPNext", "Digital": "Digital Marketing"}


def week_start(value=None):
    """The Sunday the week of `value` (today by default) starts on: KSA works Sunday to
    Thursday, so its weekly report runs from Sunday."""
    day = getdate(value)
    return day - timedelta(days=(day.weekday() + 1) % 7)


def report_division(user: str | None = None) -> str | None:
    """The user's active division, when it keeps the lead report (a Super Admin
    switches it on per division) and its leads are open to them; else None."""
    user = user or frappe.session.user
    division = active_division(user)
    if not division or not frappe.db.get_value(
        DIVISION, division, "weekly_lead_report"
    ):
        return None
    if not (is_super_admin(user) or division in memberships(user)):
        return None
    if (
        not can_use_leads(user)
        or division_without_site(user)
        or leads_closed_by_site(user)
    ):
        return None
    return division


def sees_team(division: str, user: str | None = None) -> bool:
    """Super Admins and the division's managers see everyone's rows; a salesperson their own."""
    user = user or frappe.session.user
    return is_super_admin(user) or division in overview_divisions(user)


def read_week(division: str, start, owner: str | None = None) -> list[dict]:
    """The leads created or updated in the week starting `start` (only `owner`'s, when
    given), in the template's columns, read from the division's ERP site with the hub's key."""
    client = division_client(division)
    filters = [
        ["modified", ">=", str(start)],
        ["modified", "<", str(add_days(start, 7))],
    ]
    if owner:
        filters.append(["lead_owner", "=", owner])
    leads = client.get_list("Lead", LEAD_FIELDS, filters)
    quotations = read_quotations(client, [lead["name"] for lead in leads])
    return [lead_columns(lead, quotations.get(lead["name"], [])) for lead in leads]


def read_lead(client, name: str) -> dict:
    """One lead in the template's columns."""
    leads = client.get_list("Lead", LEAD_FIELDS, [["name", "=", name]])
    if not leads:
        frappe.throw(frappe._("That lead isn't on the ERP site any more."))
    return lead_columns(leads[0], read_quotations(client, [name]).get(name, []))


def read_quotations(client, names: list[str]) -> dict[str, list[dict]]:
    """{lead: its quotations}, cancelled ones left out."""
    if not names:
        return {}
    by_lead: dict[str, list[dict]] = defaultdict(list)
    for quotation in client.get_list(
        "Quotation",
        ["name", "party_name", "grand_total", "currency", "transaction_date"],
        [
            ["quotation_to", "=", "Lead"],
            ["party_name", "in", names],
            ["docstatus", "<", 2],
        ],
    ):
        by_lead[quotation["party_name"]].append(quotation)
    return by_lead


def lead_columns(lead: dict, quotations: list[dict]) -> dict:
    """The template's columns of one lead."""
    latest = max(
        quotations,
        key=lambda q: (str(q.get("transaction_date") or ""), q["name"]),
        default=None,
    )
    segment = lead.get(SEGMENT_FIELD)
    return {
        "lead": lead["name"],
        "salesperson": lead.get("lead_owner") or "",
        "updated": str(lead.get("modified") or ""),
        "company_name": lead.get("company_name") or lead.get("lead_name") or "",
        "contact_number": lead.get("mobile_no") or lead.get("phone") or "",
        "email": lead.get("email_id") or "",
        "business": lead.get("industry") or lead.get("tbo_business_type") or "",
        "contact_name": lead.get("lead_name") or "",
        "designation": lead.get(DESIGNATION_FIELD) or "",
        "requirement": segment or "",
        "requirement_label": SEGMENT_LABELS.get(segment, segment)
        or lead.get("tbo_lead_type")
        or "",
        "quoted": bool(quotations),
        "quoted_value": flt(latest["grand_total"], 2) if latest else None,
        "currency": latest.get("currency") if latest else None,
        "quotation": latest["name"] if latest else "",
        "quotation_count": len(quotations),
        "conversion": lead.get(CONVERSION_FIELD) or "",
        "visits": cint(lead.get(VISITS_FIELD)),
        "follow_up": lead.get(FOLLOW_UP_FIELD) or "",
        "remarks": remarks_text(lead.get(REMARKS_FIELD)),
    }


def remarks_text(html: str | None) -> str:
    """The lead's Comment (a text editor field) as plain text."""
    return html2text(html or "", wrap=False).strip() if html else ""


def remarks_html(text: str) -> str:
    """Plain remarks as the Comment field keeps them."""
    return "<br>".join(escape_html(line) for line in text.splitlines())


# a filter value that keeps the leads with the field empty
NOT_SET = "not_set"


def filter_rows(rows: list[dict], filters: dict) -> list[dict]:
    """The rows matching every filter given: `search` (a part of the company, contact,
    number or email), `requirement`, `conversion` and `follow_up` (that value, or NOT_SET
    for empty), and `quoted` ("Yes" or "No")."""
    search = str(filters.get("search") or "").strip().casefold()
    picked = {
        key: filters[key]
        for key in ("requirement", "conversion", "follow_up")
        if filters.get(key)
    }
    quoted = filters.get("quoted")

    def keeps(row: dict) -> bool:
        if search and not any(
            search in str(row[key]).casefold()
            for key in ("company_name", "contact_name", "contact_number", "email")
        ):
            return False
        for key, value in picked.items():
            if (row[key] or NOT_SET) != value:
                return False
        return not quoted or row["quoted"] == (quoted == "Yes")

    return [row for row in rows if keeps(row)]
