# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Copilot on the ticket page: start, see, rate and cancel a run (agents); confirm or reopen (the customer)."""

import json

import frappe
from frappe import _
from frappe.utils import format_datetime, get_fullname, now_datetime, sbool

from helpdesk.api.customization import is_ticket_customer
from helpdesk.copilot import customer, router, runs
from helpdesk.copilot import settings as copilot_settings
from helpdesk.copilot import suspicious
from helpdesk.utils import agent_only, is_agent

VERDICTS = ("Right", "Partly", "Wrong")


@frappe.whitelist(methods=["POST"])
@agent_only
def start_run(
    ticket: str | int, base_commit: str | None = None, base_app: str | None = None
) -> dict:
    """Queues a Copilot run for the ticket (or returns the active one).

    `base_app` and `base_commit` make the worker read that app at that commit
    instead of the deployed code (evaluation runs).
    """
    frappe.has_permission("HD Ticket", "write", str(ticket), throw=True)
    runs.start_run(
        str(ticket), actor=runs.AGENT, base_commit=base_commit, base_app=base_app
    )
    return get_run(ticket)


@frappe.whitelist(methods=["POST"])
@agent_only
def cancel_run(ticket: str | int) -> dict:
    frappe.has_permission("HD Ticket", "write", str(ticket), throw=True)
    run = runs.active_run(str(ticket))
    if run and run.state in runs.CANCELLABLE:
        runs.transition(
            run, "Cancelled", runs.AGENT, note=f"cancelled by {frappe.session.user}"
        )
    return get_run(ticket)


@frappe.whitelist()
@agent_only
def get_run(ticket: str | int) -> dict:
    """The latest run on a ticket, for the Copilot dialog."""
    frappe.has_permission("HD Ticket", "read", str(ticket), throw=True)
    run = customer.latest_run(str(ticket))
    if not run:
        return {"run": None, "can_start": True}
    events = [
        {
            "creation": str(e.creation)[:19],
            "event_type": e.event_type,
            "actor": e.actor,
            "note": _event_note(e.payload),
        }
        for e in frappe.get_all(
            "HDS Copilot Event",
            filters={"run": run.name},
            fields=["creation", "event_type", "actor", "payload"],
            order_by="creation desc",
            limit=20,
        )
    ]
    return {
        "run": run.name,
        "kind": run.kind,
        "state": run.state,
        "stage": frappe.db.get_value("HD Ticket", run.ticket, "custom_copilot_stage"),
        "root_cause": run.root_cause_category,
        "confidence": run.confidence,
        "summary": run.summary,
        "customer_message": run.customer_message,
        "evidence": json.loads(run.evidence or "[]"),
        "proposal": json.loads(run.proposal or "{}"),
        "task": run.task,
        "handed_over_to": run.handed_over_to,
        "failure_reason": run.failure_reason,
        "worker_id": run.worker_id,
        "lease_expires": str(run.lease_expires) if run.lease_expires else None,
        "queued_at": str(run.queued_at) if run.queued_at else None,
        "events": events,
        "can_cancel": run.state in runs.CANCELLABLE,
        "can_start": runs.active_run(run.ticket) is None,
        # the customer asked TBO to correct their own entries, after Copilot's explanation
        "can_prepare_correction": run.root_cause_category == "customer_mistake"
        and run.get("kind") != "revert"
        and runs.active_run(run.ticket) is None
        and copilot_settings.allows(run.customer, copilot_settings.CORRECT),
        "level": copilot_settings.level_of(run.customer),
        # text that tried to instruct the AI, found by the hub (ticket) or the worker (what it read)
        "suspicious": suspicious.seen(run.name),
        "shadow": bool(run.shadow),
        "base_app": run.base_app,
        "base_commit": run.base_commit,
        "model_used": run.model_used,
        "tokens_in": run.tokens_in,
        "tokens_out": run.tokens_out,
        "cost_usd": run.cost_usd,
        "review": {
            "verdict": run.review_verdict or None,
            "root_cause": run.reviewed_root_cause or None,
            "note": run.review_note or None,
            "by": run.reviewed_by,
            "by_name": get_fullname(run.reviewed_by) if run.reviewed_by else None,
            "at": str(run.reviewed_at)[:19] if run.reviewed_at else None,
        },
        "can_review": bool(run.root_cause_category),
        "categories": list(router.CATEGORIES),
        "fix": _fix_card(run),
        "build": _build_card(run),
    }


