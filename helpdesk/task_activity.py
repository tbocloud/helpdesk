"""A task's history for its details window, newest first.

See docs/workspace-pages.md "Activity".
"""

import html
import json
import re

import frappe
from frappe import _
from frappe.query_builder import Criterion, Order
from frappe.utils import flt, get_datetime, getdate, strip_html
from frappe.utils.dateutils import parse_date

from helpdesk.api.content_board import user_full_names

MAX_ITEMS = 300
MAX_COMMENT_LENGTH = 5000
# a note saved with a status or due date change already explains that change
NOTE_WINDOW_SECONDS = 10
NOTE_EXPLAINS = {
    "Due date moved": ("due",),
    "On hold": ("status", "due"),
    "Resumed": ("status", "due"),
    "Sent for review": ("status",),
    "Approved": ("status",),
    "Sent back": ("status",),
    "Handed over": ("status",),
    "Reassigned": ("status",),
}
# field changes in a Version that become their own item
TRACKED_FIELDS = {
    "status": "status",
    "exp_end_date": "due",
    "custom_estimated_hours": "estimate",
}
# kinds whose "to" is a person; elsewhere it is a status, date or hours
PERSON_KINDS = ("assigned", "unassigned")
ORIGIN_FIELDS = (
    ("hd_ticket", "ticket"),
    ("content_post", "content_post"),
    ("custom_recurring_task", "recurring"),
)


class TaskActivity:
    def __init__(self, doc):
        self.doc = doc

    def get_items(self) -> list[dict]:
        items = [
            self.created_item(),
            *self.assignment_items(),
            *self.change_items(),
            *self.comment_items(),
            *self.time_items(),
        ]
        items = self.drop_explained_changes(items)
        # microseconds keep a save's own order; the shown time is cut to seconds below
        items.sort(key=lambda i: get_datetime(i["at"]), reverse=True)
        items = items[:MAX_ITEMS]
        self.add_names(items)
        for item in items:
            item["at"] = _to_seconds(item["at"])
        return items

    def created_item(self) -> dict:
        origin = {"type": None, "name": None}
        for fieldname, origin_type in ORIGIN_FIELDS:
            if self.doc.get(fieldname):
                origin = {"type": origin_type, "name": self.doc.get(fieldname)}
                break
        return {
            "kind": "created",
            "at": self.doc.creation,
            "by": self.doc.owner,
            "origin": origin,
        }

    def assignment_items(self) -> list[dict]:
        todos = frappe.qb.get_query(
            "ToDo",
            fields=[
                "allocated_to",
                "assigned_by",
                "owner",
                "description",
                "status",
                "creation",
                "modified",
                "modified_by",
            ],
            filters={"reference_type": "Task", "reference_name": self.doc.name},
            order_by="creation desc",
            limit=MAX_ITEMS,
        ).run(as_dict=True)
        items = []
        for todo in todos:
            items.append(
                {
                    "kind": "assigned",
                    "at": todo.creation,
                    "by": todo.assigned_by or todo.owner,
                    "to": todo.allocated_to,
                    "note": self.assignment_note(todo.description),
                }
            )
            if todo.status == "Cancelled":
                items.append(
                    {
                        "kind": "unassigned",
                        "at": todo.modified,
                        "by": todo.modified_by,
                        "to": todo.allocated_to,
                    }
                )
        return items

    def assignment_note(self, description: str | None) -> str | None:
        """Frappe fills an empty assignment note with its own text, and a content plan
        fills it with the task's subject; neither says anything."""
        note = plain_text(description)
        generic = {
            "Assignment for Task {0}".format(self.doc.name),
            _("Assignment for {0} {1}").format("Task", self.doc.name),
            _("Assignment for {0} {1}").format(_("Task"), self.doc.name),
            plain_text(self.doc.subject),
        }
        return note if note and note not in generic else None

    def change_items(self) -> list[dict]:
        version = frappe.qb.DocType("Version")
        # only saves touching a tracked field count toward the cap, so edits to other
        # fields can't push older status or due date changes out
        touches_tracked = Criterion.any(
            version.data.like(f'%"{fieldname}"%') for fieldname in TRACKED_FIELDS
        )
        versions = (
            frappe.qb.get_query(
                "Version",
                fields=["data", "owner", "creation"],
                filters={"ref_doctype": "Task", "docname": self.doc.name},
                order_by="creation desc",
                limit=MAX_ITEMS,
            )
            .where(touches_tracked)
            .run(as_dict=True)
        )
        items = []
        for version in versions:
            changed = json.loads(version.data or "{}").get("changed") or []
            for fieldname, old, new in changed:
                kind = TRACKED_FIELDS.get(fieldname)
                if kind:
                    items.append(
                        {
                            "kind": kind,
                            "at": version.creation,
                            "by": version.owner,
                            **self.change_values(kind, old, new),
                        }
                    )
        return items

    @staticmethod
    def change_values(kind: str, old, new) -> dict:
        if kind == "due":
            return {"from": _as_date(old), "to": _as_date(new), "reason": None}
        if kind == "estimate":
            return {"from": flt(old), "to": flt(new)}
        return {"from": old, "to": new}

    def comment_items(self) -> list[dict]:
        comments = frappe.qb.get_query(
            "Comment",
            fields=[
                "name",
                "comment_type",
                "content",
                "comment_email",
                "owner",
                "creation",
            ],
            filters={
                "reference_doctype": "Task",
                "reference_name": self.doc.name,
                # Assigned / Assignment Completed repeat the ToDo rows
                "comment_type": ("in", ("Info", "Comment")),
            },
            order_by="creation desc",
            limit=MAX_ITEMS,
        ).run(as_dict=True)
        return [comment_item(c) for c in comments]

    def time_items(self) -> list[dict]:
        detail = frappe.qb.DocType("Timesheet Detail")
        sheet = frappe.qb.DocType("Timesheet")
        logs = (
            frappe.qb.from_(detail)
            .join(sheet)
            .on(detail.parent == sheet.name)
            .select(detail.hours, detail.from_time, detail.creation, sheet.owner)
            .where(detail.parenttype == "Timesheet")
            .where(detail.task == self.doc.name)
            .where(sheet.docstatus != 2)
            .orderby(detail.creation, order=Order.desc)
            .limit(MAX_ITEMS)
        ).run(as_dict=True)
        return [
            {
                "kind": "time",
                "at": log.creation,
                "by": log.owner,
                "hours": flt(log.hours),
                "date": str(getdate(log.from_time)) if log.from_time else None,
            }
            for log in logs
        ]

    @staticmethod
    def drop_explained_changes(items: list[dict]) -> list[dict]:
        notes = [i for i in items if i["kind"] == "note"]

        def explained(item) -> bool:
            return any(
                note["by"] == item["by"]
                and item["kind"] in _explains(note["text"])
                and abs(
                    (
                        get_datetime(note["at"]) - get_datetime(item["at"])
                    ).total_seconds()
                )
                <= NOTE_WINDOW_SECONDS
                for note in notes
            )

        return [
            i for i in items if i["kind"] not in ("status", "due") or not explained(i)
        ]

    @staticmethod
    def add_names(items: list[dict]):
        users = {i["by"] for i in items} | {
            i["to"] for i in items if i["kind"] in PERSON_KINDS
        }
        names = user_full_names(users - {None})
        for item in items:
            item["by_name"] = names.get(item["by"], item["by"]) if item["by"] else None
            if item["kind"] in PERSON_KINDS:
                item["to_name"] = names.get(item["to"], item["to"])


