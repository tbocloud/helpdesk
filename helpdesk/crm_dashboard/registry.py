"""What an ERP site's leads map to (docs/divisions.md, "ERP sites"): the reporting categories
and the lead fields a data source maps.

This is the one home of these rules. HD CRM Source validates against it, the sync reads it
and the settings page gets it through `helpdesk.api.erp_sites.get_sources`.
"""

from frappe import _

CATEGORIES = ("Open", "Won", "Lost", "Converted", "Other")
# Each lead has exactly one category, so a lead counts once: a converted lead is never a won
# lead too.
CLOSED = ("Won", "Converted", "Lost")


def mapped_fields() -> dict[str, dict]:
    """The lead fields a data source maps: {fieldname on HD CRM Source: {label, kind}}.
    `kind` says what a remote field must be: an org or lead value, a status, money or a date."""
    return {
        "company_field": {"label": _("Company"), "kind": "dimension"},
        "branch_field": {"label": _("Branch"), "kind": "dimension"},
        "department_field": {"label": _("Department"), "kind": "dimension"},
        "team_field": {"label": _("Team"), "kind": "dimension"},
        "employee_field": {"label": _("Employee"), "kind": "dimension"},
        "owner_field": {"label": _("Lead owner"), "kind": "dimension"},
        "status_field": {"label": _("Lead status"), "kind": "status"},
        "source_field": {"label": _("Lead source"), "kind": "dimension"},
        "expected_revenue_field": {"label": _("Expected revenue"), "kind": "money"},
        "won_value_field": {"label": _("Won sales value"), "kind": "money"},
        "created_field": {"label": _("Lead creation date"), "kind": "date"},
        "closing_date_field": {"label": _("Closing date"), "kind": "date"},
    }


REQUIRED_FIELDS = ("status_field", "created_field")
# the remote field types each kind accepts
FIELD_TYPES = {
    "dimension": {"Link", "Data", "Select", "Dynamic Link", "Autocomplete"},
    "status": {"Select", "Data", "Link"},
    "money": {"Currency", "Float", "Int", "Percent"},
    "date": {"Date", "Datetime"},
}
# fields every Frappe document has, which the doctype's meta doesn't list
STANDARD_FIELDS = (
    {"fieldname": "name", "label": "ID", "fieldtype": "Data"},
    {"fieldname": "owner", "label": "Created By", "fieldtype": "Link"},
    {"fieldname": "creation", "label": "Created On", "fieldtype": "Datetime"},
    {"fieldname": "modified", "label": "Last Updated On", "fieldtype": "Datetime"},
)


def describe() -> dict:
    """Everything above, labelled, for the source editor's pickers."""
    return {
        "categories": list(CATEGORIES),
        "mapped_fields": mapped_fields(),
        "required_fields": list(REQUIRED_FIELDS),
        "field_types": {k: sorted(v) for k, v in FIELD_TYPES.items()},
    }
