from frappe.tests.utils import FrappeTestCase

from helpdesk import chatwoot_bridge, kb_drafts, work_summary


class TestAiPrompts(FrappeTestCase):
    """The writing rules each AI prompt promises (and the safety rules they must keep)."""

    def test_chat_acknowledges_then_checks_back(self):
        prompt = chatwoot_bridge.CHAT_SYSTEM_PROMPT
        self.assertIn("acknowledge it in a few words", prompt)
        self.assertIn("asking whether it worked", prompt)
        self.assertIn("Never invent causes", prompt)

    def test_weekly_summary_puts_impact_first(self):
        prompt = work_summary.SYSTEM_PROMPT
        self.assertIn("by impact on the customer", prompt)
        self.assertIn("Never invent tickets", prompt)

    def test_kb_articles_are_one_task_with_a_final_check(self):
        prompt = kb_drafts.DRAFT_SYSTEM_PROMPT
        self.assertIn("one task per article", prompt)
        self.assertIn("how they can check it worked", prompt)
        self.assertIn("Never include names", prompt)
