"""A project's access entries: its Git repositories, backend and frontend URLs, apps,
servers and logins, with notes (docs/project-access.md).

The doctype is System Manager only. Reading checks `can_see_project_access`, changing
and showing a password `can_handle_project_access`; then everything works as the system.
Passwords are never part of a list: `reveal_access_password` returns one and writes who
looked on the project's timeline."""

import frappe
from frappe import _
from frappe.utils import cstr, escape_html, get_fullname
from frappe.utils.password import get_decrypted_password

from helpdesk.tasky.permissions import can_handle_project_access, can_see_project_access

ACCESS = "HD Project Access"
EDITABLE = ("kind", "environment", "label", "url", "username", "notes")


def options(fieldname: str) -> list[str]:
    """A Select field's choices, from the doctype itself."""
    return [
        o for o in frappe.get_meta(ACCESS).get_field(fieldname).options.split("\n") if o
    ]


def require_project(project: str) -> None:
    if not project or not frappe.db.exists("Project", project):
        frappe.throw(_("Project not found: {0}").format(project))


def require_see(project: str) -> None:
    require_project(project)
    if not can_see_project_access(project):
        frappe.throw(_("You can't see this project."), frappe.PermissionError)


def require_handle(project: str) -> None:
    require_project(project)
    if not can_handle_project_access(project):
        frappe.throw(
            _("Only the project's managers and developers can do this."),
            frappe.PermissionError,
        )


def entry_doc(name: str, project: str):
    """The entry, if it belongs to the project."""
    doc = frappe.get_doc(ACCESS, name)
    if doc.project != project:
        frappe.throw(_("That entry belongs to another project."))
    return doc


def stored_password(name: str) -> str | None:
    return get_decrypted_password(ACCESS, name, "password", raise_exception=False)


def format_entry(doc) -> dict:
    """An entry as the page shows it: whether it has a password, never the password."""
    return {
        "name": doc.name,
        **{field: doc.get(field) for field in EDITABLE},
        "has_password": bool(stored_password(doc.name)),
        "added_by": doc.added_by,
        "added_by_name": get_fullname(doc.added_by) if doc.added_by else None,
        "modified": cstr(doc.modified),
    }


@frappe.whitelist()
def get_project_access(project: str) -> dict:
    """The project's entries, grouped by kind on the page, with no passwords."""
    require_see(project)
    kinds = options("kind")
    names = frappe.qb.get_query(
        ACCESS, fields=["name"], filters={"project": project}, order_by="creation asc"
    ).run(pluck=True)
    entries = [format_entry(frappe.get_doc(ACCESS, n)) for n in names]
    entries.sort(
        key=lambda e: kinds.index(e["kind"]) if e["kind"] in kinds else len(kinds)
    )
    return {
        "entries": entries,
        "kinds": kinds,
        "environments": options("environment"),
        "can_handle": can_handle_project_access(project),
    }


@frappe.whitelist(methods=["POST"])
def save_access_entry(project: str, entry: dict | str, name: str | None = None) -> dict:
    """Add an entry, or change one. A password is changed only when a new one is sent;
    `clear_password` removes it."""
    require_handle(project)
    entry = frappe.parse_json(entry) if isinstance(entry, str) else entry or {}
    values = {field: cstr(entry.get(field)).strip() or None for field in EDITABLE}
    if not values["label"]:
        frappe.throw(_('Give it a name, e.g. "Backend repository" or "Demo login".'))
    if values["kind"] not in options("kind"):
        frappe.throw(_("Choose what kind of entry this is."))
    if values["environment"] and values["environment"] not in options("environment"):
        frappe.throw(_("Choose Live, Staging, Demo or Development."))
    if name:
        doc = entry_doc(name, project)
    else:
        doc = frappe.new_doc(ACCESS)
        doc.update({"project": project, "added_by": frappe.session.user})
    doc.update(values)
    password = cstr(entry.get("password"))
    if password:
        doc.password = password
    elif entry.get("clear_password"):
        doc.password = ""
    doc.save(ignore_permissions=True)
    return format_entry(doc)


@frappe.whitelist(methods=["POST"])
def delete_access_entry(project: str, name: str) -> dict:
    """Remove an entry and its password; the project's timeline says who did."""
    require_handle(project)
    doc = entry_doc(name, project)
    label = doc.label
    frappe.delete_doc(ACCESS, doc.name, ignore_permissions=True)
    frappe.get_doc("Project", project).add_comment(
        "Info",
        _("{0} removed the access entry {1}").format(
            get_fullname(frappe.session.user), escape_html(label)
        ),
    )
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def reveal_access_password(project: str, name: str) -> dict:
    """One entry's password, and a line on the project's timeline that this person looked."""
    require_handle(project)
    doc = entry_doc(name, project)
    password = stored_password(doc.name)
    if not password:
        frappe.throw(_("No password was saved for this entry."))
    frappe.get_doc("Project", project).add_comment(
        "Info",
        _("{0} viewed the password of {1}").format(
            get_fullname(frappe.session.user), escape_html(doc.label)
        ),
    )
    return {"password": password}
