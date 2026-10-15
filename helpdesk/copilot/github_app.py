# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The TBO Copilot GitHub App: a short-lived key per repository, for the hub and for the worker's push.

The hub holds the App's private key (HDS Copilot Settings). For a repository it
finds the App's installation on that repository's owner and asks GitHub for an
installation key limited to that one repository. Keys live an hour: the hub
keeps its own in the cache until five minutes before they expire; the worker's
push key is made for each request, only for the run's own repository, and
never kept.
"""

import re
import time
from datetime import datetime, timezone

import frappe
import jwt
import requests
from cryptography.hazmat.primitives import serialization
from frappe import _

from helpdesk.copilot.github import GITHUB_API, TIMEOUT, GitHubError

# the worker may push its branch and open the pull request, nothing else
PUSH_PERMISSIONS = {"contents": "write", "pull_requests": "write"}
CACHE_PREFIX = "copilot_github_app:"
RENEW_BEFORE = 300  # seconds before expiry a kept key is replaced
PEM_BLOCK = re.compile(r"-----BEGIN ([A-Z ]+)-----(.*?)-----END \1-----", re.S)


def _private_key() -> str | None:
    from frappe.utils.password import get_decrypted_password

    return as_pem(
        get_decrypted_password(
            "HDS Copilot Settings",
            "HDS Copilot Settings",
            "github_app_private_key",
            raise_exception=False,
        )
    )


def as_pem(text: str | None) -> str:
    """The private key in PEM form, however it was pasted.

    The settings field holds one line, so a pasted .pem file arrives with its line
    breaks turned into spaces or gone, and sometimes without its BEGIN and END lines.
    The base64 body is the key; this puts it back together. GitHub's App keys are
    PKCS#1 ("RSA PRIVATE KEY"); a PKCS#8 body ("PRIVATE KEY") is tried next.
    """
    text = (text or "").strip()
    if not text:
        return ""
    found = PEM_BLOCK.search(text)
    kinds = [found.group(1)] if found else ["RSA PRIVATE KEY", "PRIVATE KEY"]
    body = "".join((found.group(2) if found else text).split())
    lines = "\n".join(body[i : i + 64] for i in range(0, len(body), 64))
    candidates = [f"-----BEGIN {k}-----\n{lines}\n-----END {k}-----\n" for k in kinds]
    for pem in candidates:
        try:
            serialization.load_pem_private_key(pem.encode(), password=None)
            return pem
        except (ValueError, TypeError):
            continue
    return candidates[0]  # not a key: signing says so plainly (app_jwt)


def _app_id() -> str:
    from helpdesk.copilot import settings as copilot_settings

    return (copilot_settings.get_settings().get("github_app_id") or "").strip()


def configured() -> bool:
    return bool(_app_id() and _private_key())


def app_jwt() -> str:
    """The App's own ten-minute token, signed with its private key."""
    key, app_id = _private_key(), _app_id()
    if not (key and app_id):
        raise GitHubError(0, _("The GitHub App is not set up in HDS Copilot Settings."))
    now = int(time.time())
    try:
        return jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": app_id}, key, algorithm="RS256"
        )
    except Exception as e:  # a key that is not an RSA private key in PEM form
        raise GitHubError(
            0,
            _("The GitHub App's private key cannot be used: {0}").format(str(e)[:200]),
        ) from e


def _call(method: str, path: str, bearer: str, body: dict | None = None) -> dict:
    try:
        response = requests.request(
            method,
            f"{GITHUB_API}{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {bearer}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json=body,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise GitHubError(
            0, _("GitHub could not be reached: {0}").format(str(e)[:200])
        ) from e
    if response.status_code >= 400:
        try:
            message = response.json().get("message") or response.text
        except ValueError:
            message = response.text
        raise GitHubError(response.status_code, str(message)[:300])
    return response.json() if response.content else {}


def installation(owner_or_repo: str) -> int:
    """The App's installation on the owner of `owner_or_repo` (`owner` or `owner/name`), kept a day."""
    owner = owner_or_repo.split("/", 1)[0].lower()
    key = f"{CACHE_PREFIX}installation:{owner}"
    if found := frappe.cache().get_value(key, expires=True):
        return int(found)
    try:
        if "/" in owner_or_repo:
            found = _call("GET", f"/repos/{owner_or_repo}/installation", app_jwt())
        else:
            found = _call("GET", f"/orgs/{owner}/installation", app_jwt())
    except GitHubError as e:
        if e.status != 404:
            raise
        raise GitHubError(
            404,
            _("The TBO Copilot GitHub App is not installed on {0}.").format(owner),
        ) from e
    frappe.cache().set_value(key, int(found["id"]), expires_in_sec=86400)
    return int(found["id"])


def _mint(
    installation_id: int,
    repositories: list[str] | None = None,
    permissions: dict | None = None,
) -> dict:
    body = {}
    if repositories:
        body["repositories"] = repositories
    if permissions:
        body["permissions"] = permissions
    found = _call(
        "POST",
        f"/app/installations/{installation_id}/access_tokens",
        app_jwt(),
        body or None,
    )
    return {"token": found["token"], "expires_at": found.get("expires_at") or ""}


def _seconds_left(expires_at: str) -> int:
    try:
        expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return int((expires - datetime.now(timezone.utc)).total_seconds())


def _kept(name: str, mint) -> str:
    key = f"{CACHE_PREFIX}token:{name}"
    if found := frappe.cache().get_value(key, expires=True):
        return found
    minted = mint()
    seconds = _seconds_left(minted["expires_at"]) - RENEW_BEFORE
    if seconds > 60:
        frappe.cache().set_value(key, minted["token"], expires_in_sec=seconds)
    return minted["token"]


def token_for_repo(repo: str) -> str:
    """The hub's key for `repo`: the App's permissions, that repository only."""
    name = repo.split("/", 1)[1]
    return _kept(f"repo:{repo.lower()}", lambda: _mint(installation(repo), [name]))


def token_for_owner(owner: str) -> str:
    """The hub's key for every repository of `owner` the App is installed on (for search)."""
    return _kept(f"owner:{owner.lower()}", lambda: _mint(installation(owner)))


def push_token(repo: str) -> dict:
    """The worker's key: push a branch to `repo` and open its pull request; `{token, expires_at}`, never kept."""
    return _mint(installation(repo), [repo.split("/", 1)[1]], PUSH_PERMISSIONS)


def bot_login() -> str:
    """The login GitHub shows for the App's pull requests and commits (`<slug>[bot]`), kept a day."""
    key = f"{CACHE_PREFIX}bot_login"
    if found := frappe.cache().get_value(key, expires=True):
        return found
    login = f"{_call('GET', '/app', app_jwt())['slug']}[bot]"
    frappe.cache().set_value(key, login, expires_in_sec=86400)
    return login
