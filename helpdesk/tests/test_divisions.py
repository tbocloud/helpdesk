from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

from helpdesk import content_team, division_overview, divisions
from helpdesk.api import division_overview as overview_api
from helpdesk.api import divisions as divisions_api
from helpdesk.crm_dashboard import sync
from helpdesk.helpdesk.doctype.hd_crm_source.hd_crm_source import HDCRMSource
from helpdesk.integrations.crm import leads
from helpdesk.integrations.crm.client import CRMClient
from helpdesk.test_utils import (
    FakeCRM,
    FakeCRMSite,
    FakeERPSales,
    enable_leads,
    hold_commits,
    make_assignment,
    make_crm_source,
    make_division,
    make_project,
    make_task,
    make_tasky_user,
    make_team,
)

ANN = "ann.division@example.com"  # India employee
BOB = "bob.division@example.com"  # KSA employee
CARA = "cara.division@example.com"  # India division admin
DEV = "dev.division@example.com"  # Agent Manager: Super Admin
TABLES = (
    "HD Division",
    "HD Division Member",
    "HD CRM Source",
    "HD CRM Source Role",
    "HD CRM Source User",
    "HD CRM Report Lead",
)


class DivisionCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")
        frappe.db.set_value("Project", {"division": ("is", "set")}, "division", None)
        for doctype in ("HD Team", "HD Department"):
            frappe.db.set_value(doctype, {"division": ("is", "set")}, "division", None)
        for table in TABLES:
            frappe.db.delete(table)
        frappe.db.delete("DefaultValue", {"defkey": divisions.ACTIVE_DEFAULT})
        frappe.clear_cache()
        for email, name in (
            (ANN, "Ann India"),
            (BOB, "Bob Saudi"),
            (CARA, "Cara Admin"),
        ):
            make_tasky_user(email, name)
        make_tasky_user(DEV, "Dev Super", roles=("Agent Manager",))
        enqueue = patch.object(frappe, "enqueue")
        enqueue.start()
        self.addCleanup(enqueue.stop)

    def make_india_and_ksa(self):
        self.india = make_division(
            "IND",
            "India",
            members=[(ANN, divisions.EMPLOYEE), (CARA, divisions.DIVISION_ADMIN)],
        )
        self.ksa = make_division(
            "KSA",
            "KSA",
            members=[(BOB, divisions.SALES_EXECUTIVE)],
            country="Saudi Arabia",
            currency="SAR",
        )


