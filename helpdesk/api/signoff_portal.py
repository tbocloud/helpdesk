"""The customer's training sign-off page at /project-signoff?token=...

The customer has no helpdesk login. Two things let them in, and every call checks
both again:

1. The link's token. Only its SHA-256 is stored on the sign-off; it expires
   (30 days), and sending a new link or revoking it makes the old one useless.
2. A one-time code emailed to the sign-off's named signatory. A correct code
   starts a session (Redis, behind an HttpOnly browser-session cookie) bound to
   that sign-off, that token and that email.

Nothing here ever returns another sign-off, the project's tasks or internal notes.
See docs/project-signoff.md.
"""

import hmac
import secrets

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import (
    cstr,
    formatdate,
    get_datetime,
    get_fullname,
    get_url,
    now_datetime,
)

from helpdesk.helpdesk.doctype.hd_project_signoff.hd_project_signoff import (
    DRAFT,
    SIGNED,
    HDProjectSignoff,
)

SESSION_COOKIE = "hd_signoff"
SESSION_TTL_SECONDS = 2 * 60 * 60
OTP_TTL_SECONDS = 10 * 60
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5


# --------------------------------------------------------------- link --


def find_signoff(token: str):
    """The sign-off this token opens, or None (unknown, replaced or revoked)."""
    token = cstr(token).strip()
    if len(token) < 32:
        return None
    name = frappe.db.get_value(
        "HD Project Signoff",
        {"link_token_hash": HDProjectSignoff.hash_token(token)},
        "name",
    )
    return frappe.get_doc("HD Project Signoff", name) if name else None


def link_state(doc) -> str:
    """'open', 'expired' or 'invalid'."""
    if not doc or not doc.link_token_hash or doc.status == DRAFT:
        return "invalid"
    if not doc.link_expires_on or get_datetime(doc.link_expires_on) <= now_datetime():
        return "expired"
    return "open"


def require_link(token: str):
    doc = find_signoff(token)
    state = link_state(doc)
    if state == "expired":
        frappe.throw(
            _("This link has expired. Ask your trainer to send a new one."),
            frappe.PermissionError,
        )
    if state != "open":
        frappe.throw(
            _(
                "This link isn't valid any more. Open the most recent email from us, or ask your trainer to send a new link."
            ),
            frappe.PermissionError,
        )
    return doc


# ------------------------------------------------------------ session --


def get_session(doc) -> dict | None:
    """The verified session for this sign-off, if the browser has one."""
    request = getattr(frappe.local, "request", None)
    sid = request.cookies.get(SESSION_COOKIE) if request else None
    if not sid or not doc:
        return None
    session = frappe.cache.get_value(session_key(sid), expires=True)
    if (
        not session
        or session.get("signoff") != doc.name
        or not hmac.compare_digest(
            cstr(session.get("token_hash")), cstr(doc.link_token_hash)
        )
        or session.get("email") != doc.signatory_email
    ):
        return None
    return session


def start_session(doc):
    sid = secrets.token_urlsafe(32)
    frappe.cache.set_value(
        session_key(sid),
        {
            "signoff": doc.name,
            "token_hash": doc.link_token_hash,
            "email": doc.signatory_email,
        },
        expires_in_sec=SESSION_TTL_SECONDS,
    )
    # no max_age, so the cookie is gone once the browser closes
    frappe.local.cookie_manager.set_cookie(
        SESSION_COOKIE,
        sid,
        httponly=True,
        samesite="Lax",
        secure=get_url().startswith("https://"),
    )


def require_session(token: str):
    """The sign-off, only for a valid link plus a verified code from this browser."""
    doc = require_link(token)
    session = get_session(doc)
    if not session:
        frappe.throw(
            _("Your session has ended. Ask for a new code to continue."),
            frappe.AuthenticationError,
        )
    return doc, session


def session_key(sid: str) -> str:
    return f"hd_signoff_session:{sid}"


def otp_key(signoff: str) -> str:
    return f"hd_signoff_otp:{signoff}"


def mask_email(email: str) -> str:
    local, _sep, domain = cstr(email).partition("@")
    return f"{local[:1]}{'•' * max(len(local) - 1, 1)}@{domain}"


def request_meta() -> tuple[str | None, str | None]:
    request = getattr(frappe.local, "request", None)
    agent = request.headers.get("User-Agent") if request else None
    return getattr(frappe.local, "request_ip", None), agent


# ---------------------------------------------------------------- otp --


