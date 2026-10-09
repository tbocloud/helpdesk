# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.test_utils import (
    call_project_files,
    get_reminder_messages,
    hold_commits,
    make_attachment,
    make_project,
    make_project_file,
    make_project_folder,
    make_project_item_comment,
    make_tasky_user,
    mark_project_item,
)

PM = ("pm.versions@project-versions.example", "Sammish Thundiyil")
DEV_A = ("dev.a.versions@project-versions.example", "Sanika Menon")
DEV_B = ("dev.b.versions@project-versions.example", "Arjun Das")
DEV_C = ("dev.c.versions@project-versions.example", "Meera Pillai")
ADMIN = ("admin.versions@project-versions.example", "Lakshmi Varma")
OUTSIDER = ("outsider.versions@project-versions.example", "Kiran Rao")
PROJECT_NAME = "Project Versions - GrowthX"


class TestProjectItemStatusAndComments(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_tasky_user(*PM, roles=("Project Manager",))
        make_tasky_user(*ADMIN, roles=("Agent Manager",))
        for user in (DEV_A, DEV_B, DEV_C, OUTSIDER):
            make_tasky_user(*user)
        self.project = make_project(
            PROJECT_NAME,
            members=[
                (PM[0], "Project Manager"),
                (DEV_A[0], "Developer"),
                (DEV_B[0], "Developer"),
                (DEV_C[0], "Developer"),
            ],
            owner=PM[0],
        ).name

    def call(self, user, method, **kwargs):
        return call_project_files(user[0], method, project=self.project, **kwargs)

    def mark(self, user, kind, item, **kwargs):
        return mark_project_item(user[0], self.project, kind, item, **kwargs)

    def comment(self, user, kind, item, **kwargs):
        return make_project_item_comment(user[0], self.project, kind, item, **kwargs)

    def record_of(self, file):
        return frappe.db.get_value("HD Project File", {"file": file}, "name")

    def listed_files(self, user, **kwargs):
        return {
            f["file_name"]: f
            for f in self.call(user, "list_project_files", **kwargs)["files"]
        }

    # --- status ---

    def test_who_may_change_the_status(self):
        file = make_project_file(self.project, "STATUS-REPORT-v1.md", user=DEV_A[0])
        folder = make_project_folder(self.project, "Prompts v1", user=DEV_A[0])
        for kind, item in (("file", file), ("folder", folder)):
            for who in (OUTSIDER, DEV_B):
                with self.assertRaises(frappe.PermissionError):
                    self.mark(who, kind, item)
            # the uploader or creator, the project's manager and an admin may
            self.mark(DEV_A, kind, item)
            self.mark(PM, kind, item, status="Active")
            self.mark(ADMIN, kind, item)
        for doctype, name in (
            ("HD Project File", self.record_of(file)),
            ("HD Project Folder", folder),
        ):
            row = frappe.db.get_value(
                doctype, name, ["status", "status_changed_by"], as_dict=True
            )
            self.assertEqual(row.status, "Superseded")
            self.assertEqual(row.status_changed_by, ADMIN[0])
        with self.assertRaises(frappe.ValidationError):
            self.mark(PM, "file", file, status="Archived")

    def test_replacement_must_be_the_same_kind_on_the_same_project(self):
        v1 = make_project_file(self.project, "PROMPT-v1.md", user=PM[0])
        v2 = make_project_file(self.project, "PROMPT-v2.md", user=PM[0])
        folder = make_project_folder(self.project, "Prompts", user=PM[0])
        other = make_project(
            "Project Versions - Other",
            members=[(PM[0], "Project Manager")],
            owner=PM[0],
        ).name
        foreign = make_project_file(other, "PROMPT-v3.md", user=PM[0])

        # the picker offers the project's other active files only
        choices = self.call(DEV_A, "list_replacement_choices", kind="file", item=v1)
        self.assertEqual([c["value"] for c in choices], [v2])
        self.assertEqual(
            self.call(DEV_A, "list_replacement_choices", kind="folder", item=folder),
            [],
        )

        # another project's file, or a folder in place of a file, is refused
        for replacement in (foreign, folder):
            with self.assertRaises(frappe.PermissionError):
                self.mark(PM, "file", v1, superseded_by=replacement)
        with self.assertRaises(frappe.PermissionError):
            self.mark(PM, "folder", folder, superseded_by=v2)
        with self.assertRaises(frappe.ValidationError):
            self.mark(PM, "file", v1, superseded_by=v1)

        # the record refuses a replacement from another project too
        record = frappe.get_doc("HD Project File", self.record_of(v1))
        record.status = "Superseded"
        record.superseded_by = self.record_of(foreign)
        with self.assertRaises(frappe.ValidationError):
            record.save(ignore_permissions=True)

        self.mark(PM, "file", v1, superseded_by=v2, note="v2 adds the tone rules")
        row = self.listed_files(DEV_A, show_superseded=1)["PROMPT-v1.md"]
        self.assertEqual(row["status"], "Superseded")
        self.assertEqual(
            row["superseded_by"], {"name": v2, "label": "PROMPT-v2.md", "folder": None}
        )
        self.assertEqual(row["status_note"], "v2 adds the tone rules")
        self.assertEqual(row["status_changed_by_name"], PM[1])

        # marking it active again forgets the replacement and the note
        self.mark(PM, "file", v1, status="Active")
        row = self.listed_files(DEV_A)["PROMPT-v1.md"]
        self.assertEqual(row["status"], "Active")
        self.assertIsNone(row["superseded_by"])
        self.assertEqual(row["status_note"], "")

    def test_superseded_items_are_hidden_until_shown(self):
        old = make_project_folder(self.project, "Spec v1", user=PM[0])
        drafts = make_project_folder(
            self.project, "Drafts", user=PM[0], parent_folder=old
        )
        inside = make_project_file(
            self.project, "spec.md", for_users=[DEV_A[0]], user=PM[0], folder=old
        )
        new = make_project_folder(self.project, "Spec v2", user=PM[0])
        brief_v1 = make_project_file(self.project, "brief-v1.md", user=PM[0])
        make_project_file(self.project, "brief-v2.md", user=PM[0])
        self.mark(PM, "folder", old, superseded_by=new)
        self.mark(PM, "file", brief_v1)

        top = self.call(DEV_A, "list_project_files")
        self.assertEqual({f["file_name"] for f in top["files"]}, {"brief-v2.md"})
        self.assertTrue(top["hiding_superseded"])
        # the old folder and the old brief
        self.assertEqual(top["superseded_hidden"], 2)
        folders = {f["name"]: f for f in top["folders"]}
        self.assertEqual(folders[old]["status"], "Superseded")
        self.assertEqual(
            folders[old]["superseded_by"], {"name": new, "label": "Spec v2"}
        )
        # inherited, for display only: the subfolder keeps its own status
        self.assertEqual(folders[drafts]["status"], "Active")
        self.assertTrue(folders[drafts]["superseded_via_parent"])
        self.assertFalse(folders[new]["superseded_via_parent"])

        shown = self.call(DEV_A, "list_project_files", show_superseded=1)
        self.assertEqual(
            {f["file_name"] for f in shown["files"]}, {"brief-v1.md", "brief-v2.md"}
        )
        self.assertFalse(shown["hiding_superseded"])
        self.assertEqual(shown["superseded_hidden"], 0)

        # opening the old version shows all of it, marked as inside a superseded folder
        opened = self.call(DEV_A, "list_project_files", folder=old)
        self.assertFalse(opened["hiding_superseded"])
        self.assertEqual(len(opened["files"]), 1)
        self.assertTrue(opened["files"][0]["in_superseded_folder"])
        self.assertEqual(opened["files"][0]["status"], "Active")
        self.assertEqual(
            frappe.db.get_value("HD Project File", {"file": inside}, "status"),
            "Active",
        )

        # "For me" leaves out files in a superseded folder too
        self.assertEqual(self.call(DEV_A, "list_project_files", for_me=1)["files"], [])
        self.assertEqual(
            len(
                self.call(DEV_A, "list_project_files", for_me=1, show_superseded=1)[
                    "files"
                ]
            ),
            1,
        )

    def test_the_people_it_is_for_hear_once_that_it_was_replaced(self):
        v1 = make_project_file(
            self.project,
            "STATUS-REPORT-v1.md",
            for_users=[DEV_A[0], DEV_B[0]],
            user=PM[0],
        )
        v2 = make_project_file(self.project, "STATUS-REPORT-v2.md", user=PM[0])
        record = self.record_of(v1)
        replaced = (
            f"STATUS-REPORT-v1.md was replaced by STATUS-REPORT-v2.md in {PROJECT_NAME}"
        )

        self.mark(PM, "file", v1, superseded_by=v2)
        self.mark(PM, "file", v1, status="Active")
        self.mark(PM, "file", v1, superseded_by=v2)

        for user in (DEV_A, DEV_B):
            self.assertEqual(get_reminder_messages(user[0], record).count(replaced), 1)
        self.assertNotIn(replaced, get_reminder_messages(PM[0], record))

        folder = make_project_folder(
            self.project, "Prompts v1", for_users=[DEV_A[0]], user=PM[0]
        )
        self.mark(PM, "folder", folder)
        self.assertIn(
            f"{PM[1]} marked Prompts v1 as superseded in {PROJECT_NAME}",
            get_reminder_messages(DEV_A[0], folder),
        )

    def test_deleting_a_replacement_keeps_the_old_version_superseded(self):
        v1 = make_project_file(self.project, "PROMPT-v1.md", user=PM[0])
        v2 = make_project_file(self.project, "PROMPT-v2.md", user=PM[0])
        old = make_project_folder(self.project, "Spec v1", user=PM[0])
        new = make_project_folder(self.project, "Spec v2", user=PM[0])
        self.mark(PM, "file", v1, superseded_by=v2)
        self.mark(PM, "folder", old, superseded_by=new)

        self.call(PM, "delete_project_file", file=v2)
        self.call(PM, "delete_project_folder", folder=new)

        record = frappe.db.get_value(
            "HD Project File",
            self.record_of(v1),
            ["status", "superseded_by"],
            as_dict=True,
        )
        self.assertEqual((record.status, record.superseded_by), ("Superseded", None))
        self.assertIsNone(
            frappe.db.get_value("HD Project Folder", old, "superseded_by")
        )

    # --- comments ---

    def test_only_people_on_the_project_read_and_add_comments(self):
        file = make_project_file(self.project, user=DEV_A[0])
        folder = make_project_folder(self.project, "Prompts", user=DEV_A[0])
        for kind, item in (("file", file), ("folder", folder)):
            self.comment(DEV_B, kind, item)
            with self.assertRaises(frappe.PermissionError):
                self.call(OUTSIDER, "list_item_comments", kind=kind, item=item)
            with self.assertRaises(frappe.PermissionError):
                self.comment(OUTSIDER, kind, item)
            listed = self.call(DEV_A, "list_item_comments", kind=kind, item=item)
            self.assertEqual(
                [c["text"] for c in listed["comments"]],
                ["Is this the latest version?"],
            )
            self.assertTrue(listed["can_comment"])

        # a comment on another project's file is refused
        other = make_project(
            "Project Versions - Other",
            members=[(PM[0], "Project Manager")],
            owner=PM[0],
        ).name
        foreign = make_project_file(other, user=PM[0])
        with self.assertRaises(frappe.PermissionError):
            self.comment(PM, "file", foreign)

    def test_comments_are_plain_text(self):
        file = make_project_file(self.project, user=DEV_A[0])
        text = "Use <b>v2</b> & drop <script>alert(1)</script>\nThanks"
        name = self.comment(DEV_B, "file", file, content=text)
        self.assertNotIn("<script", frappe.db.get_value("Comment", name, "content"))
        listed = self.call(DEV_A, "list_item_comments", kind="file", item=file)
        self.assertEqual(listed["comments"][0]["text"], text)
        with self.assertRaises(frappe.ValidationError):
            self.comment(DEV_B, "file", file, content="   ")

    def test_comment_on_a_file_added_outside_the_app(self):
        file = make_attachment("Project", self.project, "brief.txt", b"brief").name
        self.comment(DEV_B, "file", file)
        self.assertEqual(self.listed_files(DEV_A)["brief.txt"]["comment_count"], 1)

    def test_authors_edit_and_delete_their_own_and_managers_delete_any(self):
        file = make_project_file(self.project, user=DEV_A[0])
        name = self.comment(DEV_B, "file", file)

        listed = self.call(DEV_A, "list_item_comments", kind="file", item=file)
        self.assertFalse(listed["comments"][0]["can_edit"])
        self.assertFalse(listed["comments"][0]["can_delete"])
        for who in (DEV_A, PM, OUTSIDER):
            with self.assertRaises(frappe.PermissionError):
                self.call(who, "edit_item_comment", comment=name, content="Changed")
        for who in (DEV_A, OUTSIDER):
            with self.assertRaises(frappe.PermissionError):
                self.call(who, "delete_item_comment", comment=name)

        self.call(DEV_B, "edit_item_comment", comment=name, content="Use v2.")
        mine = self.call(DEV_B, "list_item_comments", kind="file", item=file)
        self.assertEqual(mine["comments"][0]["text"], "Use v2.")
        self.assertTrue(mine["comments"][0]["can_edit"])

        self.call(PM, "delete_item_comment", comment=name)
        self.assertFalse(frappe.db.exists("Comment", name))
        own = self.comment(DEV_B, "file", file)
        self.call(DEV_B, "delete_item_comment", comment=own)
        self.assertFalse(frappe.db.exists("Comment", own))

    def test_comment_notifications(self):
        file = make_project_file(
            self.project, "PROMPT.md", for_users=[DEV_B[0]], user=DEV_A[0]
        )
        commented = f"{PM[1]} commented on PROMPT.md in {PROJECT_NAME}: Ready?"
        mentioned = f"{PM[1]} mentioned you on PROMPT.md in {PROJECT_NAME}: Ready?"

        # the uploader and the people it is for, not the author or outsiders
        name = self.comment(PM, "file", file, content="Ready?", mentions=[OUTSIDER[0]])
        self.assertEqual(get_reminder_messages(DEV_A[0], name), [commented])
        self.assertEqual(get_reminder_messages(DEV_B[0], name), [commented])
        for user in (PM, DEV_C, OUTSIDER):
            self.assertEqual(get_reminder_messages(user[0], name), [])

        # an edit tells people newly mentioned, once, and nobody else again
        for _attempt in range(2):
            self.call(
                PM,
                "edit_item_comment",
                comment=name,
                content="Ready?",
                mentions=[DEV_B[0], DEV_C[0]],
            )
        self.assertEqual(get_reminder_messages(DEV_C[0], name), [mentioned])
        self.assertEqual(get_reminder_messages(DEV_B[0], name), [commented])
        self.assertEqual(get_reminder_messages(DEV_A[0], name), [commented])

        # someone mentioned who is also the item's audience hears once, as a mention
        again = self.comment(PM, "file", file, content="Ready?", mentions=[DEV_B[0]])
        self.assertEqual(get_reminder_messages(DEV_B[0], again), [mentioned])

        # a folder's creator hears about comments on it
        folder = make_project_folder(self.project, "Prompts", user=DEV_C[0])
        on_folder = self.comment(DEV_A, "folder", folder, content="Moved v1 here")
        self.assertEqual(
            get_reminder_messages(DEV_C[0], on_folder),
            [f"{DEV_A[1]} commented on Prompts in {PROJECT_NAME}: Moved v1 here"],
        )

    def test_comment_counts_in_the_list(self):
        file = make_project_file(self.project, "a.md", user=DEV_A[0])
        make_project_file(self.project, "b.md", user=DEV_A[0])
        folder = make_project_folder(self.project, "Prompts", user=DEV_A[0])
        first = self.comment(DEV_B, "file", file)
        self.comment(PM, "file", file)
        self.comment(PM, "folder", folder)

        listed = self.call(DEV_A, "list_project_files")
        counts = {f["file_name"]: f["comment_count"] for f in listed["files"]}
        self.assertEqual(counts, {"a.md": 2, "b.md": 0})
        self.assertEqual(listed["folders"][0]["comment_count"], 1)

        self.call(DEV_B, "delete_item_comment", comment=first)
        self.assertEqual(self.listed_files(DEV_A)["a.md"]["comment_count"], 1)

        # deleting the file takes its comments with it
        record = self.record_of(file)
        self.call(DEV_A, "delete_project_file", file=file)
        self.assertFalse(
            frappe.db.exists(
                "Comment",
                {"reference_doctype": "HD Project File", "reference_name": record},
            )
        )
