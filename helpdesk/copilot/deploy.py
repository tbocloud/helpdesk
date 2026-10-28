# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Deploying a merged Copilot fix through Press (Phase 2).

A person presses Deploy on the ticket: Tonight (the next deploy window) or
Now (senior approvers and Agent Managers only). A cron every five minutes
moves each deploy request along: it waits for Press (one Copilot deploy at a
time, none while Press is deploying the bench, the merged commit registered
on the bench), asks Press to update only the customer's sites (Press takes
its own backups first unless Skip Press's backup is on, for test benches, and
restores a site whose update fails), follows Press
until the sites are updated, then hands over to the check after
(helpdesk.copilot.verify). A failure escalates the run with Press's reason.
"""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import get_datetime, get_system_timezone, now_datetime

from helpdesk.copilot import approvals, press, runs
from helpdesk.copilot import settings as copilot_settings
from helpdesk.copilot.press import PressError

DEPLOY = "HDS Deploy Request"
WAITING = ("Scheduled", "Waiting for Press")
OPEN = WAITING + ("Deploying", "Checking")
LOCK_KEY = "copilot_deploy_lock"
LOCK_SECONDS = 3 * 3600
PRESS_HOURS = 2
# Press's Site Update statuses: done, and done badly (Press restores a site whose update fails)
SITE_DONE = {"Success"}
SITE_FAILED = {"Failure", "Fatal", "Recovered", "Recovery Failed"}
DEFAULT_WINDOW = ("21:00", "06:00", "Asia/Riyadh")


# --- the window --------------------------------------------------------------------


def _hm(value: str | None, fallback: str) -> tuple[int, int]:
    try:
        hours, minutes = (int(part) for part in (value or fallback).strip().split(":"))
        if 0 <= hours < 24 and 0 <= minutes < 60:
            return hours, minutes
    except ValueError:
        pass
    hours, minutes = (int(part) for part in fallback.split(":"))
    return hours, minutes


def _window() -> tuple[tuple[int, int], tuple[int, int], ZoneInfo]:
    settings = copilot_settings.get_settings()
    try:
        zone = ZoneInfo((settings.get("deploy_timezone") or DEFAULT_WINDOW[2]).strip())
    except (KeyError, ValueError):
        zone = ZoneInfo(DEFAULT_WINDOW[2])
    return (
        _hm(settings.get("deploy_window_start"), DEFAULT_WINDOW[0]),
        _hm(settings.get("deploy_window_end"), DEFAULT_WINDOW[1]),
        zone,
    )


def _aware(moment: datetime) -> datetime:
    """A naive datetime in the site's own timezone, made aware."""
    return moment.replace(tzinfo=ZoneInfo(get_system_timezone()))


def _naive(moment: datetime) -> datetime:
    return moment.astimezone(ZoneInfo(get_system_timezone())).replace(tzinfo=None)


def in_window(moment: datetime | None = None) -> bool:
    (sh, sm), (eh, em), zone = _window()
    local = _aware(moment or now_datetime()).astimezone(zone)
    minutes, start, end = local.hour * 60 + local.minute, sh * 60 + sm, eh * 60 + em
    if start > end:  # over midnight, e.g. 21:00 to 06:00
        return minutes >= start or minutes < end
    return start <= minutes < end


def next_opening(moment: datetime | None = None, now_counts: bool = True) -> datetime:
    """When Tonight starts: now, when inside the window (and `now_counts`), else the window's next start."""
    moment = moment or now_datetime()
    if now_counts and in_window(moment):
        return moment
    (sh, sm), _end, zone = _window()
    local = _aware(moment).astimezone(zone)
    start = local.replace(hour=sh, minute=sm, second=0, microsecond=0)
    if start <= local:
        start += timedelta(days=1)
    return _naive(start)


def local_time(moment) -> str:
    """A time as the customer and the team read it: in the window's timezone."""
    _start, _end, zone = _window()
    return _aware(get_datetime(moment)).astimezone(zone).strftime("%d %b %Y %H:%M (%Z)")