@frappe.whitelist(  # sign-off page: a valid link token is checked inside, and the code goes only to the signatory - nosemgrep
    allow_guest=True, methods=["POST"]
)
@rate_limit(key="token", limit=5, seconds=60 * 60)
def request_code(token: str) -> dict:
    doc = require_link(token)
    key = otp_key(doc.name)
    existing = frappe.cache.get_value(key, expires=True)
    if existing:
        elapsed = (now_datetime() - get_datetime(existing["sent_at"])).total_seconds()
        if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
            return {
                "success": False,
                "message": _("Wait {0}s before asking for another code.").format(
                    int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)
                ),
            }
    code = f"{secrets.randbelow(1_000_000):06d}"
    # sent first: a failed send must not leave a code (and a resend wait) the customer never got
    frappe.sendmail(
        recipients=[doc.signatory_email],
        subject=_("Your code for the {0} sign-off: {1}").format(doc.module_title, code),
        message="<p>"
        + _(
            "Your code is <b>{0}</b>. It works for {1} minutes. If you didn't open the sign-off page, ignore this email."
        ).format(code, OTP_TTL_SECONDS // 60)
        + "</p>",
        now=True,
    )
    frappe.cache.set_value(
        key,
        {"otp": code, "sent_at": str(now_datetime()), "attempts": 0},
        expires_in_sec=OTP_TTL_SECONDS,
    )
    return {
        "success": True,
        "message": _("We sent a 6-digit code to {0}.").format(
            mask_email(doc.signatory_email)
        ),
    }


@frappe.whitelist(  # sign-off page: a valid link token is checked inside, and the code is rate-limited - nosemgrep
    allow_guest=True, methods=["POST"]
)
@rate_limit(key="token", limit=15, seconds=10 * 60)
def verify_code(token: str, code: str) -> dict:
    doc = require_link(token)
    key = otp_key(doc.name)
    entry = frappe.cache.get_value(key, expires=True)
    if not entry:
        return {
            "success": False,
            "message": _("That code has expired. Ask for a new one."),
        }
    if entry["attempts"] >= OTP_MAX_ATTEMPTS:
        frappe.cache.delete_value(key)
        return {
            "success": False,
            "message": _("Too many wrong tries. Ask for a new code."),
        }
    if not hmac.compare_digest(cstr(code).strip(), entry["otp"]):
        entry["attempts"] += 1
        remaining = (
            OTP_TTL_SECONDS
            - (now_datetime() - get_datetime(entry["sent_at"])).total_seconds()
        )
        frappe.cache.set_value(key, entry, expires_in_sec=max(int(remaining), 1))
        return {"success": False, "message": _("That code is not right. Try again.")}
    frappe.cache.delete_value(key)
    start_session(doc)
    ip, _agent = request_meta()
    doc.log_event(
        _("Code verified"),
        by_email=doc.signatory_email,
        by_name=doc.signatory_name,
        ip_address=ip,
    )
    doc.flags.signoff_action = True
    doc.save(ignore_permissions=True)
    return {"success": True}


@frappe.whitelist(  # sign-off page: only ends this browser's own session - nosemgrep
    allow_guest=True, methods=["POST"]
)
def logout() -> dict:
    request = getattr(frappe.local, "request", None)
    sid = request.cookies.get(SESSION_COOKIE) if request else None
    if sid:
        frappe.cache.delete_value(session_key(sid))
    frappe.local.cookie_manager.delete_cookie(SESSION_COOKIE)
    return {"success": True}


# ------------------------------------------------------------ actions --


@frappe.whitelist(  # sign-off page: link token and verified code session are checked inside - nosemgrep
    allow_guest=True, methods=["POST"]
)
@rate_limit(key="token", limit=300, seconds=10 * 60)
def save_response(token: str, item: str, response: str, comment: str = "") -> dict:
    doc, session = require_session(token)
    ip, _agent = request_meta()
    if doc.record_response(
        cstr(item), cstr(response), cstr(comment), session["email"], ip
    ):
        doc.follow_up(cstr(item))
    doc.save(ignore_permissions=True)
    return customer_view(doc)


@frappe.whitelist(  # sign-off page: link token and verified code session are checked inside - nosemgrep
    allow_guest=True, methods=["POST"]
)
@rate_limit(key="token", limit=10, seconds=10 * 60)
def sign(token: str, full_name: str, designation: str, confirm: bool = False) -> dict:
    doc, session = require_session(token)
    if not frappe.utils.sbool(confirm):
        frappe.throw(_("Tick the confirmation to sign."))
    ip, agent = request_meta()
    doc.sign_off(cstr(full_name), cstr(designation), session["email"], ip, agent)
    return customer_view(doc)


@frappe.whitelist(  # sign-off page: link token and verified code session are checked inside - nosemgrep
    allow_guest=True, methods=["GET"]
)
def download_pdf(token: str):
    """The signed record; private on the project, so it is streamed only to the verified signatory."""
    doc, _session = require_session(token)
    if doc.status != SIGNED or not doc.signed_pdf:
        frappe.throw(_("There is no signed record yet."), frappe.DoesNotExistError)
    file_doc = frappe.get_doc("File", doc.signed_pdf)
    frappe.local.response.filename = file_doc.file_name
    frappe.local.response.filecontent = file_doc.get_content()
    frappe.local.response.type = "download"


# --------------------------------------------------------------- page --


def page_data(token: str) -> dict:
    """What /project-signoff renders: the link's state, then the sign-off once the code is verified."""
    doc = find_signoff(token)
    state = link_state(doc)
    if state != "open":
        return {"state": state}
    if not get_session(doc):
        return {
            "state": "code",
            "module_title": doc.module_title,
            "project_name": doc.project_name or doc.project,
            "email": mask_email(doc.signatory_email),
        }
    return {"state": "open", "signoff": customer_view(doc)}


def customer_view(doc) -> dict:
    """Only what the customer needs: no tasks, internal notes, other sign-offs or audit details."""
    return {
        "module_title": doc.module_title,
        "project_name": doc.project_name or doc.project,
        "customer_name": doc.customer_name(),
        "trainer_name": get_fullname(doc.trainer) if doc.trainer else None,
        "training_date": formatdate(doc.training_date) if doc.training_date else None,
        "signatory_name": doc.signatory_name,
        "status": doc.status,
        "counts": doc.counts(),
        "items": [
            {
                "name": row.name,
                "section": row.section,
                "question": row.question,
                "help_text": row.help_text,
                "response": row.response,
                "customer_comment": row.customer_comment,
                "clarified": bool(row.clarified_on) and row.response == "Pending",
                "clarification_note": row.clarification_note
                if row.response == "Pending"
                else None,
            }
            for row in doc.items
        ],
        "signed": (
            {
                "name": doc.signer_name,
                "designation": doc.signer_designation,
                "on": frappe.utils.format_datetime(doc.signed_on),
                "has_pdf": bool(doc.signed_pdf),
            }
            if doc.status == SIGNED
            else None
        ),
    }
