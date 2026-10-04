import frappe

from helpdesk.work_calendar import sync_saturdays_off

SATURDAY = "Saturday"


def execute():
    """TBO works Monday to Saturday with the 2nd and 4th Saturdays off.

    Sets the rule, makes Saturday a working day (same hours as Friday) in every enabled
    SLA that doesn't have it, and puts the Saturdays off in the SLA holiday lists.
    """
    if not frappe.db.get_single_value("HD Work Settings", "saturdays_off"):
        frappe.db.set_single_value("HD Work Settings", "saturdays_off", "2nd and 4th")
    if (
        frappe.db.get_single_value("HD Work Settings", "weekly_off") or "Sunday"
    ) != "Sunday":
        return
    for name in frappe.get_all(
        "HD Service Level Agreement", filters={"enabled": 1}, pluck="name"
    ):
        sla = frappe.get_doc("HD Service Level Agreement", name)
        days = {row.workday: row for row in sla.support_and_resolution}
        if SATURDAY in days or not days:
            continue
        template = days.get("Friday") or next(iter(days.values()))
        sla.append(
            "support_and_resolution",
            {
                "workday": SATURDAY,
                "start_time": template.start_time,
                "end_time": template.end_time,
            },
        )
        sla.save(ignore_permissions=True)
    sync_saturdays_off()