# --- who may deploy, where ------------------------------------------------------------


def may_deploy(user: str) -> bool:
    return user in (
        set(approvals.approvers())
        | set(approvals.seniors())
        | set(approvals.managers())
    )


def may_deploy_now(user: str) -> bool:
    return user in set(approvals.seniors()) | set(approvals.managers())


def open_request(run):
    name = frappe.db.get_value(
        DEPLOY,
        {"run": run.name, "status": ["in", OPEN]},
        "name",
        order_by="creation desc",
    )
    return frappe.get_doc(DEPLOY, name) if name else None


def target(run) -> tuple[str, list[str]]:
    """The bench and the customer's own sites on it, from their site cards."""
    group, sites = card_sites(run)
    if not group:
        frappe.throw(
            _(
                "The customer's site card needs its Press site and release group (bench) to deploy through Press. For a site outside Press, deploy by hand and press Mark deployed."
            )
        )
    if hub_site() in sites:
        frappe.throw(
            _(
                "{0} is TBO Support itself, which Copilot never deploys; correct the customer's site card."
            ).format(hub_site())
        )
    return group, sites


def card_sites(run) -> tuple[str | None, list[str]]:
    """What Deploy would update, without a message: the bench and the sites, or (None, [])."""
    card = (
        frappe.db.get_value(
            "HDS Site Registry",
            run.registry,
            ["customer_name", "press_site", "press_release_group"],
            as_dict=True,
        )
        if run.registry
        else None
    )
    if not (card and card.press_site and card.press_release_group):
        return None, []
    sites = frappe.get_all(
        "HDS Site Registry",
        filters={
            "customer_name": card.customer_name,
            "environment": "Production",
            "press_release_group": card.press_release_group,
            "press_site": ["is", "set"],
        },
        pluck="press_site",
    )
    return card.press_release_group, sorted(set(sites) | {card.press_site})


def keep_sites(request):
    """The sites are the ones the person saw and approved by pressing Deploy: they never change after."""
    if request.is_new():
        return
    approved = frappe.get_all(
        "HDS Deploy Site",
        filters={"parent": request.name, "parenttype": DEPLOY},
        pluck="site",
    )
    if sorted(approved) != sorted(row.site for row in request.sites):
        frappe.throw(
            _(
                "A deploy's sites are fixed when Deploy is pressed; cancel it and press Deploy again."
            )
        )


def hub_site() -> str:
    """This TBO Support site's name, which is also its Press site's name.

    It may share a bench with customers (TBO's demo bench does): a deploy
    leaves it on its current code, since Press moves only the sites it is
    given and keeps every other app at its last deployed commit.
    """
    return frappe.local.site


def _app_of(run, approval) -> dict:
    """The app the fix changes, from the site card row of the pull request's repository."""
    from helpdesk.copilot.fixes import _repo_name

    for row in frappe.get_all(
        "HDS Site App",
        filters={"parent": run.registry, "parenttype": "HDS Site Registry"},
        fields=["app", "repository", "deployed_commit"],
    ):
        if _repo_name(row.repository) == (approval.repo or "").lower():
            return row
    frappe.throw(
        _("The site card lists no app for {0}; refresh it from the site first.").format(
            approval.repo
        )
    )


# --- asking for a deploy --------------------------------------------------------------


