# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Setting and data corrections (Phase 3): a change set, checked, approved by a senior, applied.

Copilot's report names each record with its new values. The customer's site checks
every record without saving (its `check_change` tool) and says what each holds now;
a senior approves the whole set on the ticket; the hub applies it through the
connector one record at a time (`apply_change`), signing each batch of 200, and the
site refuses a record that changed since the check. Submitted documents are never
changed in the pilot: they are set aside for a person, with the ERP way.
"""

import csv
import hashlib
import io
import json

import frappe
from frappe import _
from frappe.utils import cstr, now_datetime

from helpdesk.copilot import approval_key, runs

CHANGE_SET = "HDS Copilot Change Set"
MAX_RECORDS = 1000
BATCH = 200
SHOWN = 20  # records on the card; all of them in the CSV
KINDS = ("Config Change", "Data Fix")
KIND_FOR_CATEGORY = {
    "wrong_setting": "Config Change",
    "data_damaged_by_bug": "Data Fix",
    "customer_mistake": "Data Fix",
}
# never prepared by Copilot; the customer's site refuses them too (helpdesk_client write_guard)
NEVER = frozenset(
    {
        "User",
        "Role",
        "Has Role",
        "DocPerm",
        "Custom DocPerm",
        "User Permission",
        "Role Profile",
        "Module Profile",
        "System Settings",
        "Email Account",
        "Email Domain",
        "OAuth Client",
        "Social Login Key",
        "Connected App",
        "Token Cache",
        "Server Script",
        "Client Script",
        "Scheduled Job Type",
        "Custom Field",
        "Property Setter",
        "DocType",
        "Workflow",
        "Print Format",
        "Bulk Update",
        "Data Import",
        "HDS Support Settings",
        "HDS Change Log",
    }
)
# words in a doctype's name that put money, stock or people at stake
SENSITIVE = (
    "Account",
    "Payment",
    "Invoice",
    "Journal",
    "Ledger",
    "Stock",
    "Tax",
    "Salary",
    "Payroll",
    "Company",
    "Bank",
    "Asset",
    "Budget",
    "Fiscal",
)


def _text(value, limit: int) -> str:
    return "" if value is None else str(value)[:limit]


def _loads(value, default):
    try:
        return json.loads(value) if value else default
    except ValueError:
        return default


# --- the worker's report ---------------------------------------------------------------


def validate_report(report) -> dict | None:
    """The worker's change set, cleaned; None when it sent none. A ValidationError names a broken rule."""
    if not report:
        return None
    if not isinstance(report, dict):
        frappe.throw(_("The change set must be an object"))
    changes = report.get("changes") or []
    set_aside = report.get("set_aside") or []
    if not isinstance(changes, list) or not isinstance(set_aside, list):
        frappe.throw(_("A change set's changes and set_aside must be lists"))
    if len(changes) > MAX_RECORDS:
        frappe.throw(
            _(
                "A change set holds at most {0} records; a bigger correction is a data patch in the customer's app"
            ).format(MAX_RECORDS)
        )
    cleaned = []
    for change in changes:
        if not isinstance(change, dict):
            frappe.throw(_("Each change must be an object"))
        action = change.get("action") or "update"
        if action not in ("update", "create"):
            frappe.throw(
                _("Copilot updates or creates records, never {0}").format(action)
            )
        doctype = _text(change.get("doctype"), 140).strip()
        name = _text(change.get("name"), 140).strip()
        if not doctype or (action == "update" and not name):
            frappe.throw(_("Each change names its doctype, and the record it updates"))
        if doctype in NEVER:
            frappe.throw(_("Copilot never changes {0} records").format(doctype))
        values = change.get("values") or {}
        rows = change.get("rows") or []
        add_rows = change.get("add_rows") or []
        if (
            not isinstance(values, dict)
            or not isinstance(rows, list)
            or not isinstance(add_rows, list)
        ):
            frappe.throw(_("A change's values must be an object, its rows lists"))
        if not values and not rows and not add_rows:
            frappe.throw(
                _("{0} {1}: a change must change something").format(doctype, name)
            )
        if len(json.dumps([values, rows, add_rows], default=str)) > 20000:
            frappe.throw(_("{0} {1}: the change is too large").format(doctype, name))
        cleaned.append(
            {
                "action": action,
                "doctype": doctype,
                "name": name if action == "update" else "",
                "values": values,
                "rows": rows,
                "add_rows": add_rows,
                "why": _text(change.get("why"), 1000),
            }
        )
    aside = [
        {
            "doctype": _text(item.get("doctype"), 140),
            "name": _text(item.get("name"), 140),
            "why": _text(item.get("why"), 1000),
        }
        for item in set_aside[:200]
        if isinstance(item, dict)
    ]
    if not cleaned and not aside:
        return None
    return {
        "summary": _text(report.get("summary"), 2000),
        "customer_note": _text(report.get("customer_note"), 2000),
        "found_by": _text(report.get("found_by"), 2000),
        "changes": cleaned,
        "set_aside": aside,
    }


