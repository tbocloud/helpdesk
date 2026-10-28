"""A project's client credentials: the logins a client hands over, and the hand-back when
the client leaves (docs/client-credentials.md).

The doctypes are System Manager only. Everything here checks `can_handle_credentials`
first and then works as the system, so people get exactly that access and no more.
Passwords are never part of a list: `reveal_password` returns one, and writes who
looked to the project's timeline."""

import frappe
from frappe import _
from frappe.utils import cstr, get_fullname, today
from frappe.utils.password import get_decrypted_password

from helpdesk.helpdesk.doctype.hd_client_credential_handover.hd_client_credential_handover import (
    RECEIVED,
    RETURNED,
)
from helpdesk.tasky.permissions import can_handle_credentials

HANDOVER = "HD Client Credential Handover"
CREDENTIAL = "HD Client Credential"


def platforms() -> list[str]:
    """The platforms a client may hand over, from the doctype's own Select."""
    options = frappe.get_meta(CREDENTIAL).get_field("platform").options
    return [p for p in options.split("\n") if p]


def require_access(project: str) -> None:
    if not project or not frappe.db.exists("Project", project):
        frappe.throw(_("Project not found: {0}").format(project))
    if not can_handle_credentials(project):
        frappe.throw(
            _("You can't see this project's client credentials."),
            frappe.PermissionError,
        )


def handover_doc(name: str, project: str):
    """The handover, if it belongs to the project."""
    doc = frappe.get_doc(HANDOVER, name)
    if doc.project != project:
        frappe.throw(_("That handover belongs to another project."))
    return doc


def format_handover(doc) -> dict:
    """A handover as the page shows it: each login says whether it has a password, and
    the password itself is not here."""
    return {
        "name": doc.name,
        "direction": doc.direction,
        "handed_over_on": cstr(doc.handed_over_on),
        "handed_over_by": doc.handed_over_by,
        "received_by": doc.received_by,
        "received_by_name": get_fullname(doc.received_by) if doc.received_by else None,
        "client_signoff_name": doc.client_signoff_name,
        "signed_on": cstr(doc.signed_on) if doc.signed_on else None,
        "close_reason": doc.close_reason,
        "remarks": doc.remarks,
        "items": [
            {
                "name": row.name,
                "platform": row.platform,
                "account_url": row.account_url,
                "username": row.username,
                "two_factor_contact": row.two_factor_contact,
                "notes": row.notes,
                "has_password": has_password(row),
                "returned_from": row.returned_from,
            }
            for row in doc.items
        ],
    }


def has_password(row) -> bool:
    return bool(
        get_decrypted_password(
            CREDENTIAL, row.returned_from or row.name, "password", raise_exception=False
        )
    )


@frappe.whitelist()
def get_credentials(project: str) -> dict:
    """The project's handovers, newest first, with no passwords."""
    require_access(project)
    names = frappe.qb.get_query(
        HANDOVER,
        fields=["name"],
        filters={"project": project},
        order_by="creation desc",
    ).run(pluck=True)
    return {
        "project_status": frappe.db.get_value("Project", project, "status"),
        "platforms": platforms(),
        "handovers": [format_handover(frappe.get_doc(HANDOVER, n)) for n in names],
    }


@frappe.whitelist(methods=["POST"])
def save_handover(
    project: str,
    handed_over_by: str,
    items: list | str,
    handed_over_on: str | None = None,
    remarks: str | None = None,
    name: str | None = None,
) -> dict:
    """Record what the client handed over (a new Received handover), or change one.
    On a change, a login sent with its `name` keeps its password unless one is sent."""
    require_access(project)
    items = frappe.parse_json(items) if isinstance(items, str) else items
    if not isinstance(items, list) or not items:
        frappe.throw(_("Add at least one login."))
    if name:
        doc = handover_doc(name, project)
        if doc.direction != RECEIVED:
            frappe.throw(_("A hand-back can't be changed."))
    else:
        doc = frappe.new_doc(HANDOVER)
        doc.update({"project": project, "direction": RECEIVED})
    doc.update(
        {
            "handed_over_by": cstr(handed_over_by).strip(),
            "handed_over_on": handed_over_on or today(),
            "received_by": doc.received_by or frappe.session.user,
            "remarks": cstr(remarks).strip() or None,
        }
    )
    doc.set_items(items)
    doc.save(ignore_permissions=True)
    return format_handover(doc)


@frappe.whitelist(methods=["POST"])
def reveal_password(project: str, handover: str, item: str) -> dict:
    """One login's password, and a line on the project's timeline that this person looked."""
    require_access(project)
    row = next(
        (r for r in handover_doc(handover, project).items if r.name == item), None
    )
    if not row:
        frappe.throw(_("Login not found."))
    password = get_decrypted_password(
        CREDENTIAL, row.returned_from or row.name, "password", raise_exception=False
    )
    if not password:
        frappe.throw(_("No password was saved for this login."))
    frappe.get_doc("Project", project).add_comment(
        "Info",
        _("{0} viewed the {1} password").format(
            get_fullname(frappe.session.user), row.platform
        ),
    )
    return {"password": password}


@frappe.whitelist(methods=["POST"])
def hand_back_and_close(
    project: str, client_signoff_name: str, signed_on: str, reason: str
) -> dict:
    """Hand every credential back to the client, with the client's sign-off, and close
    the project (Cancelled). The hand-back lists the logins without copying passwords."""
    require_access(project)
    doc = frappe.get_doc(
        {
            "doctype": HANDOVER,
            "project": project,
            "direction": RETURNED,
            "handed_over_on": today(),
            "received_by": frappe.session.user,
            "client_signoff_name": cstr(client_signoff_name).strip(),
            "signed_on": signed_on,
            "close_reason": cstr(reason).strip(),
        }
    )
    doc.insert(ignore_permissions=True)
    return {"handover": format_handover(doc), "status": "Cancelled"}
