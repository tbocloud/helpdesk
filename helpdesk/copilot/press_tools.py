# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Press through Copilot (Phase 18): what the team may ask of TBO's own Press, from Teams, the
desktop app or a Copilot run, on the client of helpdesk.copilot.press.

ACTIONS is the only place that says what Copilot may do, by level: a read answers at once, a
logged action runs at once and is written down, an approval action waits for an H65 card and runs
after Approve, and NEVER names what no path may call (a test keeps those names out of the code).
Press itself cannot limit what a key does, so this table is the guard
(docs/tbo-copilot.md, Press tools).
"""

import json
import time

import frappe
import requests
from frappe import _
from frappe.utils import add_to_date, now_datetime

from helpdesk.copilot import actions, press
from helpdesk.copilot.press import PressError

READ, LOGGED, APPROVAL = "read", "logged", "approval"
KIND = "Press"
PING_TIMEOUT = 5
FOLLOW_SECONDS = 180  # how long an approved action's job is watched before reporting
FOLLOW_EVERY = 15
MAX_SITES = 500
CLIP = 4000

# an action: its level, Press's method, what the target names, the risk for the approval card,
# and the job Press runs so the outcome can be followed
ACTIONS = {
    "backup": {
        "level": LOGGED,
        "method": "press.api.site.backup",
        "target": "site",
        "job": "Backup Site",
        "title": "Back up {target}",
    },
    "restart_bench": {
        "level": APPROVAL,
        "method": "press.api.bench.restart",
        "target": "bench",
        "risk": "normal",
        "job": "Bench Restart",  # Press's own name (press/agent.py restart_bench)
        "title": "Restart {target}",
    },
    "update_site": {
        "level": APPROVAL,
        "method": "press.api.site.update",
        "target": "site",
        "risk": "normal",
        # Press names the job by the update's kind (press/agent.py update_site)
        "job": ("Update Site Pull", "Update Site Migrate"),
        "title": "Update {target} to its bench's newest build",
    },
    "migrate_site": {
        "level": APPROVAL,
        "method": "press.api.site.migrate",
        "target": "site",
        "risk": "normal",
        "job": "Migrate Site",
        "title": "Migrate {target} (bench migrate)",
    },
    "change_plan": {
        "level": APPROVAL,
        "method": "press.api.site.change_plan",
        "target": "site",
        "risk": "normal",
        "extra": ("plan",),
        "title": "Change the plan of {target} to {plan}",
    },
    "deploy": {
        "level": APPROVAL,
        "method": "press.api.bench.deploy_and_update",
        "target": "group",
        "risk": "senior",
        "title": "Deploy the bench group {target} and update its sites",
    },
    "restore": {
        "level": APPROVAL,
        "method": "press.api.site.restore",
        "target": "site",
        "risk": "senior",
        "extra": ("files",),
        "job": "Restore Site",
        "title": "Restore {target} from a backup",
    },
    "new_site": {
        "level": APPROVAL,
        "method": "press.api.site.new",
        "target": "site",
        "risk": "senior",
        "extra": ("site",),
        "job": "New Site",
        "title": "Create the site {target}",
    },
}
# what no path through Copilot may call, by name; test_copilot_press keeps them out of the code
NEVER = (
    "press.api.site.archive",
    "press.api.site.reinstall",
    "press.api.site.deactivate",
    "press.api.site.login",
    "press.api.site.update_config",
    "press.api.site.delete_config",
    "press.api.site.run_sql_query_in_database",
    "press.api.site.kill_database_process",
    "press.api.site.uninstall_app",
    "press.api.site.remove_domain",
    "press.api.bench.archive",
    "press.api.bench.remove_app",
    "press.api.server.archive",
    "press.api.server.reboot",
    "press.api.client.delete",
    "press.api.client.insert",
    "press.api.client.set_value",
)


# --- reads -----------------------------------------------------------------------------------


def list_sites(status: str | None = "Active", query: str = "") -> list[dict]:
    """The team's sites on Press: name, status, bench group, server, plan."""
    filters = {}
    if status:
        filters["status"] = status
    if query:
        filters["name"] = ["like", f"%{query.strip().lower()}%"]
    return press.get_list(
        "Site",
        filters,
        ["name", "status", "group", "server", "plan", "bench", "creation"],
        limit=MAX_SITES,
        order_by="name asc",
    )


def find_site(text: str) -> list[dict]:
    """The sites a person may mean by `text`: the exact name, else the names that start with it,
    else the names that contain it. Empty when there is none."""
    text = (text or "").strip().lower().rstrip(".")
    if not text:
        return []
    sites = list_sites(status=None)
    exact = [s for s in sites if s["name"].lower() == text]
    if exact:
        return exact
    starts = [s for s in sites if s["name"].lower().startswith(text + ".")] or [
        s for s in sites if s["name"].lower().startswith(text)
    ]
    return starts or [s for s in sites if text in s["name"].lower()]


