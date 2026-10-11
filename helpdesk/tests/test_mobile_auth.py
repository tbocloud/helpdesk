# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import json
import time
from urllib.parse import urlencode

import frappe
from frappe.integrations.oauth2 import get_oauth_server
from frappe.tests.utils import FrappeTestCase

from helpdesk.test_utils import (
    TEST_MS_CLIENT,
    TEST_MS_TENANT,
    call_as_user,
    create_user,
    disable_microsoft_sso,
    enable_microsoft_sso,
    hold_commits,
    make_oauth_client,
    make_rsa_key,
    make_tasky_user,
    microsoft_id_token,
    mock_microsoft_keys,
)

AGENT = ("sso.agent@mobile-auth.example", "Nisha Varghese")
CUSTOMER = "sso.customer@mobile-auth.example"
EXCHANGE = "helpdesk.api.mobile_auth.exchange_microsoft_token"
HUB = "https://hub.example/api/method/"


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
        self.assertTrue(data["refresh_token"])

        stored = frappe.get_doc("OAuth Bearer Token", data["access_token"])
        self.assertEqual(stored.user, AGENT[0])
        self.assertEqual(stored.client, self.client.name)
        self.assertEqual(stored.refresh_token, data["refresh_token"])
        self.assertEqual(stored.status, "Active")

        uri = f"{HUB}helpdesk.api.mobile.get_me?" + urlencode(
            {"access_token": data["access_token"]}
        )
        valid, request = get_oauth_server().verify_request(
            uri, "GET", None, {}, ["all", "openid"]
        )
        self.assertTrue(valid)
        self.assertEqual(request.user, AGENT[0])

    def test_email_falls_back_to_preferred_username_case_insensitively(self):
        answer = self.exchange(
            self.token(email=None, preferred_username=AGENT[0].upper())
        )
        self.assertEqual(answer["data"]["user"], AGENT[0])

    def test_refresh_works_through_frappe_get_token(self):
        data = self.exchange(self.token())["data"]

        _headers, body, status = get_oauth_server().create_token_response(
            f"{HUB}frappe.integrations.oauth2.get_token",
            "POST",
            urlencode(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": data["refresh_token"],
                    "client_id": self.client.name,
                }
            ),
            {"Content-Type": "application/x-www-form-urlencoded"},
        )

        self.assertEqual(status, 200, body)
        refreshed = json.loads(body)
        self.assertNotEqual(refreshed["access_token"], data["access_token"])
        stored = frappe.get_doc("OAuth Bearer Token", refreshed["access_token"])
        self.assertEqual(stored.user, AGENT[0])
        self.assertEqual(stored.client, self.client.name)

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
