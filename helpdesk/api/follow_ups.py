"""Settings → Follow-ups, the test digest and the views of what the engine found.

The engine is helpdesk.follow_ups; docs/follow-ups.md describes both.
"""

import frappe
from frappe import _
from frappe.model import no_value_fields

from helpdesk import follow_ups
from helpdesk.recurrence import time_label
from helpdesk.tasky.permissions import is_tasky_admin
from helpdesk.utils import agent_only

# what the page may change; digest_sent_through is the engine's own bookkeeping
READ_ONLY_FIELDS = ("digest_sent_through",)


def check_admin():
    # only_for is skipped in tests, so check the roles directly
    if not is_tasky_admin():
        frappe.throw(
            _("Only System Managers and Agent Managers can change follow-ups."),
            frappe.PermissionError,
        )


def editable_fields() -> list[str]:
    meta = frappe.get_meta(follow_ups.SETTINGS)
    return [
        df.fieldname
        for df in meta.fields
        if df.fieldtype not in no_value_fields and df.fieldname not in READ_ONLY_FIELDS
    ]


@frappe.whitelist()
def get_settings() -> dict:
    """The settings, with where working hours, auto-close and chat come from."""
    check_admin()
    doc = follow_ups.get_settings()
    hd = frappe.get_cached_doc("HD Settings")
    chat = frappe.get_cached_doc("HD Chat Settings")
    return {
        "settings": {f: doc.get(f) for f in editable_fields()},
        "working_hours": working_hours(),
        "auto_close": {
            "enabled": bool(hd.auto_close_tickets),
            "days": hd.auto_close_after_days,
            "status": hd.auto_close_status,
        },
        "chat": {
            "enabled": bool(chat.enabled),
            "platform": chat.platform,
            "direct_messages": bool(
                chat.get_password("teams_direct_webhook", raise_exception=False)
                if chat.platform == "Microsoft Teams"
                else chat.slack_bot_token
            ),
        },
    }


def working_hours() -> dict:
    """The default SLA's working days and hours, which the follow-ups keep to."""
    name = frappe.db.get_value(
        "HD Service Level Agreement", {"default_sla": 1, "enabled": 1}
    )
    if not name:
        return {"sla": None, "days": []}
    sla = frappe.get_cached_doc("HD Service Level Agreement", name)
    return {
        "sla": name,
        "holiday_list": sla.holiday_list,
        "days": [
            {
                "day": row.workday,
                "start": time_label(row.start_time),
                "end": time_label(row.end_time),
            }
            for row in sla.support_and_resolution
        ],
    }


@frappe.whitelist(methods=["POST"])
def save_settings(values: dict | str) -> dict:
    check_admin()
    values = frappe.parse_json(values) or {}
    allowed = set(editable_fields())
    doc = frappe.get_doc(follow_ups.SETTINGS)
    doc.update({k: v for k, v in values.items() if k in allowed})
    doc.save(ignore_permissions=True)
    follow_ups.clear_cache()
    return {f: doc.get(f) for f in editable_fields()}


@frappe.whitelist(methods=["POST"])
def send_test_digest() -> dict:
    """Today's digest for the person asking, sent to them only, now."""
    check_admin()
    user = frappe.session.user
    items = follow_ups.items_by_user(follow_ups.current()).get(user, [])
    steps = follow_ups.plan_steps(user)
    subject, sections = follow_ups.compose_digest(user, items, steps)
    via = follow_ups.deliver_digest(user, subject, sections)
    if not via:
        frappe.throw(
            _(
                "The digest couldn't be sent: set up chat in Settings → Chat & Teams or an outgoing email account, and keep email notifications on."
            )
        )
    return {"via": via, "items": len(items)}


@frappe.whitelist()
def get_preview() -> list[dict]:
    """What each person would get in their digest now."""
    check_admin()
    return follow_ups.preview()


@frappe.whitelist()
@agent_only
def get_follow_up_overview() -> dict:
    """The Overview's Follow-ups section, for managers."""
    check_admin()
    return follow_ups.overview()
