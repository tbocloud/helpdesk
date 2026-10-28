from frappe.tests.utils import FrappeTestCase

from helpdesk import kb_drafts, work_summary
from helpdesk.copilot import conversation


class TestAiPrompts(FrappeTestCase):
    """The writing rules each AI prompt promises (and the safety rules they must keep)."""

    def test_chat_acknowledges_then_checks_back(self):
        # the customer chat's engine, in the ERP and in TBO Chat (Copilot Phase 5)
        prompt = conversation.PROMPT
        self.assertIn("acknowledge it in a few words", prompt)
        self.assertIn("asking whether it worked", prompt)
        self.assertIn("Never invent causes", prompt)
        self.assertIn("Never promise a date", prompt)

    def test_weekly_summary_puts_impact_first(self):
        prompt = work_summary.SYSTEM_PROMPT
        self.assertIn("by impact on the customer", prompt)
        self.assertIn("Never invent tickets", prompt)

    def test_kb_articles_are_one_task_with_a_final_check(self):
        prompt = kb_drafts.DRAFT_SYSTEM_PROMPT
        self.assertIn("one task per article", prompt)
        self.assertIn("how they can check it worked", prompt)
        self.assertIn("Never include names", prompt)
