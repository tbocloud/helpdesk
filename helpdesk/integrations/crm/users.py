"""Keep every active helpdesk agent as a user in the TBO CRM.

Missing users are created on the CRM site (with a welcome email so they can set a
password), disabled ones are enabled again, and anyone without a CRM role gets the
role from HD CRM Settings through Frappe CRM's own API. People who leave the helpdesk
are not touched on the CRM site; that stays a manual decision there.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from helpdesk.automation import automation_user
from helpdesk.integrations.crm.client import CRMClient, CRMError

# a user with any of these already has CRM access
CRM_ROLES = {"Sales User", "Sales Manager", "System Manager"}
SYNC_JOB = "helpdesk.integrations.crm.users.sync_users_job"


def helpdesk_users() -> list[dict]:
    """Active agents with an enabled desk account, minus system and bot users."""
    skip = {"Administrator", "Guest", automation_user()}
    agents = frappe.get_all(
        "HD Agent", filters={"is_active": 1}, fields=["user", "agent_name"]
    )
    users = {
        u.name: u
        for u in frappe.get_all(
            "User",
            filters={
                "name": ["in", [a.user for a in agents] or [""]],
                "enabled": 1,
                "user_type": "System User",
            },
            fields=["name", "full_name"],
        )
    }
    return [
        {"email": a.user, "full_name": users[a.user].full_name or a.agent_name}
        for a in agents
        if a.user in users and a.user not in skip
    ]


def sync_users() -> dict:
    """Make the CRM match the helpdesk's active agents; returns what changed."""
    settings = frappe.get_single("HD CRM Settings")
    client = CRMClient.from_settings()
    result = {
        "created": [],
        "enabled": [],
        "role_added": [],
        "in_sync": 0,
        "failed": [],
    }
    needs_role = []
    for person in helpdesk_users():
        email = person["email"]
        try:
            crm_user = client.get_user(email)
            if not crm_user:
                client.create_user(
                    email, person["full_name"], settings.send_welcome_email
                )
                result["created"].append(email)
                needs_role.append(email)
                continue
            if not crm_user.get("enabled"):
                client.enable_user(email)
                result["enabled"].append(email)
            roles = {row.get("role") for row in crm_user.get("roles") or []}
            if roles & CRM_ROLES:
                result["in_sync"] += 1
            else:
                needs_role.append(email)
        except CRMError as e:
            result["failed"].append(f"{email}: {e}")
    if needs_role:
        try:
            client.add_to_crm(needs_role, settings.crm_role or "Sales User")
            result["role_added"] = needs_role
        except CRMError as e:
            result["failed"].append(_("Couldn't give CRM roles: {0}").format(str(e)))
    record_result(result)
    return result


def record_result(result: dict):
    text = _(
        "{0} created, {1} enabled again, {2} given a CRM role, {3} already in the CRM."
    ).format(
        len(result["created"]),
        len(result["enabled"]),
        len(result["role_added"]),
        result["in_sync"],
    )
    if result["failed"]:
        text += " " + _("Failed: {0}").format("; ".join(result["failed"])[:900])
    frappe.db.set_single_value(
        "HD CRM Settings", {"last_sync_on": now_datetime(), "last_sync_result": text}
    )


def is_on() -> bool:
    return bool(
        frappe.db.get_single_value("HD CRM Settings", "enabled")
        and frappe.db.get_single_value("HD CRM Settings", "sync_users")
    )


def sync_users_job():
    """Hourly, and after an agent is added: a failure is logged, never raised."""
    if not is_on():
        return
    try:
        sync_users()
    except CRMError as e:
        frappe.log_error(title="CRM user sync failed", message=str(e))


def on_agent_change(doc, method=None):
    """HD Agent saved: a new or re-activated agent gets their CRM user soon, not in an hour."""
    if not doc.is_active or not is_on():
        return
    if method != "after_insert" and not doc.has_value_changed("is_active"):
        return
    frappe.enqueue(
        SYNC_JOB,
        job_id="crm-user-sync",
        deduplicate=True,
        enqueue_after_commit=True,
    )
