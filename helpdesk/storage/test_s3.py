# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import io
import os
import zipfile
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.storage import s3
from helpdesk.test_utils import (
    FakeS3,
    create_customer,
    enable_file_storage,
    make_attachment,
    make_content_post,
    make_tasky_user,
)

CUSTOMER = "S3 Test Customer"
OUTSIDER = ("s3.outsider@s3-test.example", "Omar Outsider")


class TestS3Storage(FrappeTestCase):
    def setUp(self):
        self.bucket = FakeS3()
        patcher = patch.object(s3, "get_client", return_value=self.bucket)
        patcher.start()
        # cleanups run last-in first-out: roll back while the fake bucket is still in place
        self.addCleanup(patcher.stop)
        self.addCleanup(setattr, frappe.flags, "hd_fake_s3", False)
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        create_customer(CUSTOMER)
        enable_file_storage()
        self.post = make_content_post("S3 post", CUSTOMER)

    def attach(self, file_name="design.png", content=b"\x89PNG fake image", **kwargs):
        doc = make_attachment(
            "HD Content Post", self.post.name, file_name, content, **kwargs
        )
        local = doc.get_full_path() if not doc.get(s3.KEY_FIELD) else None
        if local:
            self.addCleanup(lambda: os.path.exists(local) and os.remove(local))
        return frappe.get_doc("File", doc.name)

    def test_new_attachment_goes_to_the_bucket(self):
        doc = self.attach()

        key = doc.get(s3.KEY_FIELD)
        self.assertTrue(key.startswith(f"test-site/hd_content_post/{self.post.name}/"))
        self.assertEqual(self.bucket.objects[key], b"\x89PNG fake image")
        self.assertEqual(doc.file_url, s3.download_url(doc))
        self.assertFalse(
            os.path.exists(frappe.get_site_path("private", "files", doc.file_name))
        )
        self.assertEqual(doc.get_content(), b"\x89PNG fake image")
        # saving again (e.g. renaming) must not trip the on-disk checks
        doc.save(ignore_permissions=True)

    def test_other_documents_stay_on_this_server(self):
        doc = make_attachment("HD Customer", CUSTOMER, "contract.txt", b"terms")
        self.addCleanup(
            lambda: os.path.exists(doc.get_full_path())
            and os.remove(doc.get_full_path())
        )
        self.assertFalse(doc.get(s3.KEY_FIELD))
        self.assertTrue(doc.file_url.startswith("/private/files/"))
        self.assertFalse(self.bucket.objects)

    def test_bucket_failure_keeps_the_file_local(self):
        self.bucket.fail_uploads = True
        # Error Logs survive a rollback, so capture the call instead of writing one
        with patch.object(frappe, "log_error") as log_error:
            doc = self.attach("kept.png")
        self.assertFalse(doc.get(s3.KEY_FIELD))
        self.assertTrue(os.path.exists(doc.get_full_path()))
        self.assertEqual(
            log_error.call_args.kwargs["title"], f"S3 upload failed for {doc.name}"
        )

    def test_download_checks_access_then_signs(self):
        doc = self.attach()
        s3.download(doc.name)
        self.assertEqual(frappe.local.response["type"], "redirect")
        self.assertTrue(
            frappe.local.response["location"].startswith("https://bucket.example/")
        )

        make_tasky_user(*OUTSIDER)
        frappe.set_user(OUTSIDER[0])
        with self.assertRaises(frappe.PermissionError):
            s3.download(doc.name)

    def test_zip_and_delete(self):
        first = self.attach("one.png", b"one")
        second = self.attach("two.png", b"two")

        from frappe.core.doctype.file.file import File

        archive = zipfile.ZipFile(io.BytesIO(File.zip_files([first.name, second.name])))
        self.assertEqual(sorted(archive.namelist()), ["one.png", "two.png"])

        key = first.get(s3.KEY_FIELD)
        first.delete(ignore_permissions=True)
        self.assertNotIn(key, self.bucket.objects)
        self.assertIn(second.get(s3.KEY_FIELD), self.bucket.objects)

    def test_existing_local_files_can_be_moved(self):
        frappe.db.set_single_value("HD File Storage Settings", "enabled", 0)
        frappe.clear_document_cache(
            "HD File Storage Settings", "HD File Storage Settings"
        )
        doc = self.attach("old.png", b"old")
        self.assertFalse(doc.get(s3.KEY_FIELD))

        frappe.db.set_single_value("HD File Storage Settings", "enabled", 1)
        frappe.clear_document_cache(
            "HD File Storage Settings", "HD File Storage Settings"
        )
        # only this test's files: never the site's real attachments
        s3.move_existing_files_job({"attached_to_name": self.post.name})

        doc.reload()
        self.assertTrue(doc.get(s3.KEY_FIELD))
        self.assertEqual(self.bucket.objects[doc.get(s3.KEY_FIELD)], b"old")


class TestS3KeepLocalCopy(FrappeTestCase):
    """The default: files stay on this server and the bucket holds a second copy."""

    def setUp(self):
        self.bucket = FakeS3()
        patcher = patch.object(s3, "get_client", return_value=self.bucket)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(setattr, frappe.flags, "hd_fake_s3", False)
        self.addCleanup(frappe.db.rollback)
        create_customer(CUSTOMER)
        enable_file_storage(keep_local_copy=1)
        self.post = make_content_post("Kept post", CUSTOMER)

    def test_file_stays_local_and_is_copied(self):
        doc = make_attachment("HD Content Post", self.post.name, "kept.png", b"both")
        doc.reload()
        local = doc.get_full_path()
        self.addCleanup(lambda: os.path.exists(local) and os.remove(local))

        self.assertTrue(doc.file_url.startswith("/private/files/"))
        self.assertTrue(os.path.exists(local))
        self.assertEqual(self.bucket.objects[doc.get(s3.KEY_FIELD)], b"both")
        self.assertEqual(doc.get_content(), b"both")

        # a lost local copy is read back from the bucket, and saving still works
        os.remove(local)
        doc = frappe.get_doc("File", doc.name)
        self.assertEqual(doc.get_content(), b"both")
        doc.save(ignore_permissions=True)

    def test_delete_removes_both_copies(self):
        doc = make_attachment("HD Content Post", self.post.name, "gone.png", b"bye")
        doc.reload()
        local, key = doc.get_full_path(), doc.get(s3.KEY_FIELD)
        doc.delete(ignore_permissions=True)
        self.assertFalse(os.path.exists(local))
        self.assertNotIn(key, self.bucket.objects)
