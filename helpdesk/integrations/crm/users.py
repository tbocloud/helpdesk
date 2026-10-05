"""Keep helpdesk agents and TBO CRM users in step, both ways, adding only what's missing.

- Helpdesk → CRM: every active agent gets a CRM user (welcome email optional), a disabled
  one is enabled again, and anyone without a CRM role gets the role from HD CRM Settings
  through Frappe CRM's own API.
- CRM → helpdesk: a CRM user (Sales User or Sales Manager) without a helpdesk account gets
  one, as an agent. Existing helpdesk users are left as they are.
- Leaving: users this connection created on the CRM site are disabled there when they're
  disabled or deactivated in helpdesk. People created directly in the CRM are never touched.
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from helpdesk.automation import automation_user
from helpdesk.integrations.crm.client import CRMClient, CRMError

# a user with any of these already has CRM access
CRM_ROLES = {"Sales User", "Sales Manager", "System Manager"}
SYNC_JOB = "helpdesk.integrations.crm.users.sync_users_job"
SKIP = {"Administrator", "Guest"}


def helpdesk_users() -> list[dict]:
    """Active agents with an enabled desk account, minus system and bot users."""
    skip = SKIP | {automation_user()}
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
    """Make both sides match; returns what changed."""
    settings = frappe.get_single("HD CRM Settings")
    client = CRMClient.from_settings()
    result = {
        "created": [],
        "enabled": [],
        "role_added": [],
        "in_sync": 0,
        "added_to_helpdesk": [],
        "disabled_in_crm": [],
        "failed": [],
    }
    created_before = created_in_crm()
    if settings.sync_users:
        push_users(client, settings, result)
    if settings.add_crm_users:
        pull_users(client, settings, result)
    if settings.disable_left_users:
        disable_left_users(client, created_before, result)
    remember_created(created_before | set(result["created"]))
    record_result(result)
    return result


def push_users(client, settings, result: dict):
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
            result["failed"].append(f"{email}: {str(e)}")
    if needs_role:
        try:
            client.add_to_crm(needs_role, settings.crm_role or "Sales User")
            result["role_added"] = needs_role
        except CRMError as e:
            result["failed"].append(_("Couldn't give CRM roles: {0}").format(str(e)))


def pull_users(client, settings, result: dict):
    """CRM users without a helpdesk account become agents; nobody existing is changed."""
    try:
        crm_users = client.crm_users()
    except CRMError as e:
        result["failed"].append(_("Couldn't read CRM users: {0}").format(str(e)))
        return
    for person in crm_users:
        email = (person.get("email") or "").strip().lower()
        if not email or email in SKIP or frappe.db.exists("User", email):
            continue
        try:
            add_helpdesk_agent(
                email, person.get("full_name"), settings.send_welcome_email
            )
            result["added_to_helpdesk"].append(email)
        except frappe.ValidationError as e:
            result["failed"].append(f"{email}: {str(e)}")


def add_helpdesk_agent(email: str, full_name: str | None, send_welcome_email: bool):
    first, _sep, last = (full_name or email.split("@")[0]).partition(" ")
    frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": first,
            "last_name": last or None,
            "user_type": "System User",
            "send_welcome_email": 1 if send_welcome_email else 0,
        }
    ).insert(ignore_permissions=True)
    # HD Agent gives the Agent role when it's saved
    frappe.get_doc(
        {
            "doctype": "HD Agent",
            "user": email,
            "agent_name": full_name or first,
            "is_active": 1,
        }
    ).insert(ignore_permissions=True)


def disable_left_users(client, created: set, result: dict):
    """Users this connection created in the CRM, who left helpdesk, are disabled there."""
    active = {p["email"] for p in helpdesk_users()}
    for email in sorted(created - active):
        try:
            crm_user = client.get_user(email)
            if crm_user and crm_user.get("enabled"):
                client.disable_user(email)
                result["disabled_in_crm"].append(email)
        except CRMError as e:
            result["failed"].append(f"{email}: {str(e)}")


def created_in_crm() -> set:
    raw = frappe.db.get_single_value("HD CRM Settings", "created_in_crm") or "[]"
    try:
        return set(json.loads(raw))
    except ValueError:
        return set()


def remember_created(emails: set):
    frappe.db.set_single_value(
        "HD CRM Settings", "created_in_crm", json.dumps(sorted(emails))
    )


def record_result(result: dict):
    text = _(
        "Users: {0} created in the CRM, {1} enabled again, {2} given a CRM role, {3} already there; {4} added to helpdesk; {5} disabled in the CRM."
    ).format(
        len(result["created"]),
        len(result["enabled"]),
        len(result["role_added"]),
        result["in_sync"],
        len(result["added_to_helpdesk"]),
        len(result["disabled_in_crm"]),
    )
    if result["failed"]:
        text += " " + _("Failed: {0}").format("; ".join(result["failed"])[:900])
    frappe.db.set_single_value(
        "HD CRM Settings", {"last_sync_on": now_datetime(), "last_sync_result": text}
    )


def is_on() -> bool:
    return bool(frappe.db.get_single_value("HD CRM Settings", "enabled"))


def sync_users_job():
    """Hourly, and after an agent changes: users then customers; failures are logged."""
    if not is_on():
        return
    from helpdesk.integrations.crm.customers import sync_customers

    try:
        sync_users()
        if frappe.db.get_single_value("HD CRM Settings", "sync_customers"):
            sync_customers()
    except CRMError as e:
        frappe.log_error(title="CRM sync failed", message=str(e))


def on_agent_change(doc, method=None):
    """HD Agent saved: a new, re-activated or deactivated agent is synced soon, not in an hour."""
    if not is_on():
        return
    if method != "after_insert" and not doc.has_value_changed("is_active"):
        return
    frappe.enqueue(
        SYNC_JOB,
        job_id="crm-user-sync",
        deduplicate=True,
        enqueue_after_commit=True,
    )
