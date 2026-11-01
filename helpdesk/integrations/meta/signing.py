"""Short-lived signed tokens: the OAuth `state` and the public media links.

Both are `payload.signature`, signed with HMAC-SHA256 under a key derived from the
site's encryption key, so they can't be forged and each one is only good for what it
names until it expires."""

import base64
import hashlib
import hmac
import json
import secrets

import frappe
from frappe import _
from frappe.utils import cint, get_url, now_datetime
from frappe.utils.password import get_encryption_key

STATE_SECONDS = 10 * 60
MEDIA_SECONDS = 60 * 60


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def signature(purpose: str, body: str) -> str:
    key = hashlib.sha256(f"meta-{purpose}:{get_encryption_key()}".encode()).digest()
    return b64(hmac.new(key, body.encode(), hashlib.sha256).digest())


def now_seconds() -> int:
    return cint(now_datetime().timestamp())


def sign(purpose: str, values: dict, lifetime: int) -> str:
    body = b64(
        json.dumps(
            {**values, "exp": now_seconds() + lifetime}, separators=(",", ":")
        ).encode()
    )
    return f"{body}.{signature(purpose, body)}"


def verify(purpose: str, token: str) -> dict:
    """The signed values, or a ValidationError when the token is forged or has expired."""
    body, _dot, sig = (token or "").partition(".")
    if not body or not hmac.compare_digest(sig, signature(purpose, body)):
        frappe.throw(_("This link isn't valid."), frappe.ValidationError)
    try:
        values = json.loads(unb64(body))
    except ValueError:
        frappe.throw(_("This link isn't valid."), frappe.ValidationError)
    if values.get("exp", 0) < now_seconds():
        frappe.throw(_("This link has expired."), frappe.ValidationError)
    return values


def make_state(user: str, project: str) -> str:
    """The OAuth `state`: who is connecting which project, for ten minutes."""
    return sign(
        "state", {"u": user, "p": project, "n": secrets.token_hex(8)}, STATE_SECONDS
    )


def read_state(state: str) -> tuple[str, str]:
    """(user, project) from a state made by `make_state`."""
    values = verify("state", state)
    return values["u"], values["p"]


def media_url(file_name: str) -> str:
    """A public link to one file, good for an hour (Meta fetches the file itself)."""
    token = sign("media", {"f": file_name}, MEDIA_SECONDS)
    return get_url(f"/api/method/helpdesk.api.meta.media?token={token}")


def read_media_token(token: str) -> str:
    """The File name a media token allows."""
    return verify("media", token)["f"]