class TestDivisionIsolation(DivisionCase):
    def test_without_divisions_nothing_changes(self):
        project = make_project("Div Open Project", members=[(ANN, "Developer")])
        self.assertIsNone(divisions.division_condition("`division`", ANN))
        self.assertIsNone(project.division)
        frappe.set_user(ANN)
        self.assertIn(project.name, frappe.get_list("Project", pluck="name"))

    def test_members_see_their_division_and_unassigned_projects_only(self):
        self.make_india_and_ksa()
        team = [(ANN, "Developer"), (BOB, "Developer")]
        india = make_project("Div India Project", members=[(ANN, "Developer")])
        india.db_set("division", "IND")
        ksa = make_project("Div KSA Project", members=[(BOB, "Developer")])
        ksa.db_set("division", "KSA")
        shared = make_project("Div Shared Project", members=team)

        frappe.set_user(ANN)
        seen = frappe.get_list("Project", pluck="name")
        self.assertIn(india.name, seen)
        self.assertIn(shared.name, seen)
        self.assertNotIn(ksa.name, seen)
        self.assertFalse(frappe.has_permission("Project", "read", ksa.name))

        frappe.set_user(DEV)
        seen = frappe.get_list("Project", pluck="name")
        self.assertTrue({india.name, ksa.name, shared.name} <= set(seen))

    def test_a_task_follows_its_projects_division(self):
        self.make_india_and_ksa()
        ksa = make_project("Div KSA Tasks", members=[(BOB, "Developer")])
        ksa.db_set("division", "KSA")
        task = make_task(ksa.name, "Div KSA task")
        task.db_set("owner", ANN)

        frappe.set_user(ANN)
        self.assertNotIn(task.name, frappe.get_list("Task", pluck="name"))
        self.assertFalse(frappe.has_permission("Task", "read", task.name))

    def test_inactive_division_hides_its_records_from_members(self):
        self.make_india_and_ksa()
        project = make_project("Div Paused Project", members=[(BOB, "Developer")])
        project.db_set("division", "KSA")
        self.ksa.db_set("status", "Inactive")
        frappe.set_user(BOB)
        self.assertNotIn(project.name, frappe.get_list("Project", pluck="name"))

    def test_tasks_of_a_division_go_only_to_its_members(self):
        self.make_india_and_ksa()
        project = make_project("Div Assign Project")
        project.db_set("division", "IND")
        task = make_task(project.name, "Div assign task")
        make_assignment("Task", task.name, ANN)
        with self.assertRaisesRegex(frappe.ValidationError, "isn't a member"):
            make_assignment("Task", task.name, BOB)

    def test_a_projects_people_must_be_in_its_division(self):
        self.make_india_and_ksa()
        project = make_project("Div People Project", members=[(BOB, "Developer")])
        project.division = "IND"
        with self.assertRaisesRegex(frappe.ValidationError, "Bob Saudi isn't a member"):
            project.save(ignore_permissions=True)

    def test_new_project_takes_the_makers_active_division(self):
        self.make_india_and_ksa()
        frappe.set_user(ANN)
        project = make_project("Div Default Project")
        self.assertEqual(project.division, "IND")

    def test_nobody_puts_a_project_in_a_division_they_arent_in(self):
        self.make_india_and_ksa()
        frappe.set_user(ANN)
        project = frappe.get_doc(
            {
                "doctype": "Project",
                "project_name": "Div Wrong Division",
                "division": "KSA",
            }
        )
        with self.assertRaises(frappe.PermissionError):
            project.insert(ignore_permissions=True)


class TestActiveDivision(DivisionCase):
    def test_only_super_admins_switch_divisions(self):
        self.make_india_and_ksa()
        self.india.append("members", {"user": BOB, "role": divisions.EMPLOYEE})
        self.india.save()
        # Bob is in India and KSA: he works in his first, and can't switch, not even to his own
        self.assertEqual(divisions.active_division(BOB), "IND")
        frappe.set_user(BOB)
        for division in ("KSA", "IND", None):
            with self.assertRaisesRegex(frappe.PermissionError, "Only Super Admins"):
                divisions_api.switch_division(division)
        # a pick saved earlier no longer moves him
        frappe.defaults.set_user_default(divisions.ACTIVE_DEFAULT, "KSA", BOB)
        self.assertEqual(divisions.active_division(BOB), "IND")

    def test_super_admin_starts_on_all_divisions_and_may_pick_any(self):
        self.make_india_and_ksa()
        self.assertIsNone(divisions.active_division(DEV))
        frappe.set_user(DEV)
        divisions_api.switch_division("KSA")
        self.assertEqual(divisions.active_division(DEV), "KSA")
        frappe.set_user("Administrator")
        log = divisions_api.get_audit_log()
        self.assertTrue(any("Switched to KSA" in e["lines"][0] for e in log))

    def test_the_workspace_url_picks_the_division(self):
        self.make_india_and_ksa()
        self.ksa.db_set("workspace_url", "https://erp.teambackoffice.com")
        request = frappe._dict(host="erp.teambackoffice.com")
        with patch.object(frappe.local, "request", request, create=True):
            self.assertEqual(divisions.active_division(DEV), "KSA")
            # Ann isn't in KSA, so her own division stays
            self.assertEqual(divisions.active_division(ANN), "IND")

    def test_user_info_lists_only_the_persons_divisions(self):
        self.make_india_and_ksa()
        info = divisions.division_info(ANN)
        self.assertEqual([d["name"] for d in info["divisions"]], ["IND"])
        self.assertEqual(info["divisions"][0]["role"], divisions.EMPLOYEE)
        self.assertFalse(info["can_manage_divisions"])
        self.assertFalse(info["can_view_division_overview"])
        self.assertTrue(divisions.division_info(CARA)["can_manage_divisions"])
        self.assertEqual(len(divisions.division_info(DEV)["divisions"]), 2)


