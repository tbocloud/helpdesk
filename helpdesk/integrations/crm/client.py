"""A small REST client for the TBO CRM site, using the key and secret in HD CRM Settings."""

import json
from urllib.parse import quote

import frappe
import requests
from frappe import _

TIMEOUT = 20


class CRMError(Exception):
    """The CRM site is unreachable, refused the key, or rejected a request."""


class CRMClient:
    def __init__(self, site_url: str, api_key: str, api_secret: str):
        self.base = site_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"token {api_key}:{api_secret}",
                "Accept": "application/json",
            }
        )

    @classmethod
    def from_settings(cls) -> "CRMClient":
        settings = frappe.get_single("HD CRM Settings")
        secret = settings.get_password("api_secret", raise_exception=False)
        if not (settings.site_url and settings.api_key and secret):
            raise CRMError(_("Add the CRM site URL, API key and API secret first."))
        return cls(settings.site_url, settings.api_key, secret)

    def request(self, method: str, path: str, **kwargs):
        try:
            response = self.session.request(
                method, f"{self.base}{path}", timeout=TIMEOUT, **kwargs
            )
        except requests.RequestException as e:
            raise CRMError(_("Couldn't reach the CRM site: {0}").format(str(e))) from e
        if response.status_code == 404:
            return None
        if response.status_code in (401, 403):
            raise CRMError(
                _("The CRM site refused the API key ({0}).").format(
                    response.status_code
                )
            )
        if not response.ok:
            raise CRMError(
                _("The CRM site answered {0}: {1}").format(
                    response.status_code, error_text(response)
                )
            )
        return response.json() if response.content else {}

    def logged_user(self) -> str:
        """Who the key belongs to on the CRM site; proves the connection works."""
        data = self.request("GET", "/api/method/frappe.auth.get_logged_user") or {}
        return data.get("message") or ""

    def get_user(self, email: str) -> dict | None:
        data = self.request("GET", f"/api/resource/User/{quote(email)}")
        return (data or {}).get("data")

    def create_user(self, email: str, full_name: str, send_welcome_email: bool) -> dict:
        first, _sep, last = (full_name or email.split("@")[0]).partition(" ")
        data = self.request(
            "POST",
            "/api/resource/User",
            json={
                "email": email,
                "first_name": first,
                "last_name": last or None,
                "enabled": 1,
                "user_type": "System User",
                "send_welcome_email": 1 if send_welcome_email else 0,
            },
        )
        return (data or {}).get("data") or {}

    def enable_user(self, email: str):
        self.request("PUT", f"/api/resource/User/{quote(email)}", json={"enabled": 1})

    def add_to_crm(self, emails: list[str], role: str):
        """Give existing users a CRM role (Frappe CRM's own API, so its rules apply)."""
        self.request(
            "POST",
            "/api/method/crm.api.user.add_existing_users",
            data={"users": json.dumps(emails), "role": role},
        )


def error_text(response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    messages = body.get("_server_messages")
    if messages:
        try:
            first = json.loads(json.loads(messages)[0])
            return frappe.utils.strip_html(first.get("message", ""))[:200]
        except (ValueError, TypeError, IndexError, AttributeError):
            pass
    return str(body.get("exception") or body.get("message") or "")[:200]
