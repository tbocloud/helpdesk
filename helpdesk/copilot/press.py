# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""TBO's Press, as Copilot uses it to deploy a merged fix.

A typed client over Press's own API, signed in as Copilot's Press user (HDS
Copilot Settings). Every refusal is raised as PressError with Press's own
message, so a person reading the run sees exactly what Press said.
"""

import json

import frappe
import requests
from frappe import _

TIMEOUT = 30


class PressError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"Press {status}: {message}" if status else message)
        self.status = status
        self.message = message


def _settings():
    from helpdesk.copilot import settings as copilot_settings

    return copilot_settings.get_settings()


def _secret() -> str | None:
    from frappe.utils.password import get_decrypted_password

    return get_decrypted_password(
        "HDS Copilot Settings",
        "HDS Copilot Settings",
        "press_api_secret",
        raise_exception=False,
    )


def configured() -> bool:
    settings = _settings()
    return bool(
        (settings.get("press_url") or "").strip()
        and (settings.get("press_api_key") or "").strip()
        and _secret()
    )


def press_message(body, fallback: str = "") -> str:
    """The readable part of a Frappe error body: the first server message, else the exception's last line."""
    if not isinstance(body, dict):
        return fallback
    try:
        first = json.loads(json.loads(body.get("_server_messages") or "[]")[0])
        if first.get("message"):
            return frappe.utils.strip_html(str(first["message"]))[:300]
    except (ValueError, IndexError, TypeError, AttributeError):
        pass
    exception = body.get("exception") or body.get("exc_type") or ""
    return str(exception).strip().split("\n")[-1][:300] or fallback


def call(method: str, **args):
    """One whitelisted Press method; its `message`, or PressError."""
    settings = _settings()
    url = (settings.get("press_url") or "").strip().rstrip("/")
    key = (settings.get("press_api_key") or "").strip()
    secret = _secret()
    if not (url and key and secret):
        raise PressError(0, _("Press is not set up in HDS Copilot Settings."))
    if not url.lower().startswith("https://"):
        # the key travels in a header, so never in clear text
        raise PressError(0, _("The Press URL must start with https://."))
    headers = {"Authorization": f"token {key}:{secret}", "Accept": "application/json"}
    if team := (settings.get("press_team") or "").strip():
        headers["X-Press-Team"] = team
    try:
        response = requests.post(
            f"{url}/api/method/{method}",
            json=args,
            headers=headers,
            timeout=TIMEOUT,
            # a redirect would carry the key to another address
            allow_redirects=False,
        )
    except requests.RequestException as e:
        raise PressError(
            0, _("Press could not be reached: {0}").format(str(e)[:200])
        ) from e
    try:
        body = response.json()
    except ValueError:
        body = {}
    if 300 <= response.status_code < 400:
        raise PressError(
            response.status_code,
            _(
                "Press answered with a redirect, which Copilot does not follow: {0}"
            ).format(str(response.headers.get("Location") or "")[:200]),
        )
    if response.status_code >= 400:
        raise PressError(response.status_code, press_message(body, response.text[:300]))
    return body.get("message") if isinstance(body, dict) else None


def deploy_information(group: str) -> dict:
    """The bench's apps (current and next commit), its sites, and whether a deploy is running."""
    return call("press.api.bench.deploy_information", name=group) or {}


def app_commits(row: dict) -> tuple[str, str]:
    """The commit a bench app runs and the one a deploy would bring, from one app of
    `deploy_information`: Press shows them as `current_hash` and the hash of the release
    named `next_release` among `releases` (newest first). Empty when Press has none."""
    current = row.get("current_hash") or row.get("hash") or ""
    following = row.get("next_hash") or ""
    if not following:
        releases = [r for r in row.get("releases") or [] if isinstance(r, dict)]
        named = [r for r in releases if r.get("name") == row.get("next_release")]
        following = ((named or releases or [{}])[0]).get("hash") or ""
    return current, following


def fetch_latest_app_update(group: str, app: str):
    """Asks Press to register the newest commit of the app's branch on the bench."""
    call("press.api.bench.fetch_latest_app_update", name=group, app=app)


def deploy_and_update(group: str, apps: list[dict], sites: list[dict]) -> str:
    """Builds the bench with `apps` and moves `sites` to it, with backups; returns Press's deploy reference."""
    return call(
        "press.api.bench.deploy_and_update",
        name=group,
        apps=apps,
        sites=sites,
        run_will_fail_check=True,
        trigger_patch_deploy=False,
    )


def get_list(
    doctype: str,
    filters: dict,
    fields: list[str],
    limit: int = 20,
    order_by: str = "creation desc",
) -> list[dict]:
    """Press's own records (Site Update, Deploy Candidate, Agent Job, Site Backup) the team may read."""
    return (
        call(
            "press.api.client.get_list",
            doctype=doctype,
            filters=filters,
            fields=fields,
            limit=limit,
            order_by=order_by,
        )
        or []
    )
