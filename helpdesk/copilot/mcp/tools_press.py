# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Press tools for people (Phase 18): the reads and the logged backup of
helpdesk.copilot.press_tools. The approval-level actions are not here: a person asks for those in
Teams or the desktop app, never a model through a tool. A Copilot run gets no Press tool: the
worker activates four tools per profile, and its set stays as it is.
"""

import frappe
from frappe import _

from helpdesk.copilot import press_tools
from helpdesk.copilot.mcp.registry import READ, WRITE, register_tool
from helpdesk.copilot.mcp.shape import clip

SITE = {"type": "string", "maxLength": 140, "description": "The site as Press names it"}
MAX_CHARS = 20_000


def _site(args_site: str) -> str:
    found = press_tools.find_site(args_site)
    if len(found) == 1:
        return found[0]["name"]
    if not found:
        frappe.throw(_("No site on Press matches {0}.").format(args_site))
    frappe.throw(
        _("Several sites match {0}: {1}.").format(
            args_site, ", ".join(s["name"] for s in found[:8])
        )
    )


def press_site_status(caller, site: str) -> dict:
    return press_tools.site_status(_site(site))


def press_sites(caller, query: str = "") -> list[dict]:
    return press_tools.list_sites(status=None, query=query)[:200]


def press_jobs(caller, site: str = "", bench: str = "", limit: int = 10) -> list[dict]:
    return press_tools.jobs(
        site=_site(site) if site else None, bench=bench or None, limit=limit
    )


def press_job(caller, job: str) -> dict:
    return clip(press_tools.job(job), MAX_CHARS)


def press_failed_jobs(caller, hours: int = 24) -> list[dict]:
    return press_tools.failed_jobs(hours)


def press_deploy_history(caller, group: str, limit: int = 10) -> list[dict]:
    return press_tools.deploy_history(group, limit)


def press_backup(caller, site: str) -> dict:
    """A backup now: logged, never an approval."""
    done = press_tools.run("backup", _site(site), frappe.session.user, "MCP person")
    return {"text": done["text"], "job": done.get("job")}


register_tool(
    "press_site_status",
    kind=READ,
    description="A hosted site's status on Press: plan and usage, health, apps and versions, last backup, last update.",
    handler=press_site_status,
    properties={"site": SITE},
    required=["site"],
)
register_tool(
    "press_sites",
    kind=READ,
    description="The sites hosted on TBO's Press, with status, bench group, server and plan; `query` narrows by name.",
    handler=press_sites,
    properties={"query": {"type": "string", "maxLength": 80}},
)
register_tool(
    "press_jobs",
    kind=READ,
    description="Recent Press agent jobs of a site or a bench (type, status, duration).",
    handler=press_jobs,
    properties={
        "site": SITE,
        "bench": {"type": "string", "maxLength": 140},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
    },
)
register_tool(
    "press_job",
    kind=READ,
    description="One Press agent job with its steps and their output.",
    handler=press_job,
    properties={"job": {"type": "string", "maxLength": 140}},
    required=["job"],
)
register_tool(
    "press_failed_jobs",
    kind=READ,
    description="Press agent jobs that failed in the last hours (default 24).",
    handler=press_failed_jobs,
    properties={"hours": {"type": "integer", "minimum": 1, "maximum": 720}},
)
register_tool(
    "press_deploy_history",
    kind=READ,
    description="The builds of a bench group on Press, newest first.",
    handler=press_deploy_history,
    properties={
        "group": {"type": "string", "maxLength": 140},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
    },
    required=["group"],
)
register_tool(
    "press_backup",
    kind=WRITE,
    description="Take a backup of a hosted site now (database only). Logged; needs no approval.",
    handler=press_backup,
    properties={"site": SITE},
    required=["site"],
)
