# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from helpdesk.crm_dashboard.registry import (
    FILTERS,
    FOLLOW_DASHBOARD,
    chart_presets,
    chart_types,
    dimensions,
    metrics,
    periods,
    scopes,
    sorts,
    templates,
)

DOCTYPE = "HD CRM Dashboard"
MAX_CHART_ITEMS = 50
# a donut's slices add up to a whole; a rate or an average doesn't
ADDITIVE_KINDS = ("count", "money")


class HDCRMDashboard(Document):
    """One CRM dashboard: who sees it and how much of the leads, what it covers, and its
    filters, KPI cards and charts in their order (docs/crm-dashboard.md)."""

    def validate(self):
        self.validate_access()
        self.validate_filters()
        self.validate_kpis()
        self.validate_charts()
        self.validate_not_empty()

    def on_update(self):
        self.keep_one_default()

    # ---------- validation ----------

    def validate_access(self):
        self.dashboard_name = (self.dashboard_name or "").strip()
        if self.scope not in scopes():
            frappe.throw(_("Pick what each viewer sees."))
        if self.default_period not in periods():
            frappe.throw(_("Pick the period the dashboard opens on."))
        self.drop_repeats("roles", "role")
        self.drop_repeats("units", "unit")

    def drop_repeats(self, table: str, field: str):
        seen = set()
        rows = []
        for row in self.get(table):
            if row.get(field) and row.get(field) not in seen:
                seen.add(row.get(field))
                rows.append(row)
        self.set(table, rows)

    def validate_filters(self):
        seen = set()
        for row in self.filters:
            if row.filter not in FILTERS:
                frappe.throw(_("Row {0}: pick a filter.").format(row.idx))
            if row.filter in seen:
                frappe.throw(
                    _("The {0} filter is listed twice.").format(
                        dimensions()[row.filter]
                    )
                )
            seen.add(row.filter)
            row.default_value = (row.default_value or "").strip()

    def validate_kpis(self):
        seen = set()
        for row in self.kpis:
            self.validate_calculation(row, _("KPI card {0}").format(row.idx))
            row.label = (row.label or "").strip()
            key = (row.metric, row.basis, row.aggregation, row.period)
            if key in seen:
                frappe.throw(
                    _("{0} is on the dashboard twice with the same settings.").format(
                        metrics()[row.metric]["label"]
                    )
                )
            seen.add(key)

    def validate_charts(self):
        for row in self.charts:
            where = _("Chart {0}").format(row.idx)
            row.title = (row.title or "").strip()
            if not row.title:
                frappe.throw(_("{0}: give it a title.").format(where))
            if row.chart_type not in chart_types():
                frappe.throw(_("{0}: pick a chart type.").format(where))
            if row.dimension not in dimensions():
                frappe.throw(_("{0}: pick what to group by.").format(where))
            if row.sort not in sorts():
                row.sort = "value_desc"
            row.max_items = cint(row.max_items) or 10
            if not 1 <= row.max_items <= MAX_CHART_ITEMS:
                frappe.throw(
                    _("{0}: show between 1 and {1} items.").format(
                        where, MAX_CHART_ITEMS
                    )
                )
            self.validate_calculation(row, where)
            self.validate_chart_shape(row, where)

    def validate_calculation(self, row, where: str):
        """The metric exists, its calculation source and aggregation are ones it supports
        (empty takes its default), and the period is known."""
        metric = metrics().get(row.metric)
        if not metric:
            frappe.throw(_("{0}: pick a metric.").format(where))
        # Frappe fills child defaults only on insert; a row added later is shown too
        if row.enabled is None:
            row.enabled = 1
        bases = metric.get("bases") or {}
        if bases:
            row.basis = row.basis or next(iter(bases))
            if row.basis not in bases:
                frappe.throw(
                    _("{0}: {1} can't be calculated from {2}.").format(
                        where, metric["label"], row.basis
                    )
                )
        else:
            row.basis = ""
        allowed = metric.get("aggregations") or ()
        if allowed:
            row.aggregation = row.aggregation or allowed[0]
            if row.aggregation not in allowed:
                frappe.throw(
                    _("{0}: {1} can't be shown as {2}.").format(
                        where, metric["label"], row.aggregation
                    )
                )
        else:
            row.aggregation = ""
        row.period = row.period or FOLLOW_DASHBOARD
        if row.period != FOLLOW_DASHBOARD and row.period not in periods():
            frappe.throw(_("{0}: pick a period.").format(where))

    def validate_chart_shape(self, row, where: str):
        kinds = metrics()
        kind = kinds[row.metric]["kind"]
        if row.chart_type == "line" and row.dimension != "month":
            frappe.throw(
                _("{0}: a line chart shows months; group it by Month.").format(where)
            )
        if row.chart_type == "donut" and kind not in ADDITIVE_KINDS:
            frappe.throw(
                _("{0}: a donut shows parts of a whole; {1} isn't one.").format(
                    where, kinds[row.metric]["label"]
                )
            )
        if not row.compare_metric:
            return
        if row.chart_type in ("donut", "table"):
            # a table shows its standard columns, a donut one metric
            row.compare_metric = ""
        elif row.compare_metric == row.metric:
            frappe.throw(_("{0}: compare it with a different metric.").format(where))
        elif kinds.get(row.compare_metric, {}).get("kind") != kind:
            frappe.throw(
                _(
                    "{0}: {1} and {2} aren't measured alike, so they can't share an axis."
                ).format(
                    where,
                    kinds[row.metric]["label"],
                    kinds.get(row.compare_metric, {}).get("label", row.compare_metric),
                )
            )

    def validate_not_empty(self):
        if not self.kpis and not self.charts:
            frappe.throw(_("Add at least one KPI card or chart."))

    # ---------- after a change ----------

    def keep_one_default(self):
        if not self.is_default:
            return
        frappe.db.set_value(
            DOCTYPE,
            {"is_default": 1, "name": ("!=", self.name)},
            "is_default",
            0,
            update_modified=False,
        )

    # ---------- what depends on a unit ----------

    @staticmethod
    def refuse_if_covering(units: list[str], what: str) -> None:
        """Refuses to delete `what` while a dashboard is kept to any of these units: taking
        its last unit off would widen that dashboard to every lead."""
        if not units:
            return
        D, U = frappe.qb.DocType(DOCTYPE), frappe.qb.DocType("HD CRM Dashboard Unit")
        names = (
            frappe.qb.from_(U)
            .join(D)
            .on(D.name == U.parent)
            .select(D.dashboard_name)
            .distinct()
            .where(U.parenttype == DOCTYPE)
            .where(U.unit.isin(units))
            .run(pluck=True)
        )
        if names:
            frappe.throw(
                _(
                    "{0} is what {1} covers. Take it off there first, or switch it off instead."
                ).format(what, ", ".join(sorted(names)))
            )

    # ---------- templates and copies ----------

    @classmethod
    def from_template(cls, template: str, dashboard_name: str) -> "HDCRMDashboard":
        """A new, unsaved dashboard filled from one of the registry's templates."""
        preset = templates().get(template)
        if not preset:
            frappe.throw(_("There's no dashboard template {0}.").format(template))
        charts = chart_presets()
        doc = frappe.new_doc(DOCTYPE)
        doc.update(
            {
                "dashboard_name": dashboard_name,
                "description": preset["description"],
                "template": template,
                "scope": preset["scope"],
                "default_period": preset["default_period"],
                "filters": [{"filter": key} for key in preset["filters"]],
                "kpis": [{"metric": key} for key in preset["kpis"]],
                "charts": [charts[key] for key in preset["charts"]],
            }
        )
        return doc

    def duplicate(self, dashboard_name: str) -> "HDCRMDashboard":
        """A new, unsaved copy under another name; it starts inactive and not the default,
        so viewers don't see it before it's ready."""
        doc = frappe.copy_doc(self)
        doc.dashboard_name = dashboard_name
        doc.is_active = 0
        doc.is_default = 0
        return doc
