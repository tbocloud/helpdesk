"""Push notifications to the TBO Smart app, through the Expo push service.

Every new HD Notification (helpdesk.work_reminders.new_notification, mentions,
assignments) is pushed to the recipient's registered phones (HD Mobile Device)
when HD Settings → Mobile push is on. The payload carries what the app needs to
deep-link: {site, doctype, name, route, app_route, notification}.

Pushing is best effort: anything that goes wrong is logged in the Error Log and
never stops the notification itself. See docs/tbo-smart-api.md, "Push".
"""

import frappe
import requests

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
# Expo takes at most 100 messages per request
EXPO_BATCH_SIZE = 100
EXPO_TIMEOUT_SECONDS = 15
DEVICE = "HD Mobile Device"
# reactions are too small to buzz a phone; the rest is what the bell shows
PUSH_TYPES = ("Assignment", "Mention", "Reminder", "Task Completed")


def is_enabled() -> bool:
    return bool(frappe.db.get_single_value("HD Settings", "enable_mobile_push"))


def enqueue_push(notification) -> None:
    """Queue the push for a new HD Notification, after the transaction commits.

    A notice kept for the person's digest (`flags.skip_delivery`) isn't pushed: the
    digest is how it reaches them, like chat and email.
    """
    try:
        if (
            notification.notification_type not in PUSH_TYPES
            or notification.flags.skip_delivery
            or not is_enabled()
            or not expo_tokens(notification.user_to)
        ):
            return
        frappe.enqueue(
            "helpdesk.mobile_push.send_push",
            notification=notification.name,
            enqueue_after_commit=True,
            now=frappe.flags.in_test,
        )
    except Exception:
        frappe.log_error(
            title="Mobile push not queued",
            reference_doctype="HD Notification",
            reference_name=notification.name,
        )


def send_push(notification: str) -> None:
    """Background job: send one notification to each of the recipient's Expo tokens and
    drop the tokens Expo says are no longer registered."""
    try:
        doc = frappe.get_doc("HD Notification", notification)
        tokens = expo_tokens(doc.user_to)
        if not tokens:
            return
        payload = push_payload(doc)
        messages = [{"to": token, **payload} for token in tokens]
        for start in range(0, len(messages), EXPO_BATCH_SIZE):
            batch = messages[start : start + EXPO_BATCH_SIZE]
            response = requests.post(
                EXPO_PUSH_URL,
                json=batch,
                headers={"Accept": "application/json"},
                timeout=EXPO_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            drop_unregistered(batch, response.json().get("data") or [])
    except Exception:
        frappe.log_error(
            title="Mobile push failed",
            reference_doctype="HD Notification",
            reference_name=notification,
        )


def push_payload(doc) -> dict:
    """The push message without its recipient: the same title, body and links the
    app's notification list shows (helpdesk.api.mobile.notification_item)."""
    from helpdesk.api.mobile import notification_item

    item = notification_item(doc)
    return {
        "title": item["title"],
        "body": item["body"],
        "sound": "default",
        "data": {
            "site": "hub",
            "doctype": item["doctype"],
            "name": item["reference"],
            "route": item["route"],
            "app_route": item["app_route"],
            "notification": doc.name,
        },
    }


def expo_tokens(user: str) -> list[str]:
    return frappe.qb.get_query(
        DEVICE,
        fields=["token"],
        filters={"user": user, "token_type": "Expo"},
        order_by="last_seen desc",
    ).run(pluck=True)


def drop_unregistered(batch: list[dict], tickets: list[dict]) -> None:
    """Expo answers with one ticket per message, in order; an uninstalled app's token
    comes back as DeviceNotRegistered and is removed so it isn't tried again."""
    gone = [
        message["to"]
        for message, ticket in zip(batch, tickets, strict=False)
        if (ticket or {}).get("status") == "error"
        and ((ticket.get("details") or {}).get("error") == "DeviceNotRegistered")
    ]
    if gone:
        frappe.db.delete(DEVICE, {"token": ("in", gone)})