def ping(site: str) -> dict:
    """Whether the site answers, and how fast, from the hub."""
    started = time.monotonic()
    try:
        response = requests.get(
            f"https://{site}/api/method/ping",
            timeout=PING_TIMEOUT,
            allow_redirects=False,
        )
        ok = response.status_code == 200
        code = response.status_code
    except requests.RequestException as e:
        ok, code = False, str(e)[:80]
    return {"ok": ok, "code": code, "ms": int((time.monotonic() - started) * 1000)}


def last_backup(site: str) -> dict | None:
    rows = press.get_list(
        "Site Backup",
        {"site": site, "status": "Success"},
        ["name", "creation", "with_files", "offsite"],
        limit=1,
    )
    return rows[0] if rows else None


def last_update(site: str) -> dict | None:
    rows = press.get_list(
        "Site Update", {"site": site}, ["name", "status", "creation"], limit=1
    )
    return rows[0] if rows else None


def site_status(site: str) -> dict:
    """Plan, health, apps, last backup and last update of one site, in one answer."""
    info = press.call("press.api.site.get", name=site) or {}
    plan = press.call("press.api.site.current_plan", name=site) or {}
    apps = press.call("press.api.site.installed_apps", name=site) or []
    row = (
        press.get_list("Site", {"name": site}, ["bench", "group", "plan"], limit=1)
        or [{}]
    )[0]
    current = plan.get("current_plan") or {}
    usage = plan.get("usage_in_percent") or {}
    return {
        "site": site,
        "status": info.get("status"),
        "group": info.get("group") or row.get("group"),
        "bench": row.get("bench"),
        "server": info.get("server"),
        "version": info.get("frappe_version"),
        "plan": {
            "name": current.get("plan_title") or current.get("name") or row.get("plan"),
            "cpu_pct": usage.get("cpu"),
            "disk_pct": usage.get("disk"),
            "database_pct": usage.get("database"),
        },
        "apps": [
            {
                "app": a.get("app"),
                "branch": a.get("branch"),
                "hash": (a.get("hash") or "")[:7],
                "tag": a.get("tag"),
            }
            for a in apps
            if isinstance(a, dict)
        ],
        "last_deployed": (info.get("info") or {}).get("last_deployed"),
        "last_backup": last_backup(site),
        "last_update": last_update(site),
        "ping": ping(site),
    }


JOB_TARGETS = ("site", "bench", "group", "server")


def release_groups() -> list[str]:
    """Every release group Copilot's Press role shows."""
    rows = press.get_list("Release Group", {}, ["name"], limit=200, order_by="name asc")
    return [str(row["name"]) for row in rows if row.get("name")]


def agent_jobs(filters: dict, fields: list[str], limit: int) -> list[dict]:
    """Agent Jobs the way Press allows them: Press answers an Agent Job list only with a site,
    bench, group or (owned) server filter (`AgentJob.get_list_query`), whatever the role. With a
    target, one call; without one, one call per release group the role shows, merged, newest
    first (the watcher's same fix, tbocloud-infra PR #9)."""
    if any(filters.get(key) for key in JOB_TARGETS):
        return press.get_list("Agent Job", filters, fields, limit=limit)
    found: dict[str, dict] = {}
    for group in release_groups():
        for row in press.get_list(
            "Agent Job", {**filters, "group": group}, fields, limit=limit
        ):
            found.setdefault(str(row.get("name")), row)
    rows = sorted(
        found.values(), key=lambda row: str(row.get("creation") or ""), reverse=True
    )
    return rows[:limit]


def jobs(
    site: str | None = None, bench: str | None = None, limit: int = 10
) -> list[dict]:
    filters = {}
    if site:
        filters["site"] = site
    if bench:
        filters["bench"] = bench
    return agent_jobs(
        filters,
        [
            "name",
            "job_type",
            "status",
            "creation",
            "start",
            "end",
            "duration",
            "site",
            "bench",
        ],
        limit=min(int(limit or 10), 50),
    )


def _redacted(value):
    """Press's output with passwords, tokens and credentials in URLs taken out (a failed job's
    output can carry a database URL, a trace a Redis password), for every reader: a person, their
    AI client, the worker (helpdesk.copilot.infra.redact)."""
    from helpdesk.copilot.infra import redact

    return redact(value)


def job(name: str) -> dict:
    """One Agent Job with its steps and their output, clipped, secrets taken out."""
    doc = press.call("press.api.site.job", job=name) or {}
    for step in doc.get("steps") or []:
        if isinstance(step, dict) and step.get("output"):
            step["output"] = str(step["output"])[-CLIP:]
    return _redacted(doc)


