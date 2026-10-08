from helpdesk.helpdesk.doctype.hd_signoff_template.hd_signoff_template import (
    ensure_default_signoff_templates,
)


def execute():
    """Existing sites get the Accounts, Stock and HR sign-off templates; new sites get them on install."""
    ensure_default_signoff_templates()
