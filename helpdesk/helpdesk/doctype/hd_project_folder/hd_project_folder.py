# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""A folder of files on a project, and who on the project it is for.

Folders nest up to MAX_DEPTH levels (`parent_folder` empty = the top level).
Names are unique among a folder's siblings. A folder's "For" list is
independent of its files' own lists, and reaches down the tree: someone a folder
is for sees the files in its subfolders under "For me" and hears about files
added anywhere below it. Deleting a folder moves its files and subfolders up to
its parent; it never deletes them. A superseded folder (an old version) makes
everything below it look superseded in the list, without changing their own
status. See docs/project-files.md.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_fullname

from helpdesk.helpdesk.doctype.hd_project_file.hd_project_file import (
    SUPERSEDED,
    ProjectItem,
    ProjectShare,
    folder_link,
)

PROJECT_FILE = "HD Project File"
PROJECT_FOLDER = "HD Project Folder"
PROJECT_FILE_USER = "HD Project File User"
# deep enough for client / workstream / topic trees, shallow enough to stay findable
MAX_DEPTH = 5


class HDProjectFolder(ProjectShare, ProjectItem, Document):
    def validate(self):
        self.validate_folder_name()
        self.validate_parent_folder()
        self.validate_unique_name()
        self.validate_for_users()
        self.validate_status()

    def on_update(self):
        self.notify_new_assignees()
        self.notify_superseded()

    def on_trash(self):
        self.move_contents_to_parent()
        self.clear_replaced_by_links()

    def item_id(self) -> str:
        return self.name

    def location(self) -> str | None:
        return self.parent_folder

    def replacement_location(self) -> str | None:
        return self.superseded_by

    def added_by(self) -> str:
        return self.owner

    def validate_folder_name(self):
        self.folder_name = " ".join((self.folder_name or "").split())
        if not self.folder_name:
            frappe.throw(_("Give the folder a name."))
        if "/" in self.folder_name:
            frappe.throw(_("A folder name can't contain /."))

    def validate_parent_folder(self):
        if not self.parent_folder:
            self.parent_folder = None
            return
        tree = FolderTree(self.project)
        if self.parent_folder not in tree.rows:
            frappe.throw(
                _("That folder isn't part of project {0}.").format(self.project),
                frappe.PermissionError,
            )
        if self.parent_folder in tree.subtree(self.name):
            frappe.throw(_("A folder can't go inside itself or one of its subfolders."))
        if tree.depth(self.parent_folder) + tree.height(self.name) > MAX_DEPTH:
            frappe.throw(_("Folders go at most {0} levels deep.").format(MAX_DEPTH))

    def validate_unique_name(self):
        # MariaDB compares case-insensitively, so "Prompts" and "prompts" clash
        if frappe.db.exists(
            self.doctype,
            {
                "project": self.project,
                "parent_folder": self.parent_folder or ("is", "not set"),
                "folder_name": self.folder_name,
                "name": ("!=", self.name),
            },
        ):
            frappe.throw(
                _("There is already a folder called {0} here.").format(self.folder_name)
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
            _("{0} shared folder '{1}' with you in {2}").format(
                get_fullname(frappe.session.user),
                self.folder_name,
                self.project_title(),
            ),
            link=folder_link(self.project, self.name),
        )

    def move_contents_to_parent(self):
        """Files and subfolders move up a level, refused when a subfolder's name is taken there."""
        folder = frappe.qb.DocType(PROJECT_FOLDER)
        record = frappe.qb.DocType(PROJECT_FILE)
        children = frappe.get_all(
            PROJECT_FOLDER, filters={"parent_folder": self.name}, pluck="folder_name"
        )
        if children:
            clash = frappe.get_all(
                PROJECT_FOLDER,
                filters={
                    "project": self.project,
                    "parent_folder": self.parent_folder or ("is", "not set"),
                    "folder_name": ("in", children),
                    "name": ("!=", self.name),
                },
                pluck="folder_name",
                limit=1,
            )
            if clash:
                frappe.throw(
                    _(
                        "Its subfolder {0} can't move up: there is already a folder with that name there. Rename one of them first."
                    ).format(clash[0])
                )
        (
            frappe.qb.update(folder)
            .set(folder.parent_folder, self.parent_folder)
            .where(folder.parent_folder == self.name)
            .run()
        )
        (
            frappe.qb.update(record)
            .set(record.folder, self.parent_folder)
            .where(record.folder == self.name)
            .run()
        )