class TestDivisionLeadsConnection(DivisionCase):
    def test_leads_go_to_the_active_divisions_erp_site(self):
        source = make_crm_source("KSA ERP")
        self.make_india_and_ksa()
        self.ksa.db_set("crm_source", source.name)
        home = object()
        with patch.object(CRMClient, "from_settings", return_value=home):
            client = divisions.crm_client(BOB)
            self.assertIsInstance(client, CRMClient)
            self.assertEqual(client.base, "https://ksa_erp.example")
            # all divisions: the CRM connection, as before divisions
            self.assertIs(divisions.crm_client(DEV), home)
            # India has no ERP site: the CRM connection's leads are another division's
            with self.assertRaisesRegex(divisions.NoDivisionSiteError, "no ERP site"):
                divisions.crm_client(ANN)
        self.assertFalse(divisions.on_crm_connection(BOB))
        self.assertFalse(divisions.on_crm_connection(ANN), "never India's copy")
        self.assertTrue(divisions.on_crm_connection(DEV))

    def test_a_division_without_an_erp_site_keeps_the_leads_page_closed(self):
        self.make_india_and_ksa()
        self.assertEqual(divisions.division_without_site(ANN), "IND")
        self.assertIsNone(divisions.division_without_site(DEV), "all divisions")
        frappe.set_user(ANN)
        with patch.object(leads, "can_use_leads", return_value=True):
            with self.assertRaisesRegex(frappe.PermissionError, "no ERP site"):
                leads.require_leads()


class TestDivisionSettings(DivisionCase):
    def test_division_validation(self):
        with self.assertRaisesRegex(frappe.ValidationError, "capital letters"):
            make_division("india!")
        with self.assertRaisesRegex(frappe.ValidationError, "isn't a time zone"):
            make_division("IND", time_zone="Mars/Olympus")
        make_division("IND", workspace_url="https://india.teambackoffice.com/")
        with self.assertRaisesRegex(frappe.ValidationError, "already uses"):
            make_division("IN2", workspace_url="https://india.teambackoffice.com")
        with self.assertRaisesRegex(frappe.ValidationError, "listed twice"):
            make_division(
                "UAE",
                members=[(ANN, divisions.EMPLOYEE), (ANN, divisions.SALES_MANAGER)],
            )

    def test_the_administrator_becomes_a_member(self):
        division = make_division("UAE", division_admin=CARA)
        self.assertEqual(
            [(m.user, m.role) for m in division.members],
            [(CARA, divisions.DIVISION_ADMIN)],
        )

    def test_a_division_admin_runs_only_their_division_and_its_local_settings(self):
        self.make_india_and_ksa()
        frappe.set_user(CARA)
        self.assertEqual(
            [d.name for d in divisions_api.get_divisions()["divisions"]], ["IND"]
        )
        with self.assertRaises(frappe.PermissionError):
            divisions_api.get_division("KSA")
        divisions_api.save_division(
            {"time_zone": "Asia/Kolkata", "currency": "USD"}, name="IND"
        )
        india = frappe.get_doc("HD Division", "IND")
        self.assertEqual(india.time_zone, "Asia/Kolkata")
        self.assertEqual(india.currency, "INR")
        with self.assertRaises(frappe.PermissionError):
            divisions_api.save_division(
                {"division_code": "UAE", "division_name": "UAE"}
            )

    def test_only_super_admins_make_group_admins(self):
        self.make_india_and_ksa()
        frappe.set_user(CARA)
        with self.assertRaises(frappe.PermissionError):
            divisions_api.set_members(
                "IND",
                [
                    {"user": CARA, "role": divisions.DIVISION_ADMIN},
                    {"user": ANN, "role": divisions.GROUP_ADMIN},
                ],
            )
        divisions_api.set_members(
            "IND",
            [
                {"user": CARA, "role": divisions.DIVISION_ADMIN},
                {"user": ANN, "role": divisions.SALES_MANAGER},
            ],
        )
        self.assertEqual(divisions.memberships(ANN), {"IND": divisions.SALES_MANAGER})

    def test_teams_move_between_divisions_only_for_super_admins(self):
        self.make_india_and_ksa()
        make_team("Div KSA Team")
        frappe.db.set_value("HD Team", "Div KSA Team", "division", "KSA")
        frappe.set_user(CARA)
        with self.assertRaises(frappe.PermissionError):
            divisions_api.set_units("IND", ["Div KSA Team"], [])
        frappe.set_user(DEV)
        divisions_api.set_units("IND", ["Div KSA Team"], [])
        self.assertEqual(
            frappe.db.get_value("HD Team", "Div KSA Team", "division"), "IND"
        )

    def test_unassigned_projects_move_unless_their_people_are_elsewhere(self):
        self.make_india_and_ksa()
        fits = make_project("Div Fits India", members=[(ANN, "Developer")])
        stays = make_project("Div Stays Out", members=[(BOB, "Developer")])
        frappe.set_user(DEV)
        result = divisions_api.assign_unassigned_projects("IND")
        self.assertIn(stays.name, result["skipped"])
        self.assertEqual(frappe.db.get_value("Project", fits.name, "division"), "IND")
        self.assertFalse(frappe.db.get_value("Project", stays.name, "division"))


