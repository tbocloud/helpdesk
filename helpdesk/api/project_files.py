"""Project files: documents, prompts and PDFs shared with everyone on a project.

Each file is a private Frappe File attached to the Project, so opening
/private/files/... is decided by Frappe's File permission, which defers to read
access on the Project (helpdesk.tasky.permissions). An HD Project File record
adds the folder it sits in (HD Project Folder, nested up to MAX_DEPTH), who the
file is "for" and its status (Active or Superseded). Files and folders carry a
comment thread (Frappe Comments on the HD Project File or HD Project Folder),
read and written only through this module. See docs/project-files.md.
"""

import html

import frappe
from frappe import _
from frappe.core.api.file import get_max_file_size
from frappe.query_builder.functions import Count
from frappe.utils import escape_html, get_fullname

from helpdesk.helpdesk.doctype.hd_project_file.hd_project_file import ACTIVE, SUPERSEDED
from helpdesk.helpdesk.doctype.hd_project_folder.hd_project_folder import (
    MAX_DEPTH,
    FolderTree,
)
from helpdesk.tasky.permissions import (
    can_add_tasks,
    can_manage_project,
    get_project_team,
)

PROJECT_FILE = "HD Project File"
PROJECT_FILE_USER = "HD Project File User"
PROJECT_FOLDER = "HD Project Folder"
TEXT_EXTENSIONS = (".md", ".markdown", ".txt")
# the in-app viewer is for prompts and notes; bigger text files are downloaded
MAX_TEXT_BYTES = 2 * 1024 * 1024
# one folder upload, so a dropped home directory doesn't become thousands of requests
MAX_UPLOAD_FILES = 200
# a comment is a remark on a version, not a document; long text belongs in a file
MAX_COMMENT_LENGTH = 5000


@frappe.whitelist()
def list_project_files(
    project: str,
    folder: str | None = None,
    for_me: bool = False,
    show_superseded: bool = False,
) -> dict:
    """Every folder on the project, and the files in `folder` (the top level when
    empty), newest first, with who each is for, its status, its comment count and
    what the user may do.

    `for_me` lists, from every folder, the files marked for the user or in a
    folder for them (a folder's "For" reaches its subfolders).

    Superseded files and subfolders (by their own status or a folder above them)
    are left out and counted in `superseded_hidden`, unless `show_superseded` or
    the open folder is superseded itself: whoever opens an old version sees all of
    it. `folders` always lists every folder, for the breadcrumb and the move dialog;
    `hiding_superseded` tells the page whether to leave superseded ones out.
    """
    project = _check_read(project)
    user = frappe.session.user
    is_manager = can_manage_project(project, user)
    tree = FolderTree(project)
    folder = str(folder or "") or None
    if folder and folder not in tree.rows:
        frappe.throw(_("This folder doesn't exist any more."), frappe.DoesNotExistError)
    for_me = frappe.utils.sbool(for_me)
    hiding = not frappe.utils.sbool(show_superseded) and (
        for_me or not tree.is_superseded(folder)
    )
    files = _project_files(project)
    records = _records_by_file([f.name for f in files])
    file_of = {r.name: f for f, r in records.items()}
    people = _people(PROJECT_FILE, [r.name for r in records.values()])
    comments = _comment_counts(PROJECT_FILE, [r.name for r in records.values()])
    folders = _folders(tree, user, is_manager, records.values())
    hidden = 0
    if hiding and not for_me:
        hidden = sum(
            1
            for f in folders
            if f["parent_folder"] == folder
            and (f["status"] == SUPERSEDED or f["superseded_via_parent"])
        )
    rows = []
    for f in files:
        record = records.get(f.name) or frappe._dict()
        file_folder = record.folder if record.folder in tree.rows else None
        for_users = people.get(record.name, [])
        is_for_me = any(u["user"] == user for u in for_users)
        via_folder = user in tree.people_for(file_folder)
        if for_me:
            if not (is_for_me or via_folder):
                continue
        elif file_folder != folder:
            continue
        status = record.status or ACTIVE
        in_superseded_folder = tree.is_superseded(file_folder)
        if hiding and (status == SUPERSEDED or in_superseded_folder):
            hidden += 1
            continue
        replacement = records.get(file_of.get(record.superseded_by))
        may_change = is_manager or f.owner == user
        rows.append(
            {
                "name": f.name,
                "project_file": record.name if record else None,
                "file_name": f.file_name,
                "file_url": f.file_url,
                "file_size": f.file_size,
                "uploaded_by": f.owner,
                "uploaded_by_name": f.uploaded_by_name or f.owner,
                "creation": f.creation,
                "folder": file_folder,
                "folder_path": tree.path(file_folder),
                "for_users": for_users,
                "is_for_me": is_for_me,
                "shared_via_folder": via_folder,
                "status": status,
                "superseded_by": (
                    {
                        "name": replacement.file,
                        "label": replacement.file_name,
                        "folder": (
                            replacement.folder
                            if replacement.folder in tree.rows
                            else None
                        ),
                    }
                    if replacement
                    else None
                ),
                "status_note": record.status_note or "",
                "status_changed_by_name": record.status_changed_by_name or "",
                "status_changed_on": record.status_changed_on,
                "in_superseded_folder": in_superseded_folder,
                "comment_count": comments.get(record.name, 0),
                "can_delete": may_change,
                "can_edit_for": may_change,
            }
        )
    current = next((f for f in folders if f["name"] == folder), None)
    return {
        "files": rows,
        "folders": folders,
        "folder": {**current, "path": tree.path(folder)} if current else None,
        "total": len(files),
        "hiding_superseded": hiding,
        "superseded_hidden": hidden,
        "team": _team(project),
        "can_upload": can_add_tasks(project, user),
        "max_file_size": get_max_file_size(),
        "max_depth": MAX_DEPTH,
        "max_upload_files": MAX_UPLOAD_FILES,
    }


