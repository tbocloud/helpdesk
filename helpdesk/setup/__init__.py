"""Post-install setup for the support hub features within Helpdesk."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from helpdesk.api.copilot_worker import ensure_role as ensure_worker_role
from helpdesk.content_team import ensure_role as ensure_content_team_role
from helpdesk.setup.form_scripts import install_form_scripts
from helpdesk.setup.install import get_custom_fields


def after_migrate():
    """Update the HD Form Scripts and ensure custom fields and roles exist."""
    create_custom_fields(get_custom_fields())
    install_form_scripts()
    ensure_content_team_role()
    ensure_worker_role()