class TestDivisionOverview(DivisionCase):
    def setUp(self):
        super().setUp()
        self.make_india_and_ksa()
        frappe.db.set_single_value("HD CRM Settings", "dashboard_currency", "INR")
        self.site = FakeERPSales(customers=7)
        source = make_crm_source("India ERP")
        self.india.db_set("crm_source", source.name)
        client = patch.object(HDCRMSource, "client", lambda doc: self.site)
        client.start()
        self.addCleanup(client.stop)
        frappe.cache.delete_keys(division_overview.CACHE_PREFIX)
        self.today = getdate()

    def test_only_managers_and_super_admins_see_the_overview(self):
        frappe.set_user(ANN)
        with self.assertRaises(frappe.PermissionError):
            overview_api.get_overview()
        frappe.set_user(CARA)
        with self.assertRaises(frappe.PermissionError):
            overview_api.get_overview(division="KSA")
        self.assertEqual(overview_api.get_overview()["kpis"]["divisions"], 1)

    def test_figures_come_from_the_records(self):
        project = make_project("Div Overview Project", members=[(ANN, "Developer")])
        project.db_set("division", "IND")
        late = make_task(
            project.name, "Div late", exp_end_date=add_days(self.today, -2)
        )
        make_assignment("Task", late.name, ANN)
        self.site.add_quotation("Ordered", 1000, self.today)
        self.site.add_quotation("Lost", 400, self.today)
        self.site.add_quotation(
            "Open", 600, add_days(self.today, -800)
        )  # out of period

        frappe.set_user(DEV)
        result = overview_api.get_overview(from_date=str(add_days(self.today, -30)))
        kpis = result["kpis"]
        self.assertEqual(kpis["divisions"], 2)
        self.assertEqual(kpis["employees"], 3)
        self.assertEqual(kpis["customers"], 7)
        self.assertEqual(kpis["quotations"], 2)
        self.assertEqual(kpis["sales_value"], 1000)
        self.assertEqual(kpis["active_projects"], 1)
        self.assertEqual(kpis["pending_activities"], 1)
        india = next(r for r in result["rows"] if r["name"] == "IND")
        self.assertEqual(india["overdue_tasks"], 1)
        self.assertEqual(india["quotation_conversion"], 50.0)
        ksa = next(r for r in result["rows"] if r["name"] == "KSA")
        # no ERP site: unknown, never zero
        self.assertIsNone(ksa["customers"])
        self.assertTrue(ksa["erp_error"])
        ann = next(p for p in result["top_people"] if p["user"] == ANN)
        self.assertEqual((ann["open"], ann["overdue"]), (1, 1))

    def test_a_site_that_cant_answer_is_named_not_counted(self):
        self.site.down = True
        frappe.set_user(DEV)
        result = overview_api.get_overview(division="IND")
        self.assertIsNone(result["kpis"]["customers"])
        self.assertEqual(result["errors"][0]["division"], "India")

    def test_every_report_builds_and_exports(self):
        self.site.add_quotation("Ordered", 1000, self.today)
        frappe.set_user(DEV)
        keys = [r["key"] for r in overview_api.get_reports()["reports"]]
        self.assertEqual(len(keys), 9)
        for key in keys:
            report = overview_api.get_report(key)
            self.assertTrue(report["columns"], key)
        overview_api.export_report("quotations", "xlsx", division="IND")
        self.assertTrue(frappe.response.filename.endswith(".xlsx"))
        self.assertTrue(
            frappe.db.exists(
                "Activity Log",
                {"subject": ("like", "Exported Division-wise quotations%")},
            )
        )


