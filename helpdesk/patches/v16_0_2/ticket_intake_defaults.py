from helpdesk.intake import ensure_intake_defaults


def execute():
    """The Alert ticket type, the Resolved by monitor status and the default intake
    rules (docs/ticket-intake.md). Existing tickets are not touched: Settings → Ticket
    intake → Apply rules to open tickets does that, after a preview."""
    ensure_intake_defaults()
