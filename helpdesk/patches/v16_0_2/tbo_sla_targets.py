import frappe

HOUR = 60 * 60
# TBO's targets for every customer (first reply, resolution), in working time
TARGETS = {
    "Urgent": (30 * 60, 4 * HOUR),
    "High": (1 * HOUR, 8 * HOUR),
    "Medium": (4 * HOUR, 24 * HOUR),
    "Low": (8 * HOUR, 40 * HOUR),
}


def execute():
    """Set TBO's SLA targets on every enabled SLA; tickets already open keep theirs."""
    for name in frappe.get_all(
        "HD Service Level Agreement", filters={"enabled": 1}, pluck="name"
    ):
        sla = frappe.get_doc("HD Service Level Agreement", name)
        changed = False
        for row in sla.priorities:
            target = TARGETS.get(row.priority)
            if target and (row.response_time, row.resolution_time) != target:
                row.response_time, row.resolution_time = target
                changed = True
        if changed:
            sla.save(ignore_permissions=True)
