"""Microsoft Teams meetings through Microsoft Graph.

The hub signs in as the Entra app chosen in HD Meeting Settings (client
credentials, no user sign-in), using the Connected App's client ID, secret and
token URL with the Graph scope. The app needs the Graph *application*
permission Calendars.ReadWrite with admin consent; an Exchange
ApplicationAccessPolicy should limit it to staff mailboxes.

A meeting is an Outlook calendar event with a Teams link, created in the
organizer's calendar, so Outlook sends the invitations (to customers too) and
handles their replies.
"""

from datetime import timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

import frappe
import requests
from frappe import _
from frappe.utils import get_datetime, get_system_timezone

GRAPH = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
TIMEOUT = 20
TOKEN_CACHE_KEY = "helpdesk:graph_token:{0}"
TOKEN_EARLY_REFRESH_SECONDS = 120


class GraphError(Exception):
    """Graph refused a call; the message is safe to show to the agent."""


def get_settings():
    return frappe.get_cached_doc("HD Meeting Settings")


def is_enabled() -> bool:
    settings = get_settings()
    return bool(settings.enabled and settings.connected_app)


def organizer_mailbox(user: str | None = None) -> str:
    settings = get_settings()
    if settings.organizer == "A shared mailbox" and settings.shared_mailbox:
        return settings.shared_mailbox
    return frappe.db.get_value("User", user or frappe.session.user, "email") or (
        user or frappe.session.user
    )


def access_token() -> str:
    app_name = get_settings().connected_app
    key = TOKEN_CACHE_KEY.format(app_name)
    cached = frappe.cache.get_value(key)
    if cached:
        return cached
    app = frappe.get_doc("Connected App", app_name)
    response = requests.post(
        app.token_uri,
        data={
            "grant_type": "client_credentials",
            "client_id": app.client_id,
            "client_secret": app.get_password("client_secret"),
            "scope": GRAPH_SCOPE,
        },
        timeout=TIMEOUT,
    )
    data = _json(response)
    if response.status_code >= 300 or not data.get("access_token"):
        raise GraphError(
            _("Microsoft sign-in failed: {0}").format(
                data.get("error_description")
                or data.get("error")
                or response.status_code
            )
        )
    lifetime = int(data.get("expires_in") or 3600) - TOKEN_EARLY_REFRESH_SECONDS
    frappe.cache.set_value(key, data["access_token"], expires_in_sec=max(lifetime, 60))
    return data["access_token"]


def graph(method: str, path: str, payload: dict | None = None) -> dict:
    response = requests.request(
        method,
        GRAPH + path,
        json=payload,
        headers={"Authorization": f"Bearer {access_token()}"},
        timeout=TIMEOUT,
    )
    data = _json(response)
    if response.status_code >= 300:
        error = data.get("error") or {}
        raise GraphError(
            _("Microsoft Teams refused the request: {0}").format(
                error.get("message") or error.get("code") or response.status_code
            )
        )
    return data


def event_payload(meeting) -> dict:
    """The Outlook event (with a Teams link) for an HD Meeting."""
    return {
        "subject": meeting.subject,
        "body": {"contentType": "HTML", "content": meeting.invitation_body()},
        "start": graph_time(meeting.starts_on),
        "end": graph_time(meeting.ends_on),
        "attendees": [
            {
                "emailAddress": {"address": a.email, "name": a.full_name or a.email},
                "type": "required",
            }
            for a in meeting.attendees
        ],
        "isOnlineMeeting": True,
        "onlineMeetingProvider": "teamsForBusiness",
        "allowNewTimeProposals": True,
        # makes a retried create return the same event instead of a second one
        "transactionId": meeting.name,
    }


def create_event(meeting) -> dict:
    """Creates the event; returns its Outlook ID and Teams join link."""
    data = graph(
        "POST", f"/users/{quote(meeting.organizer)}/events", event_payload(meeting)
    )
    join_url = (data.get("onlineMeeting") or {}).get("joinUrl")
    if not join_url:
        raise GraphError(
            _(
                "The meeting was created without a Teams link. Check that Teams is enabled for {0}."
            ).format(meeting.organizer)
        )
    return {"external_id": data.get("id"), "join_url": join_url}


def cancel_event(meeting, comment: str = ""):
    """Cancels the event; Outlook tells the attendees."""
    graph(
        "POST",
        f"/users/{quote(meeting.organizer)}/events/{quote(meeting.external_id, safe='')}/cancel",
        {"comment": comment},
    )


def check_connection(mailbox: str) -> dict:
    """Reads the mailbox's calendar, which needs the same permission as creating meetings."""
    data = graph("GET", f"/users/{quote(mailbox)}/calendar")
    return {"mailbox": mailbox, "calendar": data.get("name")}


def graph_time(value) -> dict:
    """A system-timezone datetime as Graph wants it: UTC, without an offset."""
    local = get_datetime(value).replace(tzinfo=ZoneInfo(get_system_timezone()))
    utc = local.astimezone(timezone.utc)
    return {"dateTime": utc.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "UTC"}


def _json(response) -> dict:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
