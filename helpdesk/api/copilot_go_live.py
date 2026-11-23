# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Going live from a task (Phase 22, copilot/go_live.py): for the desktop app."""

import frappe

from helpdesk.copilot import go_live
from helpdesk.utils import agent_only


@frappe.whitelist()
@agent_only
def task_release(task: str) -> dict:
    """Where the task's change stands: waiting for CI, for approval, going live, or live."""
    return go_live.task_release(task)


@frappe.whitelist(methods=["POST"])
@agent_only
def ask_go_live(task: str, when: str = "tonight", note: str = "") -> dict:
    """Ask for the task's release to go live tonight or now; its approver decides."""
    return go_live.ask_go_live(task, when, note)