def _build_card(run) -> dict | None:
    """A customization: Build with Copilot with the approved scope, or why it can't be built yet."""
    from helpdesk.api.customization import checks_of
    from helpdesk.copilot import fixes

    if run.root_cause_category != "customization_request":
        return None
    ticket = frappe.db.get_value(
        "HD Ticket",
        run.ticket,
        ["custom_estimate_scope", "custom_estimate_checks", "custom_estimate_hours"],
        as_dict=True,
    )
    building = fixes.build_of(run)
    reason = None if building else fixes.build_refusal(run)
    return {
        "building": bool(building),
        "scope": (building or {}).get("scope") or ticket.custom_estimate_scope or "",
        "checks": (building or {}).get("checks")
        or checks_of(ticket.custom_estimate_checks),
        "hours": (building or {}).get("hours") or ticket.custom_estimate_hours,
        "can_build": not building and reason is None,
        "reason": reason,
    }


def _fix_card(run) -> dict | None:
    """The fix as the Copilot dialog shows it: the task, the pull request, the approval and what may be done."""
    from helpdesk.copilot import approvals, changes, deploy, fixes, press

    if (
        run.state not in fixes.FOLLOWED + ("Resolved", "Applying")
        and not run.task
        and not run.get("change_set")
    ):
        return None
    user = frappe.session.user
    attempts = copilot_settings.get_settings().get("max_fix_attempts") or 2
    task = (
        frappe.db.get_value(
            "Task", run.task, ["name", "subject", "status"], as_dict=True
        )
        if run.task
        else None
    )
    pull = (
        frappe.db.get_value(
            "HD Pull Request",
            run.pull_request,
            [
                "repo",
                "number",
                "title",
                "url",
                "state",
                "head_sha",
                "ci_state",
                "review_state",
            ],
            as_dict=True,
        )
        if run.pull_request
        else None
    )
    approval = (
        frappe.get_doc("HDS Copilot Approval", run.approval) if run.approval else None
    )
    card = None
    if approval:
        payload = json.loads(approval.payload or "{}")
        card = {
            "name": approval.name,
            "status": approval.status,
            "kind": approval.get("kind") or "Code Change",
            "change_set": approval.get("change_set"),
            "head_sha": approval.head_sha,
            "risk_level": approval.risk_level,
            "sensitive": bool(approval.sensitive),
            "reasons": [r for r in (approval.reasons or "").split("\n") if r],
            "files": payload.get("files") or [],
            "checks": payload.get("checks") or {},
            "assigned_to": approval.assigned_to,
            "assigned_name": get_fullname(approval.assigned_to)
            if approval.assigned_to
            else None,
            "decided_by": get_fullname(approval.decided_by)
            if approval.decided_by
            else None,
            "decided_at": str(approval.decided_at)[:16]
            if approval.decided_at
            else None,
            "note": approval.note,
            "deploy_date": str(approval.deploy_date) if approval.deploy_date else None,
            "merge_error": approval.merge_error,
            "url": approval.pr_url,
            "why_not_me": approvals.may_decide(approval, user)
            if approval.status == "Pending"
            else None,
            # what Copilot tested, when it made the fix, and on which commit
            "change": payload.get("change"),
            # a build: the scope the customer approved, shown next to what changed
            "build": payload.get("build"),
            "copilot_only": bool(payload.get("copilot_only")),
            "evidence_stale": bool(
                payload.get("change")
                and (payload["change"].get("tested_commit") or "") != approval.head_sha
            ),
        }
    return {
        "task": task,
        "pull_request": pull,
        "approval": card,
        "hold_label": fixes.hold_label(),
        "can_create_task": run.state == "Preparing Fix"
        and not (task and task.status not in ("Completed", "Cancelled")),
        "can_decide": bool(
            card and card["status"] == "Pending" and not card["why_not_me"]
        ),
        "can_refresh": run.state in fixes.FIX_STATES and bool(run.task),
        "can_mark_deployed": run.state == "Merged" and not deploy.open_request(run),
        "deploy": _deploy_card(run),
        "can_deploy": run.state == "Merged"
        and not deploy.open_request(run)
        and press.configured()
        and deploy.may_deploy(user),
        "can_deploy_now": deploy.may_deploy_now(user),
        # the exact sites Deploy updates, shown before it is pressed
        "deploy_sites": deploy.card_sites(run)[1] if run.state == "Merged" else [],
        "press_backups": not copilot_settings.get_settings().press_skip_backups,
        "can_undo": fixes.can_undo(run) and deploy.may_deploy(user),
        "reverts": run.get("reverts"),
        "revert_run": (fixes.revert_run_of(run) or frappe._dict()).get("name"),
        "copilot": {
            "requested": bool(run.fix_requested),
            "status": run.fix_status or None,
            "attempts": run.fix_attempts or 0,
            "max_attempts": attempts,
        },
        "can_request_fix": not fixes.fix_refusal(run),
        "merge_commit": run.merge_commit,
        "deployed_at": str(run.deployed_at)[:16] if run.deployed_at else None,
        "change_set": changes.card(frappe.get_doc(changes.CHANGE_SET, run.change_set))
        if run.get("change_set")
        else None,
        "can_undo_change": changes.can_undo(run) and deploy.may_deploy(user),
    }


