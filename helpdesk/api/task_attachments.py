"""Task attachments: screenshots and screen recordings that show an issue.

Each attachment is a private Frappe File attached to the Task, so opening
/private/files/... (or the S3 download route) is decided by Frappe's File
permission, which defers to read access on the Task (helpdesk.tasky.permissions).
Only images and videos are taken, checked by extension and by their first bytes,
so a renamed file is refused. See docs/task-attachments.md.
"""

import frappe
from frappe import _
from frappe.core.api.file import get_max_file_size
from frappe.utils import escape_html

from helpdesk.api.content_board import user_full_names
from helpdesk.tasky.permissions import can_manage_project

MB = 1024 * 1024
# a screenshot is a few MB at most; anything bigger is usually a photo of a screen
MAX_IMAGE_BYTES = 10 * MB
# about a minute of a 1080p screen recording
MAX_VIDEO_BYTES = 50 * MB
IMAGE_EXTENSIONS = ("png", "jpg", "jpeg", "webp", "gif")
VIDEO_EXTENSIONS = ("mp4", "webm", "mov")
# the formats each extension may hold; mp4 and mov are the same container (ISO BMFF)
FORMATS = {
    "png": "png",
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "webp": "webp",
    "gif": "gif",
    "mp4": "isobmff",
    "mov": "isobmff",
    "webm": "webm",
}
# top-level atoms an old QuickTime file may start with instead of "ftyp"
QUICKTIME_ATOMS = (b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot")


@frappe.whitelist()
def list_task_attachments(task: str) -> dict:
    """The task's images and videos, newest first, with what the user may do and
    the size limits the upload button checks before sending a file."""
    doc = _get_task(task)
    user = frappe.session.user
    is_manager = can_manage_project(doc.project, user)
    files = frappe.qb.get_query(
        "File",
        fields=["name", "file_name", "file_url", "file_size", "owner", "creation"],
        filters={
            "attached_to_doctype": "Task",
            "attached_to_name": doc.name,
            "is_folder": 0,
        },
        order_by="creation desc",
    ).run(as_dict=True)
    files = [f for f in files if media_kind(f.file_name)]
    names = user_full_names({f.owner for f in files})
    return {
        "attachments": [
            {
                "name": f.name,
                "file_name": f.file_name,
                "file_url": f.file_url,
                "file_size": f.file_size,
                "kind": media_kind(f.file_name),
                "uploaded_by": f.owner,
                "uploaded_by_name": names.get(f.owner, f.owner),
                "creation": f.creation,
                "can_delete": is_manager or f.owner == user,
            }
            for f in files
        ],
        "can_upload": can_upload(doc),
        "limits": upload_limits(),
        "extensions": {"image": IMAGE_EXTENSIONS, "video": VIDEO_EXTENSIONS},
    }


@frappe.whitelist(methods=["POST"])
def upload_task_attachment(task: str) -> dict:
    """Attach the uploaded image or video (multipart field "file") to the task."""
    request = getattr(frappe.local, "request", None)
    upload = request.files.get("file") if request else None
    if not upload:
        frappe.throw(_("Choose an image or a video to upload."))
    return add_task_attachment(task, upload.filename, upload.stream.read())


def add_task_attachment(task: str, file_name: str, content: bytes) -> dict:
    """Save `content` as a private File on the task, after checking its type and size.

    Goes through the File doctype like any attachment, so the site's size limit and
    HD File Storage Settings (S3, when "Task" is one of its document types) apply.
    """
    doc = _get_task(task)
    if not can_upload(doc):
        frappe.throw(
            _(
                "Only the task's assignees and the people who run its project can add files."
            ),
            frappe.PermissionError,
        )
    kind = check_media(file_name, content)
    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "attached_to_doctype": "Task",
            "attached_to_name": doc.name,
            "is_private": 1,
            "content": content,
        }
    ).insert(ignore_permissions=True)
    _log(doc, _("Attached {0}"), file_doc.file_name)
    return {"name": file_doc.name, "file_url": file_doc.file_url, "kind": kind}


