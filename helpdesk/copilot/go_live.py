# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Going live from a task (Phase 22), and deploy notices.

A merge into a branch a customer site runs becomes a release (releases.py): CI must pass, one
person who wrote none of it approves, and Press deploys it tonight or now (deploy.py). Here:

- `task_release`: where a task's change stands (waiting for CI, waiting for approval, going
  live tonight, live), for the desktop app after the person completes the task.
- `ask_go_live`: the person asks for their task's release to go live, tonight or now. The
  release's approver gets its card again with the request; they still decide, and nobody
  approves their own change.
- `alert_deploy`: when Press starts a deploy, it goes live, or it fails, Copilot People's Deploy
  Notices (else the Infrastructure people, else a Leader) hear it in Teams and TBO Support. Every Press
  deploy: releases, Copilot's own fixes and Deploy Now. Nobody is named in the code.
"""

import frappe
from frappe import _
from frappe.utils import get_fullname, get_url

from helpdesk.copilot import people

DEPLOY = "HDS Deploy Request"
WAITING = ("Waiting for CI", "Staging", "Waiting for approval")
ON_ITS_WAY = ("Scheduled", "Waiting for Press", "Deploying", "Checking")
WHEN = ("tonight", "now")


def _releases(task: str) -> list:
    """The task's releases and fix deploys, newest first."""
    # never a release's staging copy (a UAT deploy carries the task too): the release itself
    names = frappe.get_all(
        DEPLOY,
        filters={"task": task, "staging_for": ["is", "not set"]},
        pluck="name",
        order_by="creation desc",
        limit=5,
    )
    runs = frappe.get_all("HDS Copilot Run", filters={"task": task}, pluck="name")
    if runs:
        names += [
            n
            for n in frappe.get_all(
                DEPLOY,
                filters={"run": ["in", runs], "staging_for": ["is", "not set"]},
                pluck="name",
                order_by="creation desc",
                limit=5,
            )
            if n not in names
        ]
    return [frappe.get_doc(DEPLOY, n) for n in names]


def _next_step(doc) -> str:
    if doc.status == "Waiting for CI":
        return _("CI has not passed yet ({0}); then an approver is asked.").format(
            doc.ci_status or _("not reported")
        )
    if doc.status == "Staging":
        return _("It is being checked on the staging site first.")
    if doc.status == "Waiting for approval":
        return _("It waits for {0}'s approval.").format(
            get_fullname(doc.assigned_to) if doc.assigned_to else _("an approver")
        )
    if doc.status == "Scheduled":
        return _("Approved: Press deploys it {0}.").format(
            _("now")
            if doc.when == "Now"
            else _("tonight ({0})").format(str(doc.scheduled_for or "")[:16])
        )
    if doc.status in ("Waiting for Press", "Deploying", "Checking"):
        return _("Press is deploying it.")
    if doc.status == "Succeeded":
        return _("It is live.")
    return _("It ended as {0}.").format(doc.status)


def _row(doc) -> dict:
    return {
        "release": doc.name,
        "status": doc.status,
        "ci": doc.ci_status or None,
        "repository": doc.repository,
        "branch": doc.branch,
        "bench_group": doc.release_group,
        "approver": get_fullname(doc.assigned_to) if doc.assigned_to else None,
        "approved_by": get_fullname(doc.decided_by) if doc.decided_by else None,
        "when": doc.when or None,
        "scheduled_for": str(doc.scheduled_for)[:16] if doc.scheduled_for else None,
        "next": _next_step(doc),
    }


def task_release(task: str) -> dict:
    """Where the task's change stands on its way to the customer's sites."""
    task = str(task)
    frappe.has_permission("Task", "read", task, throw=True)
    rows = [_row(doc) for doc in _releases(task)]
    if not rows:
        return {
            "task": task,
            "releases": [],
            "next": _(
                "No release yet. TBO Support makes one within ten minutes of the merge into the branch the customer's site runs."
            ),
        }
    return {"task": task, "releases": rows, "next": rows[0]["next"]}


