"""A small client for Meta's Graph API (docs/meta-publishing.md).

The version is one setting (HD Meta Settings > Graph API Version) with one default here.
Error messages never carry the request, so a token can't end up in a log or a toast."""

import hashlib
import hmac

import frappe
import requests
from frappe import _

# Meta retires each version about two years after its release (v25.0: July 2028)
DEFAULT_GRAPH_VERSION = "v25.0"
GRAPH_HOST = "https://graph.facebook.com"
DIALOG_HOST = "https://www.facebook.com"
TIMEOUT = 60

# Graph error codes worth another try: temporary failure, rate limits, unknown error
TRANSIENT_CODES = {1, 2, 4, 17, 32, 341, 368, 613}
# the token is no longer valid (expired, revoked, password changed)
TOKEN_CODES = {190}


class MetaError(Exception):
    """Meta refused a request or couldn't be reached.

    `transient` means trying again later may work; `token_expired` that the connection
    must be made again; `user_message` is safe to show people."""

    def __init__(
        self,
        user_message: str,
        transient: bool = False,
        token_expired: bool = False,
        code: int | None = None,
    ):
        super().__init__(user_message)
        self.user_message = user_message
        self.transient = transient
        self.token_expired = token_expired
        self.code = code


def graph_version() -> str:
    return (
        frappe.db.get_single_value("HD Meta Settings", "graph_api_version")
        or DEFAULT_GRAPH_VERSION
    )


class GraphClient:
    def __init__(self, token: str | None = None, app_secret: str | None = None):
        self.token = token
        self.app_secret = app_secret
        self.base = f"{GRAPH_HOST}/{graph_version()}"

    def get(self, path: str, **params) -> dict:
        return self.request("GET", path, params)

    def post(self, path: str, safe_to_retry: bool = True, **params) -> dict:
        """`safe_to_retry` is False for the call that makes something public: if it
        times out, Meta may still have posted, so it is reported, not repeated."""
        return self.request("POST", path, params, safe_to_retry)

    def request(
        self, method: str, path: str, params: dict, safe_to_retry: bool = True
    ) -> dict:
        params = {k: v for k, v in params.items() if v is not None}
        if self.token:
            params["access_token"] = self.token
            if self.app_secret:
                params["appsecret_proof"] = hmac.new(
                    self.app_secret.encode(), self.token.encode(), hashlib.sha256
                ).hexdigest()
        url = f"{self.base}/{path.lstrip('/')}"
        try:
            if method == "GET":
                response = requests.get(url, params=params, timeout=TIMEOUT)
            else:
                response = requests.post(url, data=params, timeout=TIMEOUT)
        except requests.RequestException as e:
            if safe_to_retry:
                raise MetaError(
                    _("Couldn't reach Meta ({0}).").format(type(e).__name__),
                    transient=True,
                ) from None
            raise MetaError(
                _(
                    "Meta didn't answer, so the post may or may not have gone out. Check the page before trying again."
                )
            ) from None
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.ok and "error" not in body:
            return body
        raise self.error_from(response.status_code, body.get("error") or {})

    @staticmethod
    def error_from(status: int, error: dict) -> MetaError:
        code = error.get("code")
        message = error.get("error_user_msg") or error.get("message") or ""
        if code in TOKEN_CODES:
            return MetaError(
                _("The connection to Meta has expired. Connect Meta again."),
                token_expired=True,
                code=code,
            )
        transient = code in TRANSIENT_CODES or status >= 500
        return MetaError(
            _("Meta said: {0}").format(
                message or _("error {0}").format(code or status)
            ),
            transient=transient,
            code=code,
        )