@frappe.whitelist(methods=["POST"])
def upload_project_file(
    project: str,
    for_users: str | list | None = None,
    project_folder: str | None = None,
) -> dict:
    """Attach the uploaded file (multipart field "file") to the project, privately,
    in `project_folder` when given. People are told about files in folders once the
    whole upload is done (notify_folder_upload), not per file.

    Not called `folder`: frappe-ui's FileUploadHandler always posts a `folder` form
    field (the File doctype's "Home" folder), which would override ours."""
    request = getattr(frappe.local, "request", None)
    upload = request.files.get("file") if request else None
    if not upload:
        frappe.throw(_("Choose a file to upload."))
    return add_project_file(
        project, upload.filename, upload.stream.read(), for_users, project_folder
    )


def add_project_file(
    project: str,
    file_name: str,
    content: bytes,
    for_users: str | list | None = None,
    folder: str | None = None,
) -> dict:
    """Save `content` as a private File on the project, in `folder` when given, and
    record who it is for.

    Goes through the File doctype like any attachment, so the site's size limit and
    HD File Storage Settings (S3, when "Project" is one of its document types) apply.
    """
    project = _check_read(project)
    _check_can_add(project)
    if folder:
        folder = _get_folder(project, folder).name
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
            "folder": folder or None,
            "for_users": [{"user": u} for u in _parse_list(for_users)],
        }
    ).insert(ignore_permissions=True)
    return {"name": file_doc.name, "project_file": record.name}


@frappe.whitelist(methods=["POST"])
def set_project_file_for(project: str, file: str, for_users: str | list) -> dict:
    """Change who a file is for; people newly added are notified."""
    project = _check_read(project)
    file_doc = _get_project_file(project, file)
    _check_can_change(project, file_doc)
    record = _file_record(project, file_doc.name)
    record.set("for_users", [{"user": u} for u in _parse_list(for_users)])
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


@frappe.whitelist(methods=["POST"])
def move_project_file(project: str, file: str, folder: str | None = None) -> dict:
    """Put a file in another folder, or at the top level when `folder` is empty.

    The people the target folder (or one above it) is for are told, as for an upload.
    """
    project = _check_read(project)
    file_doc = _get_project_file(project, file)
    _check_can_change(project, file_doc)
    target = _get_folder(project, folder).name if folder else None
    record = _file_record(project, file_doc.name)
    if (record.folder or None) != target:
        record.folder = target
        record.save(ignore_permissions=True)
        if target:
            FolderTree(project).notify_new_files([record])
    return {"project_file": record.name, "folder": record.folder}