def prepare(run, report: dict, category: str):
    """A change set from the worker's report; the customer's site checks it in the background."""
    doc = frappe.get_doc(
        {
            "doctype": CHANGE_SET,
            "run": run.name,
            "ticket": run.ticket,
            "connection": run.connection,
            "kind": KIND_FOR_CATEGORY.get(category, "Data Fix"),
            "status": "Prepared",
            "summary": report["summary"],
            "customer_note": report["customer_note"],
            "found_by": report["found_by"],
            "set_aside": json.dumps(report["set_aside"], indent=1)
            if report["set_aside"]
            else None,
            "total": len(report["changes"]),
            "items": [
                {
                    "action": change["action"],
                    "ref_doctype": change["doctype"],
                    "ref_name": change["name"],
                    "values": json.dumps(change["values"], indent=1, default=str),
                    "rows": json.dumps(change["rows"], indent=1, default=str)
                    if change["rows"]
                    else None,
                    "add_rows": json.dumps(change["add_rows"], indent=1, default=str)
                    if change["add_rows"]
                    else None,
                    "why": change["why"],
                }
                for change in report["changes"]
            ],
        }
    )
    doc.risk_level, doc.risk_reasons = _risk(doc)
    doc.insert(ignore_permissions=True)
    run.db_set("change_set", doc.name, update_modified=False)
    runs.add_event(
        run,
        "change_set_prepared",
        {"change_set": doc.name, "kind": doc.kind, "records": doc.total},
        runs.SYSTEM,
    )
    frappe.enqueue(
        "helpdesk.copilot.changes.check_and_ask",
        queue="long",
        change_set=doc.name,
        enqueue_after_commit=True,
        now=frappe.flags.in_test,
    )
    return doc


def _risk(doc) -> tuple[str, str]:
    reasons = sorted(
        {
            _("{0} records touch money, stock or people").format(item.ref_doctype)
            for item in doc.items
            if any(word in item.ref_doctype for word in SENSITIVE)
        }
    )
    if len(doc.items) > 100:
        reasons.append(_("more than 100 records"))
    return ("high" if reasons else "medium"), "\n".join(reasons)


# --- one change, as the customer's site takes it ------------------------------------------


def change_of(item) -> dict:
    change = {
        "item": item.name,
        "action": item.action,
        "doctype": item.ref_doctype,
        "values": _loads(item.get("values"), {}),
        "rows": _loads(item.rows, []),
        "add_rows": _loads(item.add_rows, []),
    }
    if item.action == "update":
        change["name"] = item.ref_name
    return change


def expect_of(item) -> dict | None:
    """The values the approval is given for: what the site said the record held at the check."""
    if item.action != "update":
        return None
    current = _loads(item.old_values, {})
    return {"values": current.get("values") or {}, "rows": current.get("rows") or {}}


def digest_of(doc) -> str:
    """The checked content of a change set: an approval stands for exactly this."""
    content = [
        [
            item.name,
            item.action,
            item.ref_doctype,
            item.ref_name,
            change_of(item),
            expect_of(item),
            item.check_result,
        ]
        for item in doc.items
    ]
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, default=str).encode()
    ).hexdigest()


def _call(client, doc, tool: str, arguments: dict) -> tuple[dict | None, str]:
    """The site's answer as an object, or its refusal as text."""
    result = client.call_tool(tool, arguments, session_id=f"changes-{doc.name}")
    text = ((result.get("content") or [{}])[0] or {}).get("text") or ""
    if result.get("isError"):
        return None, text[:500] or _("the customer's site refused it")
    try:
        return json.loads(text), ""
    except ValueError:
        return None, _("the customer's site answered something unexpected")


# --- the check ----------------------------------------------------------------------------


