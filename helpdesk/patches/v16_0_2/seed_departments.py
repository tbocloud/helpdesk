from helpdesk.helpdesk.doctype.hd_department.hd_department import (
    ensure_default_departments,
)


def execute():
    """Existing sites get TBO's departments too; new sites get them on install."""
    ensure_default_departments()
