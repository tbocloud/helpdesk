"""Client content portal at /content-portal.

Clients have no helpdesk login here. They sign in with the email on one of
their HD Customer contacts and a one-time code, review the posts sent to them,
approve or ask for changes, and leave comments. One email can belong to several
customers, so a session holds every customer that email reaches.

The session lives in Redis behind a browser-session cookie, so closing the
browser ends it and the client has to request a new code next time.
"""

import hmac
import json
import secrets
from urllib.parse import quote

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cstr, get_datetime, get_url, now_datetime
from frappe.utils.html_utils import sanitize_html

from helpdesk.content_sync import post_images

SESSION_COOKIE = "hd_content_portal"
OTP_TTL_SECONDS = 10 * 60
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
SESSION_TTL_SECONDS = 6 * 60 * 60
MAX_POSTS = 500

# Earlier stages are internal work in progress and never reach the client
CLIENT_STATUSES = (
    "Client Review",
    "Changes Requested",
    "Approved",
    "Scheduled",
    "Published",
)
# Only these fields ever leave the building: no writer/designer, tasks or approval plumbing
CLIENT_FIELDS = (
    "name",
    "title",
    "status",
    "channel",
    "format",
    "publish_on",
    "caption",
    "hashtags",
    "client_feedback",
    "published_url",
    "published_on",
)


# --------------------------------------------------------------- identity --


def customers_for_email(email: str) -> list[str]:
    """Every HD Customer that lists a contact with this email, or has it as its own email."""
    email = normalize_email(email)
    if not email:
        return []
    Contact = frappe.qb.DocType("Contact")
    ContactEmail = frappe.qb.DocType("Contact Email")
    contacts = set(
        frappe.qb.from_(Contact)
        .select(Contact.name)
        .where(Contact.email_id == email)
        .run(pluck=True)
    ) | set(
        frappe.qb.from_(ContactEmail)
        .select(ContactEmail.parent)
        .where(ContactEmail.email_id == email)
        .where(ContactEmail.parenttype == "Contact")
        .run(pluck=True)
    )

    Customer = frappe.qb.DocType("HD Customer")
    customers = set(
        frappe.qb.from_(Customer)
        .select(Customer.name)
        .where(Customer.email_id == email)
        .run(pluck=True)
    )
    if contacts:
        Member = frappe.qb.DocType("HD Customer Member")
        customers |= set(
            frappe.qb.from_(Member)
            .select(Member.parent)
            .where(Member.parenttype == "HD Customer")
            .where(Member.contact_name.isin(list(contacts)))
            .run(pluck=True)
        )
    return sorted(customers)


def portal_emails(customer: str) -> list[str]:
    """The addresses a customer's people can sign in with."""
    Member = frappe.qb.DocType("HD Customer Member")
    Contact = frappe.qb.DocType("Contact")
    emails = set(
        frappe.qb.from_(Member)
        .join(Contact)
        .on(Contact.name == Member.contact_name)
        .select(Contact.email_id)
        .where(Member.parenttype == "HD Customer")
        .where(Member.parent == customer)
        .where(Contact.email_id.isnotnull())
        .run(pluck=True)
    )
    own = frappe.db.get_value("HD Customer", customer, "email_id")
    if own:
        emails.add(own)
    return sorted(normalize_email(e) for e in emails if e)


def normalize_email(email) -> str:
    return cstr(email).strip().lower()


def portal_enabled() -> bool:
    return bool(
        frappe.db.get_single_value("HD Content Settings", "enable_client_portal")
    )


def ensure_portal_enabled():
    if not portal_enabled():
        frappe.throw(_("The content portal is turned off."), frappe.PermissionError)


# ---------------------------------------------------------------- session --


def get_session() -> dict | None:
    request = getattr(frappe.local, "request", None)
    sid = request.cookies.get(SESSION_COOKIE) if request else None
    if not sid:
        return None
    return frappe.cache.get_value(session_key(sid), expires=True)


def start_session(email: str, customers: list[str]):
    sid = frappe.generate_hash(length=32)
    frappe.cache.set_value(
        session_key(sid),
        {"email": email, "customers": customers},
        expires_in_sec=SESSION_TTL_SECONDS,
    )
    # no max_age, so the cookie is gone once the browser closes
    frappe.local.cookie_manager.set_cookie(
        SESSION_COOKIE, sid, httponly=True, samesite="Lax"
    )


