from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import search
from helpdesk.api.article import search as search_articles
from helpdesk.test_utils import make_article


class TestSearchWithoutRediSearch(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        unavailable = patch.object(search, "redisearch_available", return_value=False)
        unavailable.start()
        self.addCleanup(unavailable.stop)

    def test_article_search_falls_back_to_the_database(self):
        export = make_article(
            "Export a report to Excel",
            "<p>Open the report, then Menu &gt; Export &gt; Excel.</p>",
        )
        make_article("Draft about exports", "<p>Export Excel</p>", status="Draft")

        results = search_articles("export report excel")

        self.assertEqual([r["id"] for r in results], [f"HD Article:{export.name}"])
        self.assertEqual(results[0]["subject"], "Export a report to Excel")
        self.assertEqual(results[0]["name"].split("#")[0], export.name)
        self.assertNotIn("<p>", results[0]["description"])

    def test_scheduled_index_build_is_skipped(self):
        with patch.object(search.HelpdeskSearch, "build_index") as build:
            search.build_index_if_not_exists()
            search.build_index_in_background()
            search.build_index()
        build.assert_not_called()

    def test_button_rebuilds_the_sqlite_search(self):
        with patch("frappe.enqueue") as enqueue:
            message = search.rebuild_search_index()

        enqueue.assert_called_once()
        self.assertEqual(
            enqueue.call_args.kwargs["search_class_path"], search.SQLITE_SEARCH_CLASS
        )
        self.assertIn("rebuilt", message)

    def test_only_system_managers_can_rebuild(self):
        frappe.set_user("Guest")
        self.addCleanup(frappe.set_user, "Administrator")
        with self.assertRaises(frappe.PermissionError):
            search.rebuild_search_index()


class TestRediSearchDetection(FrappeTestCase):
    def tearDown(self):
        frappe.local.helpdesk_redisearch = None

    def check(self, modules):
        frappe.local.helpdesk_redisearch = None
        with patch.object(frappe.cache(), "module_list", return_value=modules):
            return search.redisearch_available()

    def test_detects_the_module(self):
        self.assertTrue(self.check([{b"name": b"search", b"ver": 20811}]))
        self.assertFalse(self.check([]))
        self.assertFalse(self.check([{b"name": b"ReJSON", b"ver": 1}]))
