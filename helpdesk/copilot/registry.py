# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""HDS Site Registry: which customer site (and which apps) a ticket belongs to."""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime


def registry_for_ticket(ticket: str):
    """The Production site of a ticket: by its connection first, else by its customer; None if unknown."""
    connection, customer = frappe.db.get_value(
        "HD Ticket", ticket, ["custom_qcs_connection", "customer"]
    )
    name = None
    if connection:
        name = frappe.db.get_value(
            "HDS Site Registry", {"connection": connection, "environment": "Production"}
        )
    if not name and customer:
        name = frappe.db.get_value(
            "HDS Site Registry",
            {"customer_name": customer, "environment": "Production"},
        )
    return frappe.get_doc("HDS Site Registry", name) if name else None


def refresh_from_site(registry) -> dict:
    """Every app the site runs, with its repository, branch and commit, read through its connection.

    A sandbox copy needs all of them (Frappe, ERPNext, HRMS and the custom
    apps), not only the ones a person typed in. An app the site reports
    without a remote keeps the repository already on the card; uncommitted
    changes on the site mark the app as drifted.
    """
    from helpdesk.mcp_client import MCPClient

    if not registry.connection:
        frappe.throw(_("This site card has no connection to read the site through."))
    result = MCPClient(registry.connection).call_tool(
        "get_code_identity", {}, session_id=f"registry-{registry.name}"
    )
    text = ((result.get("content") or [{}])[0] or {}).get("text") or ""
    if result.get("isError"):
        frappe.throw(_("The site could not report its apps: {0}").format(text[:300]))
    try:
        reported = json.loads(text)
    except ValueError:
        frappe.throw(_("The site's list of apps could not be read."))
    known = {row.app: row.repository for row in registry.apps}
    rows = []
    for info in reported if isinstance(reported, list) else []:
        if not isinstance(info, dict) or not info.get("app"):
            continue
        remotes = info.get("remotes") or {}
        repository = (
            remotes.get("origin")
            or remotes.get("upstream")
            or next(iter(remotes.values()), None)
            or known.get(info["app"])
        )
        rows.append(
            {
                "app": info["app"],
                "repository": repository,
                "branch": info.get("branch"),
                "deployed_commit": info.get("commit"),
                "drift_status": "Drift"
                if info.get("dirty")
                else ("In sync" if info.get("commit") else "Unknown"),
            }
        )
    if not rows:
        frappe.throw(_("The site reported no apps."))
    registry.set("apps", rows)
    registry.last_synced = now_datetime()
    registry.save(ignore_permissions=True)
    return {
        "apps": len(rows),
        "drift": [row["app"] for row in rows if row["drift_status"] == "Drift"],
    }


def refresh_from_press(registry) -> dict:
    """The bench's apps and their commits as Press knows them, and the other sites on the bench.

    The commit the site itself reports (Refresh from the site) stays the
    deployed commit; an app whose Press commit differs is marked Drift.
    """
    from helpdesk.copilot import press

    if not registry.press_release_group:
        frappe.throw(_("This site card has no Press release group (bench)."))
    try:
        info = press.deploy_information(registry.press_release_group)
    except press.PressError as e:
        frappe.throw(_("Press: {0}").format(e.message))
    rows = {row.app: row for row in registry.apps}
    drift = []
    for app in info.get("apps") or []:
        name = app.get("app") or app.get("name")
        commit = app.get("hash") or ""
        if not name:
            continue
        row = rows.get(name) or registry.append("apps", {"app": name})
        if not row.deployed_commit:
            row.deployed_commit = commit or None
        if (
            commit
            and row.deployed_commit
            and not commit.startswith(row.deployed_commit)
            and not row.deployed_commit.startswith(commit)
        ):
            row.drift_status = "Drift"
            drift.append(name)
        elif commit:
            row.drift_status = "In sync"
    others = [
        site.get("name")
        for site in info.get("sites") or []
        if site.get("name") and site.get("name") != registry.press_site
    ]
    registry.group_sites = "\n".join(others)
    registry.last_synced = now_datetime()
    registry.save(ignore_permissions=True)
    return {"apps": len(info.get("apps") or []), "drift": drift, "other_sites": others}


def apps_for(registry) -> list[dict]:
    """The apps on a registered site, as plain dicts a worker can be handed."""
    return [
        {
            "app": row.app,
            "repository": row.repository,
            "branch": row.branch,
            "deployed_commit": row.deployed_commit,
            "drift_status": row.drift_status,
        }
        for row in registry.apps
    ]