def request_deploy(run, when: str, user: str, auto: bool = False):
    """Deploy the merged fix Tonight (the next window) or Now (seniors and Agent Managers).

    `auto`: asked on the approver's behalf once the fix is approved and merged (Phase 11, or an
    Auto-deploy category). Their approval is the go: a low-risk fix may go now without a senior;
    a bench other customers' sites share still needs a senior approver, and waits for the night
    window (TBO Support's own site on it does not count).
    """
    from helpdesk.copilot import customer

    run = frappe.get_doc("HDS Copilot Run", run.name)
    if run.state != "Merged":
        frappe.throw(
            _("Only a merged fix can be deployed (this run is {0}).").format(run.state)
        )
    if open_request(run):
        frappe.throw(_("This fix already has a deploy waiting or running."))
    if not press.configured():
        frappe.throw(_("Press is not set up in HDS Copilot Settings."))
    if not may_deploy(user):
        frappe.throw(
            _("Only the Copilot approvers and the Agent Managers may deploy fixes."),
            frappe.PermissionError,
        )
    now = str(when).strip().lower() == "now"
    if now and not auto and not may_deploy_now(user):
        frappe.throw(
            _(
                "Only senior approvers and Agent Managers may deploy now; schedule it for tonight."
            ),
            frappe.PermissionError,
        )
    approval = frappe.get_doc("HDS Copilot Approval", run.approval)
    app = _app_of(run, approval)
    group, sites = target(run)
    try:
        info = press.deploy_information(group)
    except PressError as e:
        frappe.throw(_("Press: {0}").format(e.message))
    on_bench = [site.get("name") for site in info.get("sites") or []]
    missing = [site for site in sites if site not in on_bench]
    if missing:
        frappe.throw(
            _("Press does not list {0} on the bench {1}.").format(
                ", ".join(missing), group
            )
        )
    others = [site for site in on_bench if site not in sites]
    customers = [site for site in others if site != hub_site()]
    if customers and user not in approvals.seniors():
        frappe.throw(
            _(
                "Other sites share this bench ({0}); only a senior approver may deploy it."
            ).format(", ".join(customers[:5])),
            frappe.PermissionError,
        )
    if customers and auto:
        now = False  # other customers' sites move too: the night window
    at = now_datetime() if now else next_opening()
    doc = frappe.get_doc(
        {
            "doctype": DEPLOY,
            "run": run.name,
            "ticket": run.ticket,
            "approval": approval.name,
            "status": "Scheduled",
            "when": "Now" if now else "Tonight",
            "scheduled_for": at,
            "requested_by": user,
            "requested_at": now_datetime(),
            "release_group": group,
            "other_sites": "\n".join(others),
            "sites": [{"site": site} for site in sites],
            "apps": [
                {
                    "app": app.app,
                    "repository": approval.repo,
                    "from_commit": app.deployed_commit,
                    "to_commit": run.merge_commit,
                }
            ],
        }
    ).insert(ignore_permissions=True)
    run.db_set("deploy_request", doc.name, update_modified=False)
    runs.add_event(
        run,
        "deploy_requested",
        {
            "request": doc.name,
            "when": doc.when,
            "at": str(at),
            "sites": sites,
            "by": user,
            "auto": auto,
        },
        runs.SYSTEM if auto else runs.AGENT,
    )
    customer.send_stage(run, "Fix scheduled", {"date": local_time(at)})
    from helpdesk.copilot import thread

    thread.on_deploy(run, "now" if now else "tonight", at)
    runs.publish_run(run)
    return doc


def auto_categories() -> set[str]:
    text = copilot_settings.get_settings().get("auto_deploy_categories") or ""
    return {line.strip().lower() for line in text.splitlines() if line.strip()}


def auto_request(run, approval):
    """Deploys a merged fix by itself once it is approved (Phase 11, unless Deploy Needs a
    Press): a low-risk one at once, a high-risk or sensitive one (or a bench other customers
    share) in the night window. With Deploy Needs a Press, only the root causes or risks listed
    in Auto-deploy categories go by themselves, in the window, never a sensitive or high-risk
    fix or an undo. Whatever stops it is said in the ticket's chat and leaves Deploy to a person.
    """
    risk = (approval.risk_level or "").lower()
    if not copilot_settings.get_settings().get("deploy_needs_a_press"):
        # Phase 11: an approved fix deploys by itself; low risk at once, the rest tonight
        if not press.configured():
            return None
        when = "now" if risk != "high" and not approval.sensitive else "tonight"
        return _auto(run, approval, when)
    wanted = auto_categories()
    if (
        not wanted
        or run.get("kind") == "revert"
        or approval.sensitive
        or risk == "high"
        or not ({(run.root_cause_category or "").lower(), risk} & wanted)
        or not press.configured()
    ):
        return None
    return _auto(run, approval, "tonight")