def check(doc):
    """Asks the customer's site about every record: would it take the change, what does it hold now."""
    from helpdesk.mcp_client import MCPClient

    if not doc.connection:
        frappe.throw(_("The ticket has no connection to the customer's site."))
    client = MCPClient(doc.connection)
    environment = ""
    for item in doc.items:
        reply, refusal = _call(client, doc, "check_change", {"change": change_of(item)})
        item.old_values = None
        if reply is None:
            item.check_result, item.check_note = "problem", refusal
            continue
        environment = reply.get("environment") or environment
        item.old_values = json.dumps(reply.get("current") or {}, indent=1, default=str)
        if reply.get("docstatus") == 1:
            item.check_result = "set aside"
            item.check_note = _(
                "Submitted: a person corrects it (cancel and amend, or a return or credit note where e-invoicing forbids cancelling)."
            )
        elif reply.get("problems"):
            item.check_result = "problem"
            item.check_note = "; ".join(cstr(p) for p in reply["problems"])[:1000]
        else:
            item.check_result, item.check_note = "ready", ""
    doc.site_environment = environment or doc.site_environment
    doc.ready_count = sum(item.check_result == "ready" for item in doc.items)
    doc.status = "Checked"
    doc.checked_at = now_datetime()
    doc.error = None
    doc.save(ignore_permissions=True)
    return doc


def check_and_ask(change_set: str):
    """Background: the site's check, then the senior's approval when anything can be applied."""
    from helpdesk.copilot import approvals, customer

    doc = frappe.get_doc(CHANGE_SET, change_set)
    run = frappe.get_doc("HDS Copilot Run", doc.run)
    try:
        check(doc)
    except Exception as e:
        # nothing of ours was written: the check saves the change set only at its end
        doc = frappe.get_doc(CHANGE_SET, change_set)
        doc.db_set("error", str(e)[:500])
        runs.add_event(
            run, "change_set_check_failed", {"error": str(e)[:300]}, runs.SYSTEM
        )
        customer.comment(
            run.ticket,
            frappe.utils.escape_html(
                _(
                    "Copilot could not check its correction with the customer's site: {0}"
                ).format(str(e)[:300])
            ),
        )
        return
    runs.add_event(
        run,
        "change_set_checked",
        {"change_set": doc.name, "ready": doc.ready_count, "total": doc.total},
        runs.SYSTEM,
    )
    if run.shadow:
        return  # shown to the team on the card; a shadow run never changes a customer's data
    if not doc.ready_count:
        customer.comment(
            run.ticket,
            frappe.utils.escape_html(
                _(
                    "Copilot prepared a correction ({0}), but the customer's site would take none of its records; see the change set for the reasons."
                ).format(doc.name)
            ),
        )
        runs.tell_people(
            run,
            _("Copilot's correction for ticket {0} needs a person").format(run.ticket),
        )
        return
    if run.root_cause_category == "data_damaged_by_bug":
        return  # the code fix goes first; its approval carries this change set (Phase 3, H14)
    if run.state == "Preparing Fix":
        approvals.open_change_set_approval(run, doc)


# --- applying -----------------------------------------------------------------------------


def apply(change_set: str, user: str):
    """Applies an approved change set through the connector, batch by batch; stops at the first refusal."""
    from helpdesk.mcp_client import MCPClient

    doc = frappe.get_doc(CHANGE_SET, change_set)
    run = frappe.get_doc("HDS Copilot Run", doc.run)
    if doc.status not in ("Approved", "Applying"):
        return doc
    approval = frappe.get_doc("HDS Copilot Approval", doc.approval)
    doc.db_set("status", "Applying")
    if run.state == "Approved":
        run = runs.transition(
            run, "Applying", runs.SYSTEM, note="applying the approved correction"
        )
    ticket_ref = (
        frappe.db.get_value("HD Ticket", doc.ticket, "custom_client_ticket")
        or doc.ticket
    )
    pending = [
        item
        for item in doc.items
        if item.check_result == "ready" and item.apply_result in (None, "", "failed")
    ]
    stopped = ""
    client = MCPClient(doc.connection)
    for start in range(0, len(pending), BATCH):
        batch = pending[start : start + BATCH]
        token = approval_key.approval_for(
            doc.connection,
            change_set=doc.name,
            ticket=ticket_ref,
            approved_by=approval.decided_by,
            approved_at=approval.decided_at,
            records=[
                {
                    "item": item.name,
                    "doctype": item.ref_doctype,
                    "name": item.ref_name or "",
                    "action": item.action,
                    "digest": approval_key.change_digest(
                        change_of(item), expect_of(item)
                    ),
                }
                for item in batch
            ],
        )
        if (
            not token
            and doc.site_environment != "Sandbox"
            and doc.site_environment != "UAT"
        ):
            stopped = approval_key.no_key_message()
            break
        for item in batch:
            item.batch = start // BATCH + 1
            arguments = {"change": change_of(item), "approval": token}
            if item.action == "update":
                arguments["expect"] = expect_of(item)
            try:
                reply, refusal = _call(client, doc, "apply_change", arguments)
            except Exception as e:
                item.apply_result, item.apply_note = "failed", str(e)[:500]
                stopped = item.apply_note
                break
            if reply is not None:
                item.apply_result, item.apply_note = "applied", ""
                if item.action == "create":
                    item.new_name = cstr(reply.get("name"))[:140]
            elif "applied already" in refusal:
                item.apply_result = "applied"
                item.apply_note = _("applied by an earlier attempt")
            elif "changed since" in refusal:
                item.apply_result, item.apply_note = "skipped", refusal
            else:
                item.apply_result, item.apply_note = "refused", refusal
                stopped = refusal
                break
        if stopped:
            break
    _finish(doc, run, user, stopped)
    return doc


