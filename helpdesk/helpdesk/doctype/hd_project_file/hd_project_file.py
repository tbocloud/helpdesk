# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""A file attached to a project, the folder it sits in, who on the project it is
for, and whether it is the current version.

The File (attached to the Project) holds the content and decides who may open
it; this record only adds the folder, the "For" list and the status. "For" is a
label plus a notification, not a restriction: everyone who can read the project
sees every file. See docs/project-files.md.
"""

from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_fullname, now_datetime

from helpdesk.tasky.permissions import get_project_team

ACTIVE = "Active"
SUPERSEDED = "Superseded"
# long enough to recognise the comment in the bell, a chat message or an email subject
COMMENT_SNIPPET_LENGTH = 120


def folder_link(project: str, folder: str | None, **query) -> str:
    """The project's Files tab, open in `folder` (the top level when empty), plus
    any other query, e.g. superseded=1 or comments=<item>."""
    params = {k: v for k, v in {"folder": folder, **query}.items() if v}
    path = f"/projects/{project}/files"
    return f"{path}?{urlencode(params)}" if params else path


class ProjectShare:
    """The "For" list that project files and folders share (HD Project File User rows)."""

    def validate_for_users(self):
        team = set(get_project_team(self.project))
        seen = set()
        rows = []
        for row in self.for_users:
            if not row.user or row.user in seen:
                continue
            if row.user not in team:
                frappe.throw(
                    _(
                        "{0} isn't on this project. Pick people from the project team."
                    ).format(row.user)
                )
            seen.add(row.user)
            rows.append(row)
        self.for_users = rows

    def assignees(self) -> list[str]:
        return [row.user for row in self.for_users]

    def new_assignees(self) -> list[str]:
        """People added to "For" by this save, except the person saving."""
        before = self.get_doc_before_save()
        previous = set(before.assignees()) if before else set()
        return [
            u
            for u in self.assignees()
            if u not in previous and u != frappe.session.user
        ]

    def project_title(self) -> str:
        return (
            frappe.db.get_value("Project", self.project, "project_name") or self.project
        )


class ProjectItem:
    """What project files and folders share besides "For": the Active / Superseded
    status (an old version of a prompt or spec stays on the project, marked as
    replaced) and who hears about comments on them.

    Each class says what the item is called in the app and the API (`item_id`),
    where it sits (`location`), where its replacement sits
    (`replacement_location`) and who added it (`added_by`).
    """

    def label(self) -> str:
        return self.get(self.meta.title_field) or self.name

    def validate_status(self):
        if self.status != SUPERSEDED:
            self.status = ACTIVE
            self.superseded_by = None
            self.status_note = None
        elif self.superseded_by:
            self.validate_replacement()
        if self.status_changed():
            self.status_changed_by = frappe.session.user
            self.status_changed_on = now_datetime()

    def validate_replacement(self):
        if self.superseded_by == self.name:
            frappe.throw(_("Pick another one as its replacement, not itself."))
        if frappe.db.get_value(self.doctype, self.superseded_by, "project") != (
            self.project
        ):
            frappe.throw(
                _("The replacement must be on project {0} too.").format(self.project)
            )

    def status_changed(self) -> bool:
        before = self.get_doc_before_save()
        return ((before.status if before else None) or ACTIVE) != self.status

    def notify_superseded(self):
        """Tell the people it is for that it was replaced. Once each: the same
        message about the same item isn't sent again (notify_users)."""
        from helpdesk.work_reminders import notify_users

        if self.status != SUPERSEDED or not self.status_changed():
            return
        users = [u for u in self.assignees() if u != frappe.session.user]
        if not users:
            return
        replacement = (
            frappe.db.get_value(self.doctype, self.superseded_by, self.meta.title_field)
            if self.superseded_by
            else None
        )
        if replacement:
            subject = _("{0} was replaced by {1} in {2}").format(
                self.label(), replacement, self.project_title()
            )
            link = folder_link(self.project, self.replacement_location())
        else:
            subject = _("{0} marked {1} as superseded in {2}").format(
                get_fullname(frappe.session.user), self.label(), self.project_title()
            )
            link = folder_link(self.project, self.location(), superseded=1)
        notify_users(users, self.doctype, self.name, subject, link=link)

    def clear_replaced_by_links(self):
        """Items this one replaced stay superseded, without a replacement, so their
        link to it doesn't block the delete."""
        table = frappe.qb.DocType(self.doctype)
        (
            frappe.qb.update(table)
            .set(table.superseded_by, None)
            .where(table.superseded_by == self.name)
            .run()
        )

    def notify_comment(self, comment: str, text: str, mentions: list[str]) -> None:
        """A new or edited comment: people @mentioned in it, then the people the item
        is for and whoever added it; never the author or anyone who can't read the
        project. Each person hears about a comment once, however often it is
        edited."""
        from helpdesk.work_reminders import notify_users

        author = frappe.session.user
        already = set(
            frappe.get_all(
                "HD Notification",
                filters={"reference_doctype": "Comment", "reference_name": comment},
                pluck="user_to",
            )
        )
        mentioned = [u for u in dict.fromkeys(mentions) if u != author]
        others = [
            u
            for u in dict.fromkeys([*self.assignees(), self.added_by()])
            if u and u != author and u not in mentioned
        ]
        snippet = " ".join(text.split())
        if len(snippet) > COMMENT_SNIPPET_LENGTH:
            snippet = snippet[: COMMENT_SNIPPET_LENGTH - 1] + "…"
        link = folder_link(
            self.project,
            self.location(),
            superseded=1 if self.status == SUPERSEDED else None,
            comments=self.item_id(),
        )
        who = get_fullname(author)
        for users, message in (
            (mentioned, _("{0} mentioned you on {1} in {2}: {3}")),
            (others, _("{0} commented on {1} in {2}: {3}")),
        ):
            users = [u for u in users if u not in already and self.can_read(u)]
            if users:
                notify_users(
                    users,
                    "Comment",
                    comment,
                    message.format(who, self.label(), self.project_title(), snippet),
                    link=link,
                )

    def can_read(self, user: str) -> bool:
        return bool(
            frappe.has_permission("Project", "read", doc=self.project, user=user)
        )