def ask_go_live(task: str, when: str = "tonight", note: str = "") -> dict:
    """The person asks for their task's release to go live; its approver decides."""
    from helpdesk.copilot import releases

    task = str(task)
    frappe.has_permission("Task", "write", task, throw=True)
    when = str(when or "tonight").strip().lower()
    if when not in WHEN:
        frappe.throw(_("Say tonight or now."))
    note = str(note or "").strip()[:500]
    from helpdesk.copilot import pulls

    # Phase 26: the task's pull request is still open: Copilot takes it live
    if pulls.enabled():
        taken = pulls.take(task, frappe.session.user, when, note)
        if taken is not None:
            return taken
    found = _releases(task)
    if not found:
        return task_release(task)
    doc = found[0]
    if doc.status != "Waiting for approval":
        return {"task": task, "asked": False, **_row(doc)}
    user = frappe.session.user
    approver = doc.assigned_to
    if not approver:
        approver = releases.pick_approver(bool(doc.needs_senior), releases.authors(doc))
        if not approver:
            frappe.throw(
                _(
                    "Nobody who may approve this release is set in Copilot People; ask a Leader."
                )
            )
        doc.db_set(
            {"assigned_to": approver, "assigned_at": frappe.utils.now_datetime()}
        )
    wish = _("now") if when == "now" else _("tonight")
    subject = _("{0} asks for {1} {2} to go live {3}").format(
        get_fullname(user), doc.repository, doc.branch, wish
    )
    doc.add_comment(
        "Comment",
        frappe.utils.escape_html(f"{subject}" + (f": {note}" if note else "")),
    )
    # one notice, and the request and its note on the approver's card (Phase 23, A10)
    releases.announce(
        doc, approver, ask=(subject, _("Their note: {0}").format(note) if note else "")
    )
    return {
        "task": task,
        "asked": True,
        **_row(doc),
        "next": _(
            "{0} has the release's card again with your request. They decide; nobody approves their own change."
        ).format(get_fullname(approver)),
    }


# --- deploy notices ------------------------------------------------------------------------


def deploy_people() -> list[str]:
    """Copilot People → Deploy Notices (e.g. DevOps and a senior), else the Infrastructure people,
    else a Leader."""
    return people.notice_people(people.DEPLOY)


def alert_deploy(request: str, stage: str, detail: str = "", also=()):
    """Queued: a deploy's start, its going live, or its failure, to the deploy notice people.
    `also`: the other requests that went out in the same Press deploy. Never slows or stops the
    deploy."""
    try:
        if not deploy_people():
            return
        frappe.enqueue(
            "helpdesk.copilot.go_live.send_deploy_notice",
            queue="short",
            request=request,
            stage=stage,
            detail=str(detail or "")[:500],
            also=list(also or []),
            enqueue_after_commit=True,
            now=frappe.flags.in_test,
        )
    except Exception:
        frappe.log_error(
            title=f"Copilot could not queue the deploy notice of {request}"
        )


STAGES = {
    "started": "Press is deploying {what} on {group}",
    "live": "Live: {what} on {group}",
    "failed": "Deploy failed: {what} on {group}",
}


def _what(doc) -> str:
    if doc.repository:
        return f"{doc.repository} {doc.branch}"
    return _("the fix of ticket {0}").format(doc.ticket) if doc.ticket else doc.name


def send_deploy_notice(
    request: str, stage: str, detail: str = "", also=()
) -> list[str]:
    from helpdesk.copilot import assistant

    try:
        doc = frappe.get_doc(DEPLOY, request)
        others = [frappe.get_doc(DEPLOY, name) for name in also or []]
        what = ", ".join([_what(doc)] + [_what(o) for o in others])
        title = _(STAGES[stage]).format(
            what=what, group=doc.release_group or _("its bench")
        )
        sites = sorted(
            {row.site for d in [doc, *others] for row in (d.get("sites") or [])}
        )
        lines = [
            _("Sites: {0}").format(", ".join(sites)) if sites else "",
            _("Approved by {0}").format(get_fullname(doc.decided_by))
            if doc.decided_by
            else "",
            _("Task {0}").format(doc.task) if doc.get("task") else "",
            _("Ticket {0}").format(doc.ticket) if doc.ticket else "",
            detail,
        ]
        reply = assistant.card(
            title,
            [line for line in lines if line],
            links=[
                (_("Open the ticket"), get_url(f"/helpdesk/tickets/{doc.ticket}"))
                if doc.ticket
                else (_("Open the Copilot board"), get_url("/helpdesk/copilot"))
            ],
            tone={"live": "good", "failed": "warning"}.get(stage, "default"),
        )
        return people.deliver(deploy_people(), reply, title, doc.ticket)
    except Exception:
        frappe.log_error(title=f"Copilot could not send the deploy notice of {request}")
        return []