def _counts(doc):
    doc.ready_count = sum(item.check_result == "ready" for item in doc.items)
    doc.applied_count = sum(item.apply_result == "applied" for item in doc.items)
    doc.skipped_count = sum(item.apply_result == "skipped" for item in doc.items)
    doc.refused_count = sum(
        item.apply_result in ("refused", "failed") for item in doc.items
    )


def _finish(doc, run, user: str, stopped: str):
    from helpdesk.copilot import customer

    _counts(doc)
    doc.applied_by, doc.applied_at = user, now_datetime()
    doc.status = "Stopped" if stopped else "Applied"
    doc.error = stopped[:500] if stopped else None
    doc.save(ignore_permissions=True)
    summary = {
        "change_set": doc.name,
        "applied": doc.applied_count,
        "skipped": doc.skipped_count,
        "refused": doc.refused_count,
    }
    if stopped:
        runs.add_event(
            run, "change_set_stopped", {**summary, "reason": stopped[:300]}, runs.SYSTEM
        )
        if run.state == "Applying":
            runs.transition(
                run,
                "Escalated",
                runs.SYSTEM,
                note=f"the correction stopped: {stopped}"[:140],
            )
        customer.comment(
            run.ticket,
            frappe.utils.escape_html(
                _(
                    "Copilot's correction {0} stopped after {1} records: {2}. The records not applied are as they were."
                ).format(doc.name, doc.applied_count, stopped[:300])
            ),
        )
        runs.tell_people(
            run, _("Copilot's correction for ticket {0} stopped").format(run.ticket)
        )
        return
    runs.add_event(run, "change_set_applied", summary, runs.SYSTEM)
    customer.comment(
        run.ticket,
        frappe.utils.escape_html(
            _(
                "Copilot's correction {0} is applied: {1} records changed, {2} left as people had changed them since."
            ).format(doc.name, doc.applied_count, doc.skipped_count)
        ),
    )
    if run.state == "Applying":
        run = runs.transition(
            run,
            "Resolved",
            runs.SYSTEM,
            note="the correction is applied",
            deployed_at=now_datetime(),
            deployed_by=user,
        )
        customer.send_stage(
            run,
            "Resolved",
            {"resolution": doc.customer_note or _("We corrected it on your site.")},
        )


def applied_by_hand(change_set: str, user: str):
    """A senior applied the records by hand: that is their approval; the site is read again and each record compared."""
    from helpdesk.copilot import approvals
    from helpdesk.mcp_client import MCPClient

    doc = frappe.get_doc(CHANGE_SET, change_set)
    run = frappe.get_doc("HDS Copilot Run", doc.run)
    approval = approvals.current(run)
    if not approval or approval.change_set != doc.name or approval.status != "Pending":
        frappe.throw(
            _(
                "Only a correction waiting for its approval can be marked applied by hand."
            )
        )
    reason = approvals.may_decide(approval, user)
    if reason:
        frappe.throw(reason, frappe.PermissionError)
    approval.db_set(
        {
            "status": "Approved",
            "decided_by": user,
            "decided_at": now_datetime(),
            "decided_via": "By hand",
            "note": _("applied by hand"),
        },
        update_modified=False,
    )
    doc.db_set("status", "Applying")
    run = runs.transition(
        run, "Approved", runs.AGENT, note=f"applied by hand by {user}"
    )
    runs.add_event(
        run,
        "approval_approved",
        {"approval": approval.name, "by": user, "by_hand": True},
        runs.AGENT,
    )
    run = runs.transition(
        run, "Applying", runs.SYSTEM, note="reading back what was applied by hand"
    )
    client = MCPClient(doc.connection)
    missing = 0
    for item in doc.items:
        if item.check_result != "ready" or item.apply_result == "applied":
            continue
        if item.action == "create":
            item.apply_result, item.apply_note = "applied", _("by hand (not read back)")
            continue
        reply, refusal = _call(client, doc, "check_change", {"change": change_of(item)})
        if reply is not None and _holds(reply.get("current") or {}, change_of(item)):
            item.apply_result, item.apply_note = "applied", _("by hand")
        else:
            missing += 1
            item.apply_result = "skipped"
            item.apply_note = refusal or _("not found as approved")
    stopped = (
        _("{0} records were not found as approved").format(missing) if missing else ""
    )
    _finish(doc, run, user, stopped)
    return doc


