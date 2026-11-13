"""What a CRM dashboard can show (docs/crm-dashboard.md): reporting categories, metrics,
groupings, filters, periods, viewer scopes, chart presets and the starting templates.

This is the one home of these rules. The doctypes validate against it, the report reads it
and the settings page gets it through `helpdesk.api.crm_dashboard_settings.get_settings`.
"""

from frappe import _

CATEGORIES = ("Open", "Won", "Lost", "Converted", "Other")
# Each lead has exactly one category, so a lead counts once: a converted lead is never a won
# lead too, and "sold" (won or converted) adds the two without double counting.
SOLD = ("Won", "Converted")
CLOSED = ("Won", "Converted", "Lost")

# the parts of the organisation, top down; each has HD CRM Org Units
ORG_LEVELS = ("company", "branch", "department", "team", "employee")
UNIT_TYPES = {
    "company": "Company",
    "branch": "Branch",
    "department": "Department",
    "team": "Team",
    "employee": "Employee",
}
# the parents each kind of unit can have
UNIT_PARENTS = {
    "Company": (),
    "Branch": ("company",),
    "Department": ("company", "branch"),
    "Team": ("company", "branch", "department"),
    "Employee": ("company", "branch", "department", "team"),
}


def dimensions() -> dict[str, str]:
    """What a chart can group by, and the column on HD CRM Report Lead."""
    return {
        "company": _("Company"),
        "branch": _("Branch"),
        "department": _("Department"),
        "team": _("Team"),
        "employee": _("Employee"),
        "lead_owner": _("Lead owner"),
        "lead_source": _("Lead source"),
        "category": _("Status category"),
        "status": _("Lead status"),
        "month": _("Month"),
    }


# a dashboard filter is any grouping but the month (the period picker covers dates)
FILTERS = (
    "company",
    "branch",
    "department",
    "team",
    "employee",
    "lead_owner",
    "category",
    "status",
    "lead_source",
)
# which org filters narrow the options of which: a company's branches, a branch's
# departments and teams, a department's teams, a team's employees
FILTER_PARENTS = {
    "branch": ("company",),
    "department": ("company", "branch"),
    "team": ("company", "branch", "department"),
    "employee": ("company", "branch", "department", "team"),
    "lead_owner": ("company", "branch", "department", "team", "employee"),
}


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


def periods() -> dict[str, str]:
    return {
        "this_month": _("This month"),
        "last_month": _("Last month"),
        "this_quarter": _("This quarter"),
        "this_year": _("This year"),
        "last_30_days": _("Last 30 days"),
        "last_90_days": _("Last 90 days"),
        "last_12_months": _("Last 12 months"),
        "all_time": _("All time"),
    }


# a KPI card or chart follows the period picked on the dashboard, or has its own
FOLLOW_DASHBOARD = "dashboard"
# the period picker's own choice: from and to dates typed by the viewer
CUSTOM_PERIOD = "custom"


def scopes() -> dict[str, str]:
    """What part of the leads each viewer of a dashboard sees. System Managers and Agent
    Managers always see all of it."""
    return {
        "all": _("Everything the dashboard covers"),
        "company": _("Their company"),
        "branch": _("Their branch"),
        "department": _("Their department"),
        "team": _("Their teams"),
        "own": _("Their own leads"),
    }