def failed_jobs(hours: int = 24) -> list[dict]:
    since = add_to_date(now_datetime(), hours=-max(int(hours or 24), 1))
    return agent_jobs(
        {"status": "Failure", "creation": [">", str(since)]},
        ["name", "job_type", "status", "creation", "site", "bench"],
        limit=50,
    )


def list_benches() -> list[dict]:
    return press.call("press.api.bench.all") or []


def deploy_history(group: str, limit: int = 10) -> list[dict]:
    return press.get_list(
        "Deploy Candidate Build",
        {"group": group},
        ["name", "status", "creation"],
        limit=min(int(limit or 10), 50),
    )


def list_servers() -> list[dict]:
    return press.call("press.api.server.all") or []


def site_logs(site: str) -> list:
    return _redacted(press.call("press.api.site.logs", name=site) or [])


def site_log(site: str, log: str) -> str:
    return _redacted(
        str(press.call("press.api.site.log", name=site, log=log) or "")[-CLIP * 4 :]
    )


def bench_logs(group: str, bench: str) -> list:
    return _redacted(press.call("press.api.bench.logs", name=group, bench=bench) or [])


# --- actions ---------------------------------------------------------------------------------


def spec(action: str) -> dict:
    if action not in ACTIONS:
        frappe.throw(
            _("Copilot does not know the Press action {0}. It knows: {1}.").format(
                action, ", ".join(ACTIONS)
            )
        )
    return ACTIONS[action]


def arguments(action: str, target: str, extra: dict | None = None) -> dict:
    """Press's arguments for the action: the target under its name, plus the extras it needs."""
    rule = spec(action)
    args = {"name": target}
    for key in rule.get("extra") or ():
        if not (extra or {}).get(key):
            frappe.throw(_("The action {0} needs {1}.").format(action, key))
        args[key] = extra[key]
    if action == "new_site":
        args = {"site": extra["site"]}
    return args


def describe(action: str, target: str, extra: dict | None = None) -> tuple[str, str]:
    """The card's title and details: what exactly would run."""
    rule = spec(action)
    title = rule["title"].format(
        target=target, **{k: str(v)[:60] for k, v in (extra or {}).items()}
    )
    args = arguments(action, target, extra)
    details = f"{rule['method']} " + " ".join(
        f"{k}={json.dumps(v, default=str)[:200]}" for k, v in args.items()
    )
    return title, details


def run(
    action: str,
    target: str,
    user: str,
    channel: str,
    extra: dict | None = None,
    ticket: str | None = None,
    wait: bool = True,
) -> dict:
    """A logged action runs now; an approval action asks first and runs after Approve.
    `wait` False: answer once Press took it, with its job as it stands, instead of watching the
    job for up to FOLLOW_SECONDS (the desktop app asks for the status itself; Phase 23, C5).

    Returns {"ran": True, "result": …} or {"approval": name, "title": …, "approver": …}.
    """
    from helpdesk.copilot.assistant import log_action

    rule = spec(action)
    title, details = describe(action, target, extra)
    args = arguments(action, target, extra)
    if rule["level"] == LOGGED:
        try:
            result = press.call(rule["method"], **args)
        except PressError as e:
            log_action(
                user, channel, f"press_{action}", "Error", args, str(e), ticket=ticket
            )
            raise
        followed = (
            (follow(rule, target) if wait else latest_job(rule, target))
            if rule.get("job")
            else None
        )
        text = outcome_text(action, target, followed)
        log_action(user, channel, f"press_{action}", "OK", args, text, ticket=ticket)
        return {"ran": True, "result": result, "job": followed, "text": text}
    approval = actions.request(
        KIND,
        title,
        details,
        {"action": action, "method": rule["method"], "args": args, "target": target},
        risk=rule.get("risk") or "normal",
        user=user,
        via=channel,
        ticket=ticket,
    )
    log_action(
        user,
        channel,
        f"press_{action}",
        "OK",
        args,
        f"asked: {approval.name}",
        ticket=ticket,
    )
    return {
        "approval": approval.name,
        "title": approval.title,
        "approver": approval.assigned_to,
        "status": approval.status,
    }


def as_copilot_asks(approval, payload: dict) -> bool:
    """Whether the approved payload is exactly what `run` (or Copilot's infrastructure proposal)
    builds for its action and target, at the action's own risk: the card the approver read came
    from the same action, so what runs is what they approved."""
    action = payload.get("action")
    rule = ACTIONS.get(action) if isinstance(action, str) else None
    target = payload.get("target")
    args = payload.get("args")
    if (
        not rule
        or not target
        or not isinstance(args, dict)
        or payload.get("method") != rule["method"]
        or rule["method"] in NEVER
        or approval.risk != (rule.get("risk") or "normal")
    ):
        return False
    extra = {key: args.get(key) for key in rule.get("extra") or ()}
    try:
        expected = arguments(action, target, extra)
    except frappe.ValidationError:
        return False
    return args == expected