def _auto(run, approval, when: str):
    try:
        return request_deploy(run, when, approval.decided_by, auto=True)
    except Exception as e:
        frappe.clear_last_message()  # the approver's click merged the fix; this is no error of theirs
        if not isinstance(e, (frappe.ValidationError, frappe.PermissionError)):
            frappe.log_error(
                title=_("Copilot automatic deploy of {0}").format(run.name)
            )
        runs.add_event(
            run, "auto_deploy_skipped", {"reason": str(e)[:300]}, runs.SYSTEM
        )
        from helpdesk.copilot import thread

        thread.post(
            run.ticket,
            thread._card(
                "",
                [
                    _("Copilot could not deploy it by itself: {0}").format(
                        str(e)[:300]
                    ),
                    _("A senior or an Agent Manager presses Deploy."),
                ],
                tone="warning",
            ),
            run=run.name,
            status=True,
        )
        return None


def cancel_deploy(run, user: str):
    request = open_request(run)
    if not request or request.status not in WAITING:
        frappe.throw(_("Only a deploy that has not started can be cancelled."))
    request.db_set({"status": "Cancelled", "finished_at": now_datetime()})
    _release_lock(request.name)
    runs.add_event(
        run, "deploy_cancelled", {"request": request.name, "by": user}, runs.AGENT
    )
    runs.publish_run(run)


# --- one at a time ----------------------------------------------------------------------


def _lock_key() -> str:
    return frappe.cache().make_key(LOCK_KEY)


def _lock_holder() -> str | None:
    held = frappe.cache().get(_lock_key())  # the site's own key (make_key) - nosemgrep
    return held.decode() if isinstance(held, bytes) else held


def _take_lock(owner: str) -> bool:
    """One Copilot deploy at a time: Redis SET NX with an expiry, so a crash cannot hold it for ever."""
    if frappe.cache().set(  # SET NX needs the raw call; the key is the site's own - nosemgrep
        _lock_key(), owner, ex=LOCK_SECONDS, nx=True
    ):
        return True
    return _lock_holder() == owner


def _release_lock(owner: str):
    if _lock_holder() == owner:
        frappe.cache().delete(_lock_key())


# --- the cron -----------------------------------------------------------------------


def run_due():
    """Cron: every open deploy request takes its next step, one at a time, each in its own transaction."""
    for name in frappe.get_all(
        DEPLOY,
        filters={"status": ["in", OPEN]},
        order_by="scheduled_for asc",
        pluck="name",
    ):
        try:
            step(frappe.get_doc(DEPLOY, name))
            frappe.db.commit()  # one request at a time - nosemgrep
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title=_("Copilot deploy {0} could not move on").format(name)
            )


def step(request):
    if request.status in WAITING:
        if get_datetime(request.scheduled_for) <= now_datetime():
            _start(request)
    elif request.status == "Deploying":
        _follow(request)
    elif request.status == "Checking":
        from helpdesk.copilot import verify

        verify.step(request)


def _press_app(info: dict, app: str) -> dict | None:
    return next(
        (
            row
            for row in info.get("apps") or []
            if (row.get("app") or row.get("name")) == app
        ),
        None,
    )


def _run_of(request):
    """The Copilot run a deploy request belongs to; None for a release of other people's merges."""
    return frappe.get_doc("HDS Copilot Run", request.run) if request.run else None


def _note(request, kind: str, payload: dict):
    """An event on the run, or a comment on a release (which has no run)."""
    if request.run:
        runs.add_event(request.run, kind, payload, runs.SYSTEM)
    else:
        request.add_comment(
            "Info", f"{kind}: {json.dumps(payload, default=str)}"[:1000]
        )


