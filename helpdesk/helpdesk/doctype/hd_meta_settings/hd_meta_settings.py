# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_url

from helpdesk.integrations.meta.graph import DEFAULT_GRAPH_VERSION

VERSION = re.compile(r"^v\d{1,2}\.\d$")
REDIRECT_PATH = "/api/method/helpdesk.api.meta.oauth_callback"


class HDMetaSettings(Document):
    def onload(self):
        self.set_onload("redirect_url", self.oauth_redirect_url())

    def validate(self):
        self.normalize_version()
        self.require_app()
        self.redirect_url = self.oauth_redirect_url()

    def normalize_version(self):
        """The version goes into every Graph URL, so only vNN.N is accepted."""
        self.graph_api_version = (
            self.graph_api_version or ""
        ).strip() or DEFAULT_GRAPH_VERSION
        if not VERSION.match(self.graph_api_version):
            frappe.throw(_("Graph API Version: use the form v25.0."))

    def require_app(self):
        """mandatory_depends_on isn't checked on the server."""
        if self.enabled and not (
            self.app_id and self.get_password("app_secret", raise_exception=False)
        ):
            frappe.throw(_("App ID and App Secret: add both before turning Meta on."))

    @staticmethod
    def oauth_redirect_url() -> str:
        return get_url(REDIRECT_PATH)
