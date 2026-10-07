# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import io

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfWriter

from helpdesk.api import project_files as api
from helpdesk.test_utils import (
    get_reminder_messages,
    hold_commits,
    make_project,
    make_project_file,
    make_tasky_user,
    run_as_user,
)

PM = ("pm.files@project-files.example", "Anjali Pillai")
DEV_A = ("dev.a.files@project-files.example", "Rahul Nair")
DEV_B = ("dev.b.files@project-files.example", "Meera Joseph")
OUTSIDER = ("outsider.files@project-files.example", "Vivek Kumar")


class TestProjectFiles(FrappeTestCase):
    def setUp(self):
        """A project with a manager (owner) and two developers, plus an outsider."""
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_tasky_user(*PM, roles=("Project Manager",))
        for user in (DEV_A, DEV_B, OUTSIDER):
            make_tasky_user(*user)
        self.project = make_project(
            "Project Files - Prompt Library",
            members=[
                (PM[0], "Project Manager"),
                (DEV_A[0], "Developer"),
                (DEV_B[0], "Developer"),
            ],
            owner=PM[0],
        ).name

    def list_as(self, user, **kwargs):
        """list_project_files on self.project, as `user`."""
        return run_as_user(
            user[0], lambda: api.list_project_files(self.project, **kwargs)
        )

    def test_member_can_list_and_read_a_private_file(self):
        """A project member lists an uploaded file and may read and download it."""
        file = make_project_file(self.project, user=PM[0])
        doc = frappe.get_doc("File", file)
        self.assertTrue(doc.is_private)
        self.assertEqual(
            (doc.attached_to_doctype, doc.attached_to_name), ("Project", self.project)
        )

        listed = self.list_as(DEV_B)
        self.assertEqual([f["name"] for f in listed["files"]], [file])
        self.assertEqual(listed["files"][0]["uploaded_by_name"], PM[1])
        self.assertTrue(listed["can_upload"])
        text = run_as_user(
            DEV_B[0], lambda: api.get_project_file_text(self.project, file)
        )
        self.assertIn("Master prompt", text["content"])
        # what /private/files/... checks before serving the file
        self.assertTrue(frappe.has_permission("File", "read", doc=doc, user=DEV_B[0]))
        self.assertTrue(run_as_user(DEV_B[0], doc.is_downloadable))

    def test_outsider_cannot_list_or_open_files(self):
        """Someone off the project can't list, read or download a project file."""
        file = make_project_file(self.project, user=PM[0])
        doc = frappe.get_doc("File", file)

        with self.assertRaises(frappe.PermissionError):
            self.list_as(OUTSIDER)
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                OUTSIDER[0], lambda: api.get_project_file_text(self.project, file)
            )
        self.assertFalse(
            frappe.has_permission("File", "read", doc=doc, user=OUTSIDER[0])
        )
        self.assertFalse(run_as_user(OUTSIDER[0], doc.is_downloadable))

    def test_members_upload_and_outsiders_cannot(self):
        """A project member can upload a file; an outsider is refused."""
        # Frappe parses uploaded PDFs, so the test needs a real one
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        pdf = io.BytesIO()
        writer.write(pdf)
        file = make_project_file(
            self.project, "brief.pdf", pdf.getvalue(), user=DEV_A[0]
        )
        self.assertEqual(frappe.db.get_value("File", file, "owner"), DEV_A[0])
        self.assertTrue(frappe.db.exists("HD Project File", {"file": file}))
        with self.assertRaises(frappe.PermissionError):
            make_project_file(self.project, user=OUTSIDER[0])

    def test_uploader_and_manager_can_delete_but_other_members_cannot(self):
        """Only the uploader and the project's manager may delete a file."""
        mine = make_project_file(self.project, "a.md", b"a", user=DEV_A[0])
        theirs = make_project_file(self.project, "b.md", b"b", user=DEV_A[0])

        with self.assertRaises(frappe.PermissionError):
            run_as_user(DEV_B[0], lambda: api.delete_project_file(self.project, mine))
        self.assertTrue(frappe.db.exists("File", mine))

        run_as_user(DEV_A[0], lambda: api.delete_project_file(self.project, mine))
        run_as_user(PM[0], lambda: api.delete_project_file(self.project, theirs))
        for file in (mine, theirs):
            self.assertFalse(frappe.db.exists("File", file))
            self.assertFalse(frappe.db.exists("HD Project File", {"file": file}))

    def test_file_from_another_project_is_refused(self):
        """A file attached to a different project is treated as not part of this one."""
        other = make_project(
            "Project Files - Other", members=[(PM[0], "Project Manager")], owner=PM[0]
        ).name
        stray = make_project_file(other, user=PM[0])

        for call in (
            lambda: api.get_project_file_text(self.project, stray),
            lambda: api.delete_project_file(self.project, stray),
            lambda: api.set_project_file_for(self.project, stray, [DEV_A[0]]),
        ):
            with self.assertRaises(frappe.PermissionError):
                run_as_user(PM[0], call)
        self.assertTrue(frappe.db.exists("File", stray))

    def test_assignees_are_notified_once(self):
        """People a file is for are notified once, even after the "for" list is re-saved."""
        file = make_project_file(
            self.project, for_users=[DEV_A[0], DEV_B[0]], user=PM[0]
        )
        record = frappe.db.get_value("HD Project File", {"file": file}, "name")
        for user in (DEV_A, DEV_B):
            messages = get_reminder_messages(user[0], record)
            self.assertEqual(len(messages), 1)
            self.assertIn("master-prompt.md", messages[0])
            self.assertIn("Project Files - Prompt Library", messages[0])

        run_as_user(
            PM[0],
            lambda: api.set_project_file_for(self.project, file, [DEV_B[0], DEV_A[0]]),
        )
        for user in (DEV_A, DEV_B):
            self.assertEqual(len(get_reminder_messages(user[0], record)), 1)
        link = frappe.db.get_value(
            "HD Notification", {"user_to": DEV_A[0], "reference_name": record}, "link"
        )
        self.assertEqual(link, f"/projects/{self.project}/files")

    def test_non_member_cannot_be_an_assignee(self):
        """A file can't be marked "for" someone who isn't on the project team."""
        with self.assertRaises(frappe.ValidationError):
            make_project_file(self.project, for_users=[OUTSIDER[0]], user=PM[0])
        file = make_project_file(self.project, user=PM[0])
        with self.assertRaises(frappe.ValidationError):
            run_as_user(
                PM[0],
                lambda: api.set_project_file_for(self.project, file, [OUTSIDER[0]]),
            )

    def test_editing_assignees_notifies_only_new_people(self):
        """Adding someone to the "for" list notifies them, not people already on it."""
        file = make_project_file(self.project, for_users=[DEV_A[0]], user=PM[0])
        record = frappe.db.get_value("HD Project File", {"file": file}, "name")
        self.assertEqual(get_reminder_messages(DEV_B[0], record), [])

        result = run_as_user(
            PM[0],
            lambda: api.set_project_file_for(self.project, file, [DEV_A[0], DEV_B[0]]),
        )
        self.assertEqual(result["for_users"], [DEV_A[0], DEV_B[0]])
        self.assertEqual(len(get_reminder_messages(DEV_A[0], record)), 1)
        self.assertEqual(len(get_reminder_messages(DEV_B[0], record)), 1)

    def test_only_uploader_or_managers_change_assignees(self):
        """Only the uploader or the project's manager may change who a file is for."""
        file = make_project_file(self.project, user=DEV_A[0])
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                DEV_B[0],
                lambda: api.set_project_file_for(self.project, file, [DEV_B[0]]),
            )
        run_as_user(
            DEV_A[0], lambda: api.set_project_file_for(self.project, file, [PM[0]])
        )

    def test_for_me_lists_only_files_for_the_user(self):
        """`for_me=True` filters the list down to files addressed to the caller."""
        for_a = make_project_file(
            self.project, "for-a.md", b"a", for_users=[DEV_A[0]], user=PM[0]
        )
        make_project_file(self.project, "for-everyone.md", b"e", user=PM[0])

        everything = self.list_as(DEV_A)
        self.assertEqual(len(everything["files"]), 2)
        flagged = {f["name"]: f["is_for_me"] for f in everything["files"]}
        self.assertTrue(flagged[for_a])

        mine = self.list_as(DEV_A, for_me=True)
        self.assertEqual([f["name"] for f in mine["files"]], [for_a])
        self.assertEqual(mine["files"][0]["for_users"][0]["full_name"], DEV_A[1])
        # "For" is a label, not a restriction
        self.assertEqual(len(self.list_as(DEV_B)["files"]), 2)