def _deploy_card(run) -> dict | None:
    """The run's latest deploy through Press, as the dialog shows it."""
    from helpdesk.copilot import deploy

    if not run.deploy_request:
        return None
    request = frappe.get_doc(deploy.DEPLOY, run.deploy_request)
    return {
        "name": request.name,
        "status": request.status,
        "when": request.when,
        "scheduled_for": deploy.local_time(request.scheduled_for)
        if request.scheduled_for
        else None,
        "sites": [
            {"site": row.site, "status": row.status or ""} for row in request.sites
        ],
        "other_sites": [s for s in (request.other_sites or "").split("\n") if s],
        "error": request.error,
        "check": json.loads(request.check_results or "[]"),
        "can_cancel": request.status in deploy.WAITING,
    }


def _run_of(ticket: str | int):
    run = customer.latest_run(str(ticket))
    if not run:
        frappe.throw(_("Copilot has no run on this ticket."))
    return run


@frappe.whitelist(methods=["POST"])
@agent_only
def create_fix_task(ticket: str | int) -> dict:
    """A fix task for the run's diagnosis (live runs get one by themselves)."""
    from helpdesk.copilot import fixes

    frappe.has_permission("HD Ticket", "write", str(ticket), throw=True)
    fixes.create_fix_task(_run_of(ticket), actor=runs.AGENT)
    return get_run(ticket)


@frappe.whitelist(methods=["POST"])
def refresh_site_card(registry: str) -> dict:
    """Read every app, commit and branch of a registered site through its connection."""
    from helpdesk.copilot.registry import refresh_from_site

    frappe.has_permission("HDS Site Registry", "write", registry, throw=True)
    return refresh_from_site(frappe.get_doc("HDS Site Registry", registry))


@frappe.whitelist(methods=["POST"])
@agent_only
def build_customization(ticket: str | int) -> dict:
    """Copilot builds the customization whose written scope the customer approved (Phase 8)."""
    from helpdesk.copilot import fixes

    frappe.has_permission("HD Ticket", "write", str(ticket), throw=True)
    fixes.request_build(_run_of(ticket), frappe.session.user)
    return get_run(ticket)


@frappe.whitelist(methods=["POST"])
@agent_only
def request_copilot_fix(ticket: str | int) -> dict:
    """Ask Copilot to fix the diagnosed bug on a sandbox copy of the site and open the pull request."""
    from helpdesk.copilot import fixes

    frappe.has_permission("HD Ticket", "write", str(ticket), throw=True)
    fixes.request_copilot_fix(_run_of(ticket), frappe.session.user)
    return get_run(ticket)


