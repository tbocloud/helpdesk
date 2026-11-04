"""Project status report endpoints (docs/project-status-report.md)."""

import frappe
from frappe import _
from frappe.utils import nowdate

from helpdesk.ai_suggestion import is_ai_configured
from helpdesk.project_status import (
    STALE_DAYS,
    history,
    project_rows,
    save_updates,
    select_options,
)
from helpdesk.project_status_ai import split_update
from helpdesk.utils import agent_only

# what the person may set on an update; the rest (who wrote it, since when) is the server's
SAVED_FIELDS = (
    "project",
    "stage",
    "waiting_on",
    "waiting_since",
    "update_text",
    "next_step",
    "next_step_date",
    "source",
)


@frappe.whitelist()
@agent_only
def get_project_status() -> dict:
    """The report: a row per open project the user may see, most pressing first."""
    rows = project_rows()
    return {
        "date": nowdate(),
        "stale_days": STALE_DAYS,
        "stages": select_options("stage"),
        "waiting_on": select_options("waiting_on"),
        "rows": rows,
        "can_write_any": any(row["can_write"] for row in rows),
        "ai_available": is_ai_configured(),
    }


@frappe.whitelist(methods=["POST"])
@agent_only
def save_status_updates(updates: str | list) -> dict:
    """Saves the updates, all or none. Each project needs a coordinator's permission."""
    updates = frappe.parse_json(updates)
    if not isinstance(updates, list) or not updates:
        frappe.throw(_("There is nothing to save."))
    items = [{key: u.get(key) for key in SAVED_FIELDS if u.get(key)} for u in updates]
    return {"saved": save_updates(items)}


@frappe.whitelist()
@agent_only
def get_status_history(project: str) -> list[dict]:
    """A project's updates, newest first."""
    frappe.has_permission("Project", "read", project, throw=True)
    return history(project)


@frappe.whitelist(methods=["POST"])
@agent_only
def split_status_update(text: str) -> dict:
    """Proposed updates from a pasted or spoken report, one per project mentioned, over
    the projects the user may write. Nothing is saved."""
    rows = [row for row in project_rows() if row["can_write"]]
    return {"updates": split_update(text, rows)}
