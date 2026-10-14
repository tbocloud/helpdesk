# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
    add_to_date,
    format_datetime,
    format_duration,
    get_datetime,
    now_datetime,
)
from frappe.utils.user import get_users_with_role

from helpdesk.utils import normalize_site_url

DEFAULT_CLIENT_APP = "helpdesk_client"

# A site down for maintenance or returning 503s isn't called every minute
# (docs/client-site-sync.md): after this many failed calls in a row it is Unreachable,
# and the next calls wait these minutes, the last one repeating.
FAILURES_BEFORE_BACKOFF = 3
BACKOFF_MINUTES = (1, 5, 15, 60)
UNREACHABLE = "Unreachable"
ALERT_ROLE = "System Manager"
OUTAGE_TITLE = "Customer site unreachable:"


class HDSSupportConnection(Document):
    def before_save(self):
        if self.site_url:
            self.normalize_urls()
            self._warn_on_insecure_scheme()
        self.reset_backoff_when_connected()

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

    # --- backoff: how the scheduled calls treat a site that keeps failing ---

    def reset_backoff_when_connected(self):
        """Connected again by registering or by hand: called every minute from now on."""
        if self.connection_status != "Connected" or not self.has_value_changed(
            "connection_status"
        ):
            return
        self.consecutive_failures = 0
        self.unreachable_since = None
        self.next_attempt_at = None

    def record_failure(self, error: str):
        """A scheduled call failed. The first failures only mark it Error; from
        FAILURES_BEFORE_BACKOFF in a row it is Unreachable and waits before the next call.
        The outage is logged and announced once, when it starts."""
        failures = (self.consecutive_failures or 0) + 1
        values = {
            "consecutive_failures": failures,
            "last_error": (error or "")[:500],
            "connection_status": "Error",
        }
        starts_outage = False
        if failures >= FAILURES_BEFORE_BACKOFF:
            step = min(failures - FAILURES_BEFORE_BACKOFF, len(BACKOFF_MINUTES) - 1)
            values["connection_status"] = UNREACHABLE
            values["next_attempt_at"] = add_to_date(
                now_datetime(), minutes=BACKOFF_MINUTES[step]
            )
            if not self.unreachable_since:
                values["unreachable_since"] = now_datetime()
                starts_outage = True
        self.db_set(values, update_modified=False)
        if starts_outage:
            self.announce_outage()

    def record_success(self):
        """A scheduled call worked: no backoff, and a recovery is announced once."""
        if self.connection_status == "Connected" and not (
            self.consecutive_failures or self.last_error
        ):
            return
        down_since = self.unreachable_since
        self.db_set(
            {
                "connection_status": "Connected",
                "consecutive_failures": 0,
                "last_error": "",
                "unreachable_since": None,
                "next_attempt_at": None,
            },
            update_modified=False,
        )
        if down_since:
            self.announce_recovery(down_since)

    def announce_outage(self):
        # the title stays English and fixed: the error digest and "Mark old sync errors
        # as seen" recognise it (error_alerts.SYNC_ERROR_TITLES)
        frappe.log_error(
            title=f"{OUTAGE_TITLE} {self.site_label()}",
            message=(
                f"{self.site_url} failed {self.consecutive_failures} times in a row. "
                f"Next call at {format_datetime(self.next_attempt_at, 'HH:mm')}, then "
                f"up to every {BACKOFF_MINUTES[-1]} minutes until it answers.\n\n"
                f"Last error: {self.last_error}"
            ),
            reference_doctype=self.doctype,
            reference_name=self.name,
        )
        self.notify_admins(
            _("{0} is unreachable since {1}: {2}").format(
                self.site_label(),
                format_datetime(self.unreachable_since, "d MMM, HH:mm"),
                self.last_error,
            )
        )

    def announce_recovery(self, down_since):
        down_for = (now_datetime() - get_datetime(down_since)).total_seconds()
        minutes = max(round(down_for / 60), 1)
        self.notify_admins(
            _("{0} is reachable again after {1} (unreachable since {2}).").format(
                self.site_label(),
                format_duration(minutes * 60, hide_days=True),
                format_datetime(down_since, "d MMM, HH:mm"),
            )
        )

    def notify_admins(self, text: str):
        """In the helpdesk for System Managers, and on the team's chat channel."""
        from helpdesk.work_reminders import notify_users

        link = (
            f"/customers/{self.customer_name}" if self.customer_name else "/customers"
        )
        try:
            notify_users(
                get_users_with_role(ALERT_ROLE),
                self.doctype,
                self.name,
                text,
                escalate=True,
                link=link,
                # every outage and recovery is news, even with the same words
                once=False,
            )
        except Exception:
            # a failed notice must not stop the scheduled job for the other sites
            frappe.log_error(title=f"Connection notice not sent for {self.name}")

    def site_label(self) -> str:
        return self.customer_name or self.site_url or self.name
