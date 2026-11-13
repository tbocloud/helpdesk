"""What a CRM dashboard shows one viewer (docs/crm-dashboard.md).

Everything is counted from HD CRM Report Lead. The leads counted are, in order:
1. those of enabled data sources, without an inactive unit;
2. what the dashboard covers (its units; none listed covers all);
3. the viewer's part of it (the dashboard's scope; System Managers and Agent Managers see
   all of it), which configuration can only narrow, never widen;
4. the filters picked on the page, which can only be filters the dashboard offers;
5. the period, by the date each lead was created.

Each lead has one reporting category, so won, converted and lost never count a lead twice.
"""

from datetime import date

import frappe
from frappe import _
from frappe.query_builder import Case, Criterion
from frappe.query_builder.functions import Count, Sum
from frappe.utils import (
    add_days,
    add_months,
    flt,
    get_first_day,
    get_last_day,
    get_quarter_ending,
    get_quarter_start,
    get_year_ending,
    get_year_start,
    getdate,
)

from helpdesk.api.crm import ADMIN_ROLES
from helpdesk.crm_dashboard.registry import (
    CLOSED,
    CUSTOM_PERIOD,
    FILTER_PARENTS,
    FOLLOW_DASHBOARD,
    ORG_LEVELS,
    SOLD,
    UNIT_TYPES,
    dimensions,
    mapped_fields,
    metrics,
    periods,
)
from helpdesk.integrations.crm.leads import can_use_leads

DASHBOARD = "HD CRM Dashboard"
SOURCE = "HD CRM Source"
UNIT = "HD CRM Org Unit"
LEAD = "HD CRM Report Lead"
LEVEL_OF = {label: level for level, label in UNIT_TYPES.items()}
# the columns of a performance table, in order; money only when a source maps it
TABLE_COLUMNS = (
    "total_leads",
    "open_leads",
    "won_leads",
    "lost_leads",
    "converted_leads",
    "conversion_rate",
    "won_value",
)
MAX_FILTER_OPTIONS = 500
# a card's mini trend: its figure in each of the last months up to its period's end
TREND_MONTHS = 6
UNMAPPED_SHOWN = 5


# ---------- who may open what ----------


def is_admin(user: str | None = None) -> bool:
    """System Managers and Agent Managers configure the dashboards and see every one."""
    user = user or frappe.session.user
    return user == "Administrator" or bool(ADMIN_ROLES & set(frappe.get_roles(user)))


def can_open(dashboard, user: str | None = None) -> bool:
    """Admins open any dashboard. Anyone else needs it active, one of its roles, and the
    right to see leads at all (`can_use_leads`): a dashboard never shows leads to someone
    the hub keeps them from."""
    user = user or frappe.session.user
    if is_admin(user):
        return True
    if not dashboard.is_active or not can_use_leads(user):
        return False
    return bool({r.role for r in dashboard.roles} & set(frappe.get_roles(user)))


def open_dashboards(user: str | None = None) -> list[dict]:
    """The dashboards `user` may open, the default first."""
    user = user or frappe.session.user
    admin = is_admin(user)
    rows = frappe.qb.get_query(
        DASHBOARD,
        fields=["name", "dashboard_name", "description", "is_default", "is_active"],
        filters=None if admin else {"is_active": 1},
        order_by="is_default desc, dashboard_name asc",
    ).run(as_dict=True)
    if admin or not rows:
        return rows
    if not can_use_leads(user):
        return []
    allowed = set(
        frappe.qb.get_query(
            "HD CRM Dashboard Role",
            fields=["parent"],
            filters={"parenttype": DASHBOARD, "role": ["in", frappe.get_roles(user)]},
        ).run(pluck=True)
    )
    return [row for row in rows if row.name in allowed]


def viewer_position(user: str) -> dict[str, set]:
    """Where `user` sits, as {level: {(source, name)}}: the active employee units linked to
    them (or named by their email) and the active teams they lead, with everything above
    those. Each name is kept with its source: two sites may use one name for different
    things, and one site's unit never opens another site's leads."""
    U = frappe.qb.DocType(UNIT)
    fields = [
        U.source,
        U.unit_type,
        U.unit_name,
        *(getattr(U, lvl) for lvl in ORG_LEVELS[:-1]),
    ]
    units = (
        frappe.qb.from_(U)
        .select(*fields)
        .where(U.is_active == 1)
        .where(
            ((U.unit_type == "Employee") & ((U.user == user) | (U.unit_name == user)))
            | ((U.unit_type == "Team") & (U.leader == user))
        )
        .run(as_dict=True)
    )
    position: dict[str, set] = {level: set() for level in ORG_LEVELS}
    for unit in units:
        position[LEVEL_OF[unit.unit_type]].add((unit.source, unit.unit_name))
        for level in ORG_LEVELS[:-1]:
            if unit.get(level):
                position[level].add((unit.source, unit[level]))
    return position


