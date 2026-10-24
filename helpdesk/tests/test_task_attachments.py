# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import io
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import task_attachments as api
from helpdesk.tasky.api import get_kanban_tasks
from helpdesk.test_utils import (
    call_as_user,
    hold_commits,
    make_assigned_task,
    make_assignment,
    make_image_bytes,
    make_project,
    make_task_attachment,
    make_tasky_user,
    run_as_user,
)

PM = ("pm.media@task-media.example", "Anjali Pillai")
DEV_A = ("dev.a.media@task-media.example", "Rahul Nair")
DEV_B = ("dev.b.media@task-media.example", "Meera Joseph")
OUTSIDER = ("outsider.media@task-media.example", "Vivek Kumar")
# a Project Manager on the team sees every task but changes only the ones on them
WATCHER = ("watcher.media@task-media.example", "Divya Menon")

# the first bytes are all the type check reads; the rest only makes each file unique
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
MOV = b"\x00\x00\x00\x14ftypqt  " + b"\x01" * 64
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64
EXE = b"MZ\x90\x00" + b"\x00" * 64


class TestTaskAttachments(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_tasky_user(*PM, roles=("Project Manager",))
        make_tasky_user(*WATCHER, roles=("Project Manager",))
        for user in (DEV_A, DEV_B, OUTSIDER):
            make_tasky_user(*user)
        self.project = make_project(
            "Task Media - Payment Gateway",
            members=[
                (PM[0], "Project Manager"),
                (DEV_A[0], "Developer"),
                (DEV_B[0], "Developer"),
                (WATCHER[0], "Developer"),
            ],
            owner=PM[0],
        ).name
        self.task = make_assigned_task(
            self.project, "Checkout button does nothing on Safari", DEV_A[0], PM[0]
        )
        make_assignment("Task", self.task, DEV_B[0])

    def list_as(self, user):
        return run_as_user(user[0], lambda: api.list_task_attachments(self.task))

    def test_assignee_attaches_an_image_and_a_video_privately(self):
        image = make_task_attachment(
            self.task, "safari-checkout.png", make_image_bytes("PNG"), user=DEV_A[0]
        )
        video = make_task_attachment(
            self.task, "click-recording.mp4", MP4, user=DEV_A[0]
        )
        doc = frappe.get_doc("File", image)
        self.assertTrue(doc.is_private)
        self.assertEqual(
            (doc.attached_to_doctype, doc.attached_to_name), ("Task", self.task)
        )
        self.assertEqual(doc.owner, DEV_A[0])

        listed = self.list_as(DEV_B)
        self.assertEqual(
            {a["name"]: a["kind"] for a in listed["attachments"]},
            {image: "image", video: "video"},
        )
        row = next(a for a in listed["attachments"] if a["name"] == image)
        self.assertEqual(row["file_name"], "safari-checkout.png")
        self.assertEqual(row["uploaded_by_name"], DEV_A[1])
        self.assertTrue(row["file_url"].startswith("/private/files/"))
        self.assertGreater(row["file_size"], 0)
        self.assertFalse(row["can_delete"])
        self.assertTrue(listed["can_upload"])
        self.assertEqual(
            listed["limits"],
            {
                "image": min(api.MAX_IMAGE_BYTES, api.get_max_file_size()),
                "video": min(api.MAX_VIDEO_BYTES, api.get_max_file_size()),
            },
        )
        self.assertEqual(
            listed["extensions"],
            {"image": api.IMAGE_EXTENSIONS, "video": api.VIDEO_EXTENSIONS},
        )

        notes = frappe.get_all(
            "Comment",
            filters={
                "reference_doctype": "Task",
                "reference_name": self.task,
                "comment_type": "Info",
            },
            pluck="content",
        )
        self.assertIn("Attached safari-checkout.png", notes)

    def test_every_allowed_format_is_taken(self):
        for file_name, content in (
            ("a.jpg", make_image_bytes("JPEG", "red")),
            ("b.jpeg", make_image_bytes("JPEG", "blue")),
            ("c.webp", make_image_bytes("WEBP")),
            ("d.gif", make_image_bytes("GIF")),
            ("e.mov", MOV),
            ("f.webm", WEBM),
            ("G.PNG", make_image_bytes("PNG", "white")),
        ):
            make_task_attachment(self.task, file_name, content, user=DEV_A[0])
        self.assertEqual(len(self.list_as(DEV_A)["attachments"]), 7)

    def test_other_types_and_renamed_files_are_refused(self):
        for file_name, content in (
            ("brief.pdf", b"%PDF-1.4\n" + b"\x00" * 64),
            ("setup.png", EXE),
            ("photo.png", make_image_bytes("JPEG")),
            ("clip.webm", MP4),
            ("clip.mp4", make_image_bytes("PNG")),
            ("no-extension", make_image_bytes("PNG")),
        ):
            with self.assertRaises(frappe.ValidationError, msg=file_name):
                make_task_attachment(self.task, file_name, content, user=DEV_A[0])
        self.assertFalse(
            frappe.db.exists(
                "File", {"attached_to_doctype": "Task", "attached_to_name": self.task}
            )
        )

    def test_size_limits_per_kind_and_the_site_limit(self):
        png = make_image_bytes("PNG")
        with patch.object(api, "MAX_IMAGE_BYTES", len(png) - 1):
            with self.assertRaises(frappe.ValidationError):
                make_task_attachment(self.task, "big.png", png, user=DEV_A[0])
            # videos have their own limit
            make_task_attachment(self.task, "clip.mp4", MP4, user=DEV_A[0])
        # the site's Max File Size caps the video limit too
        with patch.object(api, "get_max_file_size", return_value=len(WEBM) - 1):
            self.assertEqual(api.upload_limits()["video"], len(WEBM) - 1)
            with self.assertRaises(frappe.ValidationError):
                make_task_attachment(self.task, "clip.webm", WEBM, user=DEV_A[0])

    def test_outsider_cannot_upload_list_or_open(self):
        file = make_task_attachment(self.task, user=DEV_A[0])
        doc = frappe.get_doc("File", file)

        with self.assertRaises(frappe.PermissionError):
            self.list_as(OUTSIDER)
        with self.assertRaises(frappe.PermissionError):
            make_task_attachment(
                self.task, "x.png", make_image_bytes("PNG", "red"), user=OUTSIDER[0]
            )
        # what /private/files/... and the S3 download route check before serving it
        self.assertFalse(
            frappe.has_permission("File", "read", doc=doc, user=OUTSIDER[0])
        )
        self.assertFalse(run_as_user(OUTSIDER[0], doc.is_downloadable))
        for user in (DEV_B, PM):
            self.assertTrue(run_as_user(user[0], doc.is_downloadable))

    def test_people_who_only_see_the_task_cannot_upload(self):
        listed = self.list_as(WATCHER)
        self.assertFalse(listed["can_upload"])
        with self.assertRaises(frappe.PermissionError):
            make_task_attachment(self.task, user=WATCHER[0])

    def test_uploader_and_manager_delete_but_other_assignees_cannot(self):
        mine = make_task_attachment(
            self.task, "a.png", make_image_bytes("PNG", "red"), user=DEV_A[0]
        )
        other = make_task_attachment(
            self.task, "b.png", make_image_bytes("PNG", "blue"), user=DEV_A[0]
        )

        with self.assertRaises(frappe.PermissionError):
            run_as_user(DEV_B[0], lambda: api.delete_task_attachment(self.task, mine))
        self.assertTrue(frappe.db.exists("File", mine))
        manager_row = next(
            a for a in self.list_as(PM)["attachments"] if a["name"] == other
        )
        self.assertTrue(manager_row["can_delete"])

        run_as_user(DEV_A[0], lambda: api.delete_task_attachment(self.task, mine))
        run_as_user(PM[0], lambda: api.delete_task_attachment(self.task, other))
        for file in (mine, other):
            self.assertFalse(frappe.db.exists("File", file))
        self.assertIn(
            "Removed a.png",
            frappe.get_all(
                "Comment",
                filters={"reference_name": self.task, "comment_type": "Info"},
                pluck="content",
            ),
        )

    def test_a_file_from_another_task_is_refused(self):
        other_task = make_assigned_task(
            self.project, "Refund email is blank", DEV_A[0], PM[0]
        )
        stray = make_task_attachment(other_task, user=DEV_A[0])
        with self.assertRaises(frappe.PermissionError):
            run_as_user(PM[0], lambda: api.delete_task_attachment(self.task, stray))
        self.assertTrue(frappe.db.exists("File", stray))

    def test_upload_endpoint_reads_the_multipart_file(self):
        upload = SimpleNamespace(
            filename="recording.webm", stream=io.BytesIO(WEBM + b"\x02")
        )
        previous = getattr(frappe.local, "request", None)
        frappe.local.request = SimpleNamespace(files={"file": upload}, host=None)
        self.addCleanup(setattr, frappe.local, "request", previous)

        saved = call_as_user(
            DEV_A[0],
            "helpdesk.api.task_attachments.upload_task_attachment",
            task=self.task,
            # FileUploadHandler's own form fields are dropped
            folder="Home",
            is_private=1,
        )
        self.assertEqual(saved["kind"], "video")
        self.assertEqual(
            frappe.db.get_value("File", saved["name"], "attached_to_name"), self.task
        )

    def test_board_cards_count_images_and_videos(self):
        make_task_attachment(self.task, user=DEV_A[0])
        make_task_attachment(self.task, "clip.mp4", MP4, user=DEV_A[0])
        # a file attached some other way that isn't media isn't counted
        frappe.get_doc(
            {
                "doctype": "File",
                "file_name": "notes.txt",
                "attached_to_doctype": "Task",
                "attached_to_name": self.task,
                "is_private": 1,
                "content": b"notes",
            }
        ).insert(ignore_permissions=True)
        cards = [
            t
            for column in run_as_user(PM[0], lambda: get_kanban_tasks(self.project))[
                "columns"
            ].values()
            for t in column
        ]
        card = next(t for t in cards if t["name"] == self.task)
        self.assertEqual(card["attachment_count"], 2)
        self.assertEqual(len(self.list_as(PM)["attachments"]), 2)
