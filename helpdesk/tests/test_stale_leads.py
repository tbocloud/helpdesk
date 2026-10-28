from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import follow_ups
from helpdesk.api import leads as leads_api
from helpdesk.integrations.crm.client import CRMError
from helpdesk.test_utils import (
    FakeCRM,
    create_agent,
    enable_leads,
    follow_up_context,
    get_follow_up_notices,
    hold_commits,
    lead_department,
    make_sales_manager,
    make_tasky_user,
    set_follow_up_settings,
    stale_lead,
)

BDE = "bde.agent@leads.example"
MANAGER = "manager.stale@leads.example"
OWNER = "asha.sales@leads.example"
HEAD = "head.stale@leads.example"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
OLDER_ERP = CRMError(
    "x", 417, "Failed to get method for command tbo_smart.api.hub_leads.x"
)


class LeadsWave1Case(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(follow_ups.clear_cache)
        create_agent(BDE, "Bina", "BDE")
        enable_leads()
        self.crm = FakeCRM()
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)

    def calls(self, method):
        return [
            (post, params)
            for name, post, params in self.crm.lead_calls
            if name == method
        ]


class TestDuplicateCheck(LeadsWave1Case):
    def test_matches_come_from_the_erp_site_as_the_signed_in_person(self):
        match = {"name": "CRM-LEAD-0007", "lead_owner": OWNER, "matched_on": ["email"]}
        self.crm.lead_answers["find_duplicate_leads"] = [match]
        frappe.set_user(BDE)

        result = leads_api.find_duplicate_leads(
            email=" a@b.co ", phone="", company=None, exclude="CRM-LEAD-0001"
        )

        self.assertEqual(result, {"available": True, "matches": [match]})
        ((post, params),) = self.calls("find_duplicate_leads")
        self.assertFalse(post)
        self.assertEqual(params["acting_user"], BDE)
        self.assertEqual(
            (params["email"], params["phone"], params["exclude"]),
            ("a@b.co", None, "CRM-LEAD-0001"),
        )

    def test_nothing_typed_asks_nobody(self):
        frappe.set_user(BDE)
        self.assertEqual(
            leads_api.find_duplicate_leads(email=" ", phone=None),
            {"available": True, "matches": []},
        )
        self.assertEqual(self.crm.lead_calls, [])

    def test_an_older_erp_site_skips_the_check_quietly(self):
        self.crm.lead_answers["find_duplicate_leads"] = OLDER_ERP
        frappe.set_user(BDE)
        frappe.clear_messages()
        self.assertEqual(
            leads_api.find_duplicate_leads(email="a@b.co"),
            {"available": False, "matches": []},
        )
        self.assertEqual(frappe.message_log, [])

    def test_a_repeat_is_created_only_when_confirmed(self):
        frappe.set_user(BDE)
        leads_api.create_lead({"lead_name": "Asha"})
        leads_api.create_lead({"lead_name": "Asha"}, allow_duplicate="1")

        plain, confirmed = (params for _post, params in self.calls("create_lead"))
        self.assertNotIn("allow_duplicate", plain)
        self.assertEqual(confirmed["allow_duplicate"], 1)

    def test_the_erp_sites_refusal_reaches_the_person(self):
        self.crm.lead_answers["create_lead"] = CRMError(
            "x",
            417,
            "DuplicateEntryError",
            user_message="Possible duplicate of CRM-LEAD-0007 (Asha)",
        )
        frappe.set_user(BDE)
        with self.assertRaises(frappe.ValidationError) as caught:
            leads_api.create_lead({"lead_name": "Asha"})
        self.assertIn("Possible duplicate", str(caught.exception))


class TestStaleLeadsForTheList(LeadsWave1Case):
    def setUp(self):
        super().setUp()
        self.crm.lead_answers["get_options"] = {
            "departments": [
                lead_department("GrowthX", stale_after_days=5),
                lead_department("Pod", stale_after_days=2),
            ]
        }
        self.crm.lead_answers["get_stale_leads"] = [
            stale_lead("L-1", 4),
            stale_lead("L-2", 6),
            stale_lead("L-3", 2, tbo_department="Pod"),
            stale_lead("L-4", 3, tbo_department=None),
        ]
        frappe.set_user(BDE)

    def test_each_department_keeps_its_own_days(self):
        result = leads_api.get_stale_leads()

        self.assertTrue(result["available"])
        # L-1 is 4 days idle in a 5-day department: not yet; no department: 3 days
        self.assertEqual([r["name"] for r in result["leads"]], ["L-2", "L-3", "L-4"])
        ((_post, params),) = self.calls("get_stale_leads")
        # asked for the shortest threshold, so every department can be checked here
        self.assertEqual((params["days"], params["acting_user"]), (2, BDE))

    def test_the_answer_is_cached_per_person(self):
        leads_api.get_stale_leads()
        leads_api.get_stale_leads()
        self.assertEqual(len(self.calls("get_stale_leads")), 1)
        leads_api.get_stale_leads(fresh=1)
        self.assertEqual(len(self.calls("get_stale_leads")), 2)

    def test_an_older_erp_site_leaves_the_chip_out(self):
        self.crm.lead_answers["get_stale_leads"] = OLDER_ERP
        frappe.clear_messages()
        self.assertEqual(leads_api.get_stale_leads(), {"available": False, "leads": []})
        self.assertEqual(frappe.message_log, [])