def _riders(request) -> list:
    """The nightly train: other approved requests due on the same bench go out in the
    same Press deploy, one build instead of several. A request for an app already on
    the train waits for the next one."""
    if not request.release_group:
        return []
    apps = {row.app for row in request.apps}
    riders = []
    for name in frappe.get_all(
        DEPLOY,
        filters={
            "name": ["!=", request.name],
            "release_group": request.release_group,
            "status": ["in", WAITING],
            "scheduled_for": ["<=", now_datetime()],
        },
        order_by="scheduled_for asc",
        pluck="name",
    ):
        rider = frappe.get_doc(DEPLOY, name)
        if {row.app for row in rider.apps} & apps:
            continue
        riders.append(rider)
        apps |= {row.app for row in rider.apps}
    return riders


def _offer(info: dict, request) -> str:
    """Whether Press can deploy the request's commit: "current" (the bench runs it), "offered", or why not."""
    app = request.apps[0]
    row = _press_app(info, app.app)
    if not row:
        return _("Press's bench {0} has no app {1}").format(
            request.release_group, app.app
        )
    current, following = press.app_commits(row)
    if current.startswith(app.to_commit or "-"):
        return "current"
    if following.startswith(app.to_commit or "-"):
        return "offered"
    return _("Press does not offer the merged commit {0} yet (it offers {1})").format(
        (app.to_commit or "")[:12], (following or "none")[:12]
    )


def _already_running(request, run):
    """The bench already runs it (deployed by hand): straight to the check."""
    request.db_set(
        {"status": "Checking", "started_at": now_datetime(), "waiting_since": None}
    )
    if run:
        runs.transition(run, "Deploying", runs.SYSTEM, note="already on Press")
        runs.transition(
            run, "Verifying", runs.SYSTEM, note="the bench already runs the commit"
        )


def _start(request):
    run = _run_of(request)
    if not _take_lock(request.name):
        return _wait(request, _("another Copilot deploy is running"))
    try:
        info = press.deploy_information(request.release_group)
        if info.get("deploy_in_progress") or info.get("has_running_release_pipeline"):
            _release_lock(request.name)
            return _wait(request, _("Press is already deploying this bench"))
        offer = _offer(info, request)
        if offer == "current":
            return _already_running(request, run)
        if offer != "offered":
            if not _press_app(info, request.apps[0].app):
                return fail(request, offer)
            press.fetch_latest_app_update(request.release_group, request.apps[0].app)
            _release_lock(request.name)
            return _wait(request, offer)
        train = [request]
        for rider in _riders(request):
            rider_offer = _offer(info, rider)
            if rider_offer == "current":
                _already_running(rider, _run_of(rider))
            elif rider_offer == "offered":
                train.append(rider)
        wanted = {site.site for member in train for site in member.sites}
        skip_backups = bool(copilot_settings.get_settings().press_skip_backups)
        sites = [
            {**site, "skip_failing_patches": False, "skip_backups": skip_backups}
            for site in info.get("sites") or []
            if site.get("name") in wanted
        ]
        if len(sites) != len(wanted):
            return fail(
                request,
                _("Press no longer lists every site of this deploy on the bench"),
            )
        apps = []
        for member in train:
            row = _press_app(info, member.apps[0].app)
            apps.append(
                {
                    "app": member.apps[0].app,
                    "source": row.get("source"),
                    "release": row.get("next_release"),
                    "hash": press.app_commits(row)[1],
                }
            )
        reference = press.deploy_and_update(request.release_group, apps, sites)
    except PressError as e:
        _release_lock(request.name)
        return _wait(request, _("Press: {0}").format(e.message))
    for member in train:
        member.db_set(
            {
                "status": "Deploying",
                "started_at": now_datetime(),
                "press_reference": str(reference or "")[:140],
                "waiting_since": None,
                "error": None,
                "train": request.name if len(train) > 1 else None,
            }
        )
        member_run = run if member is request else _run_of(member)
        if member_run:
            runs.transition(
                member_run, "Deploying", runs.SYSTEM, note=f"Press {reference}"
            )
        _note(
            member,
            "deploy_started",
            {
                "request": member.name,
                "press": reference,
                "sites": sorted(row.site for row in member.sites),
                "train": [m.name for m in train] if len(train) > 1 else None,
                "backups": not skip_backups,
            },
        )


