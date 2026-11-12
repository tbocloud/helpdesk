# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Press for agents and the desktop app (Phase 18): the reads, a backup now, and the actions
that wait for an approval card (helpdesk.copilot.press_tools). Every caller is a signed-in
agent; what Press is asked is logged, and the key never leaves the hub."""

import json

import frappe
from frappe import _

from helpdesk.copilot import actions, press_tools
from helpdesk.utils import agent_only

VIA = "Desktop"


def _extra(value) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value) if value.strip() else {}
        except ValueError:
            frappe.throw(_("extra must be JSON."))
    return value or {}


@frappe.whitelist()
@agent_only
def sites(query: str = "", status: str = "") -> list[dict]:
    return press_tools.list_sites(status=status or None, query=query)


@frappe.whitelist()
@agent_only
def site_status(site: str) -> dict:
    return press_tools.site_status(site)


@frappe.whitelist()
@agent_only
def jobs(site: str = "", bench: str = "", limit: int = 10) -> list[dict]:
    return press_tools.jobs(site=site or None, bench=bench or None, limit=limit)


@frappe.whitelist()
@agent_only
def job(name: str) -> dict:
    return press_tools.job(name)


@frappe.whitelist()
@agent_only
def failed_jobs(hours: int = 24) -> list[dict]:
    return press_tools.failed_jobs(hours)


@frappe.whitelist()
@agent_only
def benches() -> list[dict]:
    return press_tools.list_benches()


@frappe.whitelist()
@agent_only
def deploy_history(group: str, limit: int = 10) -> list[dict]:
    return press_tools.deploy_history(group, limit)


@frappe.whitelist()
@agent_only
def servers() -> list[dict]:
    return press_tools.list_servers()


@frappe.whitelist()
@agent_only
def logs(site: str, log: str = "") -> dict:
    if log:
        return {"site": site, "log": log, "text": press_tools.site_log(site, log)}
    return {"site": site, "logs": press_tools.site_logs(site)}


@frappe.whitelist(methods=["POST"])
@agent_only
def backup(site: str, ticket: str | None = None) -> dict:
    """A backup now: runs, logged, no approval."""
    done = press_tools.run(
        "backup", site, frappe.session.user, VIA, ticket=ticket or None
    )
    return {"text": done["text"], "job": done.get("job")}


@frappe.whitelist(methods=["POST"])
@agent_only
def request_action(
    action: str, target: str, extra=None, ticket: str | None = None
) -> dict:
    """An approval-level action: the card goes to an approver; the hub runs it after Approve and
    tells the caller. The same ask twice returns the live request."""
    rule = press_tools.spec(action)
    if rule["level"] != press_tools.APPROVAL:
        frappe.throw(
            _("{0} needs no approval; call backup or the reads instead.").format(action)
        )
    asked = press_tools.run(
        action,
        target,
        frappe.session.user,
        VIA,
        extra=_extra(extra),
        ticket=ticket or None,
    )
    return actions.as_dict(frappe.get_doc(actions.ACTION, asked["approval"]))


@frappe.whitelist()
@agent_only
def actions_table() -> dict:
    """What Copilot may do on Press, by level, so the desktop app can show and refuse the same."""
    return {
        "actions": {
            name: {
                "level": rule["level"],
                "target": rule["target"],
                "risk": rule.get("risk"),
            }
            for name, rule in press_tools.ACTIONS.items()
        },
        "never": list(press_tools.NEVER),
    }
