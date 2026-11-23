# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""What TBO sends the customer's site, sent again until it arrives (Phase 23, B2).

An agent's reply in a chat and a stage on a ticket go to the customer's site once, at the
moment they happen. A site that is down for a minute (a restart, a deploy) used to miss them
for good. Every five minutes this sends again what did not arrive in the last two days:
- chat messages from the team or Copilot's stages (`delivered` 0), through the chat's own path;
- stages on the ticket whose push failed (`pushed` false), with the same `hub_ref`.
The site keeps one of each `hub_ref`, so a repeat is harmless.
"""

import json
import time

import frappe
from frappe.utils import add_to_date, now_datetime

from helpdesk.copilot import customer, runs

MESSAGE = "HDS Conversation Message"
CONVERSATION = "HDS Conversation"
EVENT = "HDS Copilot Event"
WINDOW_DAYS = 2
SETTLE_MINUTES = 2  # a message just sent is still on its first way
BATCH = 200
BUDGET_SECONDS = 100  # per part; the scheduler kills a job after 300


LOCK = "copilot:resend-undelivered"


def resend_undelivered(now=None) -> dict:
    """Cron, every five minutes. One run at a time: the site keeps one of each `hub_ref` against
    calls one after another, not two at once."""
    cache = frappe.cache()
    lock = cache.make_key(LOCK)
    if not cache.set(
        lock, 1, ex=4 * 60, nx=True
    ):  # the site's own key (make_key) - nosemgrep
        return {"messages": 0, "stages": 0, "busy": True}
    try:
        now = now or now_datetime()
        since = add_to_date(now, days=-WINDOW_DAYS)
        before = add_to_date(now, minutes=-SETTLE_MINUTES)
        # well inside the scheduler's five-minute job timeout; stages get their own share
        deadline = time.monotonic() + BUDGET_SECONDS
        return {
            "messages": _messages(since, before, deadline),
            "stages": _stages(since, before, time.monotonic() + BUDGET_SECONDS),
        }
    finally:
        cache.delete(lock)


def _messages(since, before, deadline: float) -> int:
    """Oldest first; a site that does not answer is left for the next run after its first
    failure (one log line an hour), and connections in an outage are skipped."""
    from helpdesk.copilot import conversation
    from helpdesk.ticket_puller import _log_once, unreachable_connections

    skip = unreachable_connections()
    sent = 0
    rows = frappe.get_all(
        MESSAGE,
        filters={
            "delivered": 0,
            "creation": ["between", [since, before]],
        },
        or_filters={"direction": "Agent", "kind": "Stage"},
        fields=["name", "conversation", "kind", "creation"],
        order_by="creation asc",
        limit=BATCH,
    )
    for row in rows:
        if time.monotonic() > deadline:
            break
        if _stale_stage(row):
            continue
        try:
            doc = frappe.get_doc(CONVERSATION, row.conversation)
            if doc.connection in skip:
                continue
            if conversation._deliver(
                doc, frappe.get_doc(MESSAGE, row.name), quiet=True
            ):
                sent += 1
            elif doc.connection:
                skip.add(
                    doc.connection
                )  # down: its other messages wait for the next run
                _log_once(
                    f"Copilot chat messages not delivered to {doc.connection}",
                    f"copilot_resend:{doc.connection}",
                )
            frappe.db.commit()  # one message at a time - nosemgrep
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title=f"Copilot could not send {row.name} again")
    return sent


def _stale_stage(row) -> bool:
    """A stage line in a chat that a newer stage already followed: sending it now would put an
    old stage after the new one."""
    return row.kind == "Stage" and bool(
        frappe.db.exists(
            MESSAGE,
            {
                "conversation": row.conversation,
                "kind": "Stage",
                "creation": [">", row.creation],
            },
        )
    )


def _stages(since, before, deadline: float) -> int:
    """For each ticket only its newest stage, and only while it did not arrive: the site moves
    its ticket to whatever stage it gets, so an older one must never follow a newer one. The
    newest is looked for among every stage up to now (not only the settled ones), so a stage
    that arrived a minute ago is never followed by an older one. Nothing goes to a closed
    ticket, or one the customer confirmed."""
    from helpdesk.ticket_puller import unreachable_connections

    skip = unreachable_connections()
    newest = {}
    for event in frappe.get_all(
        EVENT,
        filters={
            "event_type": "stage",
            "actor": runs.SYSTEM,
            "creation": [">=", since],
        },
        fields=["name", "run", "payload", "creation"],
        order_by="creation desc",
        limit=BATCH * 5,
    ):
        payload = frappe.parse_json(event.payload or "{}") or {}
        if payload.get("shadow"):
            continue
        ticket = frappe.db.get_value("HDS Copilot Run", event.run, "ticket")
        if ticket and ticket not in newest:
            newest[ticket] = (event, payload)  # the first seen is the newest
    sent = 0
    for ticket, (event, payload) in newest.items():
        if time.monotonic() > deadline:
            break
        if payload.get("pushed") is not False or event.creation > before:
            continue  # arrived, or still on its first way
        status, confirmed, connection = frappe.db.get_value(
            "HD Ticket",
            ticket,
            ["status", "custom_customer_confirmation", "custom_qcs_connection"],
        ) or (None, None, None)
        if status == "Closed" or confirmed == "Confirmed" or connection in skip:
            continue
        try:
            run = frappe.get_doc("HDS Copilot Run", event.run)
            if customer._push_stage(
                run,
                payload.get("hub_ref"),
                payload.get("stage"),
                payload.get("message"),
            ):
                payload.update({"pushed": True, "redelivered": str(now_datetime())})
                frappe.db.set_value(
                    EVENT,
                    event.name,
                    "payload",
                    json.dumps(payload, ensure_ascii=False, default=str),
                    update_modified=False,
                )
                sent += 1
            elif connection:
                skip.add(connection)
            frappe.db.commit()  # one stage at a time - nosemgrep
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title=f"Copilot could not push stage {event.name} again")
    return sent