# ---------- periods ----------


def period_range(
    period: str, from_date=None, to_date=None
) -> tuple[date | None, date | None]:
    """The first and last day of a period; (None, None) for all time."""
    today = getdate()
    if period == CUSTOM_PERIOD:
        if not (from_date and to_date):
            frappe.throw(_("Pick both dates of the period."))
        start, end = getdate(from_date), getdate(to_date)
        if start > end:
            frappe.throw(_("The period's first day is after its last."))
        return start, end
    last_month = add_months(today, -1)
    ranges = {
        "this_month": (get_first_day(today), get_last_day(today)),
        "last_month": (get_first_day(last_month), get_last_day(last_month)),
        "this_quarter": (get_quarter_start(today), get_quarter_ending(today)),
        "this_year": (get_year_start(today), get_year_ending(today)),
        "last_30_days": (add_days(today, -29), today),
        "last_90_days": (add_days(today, -89), today),
        "last_12_months": (get_first_day(add_months(today, -11)), today),
        "all_time": (None, None),
    }
    if period not in ranges:
        frappe.throw(_("There's no period {0}.").format(period))
    start, end = ranges[period]
    return (getdate(start) if start else None, getdate(end) if end else None)


# ---------- the metrics ----------


def metric_value(key: str, basis: str, aggregation: str, a: dict) -> float | None:
    """One metric from one group's aggregates (`DashboardReport.aggregates`). None when it
    can't be worked out, e.g. a rate with no leads to divide by."""

    def share(part, whole):
        return part * 100 / whole if whole else None

    def amount(total, count):
        return total if aggregation != "average" else (total / count if count else None)

    a = {k: flt(v) for k, v in a.items() if k != "key"}
    sold = a["won"] + a["converted"]
    if key == "total_leads":
        return a["total"]
    if key in ("open_leads", "won_leads", "lost_leads", "converted_leads"):
        return a[key.removesuffix("_leads")]
    if key == "conversion_rate":
        return share(sold, a["total"] if basis != "closed" else sold + a["lost"])
    if key in ("won_value", "average_deal_value"):
        prefix = "won_value" if basis != "expected_revenue" else "sold_expected"
        total, count = a[f"{prefix}_sum"], a[f"{prefix}_n"]
        if key == "average_deal_value":
            return total / count if count else None
        return amount(total, count)
    if key == "expected_revenue":
        return amount(a["expected_sum"], a["expected_n"])
    if key == "pending_value":
        return amount(a["pending_sum"], a["pending_n"])
    if key == "avg_closing_days":
        prefix = "closed" if basis == "closed" else "sold"
        count = a[f"{prefix}_days_n"]
        return a[f"{prefix}_days_sum"] / count if count else None
    frappe.throw(_("There's no metric {0}.").format(key))


def default_basis(key: str) -> str:
    return next(iter(metrics()[key].get("bases") or {}), "")


def default_aggregation(key: str) -> str:
    return (metrics()[key].get("aggregations") or ("",))[0]