@frappe.whitelist(methods=["POST"])
def delete_task_attachment(task: str, file: str) -> None:
    """The person who added it, the project's lead and managers, and admins may remove it."""
    doc = _get_task(task)
    file_doc = _get_attachment(doc, file)
    if file_doc.owner != frappe.session.user and not can_manage_project(doc.project):
        frappe.throw(
            _(
                "Only the person who added this file or the project's lead or manager can remove it."
            ),
            frappe.PermissionError,
        )
    frappe.delete_doc("File", file_doc.name, ignore_permissions=True)
    _log(doc, _("Removed {0}"), file_doc.file_name)


def can_upload(doc) -> bool:
    """Whoever may change the task: its assignees, the project's lead, managers and
    coordinators, and admins (Task write permission, see task_has_permission)."""
    return bool(frappe.has_permission("Task", "write", doc=doc))


def upload_limits() -> dict:
    """Bytes per kind. The site's own limit (System Settings → Max File Size) caps the
    request before it reaches this module, so it caps both kinds here too."""
    site = get_max_file_size()
    return {
        "image": min(MAX_IMAGE_BYTES, site),
        "video": min(MAX_VIDEO_BYTES, site),
    }


def media_kind(file_name: str | None) -> str | None:
    """ "image" or "video" by the file's extension; None for anything else."""
    ext = _extension(file_name)
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return None


def check_media(file_name: str, content: bytes) -> str:
    """Refuse anything but an image or video whose bytes match its extension, or one
    over the size limit; returns its kind."""
    kind = media_kind(file_name)
    if not kind:
        frappe.throw(
            _("Only images ({0}) and videos ({1}) can be attached.").format(
                _type_list(IMAGE_EXTENSIONS), _type_list(VIDEO_EXTENSIONS)
            )
        )
    if sniff_format(content) != FORMATS[_extension(file_name)]:
        frappe.throw(
            _("{0} isn't a real {1} file. Export it again and attach that.").format(
                file_name, _extension(file_name).upper()
            )
        )
    limit = upload_limits()[kind]
    if len(content) > limit:
        frappe.throw(
            _("{0} is larger than {1} MB, the limit for {2}.").format(
                file_name,
                round(limit / MB),
                _("an image") if kind == "image" else _("a video"),
            )
        )
    return kind


def sniff_format(content: bytes) -> str | None:
    """The format the file's first bytes (its magic number) say it is."""
    head = content[:16]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    if head[4:8] == b"ftyp" or head[4:8] in QUICKTIME_ATOMS:
        return "isobmff"
    return None


def attachment_counts(tasks: list[str]) -> dict:
    """{task: number of images and videos}, for showing on the task."""
    if not tasks:
        return {}
    rows = frappe.qb.get_query(
        "File",
        fields=["attached_to_name", "file_name"],
        filters={
            "attached_to_doctype": "Task",
            "attached_to_name": ("in", tasks),
            "is_folder": 0,
        },
    ).run(as_dict=True)
    counts: dict[str, int] = {}
    for row in rows:
        if media_kind(row.file_name):
            counts[row.attached_to_name] = counts.get(row.attached_to_name, 0) + 1
    return counts


def _get_task(task: str):
    doc = frappe.get_doc("Task", str(task or ""))
    doc.check_permission("read")
    return doc


def _get_attachment(doc, file: str):
    """The File, refused unless it is attached to this task."""
    attached = frappe.db.get_value(
        "File",
        str(file or ""),
        ["name", "attached_to_doctype", "attached_to_name"],
        as_dict=True,
    )
    if (
        not attached
        or attached.attached_to_doctype != "Task"
        or attached.attached_to_name != doc.name
    ):
        frappe.throw(_("This file isn't attached to the task."), frappe.PermissionError)
    return frappe.get_doc("File", attached.name)


def _log(doc, message: str, file_name: str):
    """An Info note in the task's activity ("Attached screenshot.png")."""
    doc.add_comment("Info", escape_html(message.format(file_name)))


def _type_list(extensions: tuple[str, ...]) -> str:
    return ", ".join(e.upper() for e in extensions)


def _extension(file_name: str | None) -> str:
    name = file_name or ""
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""
