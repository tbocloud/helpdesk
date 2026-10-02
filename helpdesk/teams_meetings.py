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

import base64
import json
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
REQUIRED_ROLE = "Calendars.ReadWrite"


class GraphError(Exception):
    """Graph refused a call; the message is safe to show to the agent."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


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


def forget_token():
    """The next call signs in again, e.g. after a permission was granted in Entra."""
    frappe.cache.delete_value(TOKEN_CACHE_KEY.format(get_settings().connected_app))


def graph(method: str, path: str, payload: dict | None = None) -> dict:
    token = access_token()
    response = requests.request(
        method,
        GRAPH + path,
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            # event times come back in UTC, whatever the mailbox's own time zone
            "Prefer": 'outlook.timezone="UTC"',
        },
        timeout=TIMEOUT,
    )
    data = _json(response)
    if response.status_code >= 300:
        error = data.get("error") or {}
        message = _("Microsoft Teams refused the request: {0}").format(
            error.get("message") or error.get("code") or response.status_code
        )
        if response.status_code == 403:
            message += " " + access_denied_hint(token)
        raise GraphError(message, response.status_code)
    return data


def access_denied_hint(token: str) -> str:
    """Why Graph said no: the token's own permissions tell a missing grant from a mailbox policy."""
    if REQUIRED_ROLE not in token_roles(token):
        return _(
            "The Microsoft app has no {0} application permission with admin consent yet. Add it in Entra (API permissions > Microsoft Graph > Application permissions), grant admin consent, wait a few minutes and test again."
        ).format(REQUIRED_ROLE)
    return _(
        "The app has {0}, so an Exchange ApplicationAccessPolicy is keeping it out of this mailbox. Add the mailbox to the policy's group, or check it with Test-ApplicationAccessPolicy."
    ).format(REQUIRED_ROLE)


def token_roles(token: str) -> list[str]:
    """The application permissions inside a Microsoft access token (read only, not verified)."""
    try:
        claims = token.split(".")[1]
        claims += "=" * (-len(claims) % 4)
        roles = json.loads(base64.urlsafe_b64decode(claims)).get("roles")
    except (IndexError, ValueError):
        return []
    return roles if isinstance(roles, list) else []


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


def get_event(meeting) -> dict:
    """The meeting as Outlook has it now: subject, times, cancelled and the attendees' replies."""
    return graph(
        "GET",
        f"/users/{quote(meeting.organizer)}/events/{quote(meeting.external_id, safe='')}"
        "?$select=subject,start,end,isCancelled,attendees",
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


def system_time(value: dict | None):
    """A Graph {dateTime, timeZone: UTC} as a naive datetime in the system time zone."""
    if not value or not value.get("dateTime"):
        return None
    # Graph sends seven decimal places; datetime takes six
    stamp = value["dateTime"].split(".")[0]
    utc = get_datetime(stamp).replace(tzinfo=timezone.utc)
    return utc.astimezone(ZoneInfo(get_system_timezone())).replace(tzinfo=None)


def _json(response) -> dict:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
