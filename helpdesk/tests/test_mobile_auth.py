# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import time

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.test_utils import (
    TEST_MS_CLIENT,
    TEST_MS_TENANT,
    bearer_token_works,
    call_as_user,
    create_user,
    disable_microsoft_sso,
    enable_microsoft_sso,
    hold_commits,
    issue_sso_token,
    make_oauth_client,
    make_rsa_key,
    make_tasky_user,
    microsoft_id_token,
    mock_microsoft_keys,
    refresh_oauth_token,
)

AGENT = ("sso.agent@mobile-auth.example", "Nisha Varghese")
CUSTOMER = "sso.customer@mobile-auth.example"
EXCHANGE = "helpdesk.api.mobile_auth.exchange_microsoft_token"


class TestMobileMicrosoftSignIn(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(disable_microsoft_sso)
        self.client = make_oauth_client()
        enable_microsoft_sso(self.client.name)
        make_tasky_user(*AGENT)
        self.key = make_rsa_key()
        mock_microsoft_keys(self, self.key)

    def exchange(self, id_token: str, **kwargs):
        return call_as_user("Guest", EXCHANGE, id_token=id_token, **kwargs)

    def token(self, email: str = AGENT[0], **claims) -> str:
        return microsoft_id_token(self.key, email, **claims)

    def assertRefused(self, id_token: str, exc=frappe.AuthenticationError, **kwargs):
        with self.assertRaises(exc):
            self.exchange(id_token, **kwargs)

    # --- a valid token ---

    def test_valid_token_issues_a_usable_bearer_token(self):
        answer = self.exchange(self.token(nonce="n-123"), nonce="n-123")

        self.assertEqual(answer["v"], 1)
        data = answer["data"]
        self.assertEqual(data["user"], AGENT[0])
        self.assertEqual(data["full_name"], AGENT[1])
        self.assertEqual(data["token_type"], "Bearer")
        self.assertEqual(data["expires_in"], 3600)
        self.assertEqual(data["scope"], "all openid")
        self.assertNotIn("refresh_token", data)

        stored = frappe.get_doc("OAuth Bearer Token", data["access_token"])
        self.assertEqual(stored.user, AGENT[0])
        self.assertEqual(stored.client, self.client.name)
        self.assertFalse(stored.refresh_token)
        self.assertEqual(stored.status, "Active")
        self.assertTrue(bearer_token_works(data["access_token"]))

    def test_email_falls_back_to_preferred_username_case_insensitively(self):
        answer = self.exchange(
            self.token(email=None, preferred_username=AGENT[0].upper())
        )
        self.assertEqual(answer["data"]["user"], AGENT[0])

    def test_there_is_nothing_to_refresh(self):
        """Access ends with the Microsoft account: a new hour needs a new ID token."""
        data = self.exchange(self.token())["data"]

        for guess in (data["access_token"], ""):
            refreshed = refresh_oauth_token(self.client.name, guess)
            self.assertIn("error", refreshed, refreshed)
        self.assertEqual(frappe.db.count("OAuth Bearer Token", {"user": AGENT[0]}), 1)

    # --- offboarding ---

    def test_disabled_users_token_is_refused(self):
        access_token = self.exchange(self.token())["data"]["access_token"]
        # straight in the database: no hook revokes it, Frappe itself must refuse
        frappe.db.set_value("User", AGENT[0], "enabled", 0)

        self.assertFalse(bearer_token_works(access_token))

    def test_disabling_a_user_revokes_their_tokens(self):
        first = self.exchange(self.token())["data"]["access_token"]
        second = issue_sso_token(AGENT[0], self.client)["access_token"]
        user = frappe.get_doc("User", AGENT[0])
        user.enabled = 0
        user.save(ignore_permissions=True)

        for access_token in (first, second):
            status = frappe.db.get_value("OAuth Bearer Token", access_token, "status")
            self.assertEqual(status, "Revoked")

        user.enabled = 1
        user.save(ignore_permissions=True)
        self.assertFalse(bearer_token_works(first))

    # --- the token itself ---

    def test_wrong_audience_is_refused(self):
        self.assertRefused(self.token(aud="11111111-2222-3333-4444-555555555555"))

    def test_wrong_issuer_is_refused(self):
        self.assertRefused(
            self.token(iss="https://login.microsoftonline.com/common/v2.0")
        )

    def test_wrong_tenant_is_refused(self):
        self.assertRefused(self.token(tid="11111111-2222-3333-4444-555555555555"))

    def test_expired_token_is_refused(self):
        now = int(time.time())
        self.assertRefused(self.token(iat=now - 7200, nbf=now - 7200, exp=now - 3600))

    def test_old_token_is_refused(self):
        now = int(time.time())
        self.assertRefused(self.token(iat=now - 3000, nbf=now - 3000))

    def test_bad_signature_is_refused(self):
        forged = microsoft_id_token(make_rsa_key(), AGENT[0])
        self.assertRefused(forged)

    def test_nonce_mismatch_is_refused(self):
        self.assertRefused(self.token(nonce="n-123"), nonce="n-456")
        self.assertRefused(self.token(), nonce="n-456")

    def test_replayed_token_is_refused(self):
        id_token = self.token()
        self.exchange(id_token)
        self.assertRefused(id_token)

    def test_token_without_id_is_refused(self):
        self.assertRefused(self.token(uti=None))

    # --- who it names ---

    def test_unknown_email_is_forbidden(self):
        self.assertRefused(
            self.token(email="nobody@mobile-auth.example"),
            exc=frappe.PermissionError,
        )

    def test_disabled_user_is_forbidden(self):
        frappe.db.set_value("User", AGENT[0], "enabled", 0)
        self.assertRefused(self.token(), exc=frappe.PermissionError)

    def test_non_agent_is_forbidden(self):
        create_user(CUSTOMER)
        self.assertRefused(self.token(email=CUSTOMER), exc=frappe.PermissionError)

    def test_inactive_agent_is_forbidden(self):
        frappe.db.set_value("HD Agent", {"user": AGENT[0]}, "is_active", 0)
        self.assertRefused(self.token(), exc=frappe.PermissionError)

    # --- settings ---

    def test_switch_off_is_refused(self):
        disable_microsoft_sso()
        self.assertRefused(self.token(), exc=frappe.PermissionError)

    def test_client_without_the_scopes_is_refused(self):
        frappe.db.set_value("OAuth Client", self.client.name, "scopes", "all")
        self.assertRefused(self.token(), exc=frappe.PermissionError)

    def test_settings_store_lowercase_ids_and_need_a_guid(self):
        settings = frappe.get_doc("HD Settings")
        settings.microsoft_tenant_id = f" {TEST_MS_TENANT.upper()} "
        settings.microsoft_client_id = TEST_MS_CLIENT.upper()
        settings.save()
        self.assertEqual(settings.microsoft_tenant_id, TEST_MS_TENANT)
        self.assertEqual(settings.microsoft_client_id, TEST_MS_CLIENT)

        settings.microsoft_tenant_id = "common"
        with self.assertRaises(frappe.ValidationError):
            settings.save()
