# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The TBO Copilot GitHub App: short keys per repository, kept for the hub, fresh for the worker."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import frappe
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from frappe.tests.utils import FrappeTestCase

from helpdesk.copilot import github, github_app
from helpdesk.test_utils import hold_commits, make_copilot_settings


def _expires(hours: float = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


class AppCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public_key = key.public_key()
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ).decode()
        self.pem = pem
        make_copilot_settings(github_app_id="12345", github_app_private_key=pem)
        frappe.cache().delete_keys(github_app.CACHE_PREFIX)
        self.addCleanup(frappe.cache().delete_keys, github_app.CACHE_PREFIX)
        self.calls = []

    def fake_github(self, method, path, bearer, body=None):
        self.calls.append((method, path, body))
        if path.endswith("/installation"):
            return {"id": 77}
        if path.startswith("/app/installations/"):
            return {"token": f"key-{len(self.calls)}", "expires_at": _expires()}
        if path == "/app":
            return {"slug": "tbo-copilot"}
        raise AssertionError(path)


class TestTheApp(AppCase):
    def test_the_apps_token_is_signed_with_its_private_key(self):
        claims = jwt.decode(github_app.app_jwt(), self.public_key, algorithms=["RS256"])
        self.assertEqual(claims["iss"], "12345")
        self.assertLessEqual(claims["exp"] - claims["iat"], 600)

    def test_the_hubs_key_is_for_one_repository_and_kept(self):
        with patch.object(github_app, "_call", side_effect=self.fake_github):
            first = github_app.token_for_repo("tbocloud/demo")
            again = github_app.token_for_repo("tbocloud/demo")

        self.assertEqual(first, again)
        minted = [c for c in self.calls if c[0] == "POST"]
        self.assertEqual(len(minted), 1)
        self.assertEqual(minted[0][2], {"repositories": ["demo"]})

    def test_the_workers_key_may_only_push_and_is_never_kept(self):
        with patch.object(github_app, "_call", side_effect=self.fake_github):
            github_app.push_token("tbocloud/demo")
            key = github_app.push_token("tbocloud/demo")

        self.assertTrue(key["token"].startswith("key-"))
        minted = [c for c in self.calls if c[0] == "POST"]
        self.assertEqual(len(minted), 2)
        self.assertEqual(
            minted[0][2],
            {"repositories": ["demo"], "permissions": github_app.PUSH_PERMISSIONS},
        )

    def test_an_owner_without_the_app_is_said_plainly(self):
        def missing(method, path, bearer, body=None):
            raise github.GitHubError(404, "Not Found")

        with patch.object(github_app, "_call", side_effect=missing):
            with self.assertRaises(github.GitHubError) as caught:
                github_app.token_for_repo("someone/else")
        self.assertIn("not installed on someone", caught.exception.message)


class TestThePastedKey(AppCase):
    """The settings field holds one line, so a pasted .pem file loses its line breaks."""

    def use(self, text):
        settings = frappe.get_single("HDS Copilot Settings")
        settings.github_app_private_key = text
        settings.save(ignore_permissions=True)

    def test_a_key_pasted_on_one_line_still_signs(self):
        lines = self.pem.strip().splitlines()
        body = lines[1:-1]
        for pasted in (
            self.pem.replace("\n", " "),  # the whole file, breaks become spaces
            " ".join(body),  # the body only, without BEGIN and END
            "".join(body),  # the body only, breaks gone
            self.pem.replace("\n", "\r\n"),  # Windows line ends
        ):
            self.use(pasted)
            claims = jwt.decode(
                github_app.app_jwt(), self.public_key, algorithms=["RS256"]
            )
            self.assertEqual(claims["iss"], "12345")

    def test_something_that_is_not_a_key_is_refused_plainly(self):
        self.use("SHA256:not-a-key")
        with self.assertRaises(github.GitHubError) as caught:
            github_app.app_jwt()
        self.assertIn("private key", str(caught.exception))


class TestTheClientUsesTheApp(AppCase):
    def test_calls_carry_the_apps_key_for_the_repository(self):
        reply = MagicMock(status_code=200, content=b"{}")
        reply.json.return_value = {"number": 1}
        with patch.object(
            github_app, "token_for_repo", return_value="app-key"
        ) as for_repo, patch("requests.request", return_value=reply) as sent:
            github.get_pull("tbocloud/demo", 1)

        for_repo.assert_called_once_with("tbocloud/demo")
        self.assertEqual(
            sent.call_args.kwargs["headers"]["Authorization"], "Bearer app-key"
        )

    def test_without_the_app_the_personal_token_is_used(self):
        make_copilot_settings(github_app_id="")
        reply = MagicMock(status_code=200, content=b"{}")
        reply.json.return_value = {}
        with patch.object(github, "token", return_value="personal"), patch(
            "requests.request", return_value=reply
        ) as sent:
            github.get_pull("tbocloud/demo", 1)
        self.assertEqual(
            sent.call_args.kwargs["headers"]["Authorization"], "Bearer personal"
        )

    def test_copilot_alone_means_the_app_opened_it_and_wrote_every_commit(self):
        commits = [
            {"commit": {"author": {"email": "copilot@teambackoffice.com"}}},
            {"commit": {"author": {"email": "Copilot@TeamBackOffice.com"}}},
        ]
        pull = {"number": 3, "author": "tbo-copilot[bot]"}
        with patch.object(
            github_app, "_call", side_effect=self.fake_github
        ), patch.object(github, "pull_commits", return_value=commits):
            self.assertTrue(
                github.copilot_only("o/r", pull, "copilot@teambackoffice.com")
            )
            commits.append({"commit": {"author": {"email": "dev@example.com"}}})
            self.assertFalse(
                github.copilot_only("o/r", pull, "copilot@teambackoffice.com")
            )
            self.assertFalse(
                github.copilot_only(
                    "o/r", dict(pull, author="dev-login"), "copilot@teambackoffice.com"
                )
            )