def require_session() -> dict:
    ensure_portal_enabled()
    session = get_session()
    if not session:
        frappe.throw(
            _("Your session has ended. Sign in again with your email."),
            frappe.AuthenticationError,
        )
    return session


def require_post(post: str):
    """The post, if the signed-in client may see it; the same error otherwise, found or not."""
    session = require_session()
    exists = frappe.db.exists("HD Content Post", cstr(post))
    doc = frappe.get_doc("HD Content Post", exists) if exists else None
    if (
        not doc
        or doc.customer not in session["customers"]
        or doc.status not in CLIENT_STATUSES
    ):
        frappe.throw(_("Post not found"), frappe.DoesNotExistError)
    return session, doc


def session_key(sid: str) -> str:
    return f"hd_content_portal_session:{sid}"


def otp_key(email: str) -> str:
    return f"hd_content_portal_otp:{email}"


# -------------------------------------------------------------------- otp --


def code_sent_message(email: str) -> str:
    return _(
        "If {0} belongs to one of our clients, a 6-digit code is on its way."
    ).format(email)


def issue_code(email: str, customer_label: str) -> dict:
    """Cache a fresh code for this email and send it.

    Shared by the client's own "email me a code" and an agent's "Share portal",
    so a code from either one works for signing in and the resend wait applies to both.
    """
    key = otp_key(email)
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
    frappe.cache.set_value(
        key,
        {"otp": code, "sent_at": str(now_datetime()), "attempts": 0},
        expires_in_sec=OTP_TTL_SECONDS,
    )
    settings = frappe.get_single("HD Content Settings")
    subject, message = settings.render(
        "portal_code",
        {
            "customer": customer_label,
            "otp": code,
            "otp_expiry_minutes": OTP_TTL_SECONDS // 60,
            # email + code_sent lets the sign-in page skip straight to entering the code
            "portal_link": get_url(f"/content-portal?email={quote(email)}&code_sent=1"),
        },
    )
    frappe.sendmail(recipients=[email], subject=subject, message=message, now=True)
    return {"success": True, "message": code_sent_message(email)}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="email", limit=5, seconds=60 * 60)
def request_code(email: str):
    ensure_portal_enabled()
    email = normalize_email(email)
    if not email:
        frappe.throw(_("Enter your email address."))
    customers = customers_for_email(email)
    if not customers:
        # same answer as a real client, so the page can't be used to test addresses
        return {"success": True, "message": code_sent_message(email)}
    label = customers[0] if len(customers) == 1 else email
    return issue_code(email, label)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="email", limit=15, seconds=10 * 60)
def verify_code(email: str, code: str):
    ensure_portal_enabled()
    email = normalize_email(email)
    code = cstr(code).strip()
    key = otp_key(email)
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

    if not hmac.compare_digest(code, entry["otp"]):
        entry["attempts"] += 1
        remaining = (
            OTP_TTL_SECONDS
            - (now_datetime() - get_datetime(entry["sent_at"])).total_seconds()
        )
        frappe.cache.set_value(key, entry, expires_in_sec=max(int(remaining), 1))
        return {"success": False, "message": _("That code is not right. Try again.")}

    frappe.cache.delete_value(key)
    customers = customers_for_email(email)
    if not customers:
        return {
            "success": False,
            "message": _("This email no longer has portal access."),
        }
    start_session(email, customers)
    return {"success": True}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def logout():
    request = getattr(frappe.local, "request", None)
    sid = request.cookies.get(SESSION_COOKIE) if request else None
    if sid:
        frappe.cache.delete_value(session_key(sid))
    frappe.local.cookie_manager.delete_cookie(SESSION_COOKIE)
    return {"success": True}


# ------------------------------------------------------------------- data --


def get_portal_posts(customer: str) -> list[dict]:
    """What the client sees for one customer: client-stage posts with their images."""
    posts = frappe.get_all(
        "HD Content Post",
        filters={"customer": customer, "status": ("in", CLIENT_STATUSES)},
        fields=list(CLIENT_FIELDS),
        order_by="publish_on asc",
        limit=MAX_POSTS,
    )
    for post in posts:
        post.caption = sanitize_html(post.caption or "", always_sanitize=True)
        post.images = [image.name for image in post_images(post.name)]
    return posts


