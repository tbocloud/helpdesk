"""Settings → GitHub: HD GitHub Settings for System Managers and Agent Managers.

The webhook secret and both tokens never go back to the browser once saved: the
page gets a masked value and whether each is set, and sends a secret only to
replace or remove it (as Settings → Chat & Teams does). docs/github-sync.md
describes the page.
"""

import frappe
import requests
from frappe import _
from frappe.utils import get_url

from helpdesk import github_sync, merge_bot
from helpdesk.tasky.permissions import is_tasky_admin

SETTINGS = github_sync.SETTINGS
PLAIN_FIELDS = (
    "enabled",
    "allowed_repos",
    "complete_on_merge",
    "unlinked_pr_project",
    "trigger_merge_bot",
    "merge_bot_repo",
    "merge_bot_workflow",
)
SECRET_FIELDS = ("webhook_secret", "github_token", "merge_bot_token")
TOKEN_FIELDS = ("github_token", "merge_bot_token")
WEBHOOK_PATH = "/api/method/helpdesk.api.github.webhook"
# GitHub's token prefixes: enough to tell which kind is saved, nothing of the key
TOKEN_PREFIXES = ("github_pat_", "ghp_", "gho_", "ghu_", "ghs_")
FINE_GRAINED = "github_pat_"


def check_admin():
    # only_for is skipped in tests, so check the roles directly
    if not is_tasky_admin():
        frappe.throw(
            _("Only System Managers and Agent Managers can change GitHub settings."),
            frappe.PermissionError,
        )


def mask(value: str) -> str:
    return next((f"{p}…" for p in TOKEN_PREFIXES if value.startswith(p)), "…")


def settings_payload(doc) -> dict:
    secrets = {}
    for field in SECRET_FIELDS:
        value = doc.get_password(field, raise_exception=False)
        secrets[field] = {"set": bool(value), "masked": mask(value) if value else ""}
    return {
        "settings": {f: doc.get(f) for f in PLAIN_FIELDS},
        "secrets": secrets,
        "webhook_url": get_url(WEBHOOK_PATH),
    }


@frappe.whitelist()
def get_settings() -> dict:
    check_admin()
    return settings_payload(frappe.get_doc(SETTINGS))


@frappe.whitelist()
def get_status() -> dict:
    """The merge bot's last request and result, and the last webhook delivery."""
    check_admin()
    Delivery = frappe.qb.DocType(github_sync.DELIVERY)
    deliveries = (
        frappe.qb.from_(Delivery)
        .select(
            Delivery.creation.as_("at"),
            Delivery.event,
            Delivery.action,
            Delivery.repo,
            Delivery.status,
        )
        .orderby(Delivery.creation, order=frappe.qb.desc)
        .limit(1)
        .run(as_dict=True)
    )
    return {
        "last_dispatch": frappe.db.get_single_value(SETTINGS, "merge_bot_last_dispatch"),
        "last_result": frappe.db.get_single_value(SETTINGS, "merge_bot_last_result"),
        # "Dispatched" or "Failed"; empty for results recorded before it existed
        "last_outcome": frappe.db.get_single_value(SETTINGS, "merge_bot_last_outcome"),
        "last_delivery": deliveries[0] if deliveries else None,
    }


@frappe.whitelist(methods=["POST"])
def save_settings(values: dict | str) -> dict:
    """Plain fields as sent. A secret only when its key is sent: a value replaces
    it, an empty string removes it; HDGitHubSettings.validate checks the rest."""
    check_admin()
    values = frappe.parse_json(values) or {}
    doc = frappe.get_doc(SETTINGS)
    doc.update({k: v for k, v in values.items() if k in PLAIN_FIELDS})
    for field in SECRET_FIELDS:
        if values.get(field) is not None:
            doc.set(field, str(values[field]).strip())
    doc.save(ignore_permissions=True)
    return settings_payload(frappe.get_doc(SETTINGS))


