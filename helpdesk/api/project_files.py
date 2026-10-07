"""Project files: documents, prompts and PDFs shared with everyone on a project.

Each file is a private Frappe File attached to the Project, so opening
/private/files/... is decided by Frappe's File permission, which defers to read
access on the Project (helpdesk.tasky.permissions). An HD Project File record
adds who the file is "for". See docs/project-files.md.
"""

import frappe
from frappe import _
from frappe.core.api.file import get_max_file_size
from frappe.query_builder.functions import Count

from helpdesk.tasky.permissions import (
    can_add_tasks,
    can_manage_project,
    get_project_team,
)

PROJECT_FILE = "HD Project File"
PROJECT_FILE_USER = "HD Project File User"
TEXT_EXTENSIONS = (".md", ".markdown", ".txt")
# the in-app viewer is for prompts and notes; bigger text files are downloaded
MAX_TEXT_BYTES = 2 * 1024 * 1024


@frappe.whitelist()
def list_project_files(project: str, for_me: bool = False) -> dict:
    """Files on the project, newest first, with who each is for and what the user may do."""
    project = _check_read(project)
    user = frappe.session.user
    files = _project_files(project)
    assignees = _assignees_by_file([f.name for f in files])
    is_manager = can_manage_project(project, user)
    rows = []
    for f in files:
        record, for_users = assignees.get(f.name, (None, []))
        is_for_me = any(u["user"] == user for u in for_users)
        if frappe.utils.sbool(for_me) and not is_for_me:
            continue
        may_change = is_manager or f.owner == user
        rows.append(
            {
                "name": f.name,
                "project_file": record,
                "file_name": f.file_name,
                "file_url": f.file_url,
                "file_size": f.file_size,
                "uploaded_by": f.owner,
                "uploaded_by_name": f.uploaded_by_name or f.owner,
                "creation": f.creation,
                "for_users": for_users,
                "is_for_me": is_for_me,
                "can_delete": may_change,
                "can_edit_for": may_change,
            }
        )
    return {
        "files": rows,
        "total": len(files),
        "team": _team(project),
        "can_upload": can_add_tasks(project, user),
        "max_file_size": get_max_file_size(),
    }


@frappe.whitelist(methods=["POST"])
def upload_project_file(project: str, for_users: str | list | None = None) -> dict:
    """Attach the uploaded file (multipart field "file") to the project, privately."""
    request = getattr(frappe.local, "request", None)
    upload = request.files.get("file") if request else None
    if not upload:
        frappe.throw(_("Choose a file to upload."))
    return add_project_file(project, upload.filename, upload.stream.read(), for_users)


def add_project_file(
    project: str, file_name: str, content: bytes, for_users: str | list | None = None
) -> dict:
    """Save `content` as a private File on the project and record who it is for.

    Goes through the File doctype like any attachment, so the site's size limit and
    HD File Storage Settings (S3, when "Project" is one of its document types) apply.
    """
    project = _check_read(project)
    if not can_add_tasks(project):
        frappe.throw(
            _("Only people on this project can add files to it."),
            frappe.PermissionError,
        )
    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "attached_to_doctype": "Project",
            "attached_to_name": project,
            "is_private": 1,
            "content": content,
        }
    ).insert(ignore_permissions=True)
    record = frappe.get_doc(
        {
            "doctype": PROJECT_FILE,
            "project": project,
            "file": file_doc.name,
            "for_users": [{"user": u} for u in _parse_users(for_users)],
        }
    ).insert(ignore_permissions=True)
    return {"name": file_doc.name, "project_file": record.name}


@frappe.whitelist(methods=["POST"])
def set_project_file_for(project: str, file: str, for_users: str | list) -> dict:
    """Change who a file is for; people newly added are notified."""
    project = _check_read(project)
    file_doc = _get_project_file(project, file)
    _check_can_change(project, file_doc)
    name = frappe.db.get_value(PROJECT_FILE, {"file": file_doc.name}, "name")
    record = (
        frappe.get_doc(PROJECT_FILE, name)
        if name
        else frappe.new_doc(PROJECT_FILE).update(
            {"project": project, "file": file_doc.name}
        )
    )
    record.set("for_users", [{"user": u} for u in _parse_users(for_users)])
    record.save(ignore_permissions=True)
    return {"project_file": record.name, "for_users": record.assignees()}


@frappe.whitelist(methods=["POST"])
def delete_project_file(project: str, file: str) -> None:
    """The uploader, the project's lead and managers, and admins may delete a file."""
    project = _check_read(project)
    file_doc = _get_project_file(project, file)
    _check_can_change(project, file_doc)
    frappe.delete_doc("File", file_doc.name, ignore_permissions=True)