def metrics() -> dict[str, dict]:
    """Every metric: label, kind (count, percent, money or days), the calculation sources it
    can use (`bases`, the first the default) with the source field each one needs, and the
    aggregations it allows (the first the default)."""
    money_bases = {
        "won_value": {"label": _("Won sales value"), "needs": "won_value_field"},
        "expected_revenue": {
            "label": _("Expected revenue of the won leads"),
            "needs": "expected_revenue_field",
        },
    }
    return {
        "total_leads": {"label": _("Total leads"), "kind": "count"},
        "open_leads": {"label": _("Open leads"), "kind": "count"},
        "won_leads": {"label": _("Won leads"), "kind": "count"},
        "lost_leads": {"label": _("Lost leads"), "kind": "count"},
        "converted_leads": {"label": _("Converted leads"), "kind": "count"},
        "conversion_rate": {
            "label": _("Conversion rate"),
            "kind": "percent",
            "bases": {
                "all": {"label": _("Won and converted, of all leads")},
                "closed": {"label": _("Won and converted, of closed leads")},
            },
        },
        "won_value": {
            "label": _("Total won sales value"),
            "kind": "money",
            "bases": money_bases,
            "aggregations": ("sum", "average"),
        },
        "expected_revenue": {
            "label": _("Expected revenue"),
            "kind": "money",
            "needs": "expected_revenue_field",
            "aggregations": ("sum", "average"),
        },
        "pending_value": {
            "label": _("Pending sales value"),
            "kind": "money",
            "needs": "expected_revenue_field",
            "aggregations": ("sum", "average"),
        },
        "average_deal_value": {
            "label": _("Average deal value"),
            "kind": "money",
            "bases": money_bases,
        },
        "avg_closing_days": {
            "label": _("Average lead closing time"),
            "kind": "days",
            "needs": "closing_date_field",
            "bases": {
                "sold": {"label": _("Won and converted leads")},
                "closed": {"label": _("All closed leads, lost included")},
            },
        },
    }


def aggregations() -> dict[str, str]:
    return {"sum": _("Total"), "average": _("Average per lead")}


def chart_types() -> dict[str, str]:
    return {
        "bar": _("Bar"),
        "line": _("Line"),
        "donut": _("Donut"),
        "table": _("Table"),
    }


def sorts() -> dict[str, str]:
    return {
        "value_desc": _("Highest first"),
        "value_asc": _("Lowest first"),
        "label": _("A to Z"),
    }


def chart_presets() -> dict[str, dict]:
    """The visualisations the spec names, ready to add to a dashboard."""
    return {
        "company_performance": {
            "title": _("Company-wise lead performance"),
            "chart_type": "table",
            "dimension": "company",
            "metric": "total_leads",
        },
        "branch_performance": {
            "title": _("Branch-wise lead performance"),
            "chart_type": "table",
            "dimension": "branch",
            "metric": "total_leads",
        },
        "department_performance": {
            "title": _("Department-wise lead performance"),
            "chart_type": "table",
            "dimension": "department",
            "metric": "total_leads",
        },
        "team_sales": {
            "title": _("Team-wise sales performance"),
            "chart_type": "bar",
            "dimension": "team",
            "metric": "won_value",
        },
        "employee_performance": {
            "title": _("Employee-wise performance"),
            "chart_type": "table",
            "dimension": "employee",
            "metric": "won_leads",
        },
        "monthly_sales": {
            "title": _("Monthly sales trend"),
            "chart_type": "line",
            "dimension": "month",
            "metric": "won_value",
            "max_items": 12,
            "width": "full",
        },
        "conversion_trend": {
            "title": _("Lead conversion trend"),
            "chart_type": "line",
            "dimension": "month",
            "metric": "conversion_rate",
            "max_items": 12,
        },
        "won_vs_lost": {
            "title": _("Won vs lost"),
            "chart_type": "bar",
            "dimension": "month",
            "metric": "won_leads",
            "compare_metric": "lost_leads",
            "max_items": 12,
        },
        "lead_sources": {
            "title": _("Lead source analysis"),
            "chart_type": "bar",
            "dimension": "lead_source",
            "metric": "total_leads",
        },
        "revenue_comparison": {
            "title": _("Sales revenue comparison"),
            "chart_type": "bar",
            "dimension": "company",
            "metric": "won_value",
            "compare_metric": "expected_revenue",
        },
    }