class FolderTree:
    """A project's folders in memory, for paths, depth and inherited "For"."""

    def __init__(self, project: str):
        self.project = project
        self.rows = {
            r.name: r
            for r in frappe.get_all(
                PROJECT_FOLDER,
                filters={"project": project},
                fields=["name", "folder_name", "parent_folder", "status"],
                order_by="folder_name asc",
                limit_page_length=0,
            )
        }
        self.children: dict = {}
        for r in self.rows.values():
            self.children.setdefault(r.parent_folder or None, []).append(r.name)
        self._assignees = None

    def chain(self, name: str | None) -> list[str]:
        """The folder and its ancestors, nearest first."""
        result = []
        while name and name in self.rows and name not in result:
            result.append(name)
            name = self.rows[name].parent_folder
        return result

    def is_superseded(self, name: str | None) -> bool:
        """The folder or one above it is superseded."""
        return any(self.rows[n].status == SUPERSEDED for n in self.chain(name))

    def depth(self, name: str | None) -> int:
        return len(self.chain(name))

    def height(self, name: str | None) -> int:
        """Levels from this folder down to its deepest subfolder (1 for a new or leaf folder)."""
        kids = self.children.get(name, []) if name else []
        return 1 + max((self.height(k) for k in kids), default=0)

    def subtree(self, name: str | None) -> set[str]:
        """The folder and everything below it."""
        if not name:
            return set()
        found = {name}
        for kid in self.children.get(name, []):
            found |= self.subtree(kid)
        return found

    def path(self, name: str | None) -> list[dict]:
        """Top level first, for the breadcrumb."""
        return [
            {"name": n, "folder_name": self.rows[n].folder_name}
            for n in reversed(self.chain(name))
        ]

    def common_ancestor(self, names: list[str]) -> str | None:
        """The deepest folder that holds all of `names` (None: the top level)."""
        chains = [self.chain(n) for n in names]
        if not chains:
            return None
        shared = set(chains[0]).intersection(*chains[1:])
        return next((n for n in chains[0] if n in shared), None)

    def order(self) -> list[str]:
        """Every folder, parents before their subfolders, siblings by name."""
        result = []

        def walk(parent):
            for name in self.children.get(parent, []):
                result.append(name)
                walk(name)

        walk(None)
        return result

    @property
    def assignees(self) -> dict:
        """{folder: set of people it is directly for}"""
        if self._assignees is None:
            self._assignees = {}
            if self.rows:
                row = frappe.qb.DocType(PROJECT_FILE_USER)
                for parent, user in (
                    frappe.qb.from_(row)
                    .select(row.parent, row.user)
                    .where(
                        (row.parenttype == PROJECT_FOLDER)
                        & (row.parent.isin(list(self.rows)))
                    )
                    .run()
                ):
                    self._assignees.setdefault(parent, set()).add(user)
        return self._assignees

    def people_for(self, name: str | None) -> set[str]:
        """Everyone the folder or one of its ancestors is for."""
        found = set()
        for n in self.chain(name):
            found |= self.assignees.get(n, set())
        return found

    def notify_new_files(self, records: list) -> None:
        """Tell people about a batch of files added to folders, once each.

        Each file reaches the people its folder or any ancestor is for, except
        whoever added it and people the file itself is marked for (they were told
        about it already). Someone reached by several files gets one notification,
        naming the deepest folder that holds all of them. It refers to their first
        file, so repeating the call doesn't repeat it.
        """
        from helpdesk.work_reminders import notify_users

        actor = frappe.session.user
        reached: dict = {}
        for record in records:
            for user in self.people_for(record.folder) - {actor}:
                if user not in record.assignees():
                    reached.setdefault(user, []).append(record)
        if not reached:
            return
        who = get_fullname(actor)
        project_name = (
            frappe.db.get_value("Project", self.project, "project_name") or self.project
        )
        messages: dict = {}
        for user, files in reached.items():
            folder = self.common_ancestor([f.folder for f in files])
            what = (
                files[0].file_name
                if len(files) == 1
                else _("{0} files").format(len(files))
            )
            subject = (
                _("{0} added {1} to folder '{2}' in {3}").format(
                    who, what, self.rows[folder].folder_name, project_name
                )
                if folder
                else _("{0} added {1} in {2}").format(who, what, project_name)
            )
            key = (subject, files[0].name, folder_link(self.project, folder))
            messages.setdefault(key, []).append(user)
        for (subject, record, link), users in messages.items():
            notify_users(users, PROJECT_FILE, record, subject, link=link)