class TestDivisionSiteRoles(DivisionCase):
    """A division whose ERP site decides access (docs/divisions.md): KSA's site makes Ann a
    Sales Manager (she is a member of India only) and Bob, its Sales Executive, a Sales User.
    """

    def setUp(self):
        super().setUp()
        self.make_india_and_ksa()
        self.site = FakeCRMSite()
        client = patch.object(HDCRMSource, "client", lambda doc: self.site)
        client.start()
        self.addCleanup(client.stop)
        self.site.add_user(ANN, "Sales Manager")
        self.site.add_user(BOB, "Sales User")
        self.ksa.db_set("crm_source", make_crm_source("KSA ERP", use_erp_roles=1).name)
        sync.run_job("KSA ERP")

    def test_the_sites_managers_and_the_division_admins_see_its_overview(self):
        self.assertEqual(divisions.overview_divisions(ANN), ["KSA"])
        self.assertEqual(divisions.overview_divisions(BOB), [], "an executive there")
        self.assertEqual(divisions.overview_divisions(CARA), ["IND"], "India unchanged")
        self.assertEqual(divisions.overview_divisions(DEV), ["IND", "KSA"])

    def test_the_leads_page_needs_a_sales_role_on_the_divisions_site(self):
        self.assertIsNone(divisions.leads_closed_by_site(BOB))
        self.site.add_user(BOB, "Employee")
        sync.run_job("KSA ERP")
        self.assertEqual(divisions.leads_closed_by_site(BOB), "KSA ERP")
        self.assertIsNone(divisions.leads_closed_by_site(ANN), "India is not narrowed")
        frappe.set_user(BOB)
        with patch.object(leads, "can_use_leads", return_value=True):
            with self.assertRaisesRegex(frappe.PermissionError, "no sales role"):
                leads.require_leads()


