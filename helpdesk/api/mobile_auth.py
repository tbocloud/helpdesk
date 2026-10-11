"""Single sign-in for the TBO Smart app (docs/tbo-smart-api.md, "Single sign-in").

The app signs in once with Microsoft (Entra ID) and sends the ID token here. When
the token is genuinely Microsoft's, for our tenant and our app, this site issues
its own OAuth Bearer Token for the matching user, exactly like Frappe's OAuth
server does, so revoke and every endpoint work unchanged. There is no refresh
token: after an hour the app exchanges a fresh Microsoft ID token, which Microsoft
won't issue to an account TBO has disabled (docs/tbo-smart-api.md, "Offboarding").
Access stays decided by this site's users and roles: users are never created here.
"""

import hmac
import re
import time
from functools import lru_cache

import frappe
import jwt
from frappe import _
from frappe.integrations.oauth2 import get_oauth_server
from frappe.rate_limiter import rate_limit
from frappe.utils import get_url
from oauthlib.common import Request

from helpdesk.api.mobile import API_VERSION, RATE_WINDOW_SECONDS

AUTHORITY = "https://login.microsoftonline.com/{0}"
ISSUER = AUTHORITY + "/v2.0"
JWKS_URL = AUTHORITY + "/discovery/v2.0/keys"
# Entra signs with keys it rotates; PyJWKClient refetches when a token names a new one
JWKS_CACHE_SECONDS = 60 * 60
JWKS_TIMEOUT_SECONDS = 10
LEEWAY_SECONDS = 60
# the app exchanges the ID token right after signing in; an older one is refused, which
# also bounds how long a used token has to be remembered
MAX_TOKEN_AGE_SECONDS = 10 * 60
REQUIRED_CLAIMS = ["exp", "nbf", "iat", "iss", "aud", "tid", "sub"]
USER_CLAIMS = ("email", "preferred_username", "upn")
# the same scopes the app gets through the OAuth Client's own sign-in
SCOPES = ("all", "openid")
APP_ROLES = {"Agent", "Agent Manager"}
# per IP address (an office shares one), per minute
EXCHANGE_RATE_LIMIT = 30
USED_TOKEN_KEY = "helpdesk:mobile_sso_used:{0}"
GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
LOG_TITLE = "TBO Smart Microsoft sign-in refused"


# guest by design: the caller has no session yet; the Microsoft ID token is the credential
@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep
@rate_limit(limit=EXCHANGE_RATE_LIMIT, seconds=RATE_WINDOW_SECONDS)
def exchange_microsoft_token(id_token: str, nonce: str | None = None) -> dict:
    """A Microsoft ID token in, this site's access token out."""
    settings = frappe.get_cached_doc("HD Settings")
    if not sso_ready(settings):
        refuse(
            "disabled",
            _("Single sign-in with Microsoft isn't turned on for this site."),
            frappe.PermissionError,
        )
    claims = verified_claims(
        id_token, nonce, settings.microsoft_tenant_id, settings.microsoft_client_id
    )
    client = frappe.get_doc("OAuth Client", settings.mobile_oauth_client)
    # Frappe's grant flows check scopes before issuing; create_token alone doesn't
    if missing_scopes(client.scopes):
        refuse(
            "client_scopes",
            _("Single sign-in with Microsoft isn't set up correctly on this site."),
            frappe.PermissionError,
        )
    user = site_user(claims, client)
    return {"v": API_VERSION, "data": issue_tokens(user, client)}


def sso_ready(settings) -> bool:
    return bool(
        settings.enable_microsoft_sso
        and settings.microsoft_tenant_id
        and settings.microsoft_client_id
        and settings.mobile_oauth_client
    )


def missing_scopes(client_scopes: str | None) -> set:
    """The scopes the issued tokens carry that the OAuth Client doesn't allow."""
    return set(SCOPES) - set((client_scopes or "").split())


def refuse(reason: str, message: str, exc=frappe.AuthenticationError):
    """Records why (the reason class only: never the token or who it named) and stops.
    Deferred, because the request rolls back when it throws."""
    frappe.log_error(title=LOG_TITLE, message=reason, defer_insert=True)
    frappe.throw(message, exc, title=_("Sign-in refused"))


