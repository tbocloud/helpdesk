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

import frappe
from frappe.utils import add_to_date, now_datetime

from helpdesk.copilot import customer

MESSAGE = "HDS Conversation Message"
CONVERSATION = "HDS Conversation"
EVENT = "HDS Copilot Event"
WINDOW_DAYS = 2
SETTLE_MINUTES = 2  # a message just sent is still on its first way
BATCH = 200


def resend_undelivered(now=None) -> dict:
    """Cron, every five minutes."""
    now = now or now_datetime()
    since = add_to_date(now, days=-WINDOW_DAYS)
    before = add_to_date(now, minutes=-SETTLE_MINUTES)
    return {"messages": _messages(since, before), "stages": _stages(since, before)}


def _messages(since, before) -> int:
    from helpdesk.copilot import conversation

    sent = 0
    rows = frappe.get_all(
        MESSAGE,
        filters={
            "delivered": 0,
            "creation": ["between", [since, before]],
        },
        or_filters={"direction": "Agent", "kind": "Stage"},
        fields=["name", "conversation"],
        order_by="creation asc",
        limit=BATCH,
    )
    for row in rows:
        try:
            doc = frappe.get_doc(CONVERSATION, row.conversation)
            if conversation._deliver(doc, frappe.get_doc(MESSAGE, row.name)):
                sent += 1
            frappe.db.commit()  # one message at a time - nosemgrep
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title=f"Copilot could not send {row.name} again")
    return sent


def _stages(since, before) -> int:
    sent = 0
    for event in frappe.get_all(
        EVENT,
        filters={"event_type": "stage", "creation": ["between", [since, before]]},
        fields=["name", "run", "payload"],
        order_by="creation asc",
        limit=BATCH * 5,
    ):
        payload = frappe.parse_json(event.payload or "{}") or {}
        if payload.get("pushed") is not False or payload.get("shadow"):
            continue
        if payload.get("redelivered"):
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
            frappe.db.commit()  # one stage at a time - nosemgrep
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title=f"Copilot could not push stage {event.name} again")
    return sent
