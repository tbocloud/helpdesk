# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import hashlib
import hmac
import time

import frappe
from frappe import _
from frappe.model.document import Document

# Chatwoot signs "{timestamp}.{body}"; an older signature is a replay, not a retry
MAX_SIGNATURE_AGE = 5 * 60
BOT = "bot"
ACCOUNT = "account"


class HDChatwootSettings(Document):
    def validate(self):
        self.normalize_base_url()

    def normalize_base_url(self):
        """API paths are appended to it, so a trailing slash would double up."""
        url = (self.base_url or "").strip().rstrip("/")
        if url and not url.startswith(("https://", "http://")):
            frappe.throw(_("The Chatwoot URL must start with https://"))
        self.base_url = url

    def verify_webhook(
        self, source: str, raw: bytes, headers, token: str | None = None
    ):
        """Refuse any delivery not provably from our Chatwoot, and everything while the bridge is off.

        Account webhooks and agent bot webhooks are signed with different
        secrets. Without the bot's secret, the bot URL must carry
        ?token=<account webhook secret> instead.
        """
        if not self.enabled:
            self.refuse()
        secret = self.signing_secret(source)
        if secret:
            self.check_signature(
                secret,
                raw,
                headers.get("X-Chatwoot-Signature"),
                headers.get("X-Chatwoot-Timestamp"),
            )
            return
        fallback = self.get_password("webhook_secret", raise_exception=False)
        if not (
            source == BOT
            and token
            and fallback
            and hmac.compare_digest(token.encode(), fallback.encode())
        ):
            self.refuse()

    def signing_secret(self, source: str) -> str | None:
        field = "bot_webhook_secret" if source == BOT else "webhook_secret"
        return self.get_password(field, raise_exception=False) or None

    def check_signature(
        self,
        secret: str,
        raw: bytes,
        signature: str | None,
        timestamp: str | None,
    ):
        signature = (signature or "").strip()
        timestamp = (timestamp or "").strip()
        if not signature or not timestamp.isdigit():
            self.refuse()
        if abs(time.time() - int(timestamp)) > MAX_SIGNATURE_AGE:
            self.refuse()
        signed = timestamp.encode() + b"." + (raw or b"")
        expected = (
            "sha256=" + hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        )
        if not hmac.compare_digest(expected, signature):
            self.refuse()

    @staticmethod
    def refuse():
        # the same answer for every failure, so a caller learns nothing about why
        frappe.throw(_("This webhook isn't accepted."), frappe.AuthenticationError)