@frappe.whitelist()
def get_project_file_text(project: str, file: str) -> dict:
    """A Markdown or text file's content, for the in-app viewer."""
    project = _check_read(project)
    file_doc = _get_project_file(project, file)
    if not (file_doc.file_name or "").lower().endswith(TEXT_EXTENSIONS):
        frappe.throw(_("Only Markdown and text files open here. Download this one."))
    if (file_doc.file_size or 0) > MAX_TEXT_BYTES:
        frappe.throw(_("This file is too large to preview. Download it instead."))
    content = file_doc.get_content()
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    return {"file_name": file_doc.file_name, "content": content}


# --- helpers ---


def _check_read(project: str) -> str:
    project = str(project or "")
    if not frappe.db.exists("Project", project):
        frappe.throw(
            _("Project not found: {0}").format(project), frappe.DoesNotExistError
        )
    frappe.has_permission("Project", "read", doc=project, throw=True)
    return project


def _get_project_file(project: str, file: str):
    """The File, refused unless it is attached to this project."""
    file = str(file or "")
    attached = frappe.db.get_value(
        "File",
        file,
        ["attached_to_doctype", "attached_to_name", "is_folder"],
        as_dict=True,
    )
    if (
        not attached
        or attached.is_folder
        or attached.attached_to_doctype != "Project"
        or attached.attached_to_name != project
    ):
        frappe.throw(_("This file isn't part of the project."), frappe.PermissionError)
    return frappe.get_doc("File", file)


def _check_can_change(project: str, file_doc) -> None:
    if file_doc.owner == frappe.session.user or can_manage_project(project):
        return
    frappe.throw(
        _(
            "Only the person who added this file or the project's lead or manager can change it."
        ),
        frappe.PermissionError,
    )


def _parse_users(for_users) -> list[str]:
    users = frappe.parse_json(for_users) if isinstance(for_users, str) else for_users
    return [str(u).strip() for u in users or [] if str(u or "").strip()]


def _project_files(project: str) -> list:
    file = frappe.qb.DocType("File")
    user = frappe.qb.DocType("User")
    return (
        frappe.qb.from_(file)
        .left_join(user)
        .on(user.name == file.owner)
        .select(
            file.name,
            file.file_name,
            file.file_url,
            file.file_size,
            file.owner,
            file.creation,
            user.full_name.as_("uploaded_by_name"),
        )
        .where(
            (file.attached_to_doctype == "Project")
            & (file.attached_to_name == project)
            & (file.is_folder == 0)
        )
        .orderby(file.creation, order=frappe.qb.desc)
        .run(as_dict=True)
    )


def _assignees_by_file(files: list[str]) -> dict:
    """{file: (HD Project File name, [{user, full_name}])}"""
    if not files:
        return {}
    record = frappe.qb.DocType(PROJECT_FILE)
    row = frappe.qb.DocType(PROJECT_FILE_USER)
    user = frappe.qb.DocType("User")
    found = (
        frappe.qb.from_(record)
        .left_join(row)
        .on((row.parent == record.name) & (row.parenttype == PROJECT_FILE))
        .left_join(user)
        .on(user.name == row.user)
        .select(
            record.name,
            record.file,
            row.user,
            user.full_name,
        )
        .where(record.file.isin(files))
        .orderby(row.idx)
        .run(as_dict=True)
    )
    result: dict = {}
    for r in found:
        _, people = result.setdefault(r.file, (r.name, []))
        if r.user:
            people.append({"user": r.user, "full_name": r.full_name or r.user})
    return result


def _team(project: str) -> list[dict]:
    team = get_project_team(project)
    names = (
        dict(
            frappe.get_all(
                "User",
                filters={"name": ("in", team)},
                fields=["name", "full_name"],
                as_list=True,
            )
        )
        if team
        else {}
    )
    return [{"user": u, "full_name": names.get(u) or u} for u in team]


def file_counts(projects: list[str]) -> dict:
    """{project: number of files}, for the project cards."""
    if not projects:
        return {}
    file = frappe.qb.DocType("File")
    return dict(
        frappe.qb.from_(file)
        .select(file.attached_to_name, Count(file.name))
        .where(
            (file.attached_to_doctype == "Project")
            & (file.attached_to_name.isin(projects))
            & (file.is_folder == 0)
        )
        .groupby(file.attached_to_name)
        .run()
    )