@frappe.whitelist(methods=["POST"])
def create_project_folder(
    project: str,
    folder_name: str,
    description: str | None = None,
    for_users: str | list | None = None,
    parent_folder: str | None = None,
) -> dict:
    """Anyone who may add files may make a folder, at the top level or inside
    `parent_folder`; the people it is for are notified."""
    project = _check_read(project)
    _check_can_add(project)
    if parent_folder:
        parent_folder = _get_folder(project, parent_folder).name
    folder = frappe.get_doc(
        {
            "doctype": PROJECT_FOLDER,
            "project": project,
            "folder_name": folder_name,
            "parent_folder": parent_folder or None,
            "description": description,
            "for_users": [{"user": u} for u in _parse_list(for_users)],
        }
    ).insert(ignore_permissions=True)
    return {"name": folder.name, "folder_name": folder.folder_name}


@frappe.whitelist(methods=["POST"])
def update_project_folder(
    project: str, folder: str, folder_name: str, description: str | None = None
) -> dict:
    """Rename a folder or change its description."""
    project = _check_read(project)
    folder_doc = _get_folder(project, folder)
    _check_can_change(project, folder_doc)
    folder_doc.update({"folder_name": folder_name, "description": description})
    folder_doc.save(ignore_permissions=True)
    return {"name": folder_doc.name, "folder_name": folder_doc.folder_name}


@frappe.whitelist(methods=["POST"])
def move_project_folder(
    project: str, folder: str, parent_folder: str | None = None
) -> dict:
    """Put a folder, with everything in it, inside another one or at the top level.

    HDProjectFolder.validate refuses a move into itself or its own subfolders,
    deeper than MAX_DEPTH, or next to a folder with the same name.
    """
    project = _check_read(project)
    folder_doc = _get_folder(project, folder)
    _check_can_change(project, folder_doc)
    if parent_folder:
        parent_folder = _get_folder(project, parent_folder).name
    folder_doc.parent_folder = parent_folder or None
    folder_doc.save(ignore_permissions=True)
    return {"name": folder_doc.name, "parent_folder": folder_doc.parent_folder}


@frappe.whitelist(methods=["POST"])
def set_project_folder_for(project: str, folder: str, for_users: str | list) -> dict:
    """Change who a folder is for; people newly added are notified."""
    project = _check_read(project)
    folder_doc = _get_folder(project, folder)
    _check_can_change(project, folder_doc)
    folder_doc.set("for_users", [{"user": u} for u in _parse_list(for_users)])
    folder_doc.save(ignore_permissions=True)
    return {"name": folder_doc.name, "for_users": folder_doc.assignees()}


