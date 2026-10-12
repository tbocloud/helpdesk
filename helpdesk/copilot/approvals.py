# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The one approval of a Copilot fix.

An approval belongs to one pull request at one commit. It is opened when the
fix's pull request is ready for review, assigned to one approver (a senior
when the change is sensitive), decided once (the first decision wins), and
superseded when new commits arrive. Approving re-reads the pull request's head
from GitHub, so what merges is exactly what was reviewed.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, getdate, now_datetime

from helpdesk.copilot import runs
from helpdesk.copilot import settings as copilot_settings

APPROVAL = "HDS Copilot Approval"
OPEN = ("Pending", "Approved")
MANAGER = "Agent Manager"


# --- people ---------------------------------------------------------------------


def _approver_rows() -> list:
    return [
        row
        for row in copilot_settings.get_settings().get("approvers") or []
        if row.active and row.user and frappe.db.get_value("User", row.user, "enabled")
    ]


def _managers() -> list[str]:
    users = frappe.get_all(
        "Has Role", filters={"role": MANAGER, "parenttype": "User"}, pluck="parent"
    )
    return sorted(
        set(
            frappe.get_all(
                "User",
                filters={"name": ["in", users or [""]], "enabled": 1},
                pluck="name",
            )
        )
    )


def seniors() -> list[str]:
    """Senior approvers; with none in the list, the Agent Managers act as seniors."""
    listed = [row.user for row in _approver_rows() if row.senior]
    return listed or _managers()


def approvers() -> list[str]:
    return [row.user for row in _approver_rows()]


def authors(run, approval=None) -> set[str]:
    """The people who made the fix (the fix task's assignees): they never approve it.

    When Copilot alone made it (the App opened the pull request and wrote every
    commit), nobody on the task wrote it, so the customer's developer may approve.
    """
    if approval and (frappe.parse_json(approval.payload or "{}") or {}).get(
        "copilot_only"
    ):
        return set()
    if not run.task:
        return set()
    return set(
        frappe.parse_json(frappe.db.get_value("Task", run.task, "_assign") or "[]")
    )


def may_decide(approval, user: str) -> str | None:
    """Why `user` may not decide `approval`, or None when they may."""
    run = frappe.get_doc("HDS Copilot Run", approval.run)
    if user in authors(run, approval):
        return _("You made this fix, so someone else must approve it.")
    if approval.sensitive and user not in seniors():
        return _(
            "This fix changes a sensitive area; only a senior approver may approve it."
        )
    if user not in approvers() and user not in seniors() and user not in _managers():
        return _("Only the Copilot approvers and the Agent Managers may decide fixes.")
    return None


def pick_approver(
    run,
    sensitive: bool,
    exclude: set[str] | None = None,
    copilot_only: bool = False,
) -> str | None:
    """The customer's developer when they may; else the least loaded approver; else nobody."""
    excluded = (set() if copilot_only else authors(run)) | (exclude or set())
    allowed = seniors() if sensitive else list(dict.fromkeys(approvers() + seniors()))
    developer = (
        frappe.db.get_value("HD Customer", run.customer, "custom_assigned_developer")
        if run.customer
        else None
    )
    if developer and developer in allowed and developer not in excluded:
        return developer
    candidates = [user for user in allowed if user not in excluded]
    if not candidates:
        return None

    def load(user: str):
        pending = frappe.db.count(APPROVAL, {"assigned_to": user, "status": "Pending"})
        last = frappe.db.get_value(
            APPROVAL, {"assigned_to": user}, "assigned_at", order_by="assigned_at desc"
        )
        return (pending, get_datetime(last) if last else get_datetime("2000-01-01"))

    return min(candidates, key=load)


# --- opening and superseding --------------------------------------------------------


