import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api.knowledge_base import get_featured_articles
from helpdesk.test_utils import make_article, make_article_category


class TestFeaturedArticles(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.category = make_article_category("Featured articles test")
        self.most_read = make_article("Reset your ERP password", "<p>Steps</p>")
        self.less_read = make_article("Export a report to Excel", "<p>Steps</p>")
        self.unread = make_article(
            "Change the print format", "<p>Steps</p>", category=self.category.name
        )
        self.draft = make_article(
            "Draft: closing the year", "<p>Steps</p>", status="Draft"
        )
        for article, views in (
            (self.most_read, 900000),
            (self.less_read, 800000),
            (self.draft, 950000),
        ):
            frappe.db.set_value(
                "HD Article", article.name, "views", views, update_modified=False
            )

    def names(self, articles):
        return [a["name"] for a in articles]

    def test_popular_is_most_viewed_first_and_skips_unread_and_drafts(self):
        popular = self.names(get_featured_articles(limit=20)["popular"])

        self.assertLess(
            popular.index(self.most_read.name), popular.index(self.less_read.name)
        )
        self.assertNotIn(self.unread.name, popular)
        self.assertNotIn(self.draft.name, popular)

    def test_recent_lists_published_articles_with_their_category(self):
        recent = get_featured_articles(limit=20)["recent"]

        self.assertIn(self.unread.name, self.names(recent))
        self.assertNotIn(self.draft.name, self.names(recent))
        article = next(a for a in recent if a["name"] == self.unread.name)
        self.assertEqual(article["category_name"], "Featured articles test")
