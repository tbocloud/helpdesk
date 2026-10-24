# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""HDS Site Registry: which customer site (and which apps) a ticket belongs to."""

import json
import re

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime

# A remote that can be cloned from elsewhere. Press builds each app from a copy in its
# build context, so a Press site reports a local path (file:///home/frappe/context/apps/...).
CLONABLE_REMOTE = re.compile(r"^(https?://|ssh://|git@)", re.IGNORECASE)


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


def refresh_from_site(registry, timeout: int | None = None) -> dict:
    """Every app the site runs, with its repository, branch and commit, read through its connection.

    A sandbox copy needs all of them (Frappe, ERPNext, HRMS and the custom
    apps), not only the ones a person typed in. An app the site reports
    without a remote that can be cloned (none, or a local path as on Press)
    keeps the repository already on the card; uncommitted changes on the
    site mark the app as drifted.
    """
    from helpdesk.mcp_client import MCPClient

    if not registry.connection:
        frappe.throw(_("This site card has no connection to read the site through."))
    client = MCPClient(registry.connection)
    if timeout:
        client.timeout, client.retries = timeout, 0
    result = client.call_tool(
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
        candidates = [remotes.get("origin"), remotes.get("upstream"), *remotes.values()]
        repository = next(
            (url for url in candidates if url and CLONABLE_REMOTE.match(url)), None
        ) or known.get(info["app"])
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


# before a worker reads the code: a quick read of the site, at most this often per site
RUN_REFRESH_SECONDS = 8
RUN_REFRESH_FRESH_MINUTES = 2


def refresh_for_run(run) -> dict | None:
    """Before a worker reads the code, the card's commits as the site reports them now.

    A deploy made outside Copilot (from the Press dashboard, say) leaves the card
    behind, and the worker would read older code than the site runs. One quick
    read through the connection; when the site does not answer in time, the card
    stays as it is and the run says so. None when there is nothing to read.
    """
    from helpdesk.copilot import runs

    if not run.registry:
        return None
    registry = frappe.get_doc("HDS Site Registry", run.registry)
    if not registry.connection:
        return None
    if registry.last_synced and get_datetime(registry.last_synced) > add_to_date(
        now_datetime(), minutes=-RUN_REFRESH_FRESH_MINUTES
    ):
        return None  # read a moment ago, for another run
    before = {row.app: row.deployed_commit or "" for row in registry.apps}
    try:
        refresh_from_site(registry, timeout=RUN_REFRESH_SECONDS)
    except Exception as e:
        frappe.clear_last_message()
        runs.add_event(
            run,
            "site_not_refreshed",
            {
                "registry": registry.name,
                "reason": str(e)[:300],
                "card_from": str(registry.last_synced or ""),
            },
            runs.SYSTEM,
        )
        return {"refreshed": False}
    changed = [
        {"app": row.app, "from": before.get(row.app) or None, "to": row.deployed_commit}
        for row in registry.apps
        if before.get(row.app, "") != (row.deployed_commit or "")
    ]
    if changed:
        runs.add_event(
            run,
            "site_refreshed",
            {"registry": registry.name, "changed": changed},
            runs.SYSTEM,
        )
    return {"refreshed": True, "changed": changed}


def refresh_from_press(registry) -> dict:
    """The bench's apps and their commits as Press knows them, and the other sites on the bench.

    The commit the site itself reports (Refresh from the site) stays the
    deployed commit; an app whose Press commit differs is marked Drift. A card
    the site already filled keeps exactly the site's apps: a shared bench holds
    every site's apps, so the others are only listed (`bench_only`). An empty
    card is filled from Press.
    """
    from helpdesk.copilot import press

    if not registry.press_release_group:
        frappe.throw(_("This site card has no Press release group (bench)."))
    try:
        info = press.deploy_information(registry.press_release_group)
    except press.PressError as e:
        frappe.throw(_("Press: {0}").format(e.message))
    rows = {row.app: row for row in registry.apps}
    filled = bool(rows)
    drift, bench_only = [], []
    for app in info.get("apps") or []:
        name = app.get("app") or app.get("name")
        commit = press.app_commits(app)[0]
        if not name:
            continue
        if name not in rows and filled:
            bench_only.append(name)
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
    return {
        "apps": len(info.get("apps") or []),
        "drift": drift,
        "other_sites": others,
        "bench_only": bench_only,
    }


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