@frappe.whitelist(methods=["POST"])
@agent_only
def decide_fix(
    ticket: str | int,
    approve: bool | int | str,
    note: str = "",
    deploy_date: str | None = None,
) -> dict:
    """Approve (with the planned deploy date) or reject (with a reason) the fix waiting for approval."""
    from helpdesk.copilot import approvals

    frappe.has_permission("HD Ticket", "read", str(ticket), throw=True)
    run = _run_of(ticket)
    approval = approvals.current(run)
    if not approval or approval.status != "Pending":
        # a second click, or a second person: say who decided first
        last = frappe.db.get_value(
            "HDS Copilot Approval",
            {"run": run.name, "decided_by": ["is", "set"]},
            ["status", "decided_by", "decided_at"],
            order_by="decided_at desc",
            as_dict=True,
        )
        if last:
            frappe.throw(
                _("This was already {0} by {1} at {2}.").format(
                    _("rejected") if last.status == "Rejected" else _("approved"),
                    last.decided_by,
                    format_datetime(last.decided_at),
                )
            )
        frappe.throw(_("No fix is waiting for approval on this ticket."))
    decision = approvals.decide(
        approval.name, frappe.session.user, bool(sbool(approve)), note, deploy_date
    )
    return {**get_run(ticket), "decision": decision}


@frappe.whitelist(methods=["POST"])
@agent_only
def refresh_fix(ticket: str | int) -> dict:
    """Read the fix's pull request from GitHub now."""
    from helpdesk.copilot import fixes

    frappe.has_permission("HD Ticket", "read", str(ticket), throw=True)
    outcome = fixes.refresh(_run_of(ticket))
    return {**get_run(ticket), "refresh": outcome}


@frappe.whitelist(methods=["POST"])
@agent_only
def request_deploy(ticket: str | int, when: str = "tonight") -> dict:
    """Deploy the merged fix through Press: tonight (the next window), or now (seniors and Agent Managers)."""
    from helpdesk.copilot import deploy

    frappe.has_permission("HD Ticket", "write", str(ticket), throw=True)
    deploy.request_deploy(_run_of(ticket), when, frappe.session.user)
    return get_run(ticket)


@frappe.whitelist(methods=["POST"])
@agent_only
def undo_fix(ticket: str | int, reason: str) -> dict:
    """Undo a merged fix that went wrong: GitHub's revert pull request, through the same one approval."""
    from helpdesk.copilot import deploy, fixes

    frappe.has_permission("HD Ticket", "write", str(ticket), throw=True)
    if not deploy.may_deploy(frappe.session.user):
        frappe.throw(
            _("Only the Copilot approvers and the Agent Managers may undo fixes."),
            frappe.PermissionError,
        )
    fixes.undo(_run_of(ticket), frappe.session.user, reason)
    return get_run(ticket)


@frappe.whitelist(methods=["POST"])
@agent_only
def change_set_applied_by_hand(ticket: str | int) -> dict:
    """A senior applied the correction by hand: Copilot reads every record back from the site."""
    from helpdesk.copilot import changes

    frappe.has_permission("HD Ticket", "write", str(ticket), throw=True)
    run = _run_of(ticket)
    if not run.get("change_set"):
        frappe.throw(_("This ticket has no correction from Copilot."))
    changes.applied_by_hand(run.change_set, frappe.session.user)
    return get_run(ticket)


@frappe.whitelist(methods=["POST"])
@agent_only
def undo_change(ticket: str | int, reason: str) -> dict:
    """Undo an applied correction: the reverse change set, through a senior's approval."""
    from helpdesk.copilot import changes, deploy

    frappe.has_permission("HD Ticket", "write", str(ticket), throw=True)
    if not deploy.may_deploy(frappe.session.user):
        frappe.throw(
            _(
                "Only the Copilot approvers and the Agent Managers may undo corrections."
            ),
            frappe.PermissionError,
        )
    changes.undo(_run_of(ticket), frappe.session.user, reason)
    return get_run(ticket)


@frappe.whitelist(methods=["POST"])
@agent_only
def prepare_correction(ticket: str | int) -> dict:
    """The customer asked TBO to correct their own entries: Copilot prepares the change set."""
    from helpdesk.copilot import changes

    frappe.has_permission("HD Ticket", "write", str(ticket), throw=True)
    changes.prepare_correction(str(ticket), frappe.session.user)
    return get_run(ticket)


@frappe.whitelist(methods=["GET"])
def download_change_set(change_set: str):
    """Every record of a correction, with its old and new values, as CSV."""
    from helpdesk.copilot import changes

    frappe.has_permission(changes.CHANGE_SET, "read", change_set, throw=True)
    doc = frappe.get_doc(changes.CHANGE_SET, change_set)
    frappe.response["result"] = changes.as_csv(doc)
    frappe.response["type"] = "csv"
    frappe.response["doctype"] = doc.name