def _holds(current: dict, change: dict) -> bool:
    """Whether the record now holds the change's new values."""
    values = current.get("values") or {}
    rows = current.get("rows") or {}
    return all(
        cstr(values.get(field)) == cstr(value)
        for field, value in change["values"].items()
    ) and all(
        cstr((rows.get(row.get("name")) or {}).get(field)) == cstr(value)
        for row in change["rows"]
        for field, value in (row.get("values") or {}).items()
    )


# --- what people see ----------------------------------------------------------------------


def _changes(item) -> list[dict]:
    old = (_loads(item.old_values, {}) or {}).get("values") or {}
    rows_old = (_loads(item.old_values, {}) or {}).get("rows") or {}
    shown = [
        {"field": field, "old": cstr(old.get(field)), "new": cstr(value)}
        for field, value in (_loads(item.get("values"), {}) or {}).items()
    ]
    for row in _loads(item.rows, []) or []:
        for field, value in (row.get("values") or {}).items():
            shown.append(
                {
                    "field": f"{row.get('table')}.{field} ({row.get('name')})",
                    "old": cstr((rows_old.get(row.get("name")) or {}).get(field)),
                    "new": cstr(value),
                }
            )
    for row in _loads(item.add_rows, []) or []:
        shown.append(
            {
                "field": _("new row in {0}").format(row.get("table")),
                "old": "",
                "new": json.dumps(row.get("values") or {}, default=str)[:200],
            }
        )
    return shown


def card(doc) -> dict:
    return {
        "name": doc.name,
        "kind": doc.kind,
        "status": doc.status,
        "risk": doc.risk_level,
        "risk_reasons": [r for r in (doc.risk_reasons or "").split("\n") if r],
        "summary": doc.summary,
        "customer_note": doc.customer_note,
        "found_by": doc.found_by,
        "environment": doc.site_environment,
        "total": doc.total,
        "ready": doc.ready_count,
        "applied": doc.applied_count,
        "skipped": doc.skipped_count,
        "refused": doc.refused_count,
        "error": doc.error,
        "set_aside": (_loads(doc.set_aside, []) or [])[:SHOWN]
        + [
            {"doctype": item.ref_doctype, "name": item.ref_name, "why": item.check_note}
            for item in doc.items
            if item.check_result == "set aside"
        ][:SHOWN],
        "records": [
            {
                "doctype": item.ref_doctype,
                "name": item.ref_name or _("(new)"),
                "action": item.action,
                "changes": _changes(item),
                "check": item.check_result,
                "applied": item.apply_result,
                "note": item.apply_note or item.check_note,
            }
            for item in doc.items[:SHOWN]
        ],
        "more": max(len(doc.items) - SHOWN, 0),
        "csv_url": "/api/method/helpdesk.api.copilot.download_change_set?change_set="
        + doc.name,
    }


def as_csv(doc) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "DocType",
            "Record",
            "Action",
            "Field",
            "Old value",
            "New value",
            "Check",
            "Check note",
            "Applied",
            "Apply note",
            "Why",
        ]
    )
    for item in doc.items:
        for change in _changes(item) or [{"field": "", "old": "", "new": ""}]:
            writer.writerow(
                [
                    item.ref_doctype,
                    item.ref_name or item.new_name or "",
                    item.action,
                    change["field"],
                    change["old"],
                    change["new"],
                    item.check_result or "",
                    item.check_note or "",
                    item.apply_result or "",
                    item.apply_note or "",
                    item.why or "",
                ]
            )
    return out.getvalue()