@frappe.whitelist(methods=["POST"])
def delete_project_folder(project: str, folder: str) -> None:
    """Delete a folder; its files and subfolders move up to its parent
    (HDProjectFolder.on_trash), so nothing in it is lost."""
    project = _check_read(project)
    folder_doc = _get_folder(project, folder)
    _check_can_change(project, folder_doc)
    frappe.delete_doc(PROJECT_FOLDER, folder_doc.name, ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def create_folder_paths(
    project: str, paths: str | list, parent_folder: str | None = None
) -> dict:
    """For a folder upload: make the folders in `paths` ("Clients/Acme") under
    `parent_folder` (the top level when empty) and return {path: folder}.

    A folder that already has that name in that place is used as it is.
    """
    project = _check_read(project)
    _check_can_add(project)
    if parent_folder:
        parent_folder = _get_folder(project, parent_folder).name
    wanted = _parse_list(paths)
    if len(wanted) > MAX_UPLOAD_FILES:
        frappe.throw(_("Upload at most {0} files at a time.").format(MAX_UPLOAD_FILES))
    tree = FolderTree(project)
    result = {}
    for path in wanted:
        current = parent_folder
        for part in path.split("/"):
            part = " ".join(part.split())
            if part:
                current = _child_folder(tree, project, current, part)
        result[path] = current
    return result


@frappe.whitelist(methods=["POST"])
def notify_folder_upload(project: str, files: str | list) -> None:
    """After an upload: tell the people of the folders the files went into, once
    each for the whole batch (FolderTree.notify_new_files).

    Only files the caller added count, so this can't announce someone else's files.
    """
    project = _check_read(project)
    _check_can_add(project)
    names = _parse_list(files)
    if not names:
        return
    record = frappe.qb.DocType(PROJECT_FILE)
    found = (
        frappe.qb.from_(record)
        .select(record.name)
        .where(
            (record.project == project)
            & (record.file.isin(names))
            & (record.folder.isnotnull())
            & (record.owner == frappe.session.user)
        )
        .orderby(record.creation)
        .run(pluck=True)
    )
    FolderTree(project).notify_new_files(
        [frappe.get_doc(PROJECT_FILE, n) for n in found]
    )


# --- status and comments, shared by files (kind "file", named by their File) and folders ---


@frappe.whitelist(methods=["POST"])
def set_project_item_status(
    project: str,
    kind: str,
    item: str,
    status: str,
    superseded_by: str | None = None,
    note: str | None = None,
) -> dict:
    """Mark a file or folder Superseded, optionally naming the file or folder that
    replaces it and why, or Active again. The same people as rename and move.

    The people it is for hear that it was replaced (ProjectItem.notify_superseded).
    """
    project = _check_read(project)
    record, added = _item(project, kind, item)
    _check_can_change(project, added)
    if status not in (ACTIVE, SUPERSEDED):
        frappe.throw(_("Status must be Active or Superseded."))
    replacement = None
    if status == SUPERSEDED and superseded_by:
        if superseded_by == item:
            frappe.throw(_("Pick another one as its replacement, not itself."))
        replacement, _added = _item(project, kind, superseded_by)
        if replacement.is_new():
            replacement.insert(ignore_permissions=True)
    record.update(
        {
            "status": status,
            "superseded_by": replacement.name if replacement else None,
            "status_note": (note or "").strip() or None,
        }
    )
    record.save(ignore_permissions=True)
    return {"status": record.status}


@frappe.whitelist()
def list_replacement_choices(project: str, kind: str, item: str) -> list[dict]:
    """The active files or folders (as `kind`) on the project that could replace
    `item`, for the "Replaced by" picker: `{value, label, path}`, `path` being the
    folder they sit in."""
    project = _check_read(project)
    tree = FolderTree(project)

    def where(folder):
        return " / ".join(p["folder_name"] for p in tree.path(folder))

    if kind == "folder":
        return [
            {
                "value": name,
                "label": tree.rows[name].folder_name,
                "path": where(tree.rows[name].parent_folder),
            }
            for name in tree.order()
            if name != item and tree.rows[name].status != SUPERSEDED
        ]
    if kind != "file":
        frappe.throw(_("Kind must be file or folder."))
    files = _project_files(project)
    records = _records_by_file([f.name for f in files])
    choices = []
    for f in files:
        record = records.get(f.name) or frappe._dict()
        if f.name != item and record.status != SUPERSEDED:
            choices.append(
                {
                    "value": f.name,
                    "label": f.file_name,
                    "path": where(
                        record.folder if record.folder in tree.rows else None
                    ),
                }
            )
    return choices


@frappe.whitelist()
def list_item_comments(project: str, kind: str, item: str) -> dict:
    """The comments on a file or folder, oldest first, and the project team for
    @mentions."""
    project = _check_read(project)
    record, _added = _item(project, kind, item)
    user = frappe.session.user
    is_manager = can_manage_project(project, user)
    rows = [] if record.is_new() else _item_comments(record)
    return {
        "comments": [
            {
                "name": r.name,
                "text": html.unescape(r.content or ""),
                "author": r.owner,
                "author_name": r.author_name or r.owner,
                "creation": r.creation,
                "edited": r.modified != r.creation,
                "can_edit": r.owner == user,
                "can_delete": is_manager or r.owner == user,
            }
            for r in rows
        ],
        "team": _team(project),
        "can_comment": can_add_tasks(project, user),
    }


@frappe.whitelist(methods=["POST"])
def add_item_comment(
    project: str,
    kind: str,
    item: str,
    content: str,
    mentions: str | list | None = None,
) -> dict:
    """Comment on a file or folder. `mentions` are people on the project team
    @mentioned in it (anyone else is ignored); they, the people the item is for and
    whoever added it are notified, except the author."""
    project = _check_read(project)
    _check_can_comment(project)
    record, _added = _item(project, kind, item)
    text = _comment_text(content)
    if record.is_new():
        record.insert(ignore_permissions=True)
    user = frappe.session.user
    comment = frappe.get_doc(
        {
            "doctype": "Comment",
            "comment_type": "Comment",
            "reference_doctype": record.doctype,
            "reference_name": record.name,
            "comment_email": user,
            "comment_by": get_fullname(user),
            # plain text, escaped: Comment.validate sanitizes it as HTML
            "content": escape_html(text),
        }
    ).insert(ignore_permissions=True)
    record.notify_comment(comment.name, text, _mentions(project, mentions))
    return {"name": comment.name}


@frappe.whitelist(methods=["POST"])
def edit_item_comment(
    project: str, comment: str, content: str, mentions: str | list | None = None
) -> dict:
    """Change your own comment; people newly @mentioned are notified."""
    project = _check_read(project)
    doc, record = _get_comment(project, comment)
    if doc.owner != frappe.session.user:
        frappe.throw(_("You can only edit your own comments."), frappe.PermissionError)
    text = _comment_text(content)
    doc.content = escape_html(text)
    doc.save(ignore_permissions=True)
    record.notify_comment(doc.name, text, _mentions(project, mentions))
    return {"name": doc.name}


@frappe.whitelist(methods=["POST"])
def delete_item_comment(project: str, comment: str) -> None:
    """Delete your own comment; the project's lead and managers and admins may
    delete any."""
    project = _check_read(project)
    doc, _record = _get_comment(project, comment)
    if doc.owner != frappe.session.user and not can_manage_project(project):
        frappe.throw(
            _("Only the author or the project's lead or manager can delete a comment."),
            frappe.PermissionError,
        )
    frappe.delete_doc("Comment", doc.name, ignore_permissions=True)


# --- helpers ---


def _check_read(project: str) -> str:
    project = str(project or "")
    if not frappe.db.exists("Project", project):
        frappe.throw(
            _("Project not found: {0}").format(project), frappe.DoesNotExistError
        )
    frappe.has_permission("Project", "read", doc=project, throw=True)
    return project


def _check_can_add(project: str) -> None:
    if not can_add_tasks(project):
        frappe.throw(
            _("Only people on this project can add files to it."),
            frappe.PermissionError,
        )


def _check_can_change(project: str, doc) -> None:
    """Whoever added the file or made the folder, the project's lead and managers, and admins."""
    if doc.owner == frappe.session.user or can_manage_project(project):
        return
    message = (
        _(
            "Only the person who made this folder or the project's lead or manager can change it."
        )
        if doc.doctype == PROJECT_FOLDER
        else _(
            "Only the person who added this file or the project's lead or manager can change it."
        )
    )
    frappe.throw(message, frappe.PermissionError)


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


def _get_folder(project: str, folder: str):
    """The folder, refused unless it belongs to this project."""
    folder = str(folder or "")
    if frappe.db.get_value(PROJECT_FOLDER, folder, "project") != project:
        frappe.throw(
            _("This folder isn't part of the project."), frappe.PermissionError
        )
    return frappe.get_doc(PROJECT_FOLDER, folder)


def _item(project: str, kind: str, item: str):
    """(record, what decides who may change it) for a file or a folder on this
    project: the folder twice, or the file's HD Project File (new and unsaved for a
    file added outside this API) and its File, whose owner is the uploader."""
    if kind == "folder":
        folder = _get_folder(project, item)
        return folder, folder
    if kind == "file":
        file_doc = _get_project_file(project, item)
        return _file_record(project, file_doc.name), file_doc
    frappe.throw(_("Kind must be file or folder."))


def _check_can_comment(project: str) -> None:
    if not can_add_tasks(project):
        frappe.throw(
            _("Only people on this project can comment on its files."),
            frappe.PermissionError,
        )


def _comment_text(content: str) -> str:
    text = str(content or "").strip()
    if not text:
        frappe.throw(_("Write something before posting the comment."))
    if len(text) > MAX_COMMENT_LENGTH:
        frappe.throw(
            _("Keep a comment under {0} characters, or add it as a file.").format(
                MAX_COMMENT_LENGTH
            )
        )
    return text


def _mentions(project: str, mentions) -> list[str]:
    team = set(get_project_team(project))
    return [u for u in _parse_list(mentions) if u in team]


def _get_comment(project: str, comment: str):
    """(Comment, its file record or folder), refused unless it is a comment on a
    file or folder of this project."""
    comment = str(comment or "")
    row = frappe.db.get_value(
        "Comment",
        comment,
        ["reference_doctype", "reference_name", "comment_type"],
        as_dict=True,
    )
    if (
        not row
        or row.comment_type != "Comment"
        or row.reference_doctype not in (PROJECT_FILE, PROJECT_FOLDER)
        or frappe.db.get_value(row.reference_doctype, row.reference_name, "project")
        != project
    ):
        frappe.throw(
            _("This comment isn't on the project's files."), frappe.PermissionError
        )
    return (
        frappe.get_doc("Comment", comment),
        frappe.get_doc(row.reference_doctype, row.reference_name),
    )


def _item_comments(record) -> list:
    comment = frappe.qb.DocType("Comment")
    author = frappe.qb.DocType("User")
    return (
        frappe.qb.from_(comment)
        .left_join(author)
        .on(author.name == comment.owner)
        .select(
            comment.name,
            comment.content,
            comment.owner,
            comment.creation,
            comment.modified,
            author.full_name.as_("author_name"),
        )
        .where(
            (comment.reference_doctype == record.doctype)
            & (comment.reference_name == record.name)
            & (comment.comment_type == "Comment")
        )
        .orderby(comment.creation)
        .run(as_dict=True)
    )


def _file_record(project: str, file: str):
    """The file's HD Project File, or a new one for a file added outside this API."""
    name = frappe.db.get_value(PROJECT_FILE, {"file": file}, "name")
    if name:
        return frappe.get_doc(PROJECT_FILE, name)
    return frappe.new_doc(PROJECT_FILE).update({"project": project, "file": file})


def _child_folder(tree: FolderTree, project: str, parent: str | None, name: str) -> str:
    """The folder called `name` in `parent`, made when missing; `tree` is kept current."""
    for child in tree.children.get(parent, []):
        if tree.rows[child].folder_name.casefold() == name.casefold():
            return child
    doc = frappe.get_doc(
        {
            "doctype": PROJECT_FOLDER,
            "project": project,
            "folder_name": name,
            "parent_folder": parent,
        }
    ).insert(ignore_permissions=True)
    tree.rows[doc.name] = frappe._dict(
        name=doc.name, folder_name=doc.folder_name, parent_folder=parent, status=ACTIVE
    )
    tree.children.setdefault(parent, []).append(doc.name)
    return doc.name


def _parse_list(values) -> list[str]:
    """A JSON list (from a form post) or a list, as trimmed non-empty strings."""
    items = frappe.parse_json(values) if isinstance(values, str) else values
    return [str(v).strip() for v in items or [] if str(v or "").strip()]


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


def _records_by_file(files: list[str]) -> dict:
    """{file: HD Project File row (name, file, file_name, folder and status)}"""
    if not files:
        return {}
    record = frappe.qb.DocType(PROJECT_FILE)
    changed_by = frappe.qb.DocType("User")
    rows = (
        frappe.qb.from_(record)
        .left_join(changed_by)
        .on(changed_by.name == record.status_changed_by)
        .select(
            record.name,
            record.file,
            record.file_name,
            record.folder,
            *_status_columns(record, changed_by),
        )
        .where(record.file.isin(files))
        .run(as_dict=True)
    )
    return {r.file: r for r in rows}


def _status_columns(table, changed_by) -> list:
    return [
        table.status,
        table.superseded_by,
        table.status_note,
        table.status_changed_on,
        changed_by.full_name.as_("status_changed_by_name"),
    ]


def _comment_counts(doctype: str, names: list[str]) -> dict:
    """{name: number of comments} for file records or folders, in one query."""
    if not names:
        return {}
    comment = frappe.qb.DocType("Comment")
    return dict(
        frappe.qb.from_(comment)
        .select(comment.reference_name, Count(comment.name))
        .where(
            (comment.reference_doctype == doctype)
            & (comment.reference_name.isin(names))
            & (comment.comment_type == "Comment")
        )
        .groupby(comment.reference_name)
        .run()
    )


def _people(parenttype: str, parents: list[str]) -> dict:
    """{parent: [{user, full_name}]} from the "For" rows of files or folders."""
    if not parents:
        return {}
    row = frappe.qb.DocType(PROJECT_FILE_USER)
    user = frappe.qb.DocType("User")
    found = (
        frappe.qb.from_(row)
        .left_join(user)
        .on(user.name == row.user)
        .select(row.parent, row.user, user.full_name)
        .where((row.parenttype == parenttype) & (row.parent.isin(parents)))
        .orderby(row.idx)
        .run(as_dict=True)
    )
    result: dict = {}
    for r in found:
        result.setdefault(r.parent, []).append(
            {"user": r.user, "full_name": r.full_name or r.user}
        )
    return result


def _folders(tree: FolderTree, user: str, is_manager: bool, records) -> list[dict]:
    """Every folder, parents before subfolders, with counts and who it is for."""
    names = tree.order()
    if not names:
        return []
    folder = frappe.qb.DocType(PROJECT_FOLDER)
    owner = frappe.qb.DocType("User")
    changed_by = frappe.qb.DocType("User").as_("changed_by")
    details = {
        r.name: r
        for r in (
            frappe.qb.from_(folder)
            .left_join(owner)
            .on(owner.name == folder.owner)
            .left_join(changed_by)
            .on(changed_by.name == folder.status_changed_by)
            .select(
                folder.name,
                folder.description,
                folder.owner,
                folder.creation,
                owner.full_name.as_("created_by_name"),
                *_status_columns(folder, changed_by),
            )
            .where(folder.name.isin(names))
            .run(as_dict=True)
        )
    }
    comments = _comment_counts(PROJECT_FOLDER, names)
    counts: dict = {}
    for r in records:
        if r.folder:
            counts[r.folder] = counts.get(r.folder, 0) + 1
    people = _people(PROJECT_FOLDER, names)
    result = []
    for name in names:
        row, detail = tree.rows[name], details[name]
        for_users = people.get(name, [])
        result.append(
            {
                "name": name,
                "folder_name": row.folder_name,
                "parent_folder": row.parent_folder or None,
                "depth": tree.depth(name),
                "height": tree.height(name),
                "description": detail.description or "",
                "created_by": detail.owner,
                "created_by_name": detail.created_by_name or detail.owner,
                "creation": detail.creation,
                "file_count": counts.get(name, 0),
                "folder_count": len(tree.children.get(name, [])),
                "for_users": for_users,
                "is_for_me": any(u["user"] == user for u in for_users),
                "for_me_via_parent": user in tree.people_for(row.parent_folder),
                "status": detail.status or ACTIVE,
                "superseded_by": (
                    {
                        "name": detail.superseded_by,
                        "label": tree.rows[detail.superseded_by].folder_name,
                    }
                    if detail.superseded_by in tree.rows
                    else None
                ),
                "status_note": detail.status_note or "",
                "status_changed_by_name": detail.status_changed_by_name or "",
                "status_changed_on": detail.status_changed_on,
                "superseded_via_parent": tree.is_superseded(row.parent_folder),
                "comment_count": comments.get(name, 0),
                "can_change": is_manager or detail.owner == user,
            }
        )
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