class TestDivisionSalesRoles(DivisionCase):
    """Division Admins and Division Sales Users get their role on the division's ERP site,
    whose lead rules decide what they see: a Sales Manager every lead, a Sales User their
    own. Ann is a Sales Manager on India's site, Cara (India's Division Admin) a Sales User
    there and Bob has no user there."""

    def setUp(self):
        super().setUp()
        self.make_india_and_ksa()
        self.erp = FakeCRM(
            users=[
                {
                    "name": ANN,
                    "roles": [{"role": "Sales Manager"}, {"role": "Blogger"}],
                },
                {"name": CARA, "roles": [{"role": "Sales User"}]},
            ]
        )
        client = patch.object(HDCRMSource, "client", lambda doc: self.erp)
        client.start()
        self.addCleanup(client.stop)
        self.source = make_crm_source("India ERP")

    def roles(self, user):
        return {r["role"] for r in self.erp.users[user]["roles"]}

    def set_india_members(self, *members):
        return divisions_api.set_members(
            "IND", [{"user": u, "role": r} for u, r in members]
        )

    def test_giving_the_division_its_site_makes_its_admin_a_sales_manager(self):
        result = divisions_api.save_division({"crm_source": self.source.name}, "IND")
        self.assertEqual(result["erp_problems"], [])
        self.assertEqual(self.roles(CARA), {"Sales User", "Sales Manager"})
        self.assertEqual(self.roles(ANN), {"Sales Manager", "Blogger"}, "an employee")

    def test_a_division_sales_user_keeps_only_their_own_leads(self):
        self.india.db_set("crm_source", self.source.name)
        result = self.set_india_members(
            (ANN, divisions.DIVISION_SALES_USER), (CARA, divisions.DIVISION_ADMIN)
        )
        self.assertEqual(result["erp_problems"], [])
        # Sales Manager would show her every lead; her other roles stay
        self.assertEqual(self.roles(ANN), {"Sales User", "Blogger"})
        self.assertEqual(
            self.erp.role_calls[:2], [(ANN, "-Sales Manager"), (ANN, "Sales User")]
        )

    def test_every_save_sets_whoever_isnt_right_on_the_site_yet(self):
        self.india.db_set("crm_source", self.source.name)
        # Cara was Division Admin before the site was set: the next save fixes her
        self.set_india_members(
            (ANN, divisions.EMPLOYEE), (CARA, divisions.DIVISION_ADMIN)
        )
        self.assertEqual(self.erp.role_calls, [(CARA, "Sales Manager")])
        # already right there: nothing is written again
        self.set_india_members((CARA, divisions.DIVISION_ADMIN))
        self.assertEqual(self.erp.role_calls, [(CARA, "Sales Manager")])

    def test_what_the_site_cant_do_is_reported_per_person(self):
        self.india.db_set("crm_source", self.source.name)
        self.erp.users[ANN]["roles"].append({"role": "System Manager"})
        result = self.set_india_members(
            (ANN, divisions.DIVISION_SALES_USER),
            (BOB, divisions.DIVISION_SALES_USER),
            (CARA, divisions.DIVISION_ADMIN),
        )
        problems = result["erp_problems"]
        self.assertEqual(len(problems), 2)
        self.assertIn("System Manager on India ERP", problems[0])
        self.assertIn("Bob Saudi has no enabled user on India ERP", problems[1])
        self.assertEqual(frappe.db.count("HD Division Member", {"parent": "IND"}), 3)

    def test_without_a_site_nothing_is_sent(self):
        result = self.set_india_members((ANN, divisions.DIVISION_SALES_USER))
        self.assertEqual(result["erp_problems"], [])
        self.assertEqual(self.erp.role_calls, [])

    def test_the_two_roles_open_the_leads_page_in_their_division(self):
        make_team("Leads Only Team", [])
        enable_leads(teams=("Leads Only Team",))
        self.india.db_set("crm_source", self.source.name)
        self.assertFalse(leads.can_use_leads(ANN), "an employee outside the team")
        self.set_india_members(
            (ANN, divisions.DIVISION_SALES_USER), (CARA, divisions.DIVISION_ADMIN)
        )
        self.assertTrue(leads.can_use_leads(ANN))
        self.assertTrue(leads.can_use_leads(CARA))
        self.assertFalse(leads.can_use_leads(BOB), "a Sales Executive in KSA")

    def test_the_two_roles_get_the_sales_screens_as_manager_or_salesperson(self):
        self.india.db_set("crm_source", self.source.name)
        self.set_india_members(
            (ANN, divisions.DIVISION_SALES_USER), (CARA, divisions.DIVISION_ADMIN)
        )
        self.assertTrue(content_team.is_sales_employee(ANN))
        self.assertTrue(content_team.is_sales_employee(CARA))
        self.assertFalse(content_team.is_sales_employee(DEV), "a Super Admin")
        # the sales user gets their own leads and calls, the admin the team's view
        self.assertTrue(content_team.is_sales_bd_role(ANN))
        self.assertFalse(content_team.is_sales_bd_role(CARA))
        self.assertEqual(divisions.scoreboard_people(ANN), {ANN})
        self.assertEqual(divisions.scoreboard_people(CARA), {ANN, CARA})
        self.assertIsNone(divisions.scoreboard_people(DEV))
        self.assertIsNone(divisions.scoreboard_people(BOB), "KSA's Sales Executive")