@frappe.whitelist(methods=["POST"])
def refresh_site_card_from_press(registry: str) -> dict:
    """The bench's apps and commits as Press knows them, and the other sites on the bench."""
    from helpdesk.copilot.registry import refresh_from_press

    frappe.has_permission("HDS Site Registry", "write", registry, throw=True)
    return refresh_from_press(frappe.get_doc("HDS Site Registry", registry))


@frappe.whitelist(methods=["POST"])
@agent_only
def cancel_deploy(ticket: str | int) -> dict:
    """Cancel a deploy that has not started."""
    from helpdesk.copilot import deploy

    frappe.has_permission("HD Ticket", "write", str(ticket), throw=True)
    deploy.cancel_deploy(_run_of(ticket), frappe.session.user)
    return get_run(ticket)


@frappe.whitelist(methods=["POST"])
@agent_only
def mark_deployed(ticket: str | int, note: str = "") -> dict:
    """The merged fix is live: the run is Resolved and the customer is asked to confirm."""
    from helpdesk.copilot import fixes

    frappe.has_permission("HD Ticket", "write", str(ticket), throw=True)
    fixes.mark_deployed(_run_of(ticket), frappe.session.user, note)
    return get_run(ticket)


@frappe.whitelist(methods=["POST"])
@agent_only
def review_diagnosis(
    ticket: str | int, verdict: str, root_cause: str = "", note: str = ""
) -> dict:
    """An agent rates Copilot's diagnosis on the ticket: Right, Partly or Wrong.

    Wrong needs the root cause the agent found; Partly may name it. Rating
    again replaces the rating; every rating is kept as an event.
    """
    frappe.has_permission("HD Ticket", "read", str(ticket), throw=True)
    run = customer.latest_run(str(ticket))
    if not run or not run.root_cause_category:
        frappe.throw(_("Copilot has no diagnosis on this ticket yet."))
    if verdict not in VERDICTS:
        frappe.throw(_("The rating must be Right, Partly or Wrong."))
    root_cause = (root_cause or "").strip()
    if root_cause and root_cause not in router.CATEGORIES:
        frappe.throw(_("Unknown root cause category: {0}").format(root_cause))
    if verdict == "Wrong" and not root_cause:
        frappe.throw(_("Please choose the root cause you found."))
    if verdict == "Right":
        root_cause = run.root_cause_category
    note = (note or "").strip()[:1000]
    run.db_set(
        {
            "review_verdict": verdict,
            "reviewed_root_cause": root_cause or None,
            "review_note": note,
            "reviewed_by": frappe.session.user,
            "reviewed_at": now_datetime(),
        },
        update_modified=False,
    )
    runs.add_event(
        run,
        "review",
        {
            "verdict": verdict,
            "root_cause": root_cause,
            "note": note,
            "by": frappe.session.user,
        },
        runs.AGENT,
    )
    runs.publish_run(run)
    return get_run(ticket)


def _event_note(payload) -> str:
    try:
        data = json.loads(payload or "{}")
    except ValueError:
        return ""
    if data.get("to"):
        return f"{data.get('from') or '—'} → {data['to']}" + (
            f" ({data['note']})" if data.get("note") else ""
        )
    if data.get("stage"):
        return f"{data['stage']}: {data.get('message', '')}"[:200]
    return (data.get("note") or data.get("tool") or "")[:200]


@frappe.whitelist()
def get_resolution(ticket: str | int) -> dict:
    """For the customer portal banner: whether the ticket waits for the customer's confirmation."""
    doc = frappe.get_doc("HD Ticket", str(ticket))
    doc.check_permission("read")
    stage = doc.get("custom_copilot_stage")
    confirmation = doc.get("custom_customer_confirmation")
    run = customer.latest_run(doc.name)
    if run and run.shadow:
        # a shadow run is the team's business only
        return {
            "stage": None,
            "confirmation": confirmation,
            "message": "",
            "can_decide": False,
        }
    return {
        "stage": stage,
        "confirmation": confirmation,
        "message": _stage_message(run) if run else "",
        "can_decide": bool(
            stage == "Resolved"
            and not confirmation
            and (is_agent() or is_ticket_customer(doc))
        ),
    }


