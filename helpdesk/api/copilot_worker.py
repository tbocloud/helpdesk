# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The worker API: a Copilot worker claims runs, keeps them alive, reports events and results.

Callers hold the role Copilot Worker (API only, created on migrate). Every call
after a claim carries the lease token, so only the worker that holds a run
can report on it.
"""

import json
import re

import frappe
from frappe import _

from helpdesk.copilot import fixes, router, runs

WORKER_ROLE = "Copilot Worker"


def ensure_role():
    """Created on migrate; API-only, so no desk access."""
    if frappe.db.exists("Role", WORKER_ROLE):
        return
    frappe.get_doc(
        {"doctype": "Role", "role_name": WORKER_ROLE, "desk_access": 0}
    ).insert(ignore_permissions=True)


def worker_only():
    # frappe.only_for is a no-op in tests, so the role is checked directly
    if WORKER_ROLE not in frappe.get_roles():
        frappe.throw(_("Only a Copilot worker may call this."), frappe.PermissionError)


def _parse(value, what: str):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            frappe.throw(_("{0} must be JSON").format(what))
    return value


@frappe.whitelist(methods=["POST"])
def claim_job(
    worker_id: str, free_slots: int = 1, capabilities: str = "", run: str | None = None
) -> dict:
    """The oldest queued run (or `run`, if it is queued) with its lease token and context, or {}."""
    worker_only()
    worker_id = (worker_id or "").strip()[:140]
    if not worker_id:
        frappe.throw(_("worker_id is required"))
    from helpdesk.copilot import board

    board.worker_seen(worker_id)  # the Copilot board shows when each worker last asked
    if int(free_slots) < 1:
        return {}
    from helpdesk.copilot import pilot
    from helpdesk.copilot import settings as copilot_settings

    if not copilot_settings.is_enabled():
        return (
            {}
        )  # switched off: no work goes out, and a worker mid-run is stopped at its heartbeat
    if not pilot.budget_allows_work():
        return (
            {}
        )  # the month's AI budget is used up: work waits (the managers were told)
    run, token = runs.claim(worker_id, capabilities or "", (run or "").strip() or None)
    if run:
        from helpdesk.copilot import registry

        # the code the site runs now, not what its card last saw (a deploy from Press's dashboard)
        registry.refresh_for_run(run)
    if not run:
        offered = re.split(r"[\s,]+", (capabilities or "").lower())
        if "pr_fix" in offered:
            from helpdesk.copilot import pulls

            job = pulls.claim(
                worker_id
            )  # a round on a developer's pull request (Phase 26)
            if job:
                return job
        if "release_check" in offered:
            from helpdesk.copilot import releases

            return releases.claim_check(worker_id)  # a release's sandbox check, or {}
        return {}
    return {
        "run": run.name,
        "lease_token": token,
        "lease_expires": str(run.lease_expires),
        "context": runs.run_context(run),
    }


@frappe.whitelist(methods=["POST"])
def release_check_result(
    release: str, lease_token: str, evidence: list | str, tested_on: str = ""
) -> dict:
    """A release's sandbox check (Phase 7, W11): `[{check, result: pass|fail|not_run, detail}]`."""
    from helpdesk.copilot import releases

    worker_only()
    return releases.check_result(
        release, lease_token, _parse(evidence, "evidence"), tested_on or ""
    )


@frappe.whitelist(methods=["POST"])
def repo_token(run: str, lease_token: str, repository: str) -> dict:
    """A one-hour key to clone and push the fix's branch to one of the run's site repositories."""
    worker_only()
    doc = runs.check_lease(run, lease_token)
    if not runs.fixing(doc):
        frappe.throw(_("Only a fix job gets a push key."), frappe.PermissionError)
    return fixes.push_key(doc, repository)


# what a worker may download from a ticket: pictures and videos of the problem (Phase 6, W9)
TICKET_FILE_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "mp4": "video/mp4",
    "webm": "video/webm",
    "mov": "video/quicktime",
    "mkv": "video/x-matroska",
}
TICKET_FILE_MAX_BYTES = 50 * 1024 * 1024