class TestDivisionAgents(DivisionCase):
    """A division's admins see its agents and bring people into it (docs/divisions.md,
    "Agents of a division"): Cara runs India, Ann works in it, Bob in KSA."""

    NEW = "new.division.agent@example.com"

    def setUp(self):
        super().setUp()
        self.make_india_and_ksa()
        frappe.db.delete("User Invitation", {"email": self.NEW})
        frappe.set_user(CARA)

    def test_an_admin_sees_only_their_divisions_agents(self):
        agents = divisions_api.get_division_agents("IND")
        self.assertEqual(
            {a["user"]: a["role"] for a in agents["agents"]},
            {ANN: divisions.EMPLOYEE, CARA: divisions.DIVISION_ADMIN},
        )
        self.assertNotIn(divisions.GROUP_ADMIN, agents["roles"])
        with self.assertRaises(frappe.PermissionError):
            divisions_api.get_division_agents("KSA")

    def test_an_agent_already_here_joins_now_without_an_invite(self):
        result = divisions_api.invite_to_division(
            "IND", BOB, divisions.DIVISION_SALES_USER
        )
        self.assertEqual(result["added"], [BOB])
        self.assertEqual(
            divisions.memberships(BOB),
            {"IND": divisions.DIVISION_SALES_USER, "KSA": divisions.SALES_EXECUTIVE},
        )
        self.assertFalse(frappe.db.exists("User Invitation", {"email": BOB}))
        again = divisions_api.invite_to_division("IND", BOB, divisions.EMPLOYEE)
        self.assertEqual(again["already_member"], [BOB])

    def test_someone_new_is_invited_as_an_agent_and_joins_on_accepting(self):
        result = divisions_api.invite_to_division(
            "IND", self.NEW, divisions.DIVISION_SALES_USER
        )
        self.assertEqual(result["invited"], [self.NEW])
        invitation = frappe.get_doc("User Invitation", {"email": self.NEW})
        self.assertEqual([r.role for r in invitation.roles], ["Agent"])
        self.assertEqual(
            (invitation.division, invitation.division_role),
            ("IND", divisions.DIVISION_SALES_USER),
        )
        pending = divisions_api.get_division_agents("IND")["invites"]
        self.assertEqual([i["email"] for i in pending], [self.NEW])
        again = divisions_api.invite_to_division("IND", self.NEW, divisions.EMPLOYEE)
        self.assertEqual(again["already_invited"], [self.NEW])

        frappe.set_user("Administrator")
        invitation.accept(ignore_permissions=True)
        self.assertTrue(frappe.db.get_value("HD Agent", self.NEW, "is_active"))
        self.assertEqual(
            divisions.memberships(self.NEW), {"IND": divisions.DIVISION_SALES_USER}
        )

    def test_an_admin_cant_give_group_admin_or_bring_people_elsewhere(self):
        with self.assertRaisesRegex(frappe.ValidationError, "isn't a role"):
            divisions_api.invite_to_division("IND", self.NEW, divisions.GROUP_ADMIN)
        with self.assertRaises(frappe.PermissionError):
            divisions_api.invite_to_division("KSA", self.NEW, divisions.EMPLOYEE)
        frappe.set_user(ANN)
        with self.assertRaises(frappe.PermissionError):
            divisions_api.invite_to_division("IND", self.NEW, divisions.EMPLOYEE)

    def test_a_division_invite_can_be_cancelled_by_its_admins_only(self):
        divisions_api.invite_to_division("IND", self.NEW, divisions.EMPLOYEE)
        name = frappe.db.get_value("User Invitation", {"email": self.NEW})
        frappe.set_user(BOB)
        with self.assertRaises(frappe.PermissionError):
            divisions_api.cancel_division_invite("IND", name)
        frappe.set_user(CARA)
        divisions_api.cancel_division_invite("IND", name)
        self.assertEqual(
            frappe.db.get_value("User Invitation", name, "status"), "Cancelled"
        )

    def test_a_plain_invite_still_needs_an_inviting_role(self):
        invitation = frappe.get_doc(
            doctype="User Invitation",
            email=self.NEW,
            roles=[{"role": "Agent"}],
            app_name="helpdesk",
            redirect_to_path="/helpdesk",
            division="IND",
            division_role=divisions.EMPLOYEE,
        )
        # no division_invite flag: Cara holds no inviting role of her own
        with self.assertRaisesRegex(frappe.ValidationError, "not an allowed role"):
            invitation.insert(ignore_permissions=True)