def comment_item(comment) -> dict:
    """A Comment row as an activity item: the app's Info notes and people's comments."""
    item = {
        "kind": "note" if comment.comment_type == "Info" else "comment",
        "at": comment.creation,
        "by": comment.comment_email or comment.owner,
        "text": plain_text(comment.content),
    }
    if item["kind"] == "comment":
        item["name"] = comment.name
    return item


def plain_text(content: str | None) -> str:
    """Notes and comments are stored as escaped html; the activity shows plain text."""
    text = re.sub(r"<br\s*/?>", "\n", content or "", flags=re.IGNORECASE)
    return html.unescape(strip_html(text)).strip()


def _explains(note_text: str) -> tuple[str, ...]:
    for prefix, kinds in NOTE_EXPLAINS.items():
        if note_text.startswith(prefix) or note_text.startswith(_(prefix)):
            return kinds
    return ()


def _as_date(value) -> str | None:
    if not value:
        return None
    # Versions store dates in the site's display format (e.g. 05-10-2026), which
    # getdate would read month first; parse_date tries the site's format first
    try:
        return parse_date(str(value))
    except Exception:
        # an old Version may hold a display string; show it as it was stored
        return str(value)


def _to_seconds(value) -> str:
    return get_datetime(value).strftime("%Y-%m-%d %H:%M:%S")


def get_activity(task: str) -> dict:
    doc = frappe.get_doc("Task", str(task))
    doc.check_permission("read")
    return {
        "items": TaskActivity(doc).get_items(),
        "can_comment": frappe.session.user != "Guest",
    }


def add_comment(task: str, content: str) -> dict:
    """Anyone who can see a task may comment on it."""
    doc = frappe.get_doc("Task", str(task))
    doc.check_permission("read")
    text = (content or "").strip()
    if not text:
        frappe.throw(_("Write a comment first."))
    if len(text) > MAX_COMMENT_LENGTH:
        frappe.throw(
            _("Keep the comment under {0} characters.").format(MAX_COMMENT_LENGTH)
        )
    user = frappe.session.user
    comment = doc.add_comment(
        "Comment",
        frappe.utils.escape_html(text).replace("\n", "<br>"),
        comment_email=user,
        comment_by=frappe.utils.get_fullname(user),
    )
    item = comment_item(comment)
    TaskActivity.add_names([item])
    item["at"] = _to_seconds(item["at"])
    return item
