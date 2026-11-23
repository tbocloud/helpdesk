# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The check after a deploy (Phase 2): the customer's site runs the merged fix, without new errors.

Read through the customer connector, as the investigation reads the site:
the app's commit (`get_code_identity`); error signatures since the deploy
began that were not seen in the week before (`get_deploy_status`,
`get_error_log`), the connector's own left out; the scheduler running and no
maintenance mode; the documents the diagnosis names still opening (`get_doc`).
"""

import json
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from helpdesk.copilot import settings as copilot_settings

NOISE = (
    "helpdesk_client",
)  # the connector's own errors (its MCP calls), not the customer's


class SiteUnreachable(Exception):
    pass


def _call(client, session: str, tool: str, args: dict):
    result = client.call_tool(tool, args, session_id=session)
    text = ((result.get("content") or [{}])[0] or {}).get("text") or ""
    if result.get("isError"):
        raise SiteUnreachable(text[:300])
    try:
        return json.loads(text)
    except ValueError:
        return text


def _row(check: str, ok: bool, detail: str = "") -> dict:
    return {
        "check": check,
        "result": "pass" if ok else "fail",
        "detail": str(detail)[:300],
    }


def signature(entry: dict) -> str:
    """The connector's error signature: app | method | the error's last line."""
    lines = [
        line.strip() for line in (entry.get("error") or "").splitlines() if line.strip()
    ]
    return f"{entry.get('app') or '?'} | {entry.get('method') or '?'} | {lines[-1][:200] if lines else ''}"


# Evidence that names a record; a customization ("Quotation Item/tier_discount_percent")
# names a field, and code, commits and the ticket name no record either
RECORD_EVIDENCE = {"data", "setting", ""}


def named_documents(run) -> list[tuple[str, str]]:
    """Documents the diagnosis names ("Sales Invoice/ACC-SINV-…"), to open again after the deploy."""
    found = []
    for item in frappe.parse_json(run.evidence or "[]") or []:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or "")
        doctype, _sep, name = ref.partition("/")
        if (
            str(item.get("type") or "").lower() in RECORD_EVIDENCE
            and name
            and doctype[:1].isupper()
            and doctype not in ("Error Log", "Version")
            and not any(mark in ref for mark in (".py", ".js", ".json", ":"))
        ):
            found.append((doctype.strip(), name.strip()))
    return found[:3]


def check(run, request) -> list[dict]:
    """The check after a Copilot fix's deploy, through the ticket's connection."""
    if not run.connection:
        return [
            {
                "check": _("the check after the deploy"),
                "result": "not_run",
                "detail": _("the ticket has no connection to the customer's site"),
            }
        ]
    return site_rows(
        run.connection, f"deploy-{run.name}", request, named_documents(run)
    )


def check_release(request) -> list[dict]:
    """The check after a release: every site through its own site card's connection."""
    rows = []
    for site in request.sites:
        connection = (
            frappe.db.get_value("HDS Site Registry", site.registry, "connection")
            if site.registry
            else None
        )
        if not connection:
            rows.append(
                {
                    "check": _("the check after the deploy of {0}").format(site.site),
                    "result": "not_run",
                    "detail": _("its site card has no connection to the site"),
                }
            )
            continue
        found = site_rows(connection, f"deploy-{request.name}", request, [])
        if len(request.sites) > 1:
            for row in found:
                row["check"] = f"{site.site}: {row['check']}"
        rows += found
    return rows


def site_rows(connection: str, session: str, request, documents) -> list[dict]:
    """One site after a deploy: it runs the merged commit, no new errors, the scheduler running, the named documents open."""
    from helpdesk.mcp_client import MCPClient

    client = MCPClient(connection)
    app = request.apps[0]
    started = get_datetime(request.started_at)
    identity = _call(client, session, "get_code_identity", {"apps": [app.app]})
    entry = (
        next(
            (
                item
                for item in identity
                if isinstance(item, dict) and item.get("app") == app.app
            ),
            {},
        )
        if isinstance(identity, list)
        else {}
    )
    commit = str(entry.get("commit") or "")
    target = app.to_commit or ""
    rows = [
        _row(
            _("the site runs the merged commit"),
            bool(commit and target)
            and (commit.startswith(target) or target.startswith(commit)),
            f"{app.app} at {commit[:12] or '?'}",
        )
    ]
    status = _call(client, session, "get_deploy_status", {"since": str(started)}) or {}
    before = _call(
        client,
        session,
        "get_error_log",
        {"since": str(started - timedelta(days=7)), "until": str(started), "limit": 50},
    )
    known = (
        {signature(entry) for entry in before if isinstance(entry, dict)}
        if isinstance(before, list)
        else set()
    )
    new = [
        top.get("signature")
        for top in ((status.get("errors") or {}).get("top") or [])
        if top.get("signature")
        and top["signature"] not in known
        and not top["signature"].startswith(NOISE)
    ]
    rows.append(_row(_("no new errors since the deploy"), not new, "; ".join(new[:3])))
    rows.append(
        _row(
            _("the scheduler is running"),
            bool(status.get("scheduler_enabled"))
            and not status.get("maintenance_mode"),
        )
    )
    for doctype, name in documents:
        try:
            _call(client, session, "get_doc", {"doctype": doctype, "name": name})
            rows.append(_row(_("{0} {1} opens").format(doctype, name), True))
        except SiteUnreachable as e:
            rows.append(_row(_("{0} {1} opens").format(doctype, name), False, str(e)))
    return rows


def step(request):
    """Checks the site once; a site that cannot answer is asked again until the time is up."""
    from helpdesk.copilot import deploy

    limit = copilot_settings.get_settings().get("deploy_check_minutes") or 30
    try:
        rows = (
            check(frappe.get_doc("HDS Copilot Run", request.run), request)
            if request.run
            else check_release(request)
        )
    except Exception as e:  # the connector or the site could not answer
        if (
            now_datetime() - get_datetime(request.modified)
        ).total_seconds() / 60 > limit:
            deploy.fail(
                request,
                _("the check after the deploy could not reach the site: {0}").format(
                    str(e)[:300]
                ),
            )
        return
    failed = [row for row in rows if row["result"] == "fail"]
    if failed:
        request.db_set("check_results", json.dumps(rows, indent=1))
        return deploy.fail(
            request,
            _("the check after the deploy failed: {0}").format(
                "; ".join(
                    row["check"] + (f" ({row['detail']})" if row["detail"] else "")
                    for row in failed
                )
            ),
        )
    deploy.succeed(request, rows)
