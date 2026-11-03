from helpdesk.helpdesk.doctype.business_health_check.business_health_check import (
    setup_api_role,
)


def execute():
    """The "Health Check API" role for the TBO website's API user: Create / Read / Write
    on Business Health Check only (docs/business-health-check.md)."""
    setup_api_role()
