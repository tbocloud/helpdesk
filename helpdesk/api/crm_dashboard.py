"""The CRM dashboards page: which dashboards the signed-in person may open, and one of them
counted for them (docs/crm-dashboard.md). Every figure is worked out on the server, with the
viewer's scope applied; the page never gets a lead it may not count."""

import frappe
from frappe import _

from helpdesk.crm_dashboard.report import (
    DASHBOARD,
    DashboardReport,
    can_open,
    is_admin,
    open_dashboards,
)


@frappe.whitelist()
def get_dashboards() -> dict:
    """{dashboards: [{name, dashboard_name, description, is_default, is_active}],
    can_configure}"""
    return {"dashboards": open_dashboards(), "can_configure": is_admin()}


@frappe.whitelist()
def get_dashboard(name: str | None = None, filters: dict | None = None) -> dict:
    """One dashboard (the viewer's default when `name` is empty) with its filters, KPI cards,
    charts and notices. `filters` holds the page's picks: `period` (a period key or
    "custom" with `from_date` and `to_date`) and a value per offered filter; without it the
    dashboard's defaults apply."""
    if not name:
        dashboards = open_dashboards()
        if not dashboards:
            frappe.throw(
                _("There's no CRM dashboard for you yet."), frappe.DoesNotExistError
            )
        name = dashboards[0].name
    if not frappe.db.exists(DASHBOARD, name):
        frappe.throw(
            _("This dashboard doesn't exist any more."), frappe.DoesNotExistError
        )
    dashboard = frappe.get_doc(DASHBOARD, name)
    if not can_open(dashboard):
        frappe.throw(_("You can't open this dashboard."), frappe.PermissionError)
    return DashboardReport(dashboard, filters=filters).run()