def _wait(request, reason: str):
    """Press cannot take it yet: wait, and after the allowed wait move it to the next window."""
    now = now_datetime()
    since = get_datetime(request.waiting_since) if request.waiting_since else now
    limit = copilot_settings.get_settings().get("deploy_start_wait_minutes") or 60
    if (now - since).total_seconds() / 60 > limit:
        request.db_set(
            {
                "status": "Scheduled",
                "scheduled_for": next_opening(
                    now + timedelta(hours=1), now_counts=False
                ),
                "waiting_since": None,
                "error": str(reason)[:1000],
            }
        )
        _note(
            request,
            "deploy_rescheduled",
            {
                "request": request.name,
                "reason": reason,
                "to": str(request.scheduled_for),
            },
        )
        return
    request.db_set(
        {
            "status": "Waiting for Press",
            "waiting_since": since,
            "error": str(reason)[:1000],
        }
    )


def _follow(request):
    """Follows Press's site updates until every site is updated, or one fails.

    A failed build ends it at once: Press then never updates a site. Agent Jobs
    are not read, since some fail by design on TBO's Press ("Add User to Proxy"
    on every new bench) without the deploy failing.
    """
    started = get_datetime(request.started_at)
    if (now_datetime() - started).total_seconds() > PRESS_HOURS * 3600:
        return fail(
            request, _("Press did not finish within {0} hours").format(PRESS_HOURS)
        )
    names = [row.site for row in request.sites]
    try:
        updates = press.get_list(
            "Site Update",
            filters={
                "site": ["in", names],
                "creation": [">=", str(started - timedelta(minutes=5))],
            },
            fields=["name", "site", "status", "creation"],
            limit=50,
        )
    except PressError:
        return  # Press could not be asked this time; the next run tries again
    latest = {}
    for update in updates:
        latest.setdefault(update.get("site"), update)
    for row in request.sites:
        if update := latest.get(row.site):
            row.site_update, row.status = update.get("name"), update.get("status")
            if not row.backup and row.status in SITE_DONE | SITE_FAILED:
                row.backup = _backup_of(row.site_update)
    request.save(ignore_permissions=True)
    failed = [row for row in request.sites if row.status in SITE_FAILED]
    if failed:
        return fail(
            request,
            _(
                "Press could not update {0} ({1}); Press puts a site back on its old code when its update fails"
            ).format(
                ", ".join(row.site for row in failed),
                ", ".join(sorted({row.status for row in failed})),
            ),
        )
    done = all(row.status in SITE_DONE for row in request.sites)
    if not done and (build := _failed_build(request, started)):
        url = (copilot_settings.get_settings().get("press_url") or "").rstrip("/")
        return fail(
            request,
            _("Press's build {0} failed, so no site was changed: {1}").format(
                build, f"{url}/app/deploy-candidate-build/{build}"
            ),
        )
    if done:
        request.db_set({"status": "Checking"})
        if request.run:
            run = runs.transition(
                request.run, "Verifying", runs.SYSTEM, note="Press updated the sites"
            )
            runs.add_event(
                run, "deploy_updated", {"request": request.name}, runs.SYSTEM
            )


def _failed_build(request, started) -> str | None:
    """The bench's newest build since the deploy started, when Press says it failed."""
    try:
        builds = press.get_list(
            "Deploy Candidate Build",
            filters={
                "group": request.release_group,
                "creation": [">=", str(started - timedelta(minutes=5))],
            },
            fields=["name", "status"],
            limit=5,
        )
    except PressError:
        return None  # Press could not be asked this time; the next run tries again
    if builds and builds[0].get("status") == "Failure":
        return builds[0].get("name")
    return None


def _backup_of(site_update: str) -> str | None:
    """The backup Press took before the update, when Press says which (best effort)."""
    try:
        rows = press.get_list(
            "Site Update",
            filters={"name": site_update},
            fields=["name", "site_backup"],
            limit=1,
        )
    except PressError:
        return None
    return ((rows or [{}])[0] or {}).get("site_backup") or None