@frappe.whitelist(methods=["POST"])
def ticket_file(run: str, lease_token: str, file_url: str):
    """One picture or video attached to the run's ticket, as bytes, while the lease holds."""
    from werkzeug.wrappers import Response

    worker_only()
    doc = runs.check_lease(run, lease_token)
    name = frappe.db.get_value(
        "File",
        {
            "file_url": file_url,
            "attached_to_doctype": "HD Ticket",
            "attached_to_name": doc.ticket,
        },
        "name",
    )
    if not name:
        frappe.throw(
            _("That file is not on this run's ticket."), frappe.PermissionError
        )
    file = frappe.get_doc("File", name)
    kind = TICKET_FILE_TYPES.get((file.file_name or "").rsplit(".", 1)[-1].lower())
    if not kind:
        frappe.throw(_("Only pictures and videos are given to the worker."))
    if (file.file_size or 0) > TICKET_FILE_MAX_BYTES:
        frappe.throw(_("The file is larger than 50 MB."))
    content = file.get_content()
    if isinstance(content, str):
        content = content.encode()
    runs.add_event(
        doc, "file_read", {"file": file.file_name, "bytes": len(content)}, runs.WORKER
    )
    return Response(content, status=200, content_type=kind)


@frappe.whitelist(methods=["POST"])
def heartbeat(run: str, lease_token: str, stage: str = "") -> dict:
    """Keeps the lease; the answer says `continue` or `cancel`."""
    worker_only()
    answer = runs.heartbeat(run, lease_token)
    if stage and answer.get("action") == "continue":
        runs.add_event(run, "progress", {"stage": stage[:140]}, runs.WORKER)
    return answer


@frappe.whitelist(methods=["POST"])
def post_events(run: str, lease_token: str, events: list | str) -> dict:
    """Stores the worker's events `{seq, type, payload}`; a repeated seq is ignored."""
    worker_only()
    doc = runs.check_lease(run, lease_token)
    acked = []
    for event in _parse(events, "events") or []:
        if not isinstance(event, dict) or "seq" not in event:
            frappe.throw(_("Each event needs a seq"))
        seq = int(event["seq"])
        runs.add_event(
            doc,
            runs.worker_event_type(event.get("type")),
            event.get("payload") or {},
            runs.WORKER,
            seq=seq,
        )
        acked.append(seq)
    return {"acked": acked}


@frappe.whitelist(methods=["POST"])
def submit_result(run: str, lease_token: str, result: dict | str) -> dict:
    """An investigation (`kind: investigation`) is routed; a failure (`kind: failure`) fails the run."""
    worker_only()
    doc = runs.check_lease(run, lease_token)
    result = _parse(result, "result") or {}
    kind = result.get("kind")
    if runs.fixing(doc):
        # a fix job ends with submit_change (the MCP tool), or with this failure
        if kind != "failure":
            frappe.throw(_("A fix job reports its change with submit_change."))
        fixes.fix_failed(doc, str(result.get("reason") or ""))
        doc.reload()
        return {"run": doc.name, "state": doc.state, "fix": doc.fix_status}
    if kind == "investigation":
        if doc.get("kind") == runs.INFRA:
            frappe.throw(
                _("An infrastructure run reports with submit_infra_investigation.")
            )
        doc = router.route(doc, result)
    elif kind == "failure":
        reason = str(result.get("reason") or "")[:2000]
        doc = runs.transition(
            doc, "Failed", runs.WORKER, note="worker failed", failure_reason=reason
        )
        runs.tell_people(
            doc,
            _("Copilot could not investigate ticket {0}: {1}").format(
                doc.ticket, reason[:200]
            ),
        )
    else:
        frappe.throw(_("Unknown result kind: {0}").format(kind))
    return {"run": doc.name, "state": doc.state, "root_cause": doc.root_cause_category}


# --- a developer's pull request Copilot takes live (Phase 26, helpdesk.copilot.pulls) ------------


@frappe.whitelist(methods=["POST"])
def pr_heartbeat(pull_request: str, lease_token: str) -> dict:
    worker_only()
    from helpdesk.copilot import pulls

    return pulls.heartbeat(pull_request, lease_token)


@frappe.whitelist(methods=["POST"])
def pr_push_key(pull_request: str, lease_token: str) -> dict:
    worker_only()
    from helpdesk.copilot import pulls

    return pulls.push_key(pull_request, lease_token)


@frappe.whitelist(methods=["POST"])
def pr_result(pull_request: str, lease_token: str, result: dict | str) -> dict:
    worker_only()
    from helpdesk.copilot import pulls

    return pulls.result(pull_request, lease_token, _parse(result, "result") or {})


OPEN_EVAL_REQUEST = ("Queued", "Running")