@lru_cache(maxsize=4)
def jwks_client(tenant: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(
        JWKS_URL.format(tenant),
        cache_keys=True,
        lifespan=JWKS_CACHE_SECONDS,
        timeout=JWKS_TIMEOUT_SECONDS,
    )


def verified_claims(
    id_token: str, nonce: str | None, tenant: str, client_id: str
) -> dict:
    """The ID token's claims, once its signature, issuer, tenant, audience, lifetime,
    age, nonce and single use all check out."""
    invalid = _("Your Microsoft sign-in couldn't be verified. Sign in again.")
    try:
        key = jwks_client(tenant).get_signing_key_from_jwt(id_token).key
        claims = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=ISSUER.format(tenant),
            leeway=LEEWAY_SECONDS,
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.PyJWTError as e:
        refuse(type(e).__name__, invalid)

    if str(claims["tid"]).lower() != tenant:
        refuse("wrong_tenant", invalid)
    now = time.time()
    if now - claims["iat"] > MAX_TOKEN_AGE_SECONDS + LEEWAY_SECONDS:
        refuse("stale_token", invalid)
    if nonce is not None and not hmac.compare_digest(
        str(claims.get("nonce") or "").encode(), nonce.encode()
    ):
        refuse("nonce_mismatch", invalid)
    mark_used(claims, now, invalid)
    return claims


def mark_used(claims: dict, now: float, invalid: str):
    """Each ID token is exchanged once on this site. Redis SET NX is atomic, so two
    requests racing with the same token can't both win."""
    token_id = claims.get("uti") or claims.get("jti")
    if not token_id:
        refuse("no_token_id", invalid)
    ttl = max(int(claims["exp"] - now), 0) + LEEWAY_SECONDS
    key = frappe.cache.make_key(USED_TOKEN_KEY.format(token_id))
    # set_value has no NX; make_key adds the site's prefix, so sites stay apart
    first_use = frappe.cache.set(key, 1, ex=ttl, nx=True)  # nosemgrep
    if not first_use:
        refuse("replayed", invalid)


def site_user(claims: dict, client) -> str:
    """The enabled user the token names, who may use the app here. One answer for
    every refusal, so the endpoint doesn't reveal which accounts exist."""
    not_set_up = _("Your TBO account isn't set up for TBO Support.")
    email = next((claims[c] for c in USER_CLAIMS if claims.get(c)), "")
    # the User table's collation compares case-insensitively
    rows = frappe.qb.get_query(
        "User",
        filters={"email": str(email).strip()},
        fields=["name", "enabled"],
        limit=1,
    ).run(as_dict=True)
    if not email or not rows:
        refuse("unknown_user", not_set_up, frappe.PermissionError)
    user = rows[0]
    if not user.enabled:
        refuse("disabled_user", not_set_up, frappe.PermissionError)
    roles = set(frappe.get_roles(user.name))
    if not is_app_user(user.name, roles):
        refuse("not_agent", not_set_up, frappe.PermissionError)
    # the OAuth Client's Allowed Roles, as Frappe's own sign-in checks them
    if not {r.role for r in client.allowed_roles} & roles:
        refuse("client_role", not_set_up, frappe.PermissionError)
    return user.name


def is_app_user(user: str, roles: set) -> bool:
    """An active HD Agent; without an agent record, someone with an agent role. A
    deactivated agent keeps the Agent role, so the record decides when there is one."""
    active = frappe.db.get_value("HD Agent", {"user": user}, "is_active")
    if active is not None:
        return bool(active)
    return bool(APP_ROLES & roles)


def issue_tokens(user: str, client) -> dict:
    """An OAuth Bearer Token made by Frappe's own OAuth server: its token generator,
    lifetime (3600 s) and save_bearer_token, so the token works like one issued at
    get_token. Without a refresh token, so access never outlives the Microsoft account:
    a refresh at get_token would skip Microsoft."""
    server = get_oauth_server()
    request = Request(get_url())
    request.client = client.as_dict()
    request.user = user
    request.scopes = list(SCOPES)
    token = server.bearer.create_token(request, refresh_token=False)
    server.bearer.request_validator.save_bearer_token(token, request)
    return {
        "access_token": token["access_token"],
        "expires_in": token["expires_in"],
        "token_type": "Bearer",
        "scope": token["scope"],
        "user": user,
        "full_name": frappe.db.get_value("User", user, "full_name") or user,
    }
