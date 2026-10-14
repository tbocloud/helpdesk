DEFAULT_TICKET_TYPE = "Unspecified"
DEFAULT_TICKET_PRIORITY = "Medium"
DEFAULT_TICKET_TEMPLATE = "Default"
DEFAULT_ARTICLE_CATEGORY = "General"

# Chat contacts without an email (e.g. WhatsApp) get chat-<id>@chat.invalid as the
# ticket's raised_by: HD Ticket needs an address, and .invalid can never be delivered
CHAT_PLACEHOLDER_DOMAIN = "chat.invalid"

# monitoring alerts (Grafana and the like) that the intake rules turn into tickets: no
# SLA, and left out of Home and the SLA figures (helpdesk/intake.py, docs/ticket-intake.md)
ALERT_TICKET_TYPE = "Alert"
# the Resolved-category status a monitor's own "resolved" mail closes an alert with
MONITOR_RESOLVED_STATUS = "Resolved by monitor"

# what the AI may answer as the category; Settings → Ticket intake routes each to a team
TRIAGE_CATEGORIES = (
    "Account",
    "Billing",
    "Configuration",
    "Data",
    "Integration",
    "Performance",
    "Permissions",
    "Print",
    "Report",
    "Stock",
    "Workflow",
    "Other",
)
