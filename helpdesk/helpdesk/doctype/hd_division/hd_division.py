# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import re
from urllib.parse import urlparse

import frappe
import pytz
from frappe import _
from frappe.model.document import Document

from helpdesk.divisions import (
    DIVISION,
    DIVISION_ADMIN,
    DIVISION_SALES_USER,
    ERP_SALES_ROLES,
)
from helpdesk.integrations.crm.client import CRMError

CODE = re.compile(r"^[A-Z0-9]{2,10}$")


class HDDivision(Document):
    """One country or business division: its profile, ERP site and members
    (docs/divisions.md)."""

    def validate(self):
        self.validate_code()
        self.validate_workspace_url()
        self.validate_time_zone()
        self.add_division_admin()
        self.validate_members()

    def validate_code(self):
        self.division_code = (self.division_code or "").strip().upper()
        if not CODE.match(self.division_code):
            frappe.throw(
                _("The division code is 2 to 10 capital letters or digits, e.g. IND.")
            )

    def validate_workspace_url(self):
        self.workspace_url = (self.workspace_url or "").strip().rstrip("/")
        if not self.workspace_url:
            return
        host = urlparse(self.workspace_url).hostname
        if not (self.workspace_url.startswith(("http://", "https://")) and host):
            frappe.throw(
                _(
                    "The workspace URL is a web address, e.g. https://india.teambackoffice.com."
                )
            )
        for name, url in frappe.get_all(
            DIVISION,
            filters={"name": ("!=", self.name), "workspace_url": ("is", "set")},
            fields=["name", "workspace_url"],
            as_list=True,
        ):
            # the URL tells which division a visit is for, so it can't be shared
            if urlparse(url).hostname == host:
                frappe.throw(_("{0} already uses {1}.").format(name, host))

    def validate_time_zone(self):
        self.time_zone = (self.time_zone or "").strip()
        if self.time_zone and self.time_zone not in pytz.all_timezones_set:
            frappe.throw(
                _("{0} isn't a time zone. Pick one such as Asia/Kolkata.").format(
                    self.time_zone
                )
            )

    def add_division_admin(self):
        if self.division_admin and not any(
            m.user == self.division_admin for m in self.members
        ):
            self.append(
                "members", {"user": self.division_admin, "role": DIVISION_ADMIN}
            )

    def validate_members(self):
        seen = set()
        for member in self.members:
            if member.user in seen:
                frappe.throw(
                    _("{0} is listed twice. Keep one row with their role.").format(
                        frappe.utils.get_fullname(member.user)
                    )
                )
            seen.add(member.user)

    def add_member(self, user: str, role: str) -> bool:
        """Put `user` in the division with `role`, in memory; False when they are in it
        already (their role there stays). The caller saves."""
        if any(m.user == user for m in self.members):
            return False
        self.append("members", {"user": user, "role": role})
        return True

    def apply_erp_roles(self, users: list[str] | None = None) -> list[str]:
        """Give the Division Admins and Division Sales Users among `users` (every member
        when None) their role on the division's ERP site, whose lead rules then decide what
        they see. Returns what couldn't be done, one line per person; nothing is undone.
        """
        targets = {
            m.user: m.role
            for m in self.members
            if m.role in ERP_SALES_ROLES and (users is None or m.user in users)
        }
        if not (self.crm_source and targets):
            return []
        source = frappe.get_doc("HD CRM Source", self.crm_source)
        try:
            client = source.client()
        except CRMError as e:
            return [str(e)]
        problems = []
        for user, role in targets.items():
            try:
                problem = self.apply_erp_role(client, source.name, user, role)
            except CRMError as e:
                problem = _("{0}: {1}").format(
                    frappe.utils.get_fullname(user), e.user_message or str(e)
                )
            if problem:
                problems.append(problem)
        return problems

    def apply_erp_role(self, client, site: str, user: str, role: str) -> str | None:
        """Give `user` the ERP role of their division role. A Division Sales User also loses
        Sales Manager there, which would show them every lead."""
        name = frappe.utils.get_fullname(user)
        erp_user = client.get_user(user)
        if not erp_user or not erp_user.get("enabled"):
            return _("{0} has no enabled user on {1}. Add them there first.").format(
                name, site
            )
        have = {row.get("role") for row in erp_user.get("roles") or []}
        manager = ERP_SALES_ROLES[DIVISION_ADMIN]
        # removed first: the removal writes back the roles read above
        if role == DIVISION_SALES_USER and manager in have:
            client.remove_role(user, erp_user, manager)
        wanted = ERP_SALES_ROLES[role]
        if wanted not in have:
            client.add_role(user, wanted)
        if role == DIVISION_SALES_USER and "System Manager" in have:
            return _(
                "{0} is a System Manager on {1}, so they still see every lead there."
            ).format(name, site)
        return None
