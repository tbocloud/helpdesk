from helpdesk.helpdesk.doctype.hd_department.hd_department import (
    SALES_AND_WEB_DEPARTMENTS,
    ensure_default_departments,
)


def execute():
    """Web Development (in Digital), Sales and CRM (in Sales) on existing sites.
    Only these three are added when missing, so a default deleted earlier stays
    deleted; groups are filled only where a department has none yet."""
    ensure_default_departments(SALES_AND_WEB_DEPARTMENTS)