def payload_hash(payload: dict) -> str:
    keys = ("repo", "number", "head_sha", "base_branch")
    canonical = json.dumps({key: payload.get(key) for key in keys}, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def was_rejected(run, head_sha: str) -> bool:
    """A rejected commit is not asked again: the developer's next push is."""
    return bool(
        frappe.db.exists(
            APPROVAL, {"run": run.name, "head_sha": head_sha, "status": "Rejected"}
        )
    )


def current(run):
    """The run's approval that is still open (Pending or Approved), if any."""
    name = frappe.db.get_value(
        APPROVAL,
        {"run": run.name, "status": ["in", OPEN]},
        "name",
        order_by="creation desc",
    )
    return frappe.get_doc(APPROVAL, name) if name else None


def open_approval(
    run,
    pull_request: str | None,
    pull: dict,
    files: list[dict] | None,
    risk: dict,
    checks: dict | None,
    extra: dict | None = None,
):
    """A Pending approval for the pull request's head commit, assigned and announced.

    `extra` joins the payload: whether Copilot alone made the change, and what it tested.
    """
    payload = {
        "repo": pull.get("repo"),
        "number": pull.get("number"),
        "head_sha": pull.get("head_sha"),
        "base_branch": pull.get("base_branch"),
        "title": pull.get("title"),
        "url": pull.get("url"),
        "author": pull.get("author"),
        "files": [
            {
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions"),
                "deletions": f.get("deletions"),
            }
            for f in (files or [])[:100]
        ],
        "risk": risk,
        "checks": checks or {},
        **(extra or {}),
    }
    approver = pick_approver(
        run, bool(risk.get("sensitive")), copilot_only=bool(payload.get("copilot_only"))
    )
    doc = frappe.get_doc(
        {
            "doctype": APPROVAL,
            "run": run.name,
            "ticket": run.ticket,
            "status": "Pending",
            "pull_request": pull_request,
            "repo": pull.get("repo"),
            "number": pull.get("number"),
            "head_sha": pull.get("head_sha"),
            "base_branch": pull.get("base_branch"),
            "pr_url": pull.get("url"),
            "risk_level": risk.get("level") or "unknown",
            "sensitive": int(bool(risk.get("sensitive"))),
            "reasons": "\n".join(risk.get("reasons") or []),
            "payload": json.dumps(payload, indent=1),
            "payload_hash": payload_hash(payload),
            "assigned_to": approver,
            "assigned_at": now_datetime(),
        }
    ).insert(ignore_permissions=True)
    run.db_set("approval", doc.name, update_modified=False)
    runs.add_event(
        run,
        "approval_opened",
        {
            "approval": doc.name,
            "head_sha": doc.head_sha,
            "risk": doc.risk_level,
            "approver": approver,
        },
        runs.SYSTEM,
    )
    announce(
        doc, _("A Copilot fix waits for your approval on ticket {0}").format(run.ticket)
    )
    return doc


def supersede(approval, reason: str):
    if approval.status not in OPEN:
        return
    approval.db_set(
        {"status": "Superseded", "note": reason[:500]}, update_modified=False
    )
    runs.add_event(
        approval.run,
        "approval_superseded",
        {"approval": approval.name, "reason": reason},
        runs.SYSTEM,
    )


# --- deciding -----------------------------------------------------------------------


def decide(
    approval_name: str,
    user: str,
    approve: bool,
    note: str = "",
    deploy_date=None,
    via: str = "Hub",
):
    """The first decision wins. Approving checks that the pull request still has the approved commit."""
    from helpdesk.copilot import fixes

    frappe.db.get_value(APPROVAL, approval_name, "status", for_update=True)
    approval = frappe.get_doc(APPROVAL, approval_name)
    if approval.status != "Pending":
        who = (
            frappe.utils.get_fullname(approval.decided_by)
            if approval.decided_by
            else _("the hub")
        )
        frappe.throw(
            _("This fix is already {0} by {1} at {2}.").format(
                _(approval.status).lower(),
                who,
                str(approval.decided_at or approval.modified)[:16],
            )
        )
    reason = may_decide(approval, user)
    if reason:
        frappe.throw(reason, frappe.PermissionError)
    note = (note or "").strip()[:1000]
    run = frappe.get_doc("HDS Copilot Run", approval.run)

    if not approve:
        if not note:
            frappe.throw(
                _("Please say why the fix is rejected; the developer gets your reason.")
            )
        approval.db_set(
            {
                "status": "Rejected",
                "decided_by": user,
                "decided_at": now_datetime(),
                "decided_via": via,
                "note": note,
            },
            update_modified=False,
        )
        runs.add_event(
            run,
            "approval_rejected",
            {"approval": approval.name, "by": user, "note": note},
            runs.AGENT,
        )
        fixes.on_rejected(run, approval, note)
        return {"outcome": "rejected"}

    head = fixes.live_head(approval)
    if head and head != approval.head_sha:
        # not an error: raising would roll back the new approval opened for the new commits
        fixes.reopen_for_new_head(
            run, approval, _("new commits arrived before the decision")
        )
        return {
            "outcome": "superseded",
            "message": _(
                "The pull request changed after this card was made. Please review the new version."
            ),
        }
    approval.db_set(
        {
            "status": "Approved",
            "decided_by": user,
            "decided_at": now_datetime(),
            "decided_via": via,
            "note": note,
            "deploy_date": getdate(deploy_date) if deploy_date else None,
        },
        update_modified=False,
    )
    run = runs.transition(run, "Approved", runs.AGENT, note=f"approved by {user}")
    runs.add_event(
        run,
        "approval_approved",
        {"approval": approval.name, "by": user, "head_sha": approval.head_sha},
        runs.AGENT,
    )
    # the decision stands whatever the merge attempt does; the refresh retries a failed one
    frappe.db.commit()  # nosemgrep
    try:
        merge = fixes.try_merge(run)
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title=_("Copilot could not merge the approved fix of {0}").format(
                run.ticket
            )
        )
        merge = "waiting"
    return {"outcome": "approved", "merge": merge}


