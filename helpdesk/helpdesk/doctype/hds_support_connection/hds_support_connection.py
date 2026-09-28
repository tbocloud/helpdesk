# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from helpdesk.utils import normalize_site_url

DEFAULT_CLIENT_APP = "helpdesk_client"


class HDSSupportConnection(Document):
    def before_save(self):
        if self.site_url:
            self.normalize_urls()
            self._warn_on_insecure_scheme()

    def normalize_urls(self):
        self.site_url = normalize_site_url(self.site_url)
        self.mcp_endpoint = f"{self.site_url}{self.client_method('mcp.handler.handle')}"

    def client_method(self, method: str) -> str:
        """Path of a whitelisted method in the client app on the customer site."""
        return f"/api/method/{self.client_app or DEFAULT_CLIENT_APP}.{method}"

    def _warn_on_insecure_scheme(self):
        """Warn (do not block) if the site URL uses plain http for a non-localhost host."""
        if not self.site_url or not self.site_url.startswith("http://"):
            return
        host = self.site_url.split("://", 1)[1].split("/", 1)[0].lower()
        if "localhost" in host or host.startswith("127.") or host == "::1":
            return
        frappe.msgprint(
            f"Site URL uses <b>http://</b> for a public host ({host}). "
            "API credentials will be sent in cleartext. Consider using https://.",
            title="Insecure scheme",
            indicator="orange",
        )