class TestStaleLeadFollowUps(LeadsWave1Case):
    def setUp(self):
        super().setUp()
        make_sales_manager(MANAGER, "Maya")
        make_tasky_user(OWNER, "Asha Sales")
        make_tasky_user(HEAD, "Hari Head")
        self.crm.lead_answers["get_lead_departments"] = [
            lead_department("GrowthX", heads=(HEAD,), stale_after_days=3)
        ]
        self.crm.lead_answers["get_stale_leads"] = [
            stale_lead("L-1", 4),
            stale_lead("L-2", 6),
        ]
        self.addCleanup(
            frappe.clear_document_cache,
            "HD Follow Up Settings",
            "HD Follow Up Settings",
        )
        # a site's stored settings predate the rule, until the patch switches it on
        set_follow_up_settings(stale_leads=1)

    def found(self, **settings):
        return {
            f.name: f
            for f in follow_ups.LeadRules(follow_up_context(**settings)).evaluate()
        }

    def test_the_owner_is_told_and_the_heads_at_twice_the_days(self):
        found = self.found()

        l0, l1 = found["L-1"], found["L-2"]
        self.assertEqual((l0.level, l0.stage, l0.recipients), (0, "L0", [OWNER]))
        self.assertIn("has had no activity for 4 days", l0.text)
        self.assertEqual((l1.level, l1.stage), (1, "L1"))
        self.assertEqual(set(l1.recipients), {OWNER, HEAD})
        self.assertEqual(l0.link, "/leads/L-1")
        # the ERP site is asked as a manager, who sees every lead
        ((_post, params),) = self.calls("get_stale_leads")
        self.assertEqual(params["acting_user"], MANAGER)

    def test_a_lead_with_no_owner_goes_to_its_heads(self):
        self.crm.lead_answers["get_stale_leads"] = [
            stale_lead("L-5", 4, lead_owner=None)
        ]
        self.assertEqual(self.found()["L-5"].recipients, [HEAD])

    def test_the_rule_can_be_switched_off(self):
        self.assertEqual(self.found(stale_leads=0), {})
        self.assertEqual(self.crm.lead_calls, [])

    def test_an_older_erp_site_adds_nothing_and_breaks_nothing(self):
        self.crm.lead_answers["get_stale_leads"] = OLDER_ERP
        self.assertEqual(self.found(), {})
        self.crm.lead_answers["get_stale_leads"] = CRMError("x", 500, "boom")
        self.assertEqual(self.found(), {})

    def test_nothing_runs_while_leads_are_off(self):
        frappe.db.set_single_value("HD CRM Settings", "enable_leads", 0)
        self.assertEqual(self.found(), {})
        self.assertEqual(self.crm.lead_calls, [])

    def test_evaluate_includes_the_lead_rule(self):
        names = {f.name for f in follow_ups.evaluate(follow_up_context())}
        self.assertLessEqual({"L-1", "L-2"}, names)

    def test_one_notice_per_person_and_lead_that_reopens_only_on_a_new_level(self):
        ctx = follow_up_context()
        with patch("helpdesk.chat_notifications.post_escalation"):
            follow_ups.post_notices(follow_ups.evaluate(ctx), ctx.today)
            follow_ups.post_notices(follow_ups.evaluate(ctx), ctx.today)
        (notice,) = get_follow_up_notices(OWNER, "L-1")
        self.assertEqual(len(get_follow_up_notices(HEAD, "L-2")), 1)
        self.assertEqual(get_follow_up_notices(HEAD, "L-1"), [])

        frappe.db.set_value("HD Notification", notice.name, "read", 1)
        self.crm.lead_answers["get_stale_leads"] = [stale_lead("L-1", 4)]
        ctx = follow_up_context()
        follow_ups.post_notices(follow_ups.evaluate(ctx), ctx.today)
        self.assertEqual(get_follow_up_notices(OWNER, "L-1")[0]["read"], 1)

        self.crm.lead_answers["get_stale_leads"] = [stale_lead("L-1", 7)]
        with patch("helpdesk.chat_notifications.post_escalation"):
            follow_ups.post_notices(follow_ups.evaluate(ctx), ctx.today)
        (reopened,) = get_follow_up_notices(OWNER, "L-1")
        self.assertEqual(reopened["read"], 0)
        self.assertEqual(len(get_follow_up_notices(HEAD, "L-1")), 1)


class TestFollowUpSettingsDefault(LeadsWave1Case):
    def test_the_lead_rule_is_on_by_default(self):
        self.assertEqual(frappe.new_doc("HD Follow Up Settings").stale_leads, 1)

    def test_the_patch_switches_it_on_where_settings_were_stored(self):
        from helpdesk.patches.v16_0_2 import enable_stale_lead_follow_up

        frappe.db.set_single_value("HD Follow Up Settings", "stale_leads", 0)
        enable_stale_lead_follow_up.execute()
        self.assertEqual(
            frappe.db.get_single_value("HD Follow Up Settings", "stale_leads"), 1
        )
