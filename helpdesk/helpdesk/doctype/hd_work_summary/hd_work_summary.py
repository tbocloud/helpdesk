# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""Weekly work summary for one customer (see helpdesk.work_summary).

Agent Managers and System Managers see every summary; other agents only see
summaries of customers whose projects they manage, own or lead. Frappe hooks
can deny but never grant, so each hook returns False to deny or None to defer
to role permissions.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from helpdesk.tasky.permissions import (
    MANAGER_PROJECT_ROLE,
    get_led_projects,
    get_managed_projects,
    is_tasky_admin,
)


class HDWorkSummary(Document):
    def validate(self):
        self.validate_period()

    def validate_period(self):
        if (
            self.period_start
            and self.period_end
            and getdate(self.period_end) < getdate(self.period_start)
        ):
            frappe.throw(_("The period can't end before it starts."))


def managed_customers(user: str, include_led: bool = True) -> set[str]:
    """Customers of the projects the user manages or owns (and leads, unless `include_led` is off)."""
    projects = set(get_managed_projects(user))
    if include_led:
        projects |= set(get_led_projects(user))
    if not projects:
        return set()
    customers = frappe.get_all(
        "Project",
        filters={"name": ("in", list(projects)), "customer": ("is", "set")},
        pluck="customer",
    )
    return set(customers)


def permission_query(user: str | None = None) -> str | None:
    user = user or frappe.session.user
    if is_tasky_admin(user):
        return None
    u = frappe.db.escape(user)
    role = frappe.db.escape(MANAGER_PROJECT_ROLE)
    projects = (
        f"select `parent` from `tabProject User` where `parenttype` = 'Project' "
        f"and `user` = {u} and `custom_role` = {role}"
    )
    return (
        f"(`tabHD Work Summary`.`customer` in (select `customer` from `tabProject` "
        f"where `owner` = {u} or `project_lead` = {u} or `name` in ({projects})))"
    )


def has_permission(
    doc, ptype: str | None = None, user: str | None = None
) -> bool | None:
    user = user or frappe.session.user
    if is_tasky_admin(user):
        return None
    return None if doc.customer in managed_customers(user) else False