class DashboardReport:
    """One dashboard for one viewer with the filters they picked."""

    def __init__(self, dashboard, user: str | None = None, filters: dict | None = None):
        self.dashboard = dashboard
        self.user = user or frappe.session.user
        self.admin = is_admin(self.user)
        self.L = frappe.qb.DocType(LEAD)
        self.offered = [row.filter for row in dashboard.filters]
        self.read_filters(filters)
        self.sources = frappe.qb.get_query(
            SOURCE,
            fields=[
                "name",
                "last_synced_on",
                "last_sync_status",
                "last_error",
                *mapped_fields(),
            ],
            filters={"enabled": 1},
        ).run(as_dict=True)
        self.mapped = {t: any(s.get(t) for s in self.sources) for t in mapped_fields()}
        self.unit_labels = {}
        for unit in frappe.qb.get_query(
            UNIT, fields=["unit_type", "unit_name", "label"]
        ).run(as_dict=True):
            self.unit_labels.setdefault((unit.unit_type, unit.unit_name), unit.label)
        self.coverage = self.dashboard_coverage()
        self.not_placed = False
        self.scope = self.viewer_scope()
        self._user_names: dict[str, str] = {}

    # ---------- what is counted ----------

    def read_filters(self, filters: dict | None):
        """The page's filters, or the dashboard's defaults when it first opens. Only the
        filters the dashboard offers are kept."""
        dashboard = self.dashboard
        if filters is None:
            self.values = {
                row.filter: row.default_value
                for row in dashboard.filters
                if row.default_value
            }
            self.period, self.from_date, self.to_date = (
                dashboard.default_period,
                None,
                None,
            )
        else:
            self.values = {
                key: str(filters[key])
                for key in self.offered
                if filters.get(key) not in (None, "")
            }
            self.period = filters.get("period") or dashboard.default_period
            self.from_date, self.to_date = filters.get("from_date"), filters.get(
                "to_date"
            )
        if self.period != CUSTOM_PERIOD and self.period not in periods():
            frappe.throw(_("There's no period {0}.").format(self.period))
        self.range = period_range(self.period, self.from_date, self.to_date)

    def matching(self, units) -> Criterion | None:
        """The leads of any of these units, each on its own source: [(source, level, name)].
        None when there are no units."""
        groups: dict[tuple, set] = {}
        for source, level, name in units:
            groups.setdefault((source, level), set()).add(name)
        terms = [
            (self.L.source == source) & getattr(self.L, level).isin(sorted(names))
            for (source, level), names in sorted(groups.items())
        ]
        return Criterion.any(terms) if terms else None

    def dashboard_coverage(self) -> Criterion | None:
        """The leads of any unit the dashboard lists (a company and a branch of another
        company: both), or None for every lead."""
        names = [row.unit for row in self.dashboard.units]
        if not names:
            return None
        units = frappe.qb.get_query(
            UNIT,
            fields=["source", "unit_type", "unit_name"],
            filters={"name": ["in", names]},
        ).run(as_dict=True)
        criterion = self.matching(
            (u.source, LEVEL_OF[u.unit_type], u.unit_name) for u in units
        )
        # listed units that are gone cover nothing; they never widen the dashboard
        return criterion if criterion is not None else self.L.name.isnull()

    def viewer_scope(self) -> Criterion | None:
        """The viewer's part of the leads, or None for everything. Someone the organisation
        doesn't place sees nothing."""
        scope = self.dashboard.scope
        if self.admin or scope == "all":
            return None
        position = viewer_position(self.user)
        if scope == "own":
            mine = self.L.lead_owner == self.user
            theirs = self.matching(
                (source, "employee", name) for source, name in position["employee"]
            )
            return mine if theirs is None else mine | theirs
        criterion = self.matching(
            (source, scope, name) for source, name in position[scope]
        )
        if criterion is None:
            self.not_placed = True
        return criterion

    def base(self, period: tuple | None = None, skip: str | None = None):
        L = self.L
        query = (
            frappe.qb.from_(L)
            .where(L.excluded == 0)
            .where(L.source.isin([s.name for s in self.sources] or [""]))
        )
        if self.coverage is not None:
            query = query.where(self.coverage)
        if self.scope is not None:
            query = query.where(self.scope)
        for key, value in self.values.items():
            if key != skip:
                query = query.where(getattr(L, key) == value)
        start, end = period or (None, None)
        if start:
            query = query.where(L.created_on >= start)
        if end:
            query = query.where(L.created_on <= end)
        return query

    def aggregates(self) -> list:
        """Every figure a metric is worked out from, for one group of leads."""
        L = self.L
        sold, closed, open_ = (
            L.category.isin(SOLD),
            L.category.isin(CLOSED),
            L.category == "Open",
        )
        # closed_on is set only where days to close mean something
        has_days = L.closed_on.isnotnull()

        def count_if(condition):
            return Sum(Case().when(condition, 1).else_(0))

        def sum_if(condition, value):
            return Sum(Case().when(condition, value).else_(0))

        return [
            Count("*").as_("total"),
            count_if(open_).as_("open"),
            count_if(L.category == "Won").as_("won"),
            count_if(L.category == "Lost").as_("lost"),
            count_if(L.category == "Converted").as_("converted"),
            sum_if(sold, L.won_value).as_("won_value_sum"),
            count_if(sold & (L.won_value > 0)).as_("won_value_n"),
            sum_if(sold, L.expected_revenue).as_("sold_expected_sum"),
            count_if(sold & (L.expected_revenue > 0)).as_("sold_expected_n"),
            Sum(L.expected_revenue).as_("expected_sum"),
            count_if(L.expected_revenue > 0).as_("expected_n"),
            sum_if(open_, L.expected_revenue).as_("pending_sum"),
            count_if(open_ & (L.expected_revenue > 0)).as_("pending_n"),
            sum_if(sold & has_days, L.closing_days).as_("sold_days_sum"),
            count_if(sold & has_days).as_("sold_days_n"),
            sum_if(closed & has_days, L.closing_days).as_("closed_days_sum"),
            count_if(closed & has_days).as_("closed_days_n"),
        ]

    def range_of(self, period: str) -> tuple:
        return self.range if period == FOLLOW_DASHBOARD else period_range(period)

    def missing(self, key: str, basis: str) -> str | None:
        """Why a metric can't be shown: no enabled source maps the field it needs."""
        metric = metrics()[key]
        need = ((metric.get("bases") or {}).get(basis) or {}).get(
            "needs"
        ) or metric.get("needs")
        if need and not self.mapped[need]:
            return _("Map the {0} on a data source to show this.").format(
                mapped_fields()[need]["label"].lower()
            )
        return None

    # ---------- the page ----------

    def run(self) -> dict:
        dashboard = self.dashboard
        page = {
            "name": dashboard.name,
            "dashboard_name": dashboard.dashboard_name,
            "description": dashboard.description,
            "is_active": dashboard.is_active,
            "value_format": dashboard.value_format,
            "currency": frappe.db.get_single_value(
                "HD CRM Settings", "dashboard_currency"
            ),
            "can_configure": self.admin,
            "periods": periods(),
            "period": {
                "key": self.period,
                "from_date": self.range[0],
                "to_date": self.range[1],
                "from_input": self.from_date,
                "to_input": self.to_date,
            },
            "synced_on": self.synced_on(),
            "setup_needed": not self.sources,
            "not_placed": self.not_placed,
            "notices": [],
            "filters": [],
            "kpis": [],
            "charts": [],
        }
        if page["setup_needed"] or self.not_placed:
            return page
        page.update(
            filters=self.filter_options(),
            trend_months=self.trend_window()[2],
            kpis=self.kpis(),
            charts=[self.chart(row) for row in dashboard.charts if row.enabled],
            notices=self.notices(),
        )
        return page

    def synced_on(self):
        times = [s.last_synced_on for s in self.sources]
        return None if not times or None in times else min(times)

    def kpis(self) -> list[dict]:
        totals: dict[str, dict] = {}
        before: dict[str, tuple | None] = {}
        trend = self.monthly_totals()
        cards = []
        for row in self.dashboard.kpis:
            if not row.enabled:
                continue
            if row.period not in totals:
                totals[row.period] = self.totals(self.range_of(row.period))
                earlier = self.previous_range(row.period)
                before[row.period] = earlier and (
                    self.totals(earlier[:2]),
                    earlier[2],
                )
            metric = metrics()[row.metric]
            missing = self.missing(row.metric, row.basis)
            value = previous = compared_to = None
            points = []
            if not missing:
                additive = metric["kind"] in ("count", "money")
                points = [
                    metric_value(row.metric, row.basis, row.aggregation, month)
                    if month
                    else (0 if additive else None)
                    for _key, month in trend
                ]
                value = metric_value(
                    row.metric, row.basis, row.aggregation, totals[row.period]
                )
                if before[row.period]:
                    previous = metric_value(
                        row.metric, row.basis, row.aggregation, before[row.period][0]
                    )
                    compared_to = before[row.period][1]
            cards.append(
                {
                    "metric": row.metric,
                    "label": row.label or self.default_label(row),
                    "kind": metric["kind"],
                    "aggregation": row.aggregation,
                    "value": value,
                    "previous": previous,
                    "compared_to": compared_to,
                    "trend": points,
                    "missing": missing,
                    "period_label": None
                    if row.period == FOLLOW_DASHBOARD
                    else periods()[row.period],
                }
            )
        return cards

    def trend_window(self) -> tuple:
        """(first day, last day, months) of the cards' mini trends: the last TREND_MONTHS
        months up to the end of the dashboard's period, this month at most."""
        end = min(self.range[1] or getdate(), getdate())
        first = getdate(get_first_day(add_months(end, -(TREND_MONTHS - 1))))
        months = [
            getdate(add_months(first, n)).strftime("%Y-%m") for n in range(TREND_MONTHS)
        ]
        return first, end, months

    def monthly_totals(self) -> list[tuple[str, dict | None]]:
        """[(month, its aggregates or None)] across the trend window, with the page's
        filters, in one query."""
        first, end, months = self.trend_window()
        L = self.L
        found = {
            row.key: row
            for row in self.base((first, end))
            .select(L.created_month.as_("key"), *self.aggregates())
            .groupby(L.created_month)
            .run(as_dict=True)
        }
        return [(month, found.get(month)) for month in months]

    def totals(self, period: tuple) -> dict:
        return self.base(period).select(*self.aggregates()).run(as_dict=True)[0]

    def previous_range(self, period: str) -> tuple | None:
        """(first day, last day, how to say it) of the stretch just before a period, to
        compare with: as many days, up to today. A month, quarter or year compares with the
        same days of the one before (the 1st to the 13th with the 1st to the 13th); any
        other period with the days just before it. None for all time."""
        key = self.period if period == FOLLOW_DASHBOARD else period
        start, end = self.range_of(period)
        if not (start and end):
            return None
        end = min(end, getdate())
        if end < start:
            return None
        months = {
            "this_month": 1,
            "last_month": 1,
            "this_quarter": 3,
            "this_year": 12,
            "last_12_months": 12,
        }.get(key)
        if months:
            first = getdate(add_months(start, -months))
            last = min(getdate(add_months(end, -months)), getdate(add_days(start, -1)))
            said = {
                1: _("vs last month"),
                3: _("vs last quarter"),
                12: _("vs last year"),
            }[months]
        else:
            days = (end - start).days + 1
            first, last = getdate(add_days(start, -days)), getdate(add_days(start, -1))
            said = _("vs the {0} days before").format(days)
        return first, last, said

    @staticmethod
    def default_label(row) -> str:
        """The metric's name, saying so when it is an average, so two cards of one metric
        never read alike."""
        label = metrics()[row.metric]["label"]
        if row.aggregation == "average":
            return _("{0}, average per lead").format(label)
        return label

    def chart(self, row) -> dict:
        all_metrics = metrics()
        L = self.L
        column = (
            L.created_month if row.dimension == "month" else getattr(L, row.dimension)
        )
        start, end = self.range_of(row.period)
        groups = (
            self.base((start, end))
            .select(column.as_("key"), *self.aggregates())
            .groupby(column)
            .run(as_dict=True)
        )
        table = row.chart_type == "table"
        columns = [k for k in TABLE_COLUMNS if not self.missing(k, default_basis(k))]
        if table and row.metric not in columns:
            columns.append(row.metric)
        items = []
        for group in groups:
            item = {
                "key": group.key or "",
                "label": self.label(row.dimension, group.key),
                "value": metric_value(row.metric, row.basis, row.aggregation, group),
            }
            if row.compare_metric:
                item["compare"] = metric_value(
                    row.compare_metric,
                    default_basis(row.compare_metric),
                    default_aggregation(row.compare_metric),
                    group,
                )
            if table:
                item["columns"] = {
                    k: metric_value(
                        k,
                        row.basis if k == row.metric else default_basis(k),
                        row.aggregation if k == row.metric else default_aggregation(k),
                        group,
                    )
                    for k in columns
                }
            items.append(item)
        additive = all_metrics[row.metric]["kind"] in ("count", "money")
        items = (
            self.months(items, start, end, row.max_items, 0 if additive else None)
            if row.dimension == "month"
            else self.ranked(items, row.sort, row.max_items)
        )
        missing = self.missing(row.metric, row.basis) or (
            row.compare_metric
            and self.missing(row.compare_metric, default_basis(row.compare_metric))
        )
        return {
            "title": row.title,
            "chart_type": row.chart_type,
            "dimension": row.dimension,
            "dimension_label": dimensions()[row.dimension],
            "metric": row.metric,
            "metric_label": all_metrics[row.metric]["label"],
            "kind": all_metrics[row.metric]["kind"],
            "aggregation": row.aggregation,
            "compare_metric": row.compare_metric or None,
            "compare_label": all_metrics[row.compare_metric]["label"]
            if row.compare_metric
            else None,
            "columns": [
                {
                    "metric": k,
                    "label": all_metrics[k]["label"],
                    "kind": all_metrics[k]["kind"],
                }
                for k in columns
            ]
            if table
            else [],
            "width": row.width or "half",
            "period_label": None
            if row.period == FOLLOW_DASHBOARD
            else periods()[row.period],
            "items": [] if missing else items,
            "total_groups": len(groups),
            "missing": missing or None,
        }

    @staticmethod
    def ranked(items: list[dict], sort: str, limit: int) -> list[dict]:
        if sort == "label":
            items.sort(key=lambda i: (i["key"] == "", i["label"].lower()))
        else:
            # a group with no value goes last either way
            known = [i for i in items if i["value"] is not None]
            unknown = [i for i in items if i["value"] is None]
            known.sort(key=lambda i: i["value"], reverse=sort != "value_asc")
            items = known + unknown
        return items[:limit]

    @staticmethod
    def months(items: list[dict], start, end, limit: int, empty_value) -> list[dict]:
        """Every month of the period in order, up to this month, the most recent `limit` of
        them. A month with no leads is 0 for a count or an amount, and a gap (None) for a rate
        or an average, which has nothing to divide."""
        found = {i["key"]: i for i in items if i["key"]}
        if not found and not start:
            return []
        first = (
            getdate(f"{min(found)}-01") if not start and found else get_first_day(start)
        )
        today = getdate()
        last = min(getdate(end), today) if end else today
        if found:
            last = max(last, getdate(f"{max(found)}-01"))
        keys, month = [], get_first_day(first)
        while month <= last:
            keys.append(month.strftime("%Y-%m"))
            month = add_months(month, 1)
        empty = {"value": empty_value, "compare": empty_value, "columns": {}}
        return [found.get(k) or {"key": k, "label": k, **empty} for k in keys][-limit:]

    def filter_options(self) -> list[dict]:
        """Each offered filter with the values there are leads for, given the other filters
        picked (so a company's branches, a team's employees), over all time."""
        L = self.L
        filters = []
        for key in self.offered:
            column = getattr(L, key)
            values = (
                self.base(skip=key)
                .select(column)
                .distinct()
                .where(column != "")
                .limit(MAX_FILTER_OPTIONS)
                .run(pluck=True)
            )
            options = sorted(
                ({"value": v, "label": self.label(key, v)} for v in values),
                key=lambda o: o["label"].lower(),
            )
            filters.append(
                {
                    "key": key,
                    "label": dimensions()[key],
                    "value": self.values.get(key, ""),
                    "parents": list(FILTER_PARENTS.get(key, ())),
                    "options": options,
                }
            )
        return filters

    def notices(self) -> list[dict]:
        """What the viewer should know about the figures: statuses that count nowhere, and
        sources that couldn't be read."""
        L = self.L
        notices = []
        unmapped = (
            self.base(self.range)
            .select(L.status, Count("*").as_("leads"))
            .where((L.category == "") | L.category.isnull())
            .groupby(L.status)
            .run(as_dict=True)
        )
        if unmapped:
            leads = sum(row.leads for row in unmapped)
            named = sorted(unmapped, key=lambda r: -r.leads)[:UNMAPPED_SHOWN]
            statuses = ", ".join(row.status or _("no status") for row in named)
            notices.append(
                {
                    "kind": "unmapped_statuses",
                    "tone": "warning",
                    "text": _(
                        "{0} leads have a status with no reporting category ({1}). They count in Total leads only."
                    ).format(leads, statuses),
                }
            )
        for source in self.sources:
            if source.last_sync_status == "Failed":
                notices.append(
                    {
                        "kind": "sync_failed",
                        "tone": "danger",
                        "text": _(
                            "{0} couldn't be read: {1} Its figures may be behind."
                        ).format(source.name, source.last_error or ""),
                    }
                )
        return notices

    # ---------- names ----------

    def label(self, dimension: str, key) -> str:
        if not key:
            return _("No category") if dimension == "category" else _("Not set")
        if dimension == "category":
            return _(key)
        if dimension in ORG_LEVELS:
            label = self.unit_label(UNIT_TYPES[dimension], key)
            if label != key or dimension != "employee":
                return label
            return self.user_name(key)
        if dimension == "lead_owner":
            return self.user_name(key)
        return str(key)

    def unit_label(self, unit_type: str, unit_name: str) -> str:
        return self.unit_labels.get((unit_type, unit_name)) or unit_name

    def user_name(self, email: str) -> str:
        if email not in self._user_names:
            self._user_names[email] = (
                frappe.db.get_value("User", email, "full_name") or email
            )
        return self._user_names[email]