@frappe.whitelist(methods=["POST"])
def test_token(field: str) -> dict:
    """Checks a saved token with GitHub: whose it is, what it may do where GitHub
    says, and, for the token the merge bot uses, that it can see the bot's repository."""
    check_admin()
    if field not in TOKEN_FIELDS:
        frappe.throw(_("Choose a token to test: github_token or merge_bot_token."))
    doc = frappe.get_doc(SETTINGS)
    token = doc.get_password(field, raise_exception=False)
    if not token:
        return {"ok": False, "message": _("No token saved yet: add it, save, then test.")}
    try:
        user = github_get("/user", token)
        if not user.ok:
            return {"ok": False, "message": user_error(user.status_code)}
        details = token_details(token, user)
        if field == "merge_bot_token" or not doc.get_password(
            "merge_bot_token", raise_exception=False
        ):
            repo = github_get(f"/repos/{doc.merge_bot_repo}", token)
            if not repo.ok:
                return {
                    "ok": False,
                    "message": repo_error(repo.status_code, doc.merge_bot_repo),
                    "details": details,
                }
            details.append({"label": _("Can see"), "value": doc.merge_bot_repo})
    except requests.RequestException as e:
        # only the kind: the error's text can hold the request
        return {
            "ok": False,
            "message": _("Couldn't reach GitHub ({0}). Try again in a minute.").format(
                type(e).__name__
            ),
        }
    return {"ok": True, "message": _("GitHub accepts this token."), "details": details}


@frappe.whitelist(methods=["POST"])
def request_merge_bot_run() -> dict:
    """Asks GitHub for a merge bot run now, with the saved settings, unless one was
    requested in the last two minutes (merge_bot's debounce)."""
    check_admin()
    if not frappe.db.get_single_value(SETTINGS, "trigger_merge_bot"):
        return {
            "ok": False,
            "message": _("Turn on Trigger the org merge bot and save, then try again."),
        }
    if not merge_bot.take_debounce():
        return {
            "ok": False,
            "message": _(
                "A run was requested less than {0} minutes ago, so this one wasn't sent. The bot merges everything that's ready in each run."
            ).format(merge_bot.DEBOUNCE_SECONDS // 60),
        }
    ok = merge_bot.dispatch()
    result = frappe.db.get_single_value(SETTINGS, "merge_bot_last_result")
    if ok:
        message = _("{0}. The bot merges what's ready within a few minutes.")
    else:
        message = _("{0}. Test the token above to see why.")
    return {"ok": ok, "message": message.format(result)}


def github_get(path: str, token: str) -> requests.Response:
    return requests.get(
        f"{github_sync.GITHUB_API}{path}",
        headers=github_sync.github_headers(token),
        timeout=github_sync.REQUEST_TIMEOUT,
    )


def token_details(token: str, user: requests.Response) -> list[dict]:
    """The account, and the scopes a classic token lists; fine-grained tokens
    don't say what they may do, so the page says what they need instead."""
    details = [{"label": _("Account"), "value": user.json().get("login") or ""}]
    if token.startswith(FINE_GRAINED):
        details.append(
            {
                "label": _("Permissions"),
                "value": _("Fine-grained token: GitHub doesn't list them"),
            }
        )
    else:
        scopes = user.headers.get("X-OAuth-Scopes")
        details.append({"label": _("Scopes"), "value": scopes or _("None")})
    if expires := user.headers.get("GitHub-Authentication-Token-Expiration"):
        details.append({"label": _("Expires"), "value": expires})
    return details


def user_error(status: int) -> str:
    if status == 401:
        return _(
            "GitHub doesn't accept this token: it's mistyped, expired or revoked. Create a new one and replace it."
        )
    if status == 403:
        return _(
            "GitHub refused this token (HTTP 403). An organisation with SSO must authorise it, or the rate limit was hit: try again later."
        )
    return _("GitHub answered HTTP {0}. Try again in a minute.").format(status)


def repo_error(status: int, repo: str) -> str:
    if status in (403, 404):
        return _(
            "The token works, but can't see {0}. Give it access to that repository (Repository access, with tbocloud as resource owner), or check the merge bot repository."
        ).format(repo)
    return _("GitHub answered HTTP {0} for {1}. Try again in a minute.").format(
        status, repo
    )