def _press_links(request) -> str:
    """Each site's update on Press, with the backup Press took first, for the people told."""
    url = (copilot_settings.get_settings().get("press_url") or "").rstrip("/")
    escape = frappe.utils.escape_html
    return ", ".join(
        '<a href="{0}/app/site-update/{1}">{2}</a>{3}'.format(
            escape(url),
            escape(row.site_update),
            escape(row.site),
            " ({0} {1})".format(escape(_("backup")), escape(row.backup))
            if row.backup
            else "",
        )
        for row in request.sites
        if row.site_update
    )


# --- the end --------------------------------------------------------------------------


def fail(request, reason: str):
    """The deploy did not work: the run is escalated with Press's reason, the people told."""
    from helpdesk.copilot import customer

    reason = str(reason)[:1000]
    if not request.run:
        from helpdesk.copilot import releases

        # the site ran the new code and the check after failed: the release is reverted
        after_check = request.status == "Checking"
        _release_lock(request.name)
        return releases.failed(
            request, reason, _press_links(request), after_check=after_check
        )
    request.db_set({"status": "Failed", "error": reason, "finished_at": now_datetime()})
    _release_lock(request.name)
    run = frappe.get_doc("HDS Copilot Run", request.run)
    if run.state in ("Merged", "Deploying", "Verifying"):
        run = runs.transition(
            run, "Escalated", runs.SYSTEM, note=f"deploy failed: {reason}"[:140]
        )
    runs.add_event(
        run, "deploy_failed", {"request": request.name, "reason": reason}, runs.SYSTEM
    )
    links = _press_links(request)
    customer.comment(
        run.ticket,
        frappe.utils.escape_html(
            _("The deploy of the Copilot fix failed: {0}").format(reason)
        )
        + (
            "<br>{0} {1}".format(frappe.utils.escape_html(_("Press:")), links)
            if links
            else ""
        ),
    )
    from helpdesk.work_reminders import notify_users

    approval = (
        frappe.db.get_value("HDS Copilot Approval", request.approval, "decided_by")
        if request.approval
        else None
    )
    people = [p for p in (approval, request.requested_by) if p] + approvals.managers()
    notify_users(
        list(dict.fromkeys(people)),
        "HD Ticket",
        run.ticket,
        _("The deploy of the Copilot fix for ticket {0} failed: {1}").format(
            run.ticket, reason[:160]
        ),
        escalate=True,
        once=False,
    )
    return None


def succeed(request, results: list[dict]):
    """The check passed: the run is Resolved and the customer is asked to confirm."""
    from helpdesk.copilot import customer

    if not request.run:
        from helpdesk.copilot import releases

        _release_lock(request.name)
        return releases.succeeded(request, results)
    request.db_set(
        {
            "status": "Succeeded",
            "finished_at": now_datetime(),
            "check_results": json.dumps(results, indent=1),
        }
    )
    _release_lock(request.name)
    from helpdesk.copilot import changes

    data = changes.approved_with_code(frappe.get_doc("HDS Copilot Run", request.run))
    if data:
        run = runs.transition(
            request.run,
            "Applying",
            runs.SYSTEM,
            note="deployed and checked; correcting the data",
            deployed_at=now_datetime(),
            deployed_by=request.requested_by,
        )
        runs.add_event(run, "deploy_checked", {"request": request.name}, runs.SYSTEM)
        changes.apply_after_code(data, request.requested_by)
        return
    run = runs.transition(
        request.run,
        "Resolved",
        runs.SYSTEM,
        note="deployed and checked",
        deployed_at=now_datetime(),
        deployed_by=request.requested_by,
    )
    runs.add_event(run, "deploy_checked", {"request": request.name}, runs.SYSTEM)
    if run.get("kind") != "revert":
        from helpdesk.copilot import fixes

        customer.send_stage(run, "Resolved", {"resolution": fixes.live_text(run)})