# --- telling people ---------------------------------------------------------------------


def announce(
    approval, subject: str, also: list[str] | None = None, escalate: bool = False
):
    """The approver (or, with none, the Agent Managers) hears it by chat or email;
    a sensitive fix or a long wait also goes to the team's channel."""
    from helpdesk.work_reminders import notify_users

    people = [approval.assigned_to] if approval.assigned_to else _managers()
    people = list(dict.fromkeys(people + (also or [])))
    notify_users(
        people,
        "HD Ticket",
        approval.ticket,
        subject,
        escalate=escalate or bool(approval.sensitive),
        once=False,
    )


def remind_and_escalate():
    """Cron: remind the approver after the reminder hours; hand to a senior or the managers after the escalation hours."""
    settings = copilot_settings.get_settings()
    remind = max(int(settings.get("approval_reminder_hours") or 4), 1)
    escalate = max(int(settings.get("approval_escalate_hours") or 24), remind)
    now = now_datetime()
    for name in frappe.get_all(APPROVAL, filters={"status": "Pending"}, pluck="name"):
        approval = frappe.get_doc(APPROVAL, name)
        if not approval.assigned_at:
            continue
        waited = (now - get_datetime(approval.assigned_at)).total_seconds() / 3600
        if waited >= escalate and not approval.escalated_at:
            run = frappe.get_doc("HDS Copilot Run", approval.run)
            exclude = {approval.assigned_to} if approval.assigned_to else set()
            successor = pick_approver(  # a senior takes over
                run,
                True,
                exclude=exclude,
                copilot_only=bool(
                    (frappe.parse_json(approval.payload or "{}") or {}).get(
                        "copilot_only"
                    )
                ),
            )
            approval.db_set(
                {"assigned_to": successor, "escalated_at": now}, update_modified=False
            )
            runs.add_event(
                run,
                "approval_escalated",
                {"approval": name, "to": successor, "hours": round(waited, 1)},
                runs.SYSTEM,
            )
            announce(
                approval,
                _(
                    "A Copilot fix on ticket {0} has waited {1} hours for approval"
                ).format(approval.ticket, int(waited)),
                also=_managers(),
                escalate=True,
            )
        elif waited >= remind and (
            not approval.reminded_at
            or (now - get_datetime(approval.reminded_at)).total_seconds() / 3600
            >= remind
        ):
            approval.db_set("reminded_at", now, update_modified=False)
            announce(
                approval,
                _(
                    "Reminder: a Copilot fix waits for your approval on ticket {0}"
                ).format(approval.ticket),
            )
        frappe.db.commit()  # one approval at a time; a failure on the next must not undo this - nosemgrep


def due_in_hours(approval) -> float:
    settings = copilot_settings.get_settings()
    hours = int(settings.get("approval_escalate_hours") or 24)
    if not approval.assigned_at:
        return float(hours)
    due = add_to_date(get_datetime(approval.assigned_at), hours=hours)
    return round((due - now_datetime()).total_seconds() / 3600, 1)