@frappe.whitelist(methods=["POST"])
def report_eval(
    model: str,
    results: list | str,
    job: str = "investigate",
    request: str | None = None,
) -> dict:
    """A run of the test set, from the worker (Phase 31): scores per case number only. It
    answers the request it names, or else the model's open request for the same job."""
    from helpdesk import ai_engine, ai_models

    worker_only()
    model = str(model or "").strip()
    # the job as store_eval keeps it
    job = job if job in ai_engine.JOBS else "investigate"
    # locked while it is checked and answered: two copies of one report never both store a run
    named = request and frappe.db.get_value(
        ai_models.EVAL_REQUEST,
        request,
        ["name", "model", "job", "status", "eval_run"],
        as_dict=True,
        for_update=True,
    )
    if named and (named.model, named.job) != (model, job):
        frappe.throw(
            _("Request {0} is for {1} ({2}), not this report's model and job.").format(
                named.name, named.model, named.job
            )
        )
    if (
        named
        and named.status == "Done"
        and named.eval_run
        and frappe.db.get_value(ai_models.EVAL_RUN, named.eval_run, "source")
        == "Worker"
    ):
        # the worker's own report sent again (its answer was lost on the way): nothing is
        # stored twice; a request a manager's import answered still takes the worker's run
        return {"eval_run": named.eval_run}
    name = ai_models.store_eval(model, frappe.parse_json(results), job=job)
    if request:
        # only the request it names, while it waits or after it was given up for taking too
        # long (a late report still answers it); a report sent again answers nothing
        late = named and named.status == "Failed" and not named.eval_run
        waiting = named and named.status in OPEN_EVAL_REQUEST
        # a manager's import answered it first: the worker's own run takes its place, so a
        # copy of this report sent again is recognised
        replaced = (
            named
            and named.status == "Done"
            and named.eval_run
            and frappe.db.get_value(ai_models.EVAL_RUN, named.eval_run, "source")
            == "Imported"
        )
        answered = [named.name] if waiting or late or replaced else []
    else:
        answered = frappe.get_all(
            ai_models.EVAL_REQUEST,
            filters={
                "model": model,
                "job": job,
                "status": ["in", list(OPEN_EVAL_REQUEST)],
            },
            pluck="name",
        )
    for open_request in answered:
        frappe.db.set_value(
            ai_models.EVAL_REQUEST, open_request, {"status": "Done", "eval_run": name}
        )
    return {"eval_run": name}


# a test-set run a worker claimed and never reported (it stopped, or lost the file): after this
# long the request is Failed with a note, and a manager can ask for a run again
EVAL_RUN_HOURS = 24


def give_up_stale_eval_requests() -> int:
    """Running test-set requests with no report for EVAL_RUN_HOURS become Failed. A late report
    for one still answers it (report_eval accepts a Failed request that names it)."""
    from frappe.utils import add_to_date, now_datetime

    from helpdesk import ai_models

    cutoff = add_to_date(now_datetime(), hours=-EVAL_RUN_HOURS)
    stale = frappe.get_all(
        ai_models.EVAL_REQUEST,
        filters={"status": "Running", "modified": ["<", cutoff]},
        pluck="name",
    )
    if not stale:
        return 0
    # one update that touches only requests still Running and still stale: a report that
    # came in meanwhile (Done) is never turned into Failed
    request = frappe.qb.DocType(ai_models.EVAL_REQUEST)
    (
        frappe.qb.update(request)
        .set(request.status, "Failed")
        .set(
            request.error,
            _("No report came back within {0} hours. Ask for a run again.").format(
                EVAL_RUN_HOURS
            ),
        )
        .set(request.modified, now_datetime())
        .where(request.name.isin(stale))
        .where(request.status == "Running")
        .where(request.modified < cutoff)
    ).run()
    return len(stale)


@frappe.whitelist(methods=["POST"])
def claim_eval_request() -> dict | None:
    """The oldest waiting request to run the test set on a model, marked Running; None when
    there is none. The worker asks only when it has no ticket work."""
    from helpdesk import ai_models

    worker_only()
    give_up_stale_eval_requests()
    # a locking read that passes over a request another worker is claiming: no two workers
    # get the same one
    name = frappe.db.get_value(
        ai_models.EVAL_REQUEST,
        {"status": "Queued"},
        "name",
        order_by="creation asc",
        for_update=True,
        skip_locked=True,
    )
    if not name:
        return None
    frappe.db.set_value(ai_models.EVAL_REQUEST, name, "status", "Running")
    return frappe.db.get_value(
        ai_models.EVAL_REQUEST, name, ["name", "model", "job"], as_dict=True
    )