def execute_approved(name: str):
    """Background, right after Approve: the exact approved payload goes to Press, the job is
    followed, the outcome is written on the record and told to the person who asked."""
    from helpdesk.copilot import assistant

    approval = frappe.get_doc(actions.ACTION, name)
    if approval.kind != KIND or approval.status != actions.APPROVED:
        return
    payload = frappe.parse_json(approval.payload or "{}") or {}
    action, args = payload.get("action"), payload.get("args") or {}
    if not as_copilot_asks(approval, payload):
        actions.mark_executed(
            name,
            False,
            _(
                "The approved request is not one Copilot asks for this action, so nothing ran."
            ),
        )
        return
    rule = ACTIONS[action]
    try:
        if action == "deploy":
            result = deploy_group(args["name"])
        else:
            result = press.call(rule["method"], **args)
        followed = (
            follow(rule, payload.get("target") or args.get("name"))
            if rule.get("job")
            else None
        )
        text = outcome_text(
            action, payload.get("target") or args.get("name"), followed, result
        )
        ok = not (followed and followed.get("status") == "Failure")
    except PressError as e:
        text, ok = _("Press refused: {0}").format(str(e)[:300]), False
    actions.mark_executed(name, ok, text)
    try:
        assistant.send(
            approval.requested_by,
            assistant.text_card(
                _("{0}: {1}").format(approval.title, text), "good" if ok else "warning"
            ),
            action_approval=name,
            ticket=approval.ticket,
        )
    except Exception:
        frappe.log_error(title=f"Copilot could not report the Press action {name}")
    if approval.ticket:
        from helpdesk.intake import add_comment

        add_comment(
            approval.ticket, f"<p><b>Press:</b> {frappe.utils.escape_html(text)}</p>"
        )


def deploy_group(group: str):
    """A deploy of the bench group, as Phase 2's train does it: the newest commit of every app
    with an update, and every site of the group moves to the new bench with backups."""
    info = press.deploy_information(group)
    apps, sites = [], []
    for row in info.get("apps") or []:
        current, following = press.app_commits(row)
        if following and following != current:
            apps.append(
                {
                    "app": row.get("app"),
                    "release": row.get("next_release"),
                    "hash": following,
                }
            )
    for site in info.get("sites") or []:
        sites.append(
            {
                "name": site.get("name"),
                "server": site.get("server"),
                "bench": site.get("bench"),
                "skip_failing_patches": False,
                "skip_backups": False,
            }
        )
    if not apps:
        frappe.throw(_("The bench group {0} has nothing new to deploy.").format(group))
    return press.deploy_and_update(group, apps, sites)


def job_type_filter(job):
    """The Agent Job type filter for an action: one name, or any of several (an update is Press's
    "Update Site Pull" or "Update Site Migrate")."""
    return ["in", list(job)] if isinstance(job, (list, tuple)) else job


def latest_job(rule: dict, target: str) -> dict | None:
    """The newest job of the action's type on the target, read once."""
    key = rule["target"] if rule["target"] in ("site", "bench") else "site"
    try:
        rows = press.get_list(
            "Agent Job",
            {key: target, "job_type": job_type_filter(rule["job"])},
            ["name", "status", "creation", "start", "end", "duration"],
            limit=1,
        )
    except PressError:
        return None
    return rows[0] if rows else None


def follow(rule: dict, target: str) -> dict | None:
    """The newest job of the action's type on the target, watched until it ends or the time is up."""
    key = rule["target"] if rule["target"] in ("site", "bench") else "site"
    deadline = time.monotonic() + FOLLOW_SECONDS
    latest = None
    while True:
        try:
            rows = press.get_list(
                "Agent Job",
                {key: target, "job_type": job_type_filter(rule["job"])},
                ["name", "status", "creation", "start", "end", "duration"],
                limit=1,
            )
        except PressError:
            rows = []
        latest = rows[0] if rows else latest
        if (
            latest
            and latest.get("status") in ("Success", "Failure")
            or time.monotonic() >= deadline
        ):
            return latest
        time.sleep(FOLLOW_EVERY)


def outcome_text(action: str, target: str, followed: dict | None, result=None) -> str:
    if followed:
        status = followed.get("status") or "Pending"
        duration = followed.get("duration")
        return _("{0} on {1}: job {2} {3}{4}").format(
            action.replace("_", " "),
            target,
            followed.get("name"),
            status.lower(),
            f" ({duration})" if duration and status in ("Success", "Failure") else "",
        )
    if result not in (None, "", {}, []):
        return _("{0} on {1}: Press accepted it ({2}).").format(
            action.replace("_", " "), target, str(result)[:120]
        )
    return _("{0} on {1}: Press accepted it.").format(action.replace("_", " "), target)
