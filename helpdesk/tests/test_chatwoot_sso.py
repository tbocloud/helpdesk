from urllib.parse import unquote

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import chatwoot_sso
from helpdesk.api.chatwoot_sso import get_settings, save_settings
from helpdesk.test_utils import (
    CHATWOOT_TEST_PLATFORM_TOKEN,
    CHATWOOT_TEST_SIGN_IN,
    create_user,
    enable_chatwoot_sso,
    fake_chatwoot_platform,
    hold_commits,
    make_tasky_user,
    open_tbo_chat,
    reset_chat_sign_in_limit,
    run_as_user,
)

AGENT = ("anjali@chatsso.example", "Anjali Pillai")
MANAGER = ("joseph@chatsso.example", "Joseph Thomas")
OUTSIDER = "visitor@chatsso.example"
PLATFORM_USERS = "/platform/api/v1/users"
ACCOUNT_USERS = "/platform/api/v1/accounts/1/account_users"


class TestChatwootSignIn(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_tasky_user(*AGENT)
        make_tasky_user(*MANAGER, roles=("Agent Manager",))
        create_user(OUTSIDER)
        enable_chatwoot_sso()
        for user in (AGENT[0], MANAGER[0], OUTSIDER):
            reset_chat_sign_in_limit(user)
            self.addCleanup(reset_chat_sign_in_limit, user)

    def test_guest_is_sent_to_sign_in_and_back(self):
        api = fake_chatwoot_platform(self)
        response = open_tbo_chat("Guest")
        self.assertEqual(response["type"], "redirect")
        self.assertTrue(response["location"].startswith("/login?redirect-to="))
        self.assertEqual(
            unquote(response["location"].partition("redirect-to=")[2]),
            chatwoot_sso.LOGIN_PATH,
        )
        self.assertEqual(api.calls, [])

    def test_someone_who_isnt_an_agent_is_refused(self):
        api = fake_chatwoot_platform(self)
        response = open_tbo_chat(OUTSIDER)
        self.assertEqual(response["type"], "page")
        self.assertEqual(response["http_status_code"], 403)
        self.assertEqual(api.calls, [])

    def test_an_inactive_agent_is_refused(self):
        frappe.db.set_value("HD Agent", {"user": AGENT[0]}, "is_active", 0)
        api = fake_chatwoot_platform(self)
        self.assertEqual(open_tbo_chat(AGENT[0])["http_status_code"], 403)
        self.assertEqual(api.calls, [])

    def test_nobody_gets_in_while_sign_in_is_off(self):
        enable_chatwoot_sso(sso_enabled=0)
        api = fake_chatwoot_platform(self)
        self.assertEqual(open_tbo_chat(AGENT[0])["http_status_code"], 404)
        self.assertEqual(api.calls, [])

    def test_an_agent_in_the_account_is_sent_to_the_one_time_link(self):
        api = fake_chatwoot_platform(
            self,
            agents=[{"id": 501, "email": "Anjali@ChatSSO.example", "role": "agent"}],
        )
        response = open_tbo_chat(AGENT[0])
        self.assertEqual(response["type"], "redirect")
        self.assertEqual(response["location"], CHATWOOT_TEST_SIGN_IN)
        # members keep their account role: nothing is added or changed
        self.assertEqual(api.calls_to(ACCOUNT_USERS), [])
        platform = [c for c in api.calls if "/platform/" in c["url"]]
        self.assertTrue(platform)
        self.assertTrue(
            all(c["token"] == CHATWOOT_TEST_PLATFORM_TOKEN for c in platform)
        )
        self.assertEqual(
            api.calls_to("/agents", "GET")[0]["token"], "bridge-user-token"
        )

    def test_a_missing_agent_is_created_and_added_to_the_account(self):
        api = fake_chatwoot_platform(self, chat_user_id=777)
        response = open_tbo_chat(AGENT[0])
        self.assertEqual(response["location"], CHATWOOT_TEST_SIGN_IN)
        created = api.calls_to(PLATFORM_USERS)[0]["body"]
        self.assertEqual(created["email"], AGENT[0])
        self.assertEqual(created["name"], AGENT[1])
        self.assertGreaterEqual(len(created["password"]), 32)
        added = api.calls_to(ACCOUNT_USERS)[0]["body"]
        self.assertEqual(added, {"user_id": 777, "role": "agent"})

    def test_a_new_manager_joins_as_administrator_when_set(self):
        api = fake_chatwoot_platform(self)
        open_tbo_chat(MANAGER[0])
        self.assertEqual(
            api.calls_to(ACCOUNT_USERS)[0]["body"]["role"], "administrator"
        )

        enable_chatwoot_sso(sso_managers_as_admins=0)
        reset_chat_sign_in_limit(MANAGER[0])
        api = fake_chatwoot_platform(self)
        open_tbo_chat(MANAGER[0])
        self.assertEqual(api.calls_to(ACCOUNT_USERS)[0]["body"]["role"], "agent")

    def test_nobody_is_created_when_adding_is_off(self):
        enable_chatwoot_sso(sso_create_users=0)
        api = fake_chatwoot_platform(self)
        response = open_tbo_chat(AGENT[0])
        self.assertEqual(response["http_status_code"], 403)
        self.assertEqual(api.calls_to(PLATFORM_USERS), [])
        self.assertEqual(api.calls_to(ACCOUNT_USERS), [])

    def test_a_link_to_another_site_is_never_followed(self):
        fake_chatwoot_platform(
            self, answers={"GET /login": {"url": "https://evil.example/app/login?x=1"}}
        )
        response = open_tbo_chat(AGENT[0])
        self.assertEqual(response["type"], "page")
        self.assertEqual(response["http_status_code"], 502)

    def test_the_tokens_and_link_never_reach_logs_or_pages(self):
        before = frappe.db.count("Error Log")
        fake_chatwoot_platform(self, answers={"GET /login": None})
        response = open_tbo_chat(AGENT[0])
        self.assertEqual(response["http_status_code"], 502)
        added = frappe.db.count("Error Log") - before
        self.assertGreater(added, 0)
        new_logs = frappe.get_all(
            "Error Log",
            fields=["error"],
            order_by="creation desc",
            limit_page_length=added,
        )
        for text in [frappe.as_json(response)] + [log.error for log in new_logs]:
            self.assertNotIn(CHATWOOT_TEST_PLATFORM_TOKEN, text)
            self.assertNotIn("bridge-user-token", text)
            self.assertNotIn("sso_auth_token", text)

        payload = frappe.as_json(get_settings())
        self.assertNotIn(CHATWOOT_TEST_PLATFORM_TOKEN, payload)
        self.assertNotIn("bridge-user-token", payload)

    def test_sign_ins_are_limited_per_person(self):
        fake_chatwoot_platform(self, agents=[{"id": 501, "email": AGENT[0]}])
        for _ in range(chatwoot_sso.RATE_LIMIT):
            self.assertEqual(open_tbo_chat(AGENT[0])["type"], "redirect")
        self.assertEqual(open_tbo_chat(AGENT[0])["http_status_code"], 429)
        # someone else isn't held up
        fake_chatwoot_platform(self, agents=[{"id": 501, "email": MANAGER[0]}])
        self.assertEqual(open_tbo_chat(MANAGER[0])["type"], "redirect")


class TestChatwootSignInSettings(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_tasky_user(*MANAGER, roles=("Agent Manager",))
        enable_chatwoot_sso()

    def test_only_system_managers_change_them(self):
        with self.assertRaises(frappe.PermissionError):
            run_as_user(MANAGER[0], get_settings)

    def test_sign_in_needs_the_platform_token(self):
        with self.assertRaises(frappe.ValidationError) as caught:
            save_settings({"platform_api_token": ""})
        self.assertTrue(str(caught.exception).startswith("Platform App Token:"))

    def test_a_token_is_only_replaced_when_sent(self):
        saved = save_settings({"sso_create_users": 0})
        self.assertTrue(saved["secrets"]["platform_api_token"]["set"])
        self.assertEqual(saved["settings"]["sso_create_users"], 0)
        settings = frappe.get_single("HD Chatwoot Settings")
        self.assertEqual(
            settings.get_password("platform_api_token"), CHATWOOT_TEST_PLATFORM_TOKEN
        )


class TestChatwootOffboarding(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_tasky_user(*AGENT)
        enable_chatwoot_sso()

    def chat_logs(self) -> list:
        return frappe.get_all(
            "HD Offboarding Log",
            filters={"user": AGENT[0], "action": chatwoot_sso.REMOVED},
            pluck="reason",
        )

    def test_a_disabled_user_is_removed_from_the_account(self):
        api = fake_chatwoot_platform(self, agents=[{"id": 501, "email": AGENT[0]}])
        user = frappe.get_doc("User", AGENT[0])
        user.enabled = 0
        user.save(ignore_permissions=True)
        removed = api.calls_to(ACCOUNT_USERS, "DELETE")
        self.assertEqual([c["body"] for c in removed], [{"user_id": 501}])
        self.assertEqual(removed[0]["token"], CHATWOOT_TEST_PLATFORM_TOKEN)
        self.assertEqual(self.chat_logs(), [chatwoot_sso.USER_DISABLED])

    def test_a_deactivated_agent_is_removed_from_the_account(self):
        api = fake_chatwoot_platform(self, agents=[{"id": 501, "email": AGENT[0]}])
        agent = frappe.get_doc("HD Agent", {"user": AGENT[0]})
        agent.is_active = 0
        agent.save(ignore_permissions=True)
        self.assertEqual(len(api.calls_to(ACCOUNT_USERS, "DELETE")), 1)
        self.assertEqual(self.chat_logs(), [chatwoot_sso.AGENT_DEACTIVATED])

    def test_someone_not_in_the_account_is_left_alone(self):
        api = fake_chatwoot_platform(self, agents=[])
        agent = frappe.get_doc("HD Agent", {"user": AGENT[0]})
        agent.is_active = 0
        agent.save(ignore_permissions=True)
        self.assertEqual(api.calls_to(ACCOUNT_USERS, "DELETE"), [])
        self.assertEqual(self.chat_logs(), [])

    def test_a_failed_removal_is_logged_not_recorded(self):
        fake_chatwoot_platform(
            self,
            agents=[{"id": 501, "email": AGENT[0]}],
            answers={"DELETE /account_users": None},
        )
        errors = frappe.db.count("Error Log", {"method": chatwoot_sso.REMOVAL_FAILED})
        agent = frappe.get_doc("HD Agent", {"user": AGENT[0]})
        agent.is_active = 0
        agent.save(ignore_permissions=True)
        self.assertEqual(self.chat_logs(), [])
        self.assertEqual(
            frappe.db.count("Error Log", {"method": chatwoot_sso.REMOVAL_FAILED}),
            errors + 1,
        )

    def test_nothing_is_called_without_the_platform_token(self):
        enable_chatwoot_sso(sso_enabled=0, platform_api_token="")
        api = fake_chatwoot_platform(self, agents=[{"id": 501, "email": AGENT[0]}])
        agent = frappe.get_doc("HD Agent", {"user": AGENT[0]})
        agent.is_active = 0
        agent.save(ignore_permissions=True)
        self.assertEqual(api.calls, [])