class HDProjectFile(ProjectShare, ProjectItem, Document):
    def validate(self):
        self.validate_file()
        self.validate_folder()
        self.validate_for_users()
        self.validate_status()

    def on_update(self):
        self.notify_new_assignees()
        self.notify_superseded()

    def on_trash(self):
        self.clear_replaced_by_links()

    def item_id(self) -> str:
        """The app and the API name a file by its File."""
        return self.file

    def location(self) -> str | None:
        return self.folder

    def replacement_location(self) -> str | None:
        return frappe.db.get_value(self.doctype, self.superseded_by, "folder")

    def added_by(self) -> str | None:
        return frappe.db.get_value("File", self.file, "owner")

    def validate_file(self):
        attached = frappe.db.get_value(
            "File", self.file, ["attached_to_doctype", "attached_to_name"]
        )
        if not attached or tuple(attached) != ("Project", self.project):
            frappe.throw(
                _("This file isn't attached to project {0}.").format(self.project)
            )

    def validate_folder(self):
        if not self.folder:
            self.folder = None
            return
        if frappe.db.get_value("HD Project Folder", self.folder, "project") != (
            self.project
        ):
            frappe.throw(
                _("That folder isn't part of project {0}.").format(self.project),
                frappe.PermissionError,
            )

    def notify_new_assignees(self):
        from helpdesk.work_reminders import notify_users

        new = self.new_assignees()
        if not new:
            return
        notify_users(
            new,
            self.doctype,
            self.name,
            _("{0} shared {1} with you in {2}").format(
                get_fullname(frappe.session.user),
                self.file_name,
                self.project_title(),
            ),
            link=f"/projects/{self.project}/files",
        )
