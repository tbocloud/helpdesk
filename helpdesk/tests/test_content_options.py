import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.content_options import (
    DEFAULT_PLATFORMS,
    DEFAULT_POST_TYPES,
    ensure_default_content_options,
)
from helpdesk.test_utils import (
    create_customer,
    hold_commits,
    make_content_option,
    make_content_post,
)

CUSTOMER = "Content Options Traders"


class TestContentOptions(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        create_customer(CUSTOMER)
        ensure_default_content_options()

    def test_every_site_has_the_default_options(self):
        self.assertTrue(
            set(DEFAULT_PLATFORMS)
            <= set(frappe.get_all("HD Content Platform", pluck="name"))
        )
        self.assertTrue(
            set(DEFAULT_POST_TYPES)
            <= set(frappe.get_all("HD Content Post Type", pluck="name"))
        )
        # running it again adds nothing
        self.assertEqual(ensure_default_content_options(), [])

    def test_a_new_option_goes_to_the_end_of_the_list(self):
        threads = make_content_option("HD Content Platform", "  Threads ")

        self.assertEqual(threads.name, "Threads")
        highest = max(frappe.get_all("HD Content Platform", pluck="sort_order"))
        self.assertEqual(threads.sort_order, highest)

    def test_posts_can_use_options_the_team_added(self):
        make_content_option("HD Content Platform", "Threads")
        make_content_option("HD Content Post Type", "Infographic")

        post = make_content_post(
            "Monsoon tips", CUSTOMER, channel="Threads", format="Infographic"
        )

        self.assertEqual(post.platforms, "Threads")
        self.assertEqual(post.format, "Infographic")

    def test_unknown_platform_is_rejected(self):
        with self.assertRaises(frappe.LinkValidationError):
            make_content_post("Retro post", CUSTOMER, channel="MySpace")
