"""The Lead Bank (docs/lead-bank.md): thin proxies to TBO Smart's `tbo_smart.api.hub_lead_bank`
and `hub_commission`'s referral settings, plus the photo reading, which is the hub's own.

Open to every active agent (`can_use_lead_bank`), a separate path from Leads: the ERP site decides
what each person may do, and a collector gets back only the leads they added.
"""

import frappe
from frappe import _
from frappe.utils import cint

from helpdesk import lead_bank
from helpdesk.api.leads import MAX_PAGE, parse_data
from helpdesk.integrations.crm.leads import (
    LeadsUnavailableError,
    call_if_deployed,
    require_lead_bank,
)

COMMISSION = "tbo_smart.api.hub_commission"
OLDER_ERP = "The Lead Bank needs the latest TBO Smart on the ERP site."
NOT_ON_ERP = "Your account isn't on the ERP site yet. Ask an admin to sync users in Settings → CRM."
MANAGERS_ONLY = "Only a Sales Manager, System Manager or TBO Management can do this."


def ask(
    method: str,
    post: bool = False,
    api: str = lead_bank.LEAD_BANK_API,
    managers: bool = False,
    **params
):
    """The ERP site's answer as the signed-in person; an older TBO Smart says so in words."""
    require_lead_bank()
    result = call_if_deployed(
        method,
        post=post,
        api=api,
        permission_message=_(MANAGERS_ONLY if managers else NOT_ON_ERP),
        **params,
    )
    if result is None:
        frappe.throw(_(OLDER_ERP), LeadsUnavailableError)
    return result


@frappe.whitelist()
def get_options() -> dict:
    """The regions with their referral rate, the cap and whether the person manages the Lead
    Bank (the ERP site decides)."""
    return ask("get_options")


@frappe.whitelist(methods=["POST"])
def scan_photos(
    photos: list | str,
    latitude: float | str | None = None,
    longitude: float | str | None = None,
) -> dict:
    """Read 1 to 5 photos ([{filename, content (base64)}]) with the hub's AI and say what the form
    should hold: {fields: {company_name, contact_name, mobile_no, phone, email_id, website,
    business_type, address, state}, message (when the photos couldn't be read), region, region_by
    ("phone" / "gps"), duplicate ({duplicate, mine, message} when the business is already a
    lead)}. Nothing is saved."""
    require_lead_bank()
    lead_bank.check_scan_limit()
    return lead_bank.scan(photos, latitude, longitude)


@frappe.whitelist()
def detect_region(
    phones: list | str | None = None,
    latitude: float | str | None = None,
    longitude: float | str | None = None,
) -> dict:
    """{region, by}: India, UAE or KSA from the phone numbers' prefix, else the GPS fix."""
    return ask(
        "detect_region", phones=phones or [], latitude=latitude, longitude=longitude
    )


@frappe.whitelist()
def check_duplicate(
    email: str | None = None, phone: str | None = None, company: str | None = None
) -> dict:
    """{duplicate, mine, message}: whether the business is already a lead, in plain words."""
    return ask(
        "check_duplicate",
        email=(email or "").strip() or None,
        phone=(phone or "").strip() or None,
        company=(company or "").strip() or None,
    )


@frappe.whitelist(methods=["POST"])
def submit_lead(data: dict | str, photos: list | str) -> dict:
    """Add the lead: {created, duplicate, mine, lead, region, department, in_pool, message}. A
    business the team already has is not made again; the first collector keeps the credit."""
    photos = frappe.parse_json(photos) if isinstance(photos, str) else photos
    if photos:
        lead_bank.photo_images(photos)
    return ask(
        "submit_lead",
        post=True,
        data=parse_data(data),
        photos=photos,
    )


@frappe.whitelist()
def get_my_leads(start: int | str = 0, page_length: int | str = 50) -> dict:
    """The leads the person added, with where each stands and what they earned or will earn."""
    return ask(
        "get_my_leads",
        start=max(cint(start), 0),
        page_length=min(max(cint(page_length) or 50, 1), MAX_PAGE),
    )


@frappe.whitelist()
def get_dashboard(month: str | None = None) -> dict:
    """Managers: the month's leads by region and collector, conversion, the pool and the referral
    due."""
    return ask("get_dashboard", managers=True, month=(month or "").strip() or None)


@frappe.whitelist(methods=["POST"])
def reassign_credit(lead: str, user: str, reason: str) -> dict:
    """Managers: move a lead's referral credit to another person, with a reason."""
    return ask(
        "reassign_credit", post=True, managers=True, lead=lead, user=user, reason=reason
    )


@frappe.whitelist()
def get_referral_settings() -> dict:
    """Managers: the referral rates, the cap and the department of each region."""
    return ask("get_referral_settings", api=COMMISSION, managers=True)


@frappe.whitelist(methods=["POST"])
def save_referral_settings(values: dict | str) -> dict:
    """Managers: set the rates, the cap and the departments."""
    return ask(
        "save_referral_settings",
        post=True,
        api=COMMISSION,
        managers=True,
        values=parse_data(values),
    )