def _stage_message(run) -> str:
    rows = frappe.get_all(
        "HDS Copilot Event",
        filters={"run": run.name, "event_type": "stage"},
        fields=["payload"],
        order_by="creation desc",
        limit=1,
    )
    if not rows:
        return ""
    try:
        return json.loads(rows[0].payload or "{}").get("message", "")
    except ValueError:
        return ""


@frappe.whitelist(methods=["POST"])
def decide_resolution(
    ticket: str | int, confirmed: bool | int | str, note: str = ""
) -> dict:
    """The customer (or an agent on their behalf) says the ticket is solved, or still broken."""
    doc = frappe.get_doc("HD Ticket", str(ticket))
    doc.check_permission("read")
    agent = is_agent()
    if not (agent or is_ticket_customer(doc)):
        frappe.throw(
            _("Only the customer or our team can answer this."), frappe.PermissionError
        )
    if doc.get("custom_copilot_stage") != "Resolved" and not agent:
        frappe.throw(_("There is nothing to confirm yet on this ticket."))
    result = customer.decide_resolution(
        doc.name,
        bool(sbool(confirmed)),
        note,
        actor=runs.AGENT if agent else runs.CUSTOMER,
    )
    return {**result, "ticket": doc.name}


# --- releases (Phase 7): every merge goes out through CI, one approval and the nightly train ---


def _release(name: str):
    from helpdesk.copilot import deploy

    doc = frappe.get_doc(deploy.DEPLOY, name)
    doc.check_permission("read")
    if doc.run:
        frappe.throw(_("A Copilot fix is decided and deployed from its ticket."))
    return doc


@frappe.whitelist()
@agent_only
def get_release(release: str) -> dict:
    """What the release card shows, and what the person may do with it."""
    from helpdesk.copilot import approvals, deploy, releases

    doc = _release(release)
    user = frappe.session.user
    return {
        "name": doc.name,
        "status": doc.status,
        "hash": doc.approval_hash,
        "may_decide": doc.status == "Waiting for approval"
        and not releases.may_decide(doc, user),
        "why_not": releases.may_decide(doc, user)
        if doc.status == "Waiting for approval"
        else None,
        "may_deploy_now": deploy.may_deploy_now(user),
        "may_override_ci": doc.status == "Waiting for CI"
        and user in approvals.seniors(),
        "may_cancel": doc.status
        in ("Waiting for CI", "Waiting for approval") + deploy.WAITING
        and deploy.may_deploy(user),
    }


@frappe.whitelist(methods=["POST"])
@agent_only
def decide_release(
    release: str,
    approve: bool | int | str,
    note: str = "",
    when: str = "tonight",
    expected_hash: str | None = None,
) -> dict:
    from helpdesk.copilot import releases

    _release(release)
    return releases.decide(
        release,
        frappe.session.user,
        bool(sbool(approve)),
        note,
        when=when,
        expected_hash=expected_hash,
    )


@frappe.whitelist(methods=["POST"])
@agent_only
def override_release_ci(release: str, reason: str) -> dict:
    """A senior lets a release with red or missing CI go to its approval, with a reason."""
    from helpdesk.copilot import releases

    doc = _release(release)
    releases.override_ci(doc, frappe.session.user, reason)
    return {"status": frappe.db.get_value(doc.doctype, doc.name, "status")}


@frappe.whitelist(methods=["POST"])
@agent_only
def cancel_release(release: str, reason: str = "") -> dict:
    """A release that has not started deploying is stopped; its commits go out with the next one."""
    from helpdesk.copilot import deploy, releases

    doc = _release(release)
    user = frappe.session.user
    if doc.status not in ("Waiting for CI", "Waiting for approval") + deploy.WAITING:
        frappe.throw(
            _("Only a release that has not started deploying can be cancelled.")
        )
    if not deploy.may_deploy(user):
        frappe.throw(
            _("Only the Copilot approvers and the Agent Managers may cancel releases."),
            frappe.PermissionError,
        )
    doc.db_set({"status": "Cancelled", "finished_at": now_datetime()})
    doc.add_comment(
        "Info",
        _("Cancelled by {0}{1}").format(
            get_fullname(user), f": {reason}" if reason else ""
        ),
    )
    releases.refresh_cards(doc.name)
    return {"status": "Cancelled"}
