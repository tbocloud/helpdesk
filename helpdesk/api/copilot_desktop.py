# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Who may use the TBO Copilot desktop app (testing fixes 7): they get "Open in TBO Copilot" on
any open task, wherever it opens. The rule is the desktop sign-in's own (tbo_desktop's
`sign_in`): its settings switched on, an active agent, then the Allowed People list when it is
used, else the role TBO Copilot Desktop. A site without the tbo_desktop app: nobody."""

import frappe

SETTINGS = "TBO Desktop Settings"
ROLE = "TBO Copilot Desktop"


def _settings():
    """tbo_desktop's settings, or None on a site without that app."""
    if not frappe.db.exists("DocType", SETTINGS):
        return None
    return frappe.get_cached_doc(SETTINGS)


def may_use_desktop(user: str | None = None) -> bool:
    user = user or frappe.session.user
    if not user or user in ("Guest", "Administrator"):
        return False
    settings = _settings()
    if not settings or not settings.get("enabled"):
        return False
    if not frappe.db.exists("HD Agent", {"user": user, "is_active": 1}):
        return False
    allowed = {row.user for row in settings.get("allowed_people") or [] if row.user}
    if allowed:
        return user in allowed
    return ROLE in frappe.get_roles(user)


@frappe.whitelist()
def desktop() -> dict:
    """Whether this person gets "Open in TBO Copilot" on tasks. Every desk user asks (the Task
    form does, on every open task); someone who is not an active agent simply gets False, never
    a "Not Allowed" message."""
    return {"may_use": may_use_desktop()}
