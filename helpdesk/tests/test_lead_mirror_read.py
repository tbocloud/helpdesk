from unittest.mock import patch

import frappe

from helpdesk import lead_mirror, lead_mirror_read
from helpdesk.api import leads as leads_api
from helpdesk.integrations.crm.leads import (
    LeadsNotDeployedError,
    LeadsUnavailableError,
)
from helpdesk.tests.test_lead_mirror import ANN, BOB, LeadMirrorCase

CARA = "cara@erp.example"
HEAD = "head@erp.example"
STRANGER = "stranger@erp.example"


class LeadCopyCase(LeadMirrorCase):
    def setUp(self):
        super().setUp()
        self.erp.scopes = {
            ANN: {"all": True, "team": [], "departments": []},
            BOB: {"all": False, "team": [BOB], "departments": []},
            CARA: {"all": False, "team": [CARA, BOB], "departments": []},
            HEAD: {"all": False, "team": [HEAD], "departments": ["Growth"]},
            "Administrator": {"all": True, "team": [], "departments": []},
        }
        self.erp.put("L-1", lead_name="Ravi Traders", lead_owner=ANN)
        self.erp.put("L-2", lead_name="Bob's Own", lead_owner=BOB, tbo_stage="Contacted")
        self.erp.put("L-3", lead_name="Given To Bob", lead_owner=ANN, assignees=[BOB])
        self.erp.put(
            "L-4", lead_name="Growth Lead", lead_owner=ANN, tbo_department="Growth"
        )
        lead_mirror.backfill_lead_mirror()

    def listed(self, user: str, **params) -> list[str]:
        return sorted(
            row["name"] for row in lead_mirror_read.list_copy(user, **params)["rows"]
        )


class TestWhoSeesWhat(LeadCopyCase):
    def test_each_person_sees_the_leads_the_erp_would_show_them(self):
        self.assertEqual(self.listed(ANN), ["L-1", "L-2", "L-3", "L-4"])
        # their own, and the ones assigned to them
        self.assertEqual(self.listed(BOB), ["L-2", "L-3"])
        # a team leader: their team's too
        self.assertEqual(self.listed(CARA), ["L-2", "L-3"])
        # a head: their department's
        self.assertEqual(self.listed(HEAD), ["L-4"])

    def test_someone_the_erp_does_not_know_gets_no_copy(self):
        self.assertIsNone(lead_mirror_read.list_copy(STRANGER))
        self.assertIsNone(lead_mirror_read.lead_copy(STRANGER, "L-1"))

    def test_a_lead_opens_read_only_and_only_for_those_who_may_see_it(self):
        detail = lead_mirror_read.lead_copy(BOB, "L-2")
        self.assertEqual(detail["lead"]["name"], "L-2")
        self.assertEqual(
            (detail["lead"]["can_write"], detail["allowed_stages"], detail["from_copy"]),
            (False, [], True),
        )
        self.assertTrue(detail["copied_at"])
        self.assertIsNone(lead_mirror_read.lead_copy(BOB, "L-1"))
        self.assertIsNone(lead_mirror_read.lead_copy(ANN, "L-404"))


class TestTheListFromTheCopy(LeadCopyCase):
    def test_search_filters_mine_and_pages(self):
        self.assertEqual(self.listed(ANN, search="ravi"), ["L-1"])
        self.assertEqual(self.listed(ANN, stage="Contacted"), ["L-2"])
        self.assertEqual(self.listed(ANN, owner=[BOB, HEAD]), ["L-2"])
        self.assertEqual(self.listed(ANN, department='["Growth"]'), ["L-4"])
        self.assertEqual(self.listed(ANN, mine=True), ["L-1", "L-3", "L-4"])
        page = lead_mirror_read.list_copy(ANN, start=1, page_length=2)
        self.assertEqual((page["total"], len(page["rows"])), (4, 2))
        self.assertTrue(page["from_copy"])
        # the last changed first
        self.assertEqual(lead_mirror_read.list_copy(ANN)["rows"][0]["name"], "L-4")


class TestTheErpIsAway(LeadCopyCase):
    def setUp(self):
        super().setUp()
        allowed = patch.object(leads_api, "require_leads")
        allowed.start()
        self.addCleanup(allowed.stop)
        self.addCleanup(frappe.clear_messages)

    def away(self, error=LeadsUnavailableError):
        def fail(*_args, **_kwargs):
            frappe.throw("The ERP site is away.", exc=error)

        return patch.object(leads_api, "call", side_effect=fail)

    def test_the_list_and_a_lead_come_from_the_copy(self):
        with self.away():
            page = leads_api.list_leads(search="ravi")
            detail = leads_api.get_lead("L-1")
        self.assertEqual([row["name"] for row in page["rows"]], ["L-1"])
        self.assertTrue(page["from_copy"])
        self.assertEqual((detail["lead"]["name"], detail["from_copy"]), ("L-1", True))
        # the ERP's error is not also shown as a toast
        self.assertEqual(frappe.get_message_log(), [])

    def test_the_erp_is_asked_first_and_its_answer_wins(self):
        answer = {"rows": [{"name": "L-9"}], "total": 1}
        with patch.object(leads_api, "call", return_value=answer):
            self.assertEqual(leads_api.list_leads(), answer)

    def test_what_only_the_erp_can_work_out_stays_an_error(self):
        with self.away():
            for params in (
                {"view": "follow_up"},
                {"view": "called"},
                {"segment": "hot"},
                {"metric": "new_leads", "period": "month"},
                {"created_by_me": 1},
            ):
                with self.assertRaises(LeadsUnavailableError, msg=params):
                    leads_api.list_leads(**params)
            with self.assertRaises(LeadsUnavailableError):
                leads_api.get_lead("L-404")

    def test_no_copy_is_used_while_it_is_off_not_yet_filled_or_the_erp_is_too_old(self):
        with self.away(LeadsNotDeployedError):
            with self.assertRaises(LeadsNotDeployedError):
                leads_api.list_leads()
        lead_mirror.set_state(since="")
        with self.away(), self.assertRaises(LeadsUnavailableError):
            leads_api.list_leads()
        lead_mirror.set_state(since="2031-03-04 05:06:07", enabled=0)
        with self.away(), self.assertRaises(LeadsUnavailableError):
            leads_api.list_leads()