# ---------------------------------------------------------------- actions --


@frappe.whitelist(allow_guest=True, methods=["POST"])
def approve(post: str):
    session, doc = require_post(post)
    doc.approve_from_portal(session["email"])
    return {"success": True, "status": doc.status}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def approve_many(posts):
    """Approve several posts in one go; ones already decided are skipped, not failed."""
    if isinstance(posts, str):
        posts = json.loads(posts)
    approved = []
    for post in posts:
        session, doc = require_post(post)
        if doc.status != "Client Review":
            continue
        doc.approve_from_portal(session["email"])
        approved.append(doc.name)
    return {"success": True, "approved": approved}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def request_changes(post: str, notes: str):
    notes = cstr(notes).strip()
    if not notes:
        frappe.throw(_("Tell us what should change."))
    session, doc = require_post(post)
    doc.request_changes_from_portal(session["email"], notes)
    return {"success": True, "status": doc.status}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def add_comment(post: str, text: str):
    text = cstr(text).strip()
    if not text:
        frappe.throw(_("Write a comment first."))
    session, doc = require_post(post)
    doc.comment_from_portal(session["email"], text)
    return {"success": True}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_image(post: str, file: str):
    """Stream one of the post's images; they are private files, so the client can't fetch them directly."""
    _session, doc = require_post(post)
    if file not in {image.name for image in post_images(doc.name)}:
        frappe.throw(_("Image not found"), frappe.DoesNotExistError)
    file_doc = frappe.get_doc("File", file)
    frappe.local.response.filename = file_doc.file_name
    frappe.local.response.filecontent = file_doc.get_content()
    frappe.local.response.type = "download"
    frappe.local.response.display_content_as = "inline"


# ------------------------------------------------------------------ agents --


@frappe.whitelist()
def get_portal_access(customer: str) -> dict:
    """What the Share portal dialog needs for a customer."""
    frappe.has_permission("HD Customer", "read", customer, throw=True)
    return {
        "enabled": portal_enabled(),
        "emails": portal_emails(customer),
        "posts_in_review": frappe.db.count(
            "HD Content Post", {"customer": customer, "status": "Client Review"}
        ),
        "portal_url": get_url("/content-portal"),
    }


@frappe.whitelist(methods=["POST"])
def send_portal_access(customer: str, email: str) -> dict:
    """Email the portal link with a sign-in code; a new address becomes a contact of the customer first."""
    frappe.has_permission("HD Customer", "read", customer, throw=True)
    ensure_portal_enabled()
    email = normalize_email(email)
    frappe.utils.validate_email_address(email, throw=True)
    if email not in portal_emails(customer):
        frappe.has_permission("HD Customer", "write", customer, throw=True)
        add_portal_contact(customer, email)
    return issue_code(email, customer)


def add_portal_contact(customer: str, email: str) -> bool:
    """Make `email` a contact of `customer` so it can sign in; True if a new Contact was created."""
    contact = frappe.db.get_value("Contact", {"email_id": email}, "name")
    created = not contact
    if created:
        contact = (
            frappe.get_doc(
                {
                    "doctype": "Contact",
                    "first_name": email.split("@")[0],
                    "email_id": email,
                    "email_ids": [{"email_id": email, "is_primary": 1}],
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    if frappe.db.exists(
        "HD Customer Member",
        {"parent": customer, "parenttype": "HD Customer", "contact_name": contact},
    ):
        return created
    # Inserted directly, not through HD Customer.save(): saving grants the HD Customer
    # role to any existing User with this email, and these emails are often staff.
    # The content portal only needs the contact link.
    frappe.get_doc(
        {
            "doctype": "HD Customer Member",
            "parent": customer,
            "parenttype": "HD Customer",
            "parentfield": "contacts",
            "contact_name": contact,
            "is_manager": 0,
            "idx": frappe.db.count("HD Customer Member", {"parent": customer}) + 1,
        }
    ).db_insert()
    return created