ALL_KPIS = (
    "total_leads",
    "open_leads",
    "won_leads",
    "lost_leads",
    "converted_leads",
    "conversion_rate",
    "won_value",
    "expected_revenue",
    "pending_value",
    "average_deal_value",
    "avg_closing_days",
)


def templates() -> dict[str, dict]:
    """Starting points for a new dashboard. Each is copied into the new HD CRM Dashboard,
    which is then edited on its own; changing a template here changes no dashboard."""
    return {
        "executive": {
            "label": _("Executive management"),
            "description": _("Every company together, and how each one is doing."),
            "scope": "all",
            "default_period": "this_quarter",
            "filters": (
                "company",
                "branch",
                "department",
                "team",
                "employee",
                "category",
                "lead_source",
            ),
            "kpis": ALL_KPIS,
            "charts": (
                "company_performance",
                "monthly_sales",
                "revenue_comparison",
                "conversion_trend",
                "won_vs_lost",
                "lead_sources",
            ),
        },
        "company_admin": {
            "label": _("Company administrator"),
            "description": _(
                "One company: its branches, departments, teams and people."
            ),
            "scope": "company",
            "default_period": "this_month",
            "filters": (
                "branch",
                "department",
                "team",
                "employee",
                "status",
                "lead_source",
            ),
            "kpis": (
                "total_leads",
                "open_leads",
                "won_leads",
                "lost_leads",
                "conversion_rate",
                "won_value",
                "pending_value",
                "avg_closing_days",
            ),
            "charts": (
                "branch_performance",
                "department_performance",
                "team_sales",
                "monthly_sales",
                "employee_performance",
            ),
        },
        "branch_manager": {
            "label": _("Branch manager"),
            "description": _("One branch: its departments, teams and people."),
            "scope": "branch",
            "default_period": "this_month",
            "filters": ("department", "team", "employee", "status", "lead_source"),
            "kpis": (
                "total_leads",
                "open_leads",
                "won_leads",
                "conversion_rate",
                "won_value",
                "pending_value",
            ),
            "charts": (
                "department_performance",
                "team_sales",
                "employee_performance",
                "won_vs_lost",
            ),
        },
        "department_manager": {
            "label": _("Department manager"),
            "description": _("One department: its teams and people."),
            "scope": "department",
            "default_period": "this_month",
            "filters": ("team", "employee", "status", "lead_source"),
            "kpis": (
                "total_leads",
                "open_leads",
                "won_leads",
                "conversion_rate",
                "won_value",
                "avg_closing_days",
            ),
            "charts": (
                "team_sales",
                "employee_performance",
                "conversion_trend",
                "lead_sources",
            ),
        },
        "team_leader": {
            "label": _("Sales team leader"),
            "description": _("The leader's teams and each salesperson in them."),
            "scope": "team",
            "default_period": "this_month",
            "filters": ("employee", "status", "lead_source"),
            "kpis": (
                "total_leads",
                "open_leads",
                "won_leads",
                "lost_leads",
                "conversion_rate",
                "won_value",
            ),
            "charts": ("employee_performance", "won_vs_lost", "lead_sources"),
        },
    }


def describe() -> dict:
    """Everything above, labelled, for the settings page's pickers."""
    return {
        "categories": list(CATEGORIES),
        "unit_types": list(UNIT_TYPES.values()),
        "unit_parents": {k: list(v) for k, v in UNIT_PARENTS.items()},
        "dimensions": dimensions(),
        "filters": list(FILTERS),
        "mapped_fields": mapped_fields(),
        "required_fields": list(REQUIRED_FIELDS),
        "field_types": {k: sorted(v) for k, v in FIELD_TYPES.items()},
        "periods": periods(),
        "scopes": scopes(),
        "metrics": metrics(),
        "aggregations": aggregations(),
        "chart_types": chart_types(),
        "sorts": sorts(),
        "chart_presets": chart_presets(),
        "templates": {
            key: {"label": t["label"], "description": t["description"]}
            for key, t in templates().items()
        },
    }
