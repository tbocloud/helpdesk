"""The stand-up page (/helpdesk/standup) and Settings → Stand-up.

The rules live in helpdesk.standup; docs/standup.md describes both.
"""

import frappe

from helpdesk import standup
from helpdesk.api.chat_settings import mask
from helpdesk.api.follow_ups import check_admin
from helpdesk.utils import agent_only

PLAIN_FIELDS = (
    "enabled",
    "open_at",
    "remind_at",
    "post_at",
    "include_hours",
    "team_view_heads",
    "team_view_leads",
    "team_view_project_managers",
)


@frappe.whitelist()
@agent_only
def get_my_standup(date: str | None = None) -> dict:
    """The caller's stand-up for `date` (today), with what the page needs around it."""
    return standup.my_standup(frappe.session.user, date)


@frappe.whitelist(methods=["POST"])
@agent_only
def save_standup(values: dict | str) -> dict:
    """Today's stand-up as edited, still a draft (or still submitted)."""
    return standup.save(frappe.session.user, frappe.parse_json(values) or {})


@frappe.whitelist(methods=["POST"])
@agent_only
def submit_standup(values: dict | str | None = None) -> dict:
    """Save today's stand-up and submit it."""
    return standup.save(frappe.session.user, frappe.parse_json(values) or {}, True)


@frappe.whitelist()
@agent_only
def get_team_standup(team: str | None = None, date: str | None = None) -> dict:
    """A department's stand-ups: the team view for its heads, leads and managers, the
    channel's summary for its members."""
    return standup.team_standup(frappe.session.user, team, date)


@frappe.whitelist()
@agent_only
def get_standup_history(user: str | None = None, limit: int | str = 30) -> dict:
    return standup.history(frappe.session.user, user, int(limit or 30))


@frappe.whitelist(methods=["POST"])
@agent_only
def nudge(name: str) -> dict:
    return standup.nudge(frappe.session.user, name)


@frappe.whitelist(methods=["POST"])
@agent_only
def assign_help(name: str, row: str, helper: str) -> dict:
    return standup.assign_help(frappe.session.user, name, row, helper)


@frappe.whitelist(methods=["POST"])
@agent_only
def create_task_from_blocker(
    name: str,
    row: str,
    project: str,
    subject: str,
    assigned_to: str | None = None,
    due_date: str | None = None,
) -> dict:
    return standup.create_task_from_blocker(
        frappe.session.user, name, row, project, subject, assigned_to, due_date
    )


# --- Settings → Stand-up ---------------------------------------------------------


@frappe.whitelist()
def get_settings() -> dict:
    check_admin()
    return settings_payload(frappe.get_doc(standup.SETTINGS))


@frappe.whitelist(methods=["POST"])
def save_settings(values: dict | str) -> dict:
    """Plain fields as sent. Departments in the order sent; a row's channel URL only
    changes when `channel_webhook` is sent (a value replaces it, "" removes it), since
    a Teams workflow URL is a secret and never goes back to the browser."""
    check_admin()
    values = frappe.parse_json(values) or {}
    doc = frappe.get_doc(standup.SETTINGS)
    doc.update({k: v for k, v in values.items() if k in PLAIN_FIELDS})
    if "departments" in values:
        stored = {row.department: row for row in doc.departments}
        rows = []
        for raw in values.get("departments") or []:
            department = (raw or {}).get("department")
            if not department:
                continue
            old = stored.get(department)
            webhook = raw.get("channel_webhook")
            if webhook is None:
                webhook = (
                    old.get_password("channel_webhook", raise_exception=False)
                    if old
                    else ""
                )
            rows.append({"department": department, "channel_webhook": webhook or ""})
        doc.set("departments", rows)
    doc.save(ignore_permissions=True)
    return settings_payload(frappe.get_doc(standup.SETTINGS))


def settings_payload(doc) -> dict:
    from helpdesk.chat_notifications import get_settings as chat_settings

    chat = chat_settings()
    return {
        "settings": {
            f: (doc.get(f) if doc.get(f) is not None else default(f))
            for f in PLAIN_FIELDS
        },
        "departments": [
            {
                "department": row.department,
                "channel": channel_status(
                    row.get_password("channel_webhook", raise_exception=False)
                ),
            }
            for row in doc.departments
        ],
        "chat": {
            "enabled": bool(chat.enabled),
            "platform": chat.platform,
            "fallback_channel": bool(
                chat.get_password("teams_channel_webhook", raise_exception=False)
                if chat.platform == "Microsoft Teams"
                else chat.slack_escalation_channel
            ),
        },
    }


def channel_status(value: str | None) -> dict:
    return {"set": bool(value), "masked": mask(value) if value else ""}


def default(field: str):
    if field in standup.DEFAULT_TIMES:
        return standup.DEFAULT_TIMES[field]
    return 0 if field == "enabled" else 1

