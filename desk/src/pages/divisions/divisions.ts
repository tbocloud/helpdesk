import {
  formatValue,
  type ChartItem,
  type DashboardChart,
  type MetricKind,
} from "./chartLook";
import { monthLabel } from "@/pages/leads/business/businessFormat";
import { __ } from "@/translation";
import { call, dayjs } from "frappe-ui";

/** The division module (docs/divisions.md). The server enforces every permission; the
 * flags here only decide what to show. */
export const DIVISIONS_API = "helpdesk.api.divisions";
export const OVERVIEW_API = "helpdesk.api.division_overview";

/** A division the person may switch to (helpdesk.divisions.division_info). */
export interface Division {
  name: string;
  division_name: string;
  country: string;
  currency: string;
  workspace_url: string | null;
  /** their role in it; null for a Super Admin who isn't a member */
  role: string | null;
  /** whether the person may switch to it (divisions.switchable_divisions) */
  can_switch: boolean;
}

/** Switch the active division. The page reloads, so every list, cache and the Leads
 * page's ERP site follow the new division at once. */
export async function switchDivision(division: string | null) {
  await call(`${DIVISIONS_API}.switch_division`, { division });
  window.location.reload();
}

// ---------- period ----------

export const PERIODS = [
  { value: "this_month", label: __("This month") },
  { value: "last_3_months", label: __("Last 3 months") },
  { value: "this_year", label: __("This year") },
  { value: "last_12_months", label: __("Last 12 months") },
  { value: "custom", label: __("Custom") },
];

export function periodRange(
  period: string,
  custom: { from: string; to: string }
): { from_date: string; to_date: string } | null {
  const today = dayjs();
  const fmt = (d: ReturnType<typeof dayjs>) => d.format("YYYY-MM-DD");
  switch (period) {
    case "this_month":
      return { from_date: fmt(today.startOf("month")), to_date: fmt(today) };
    case "last_3_months":
      return {
        from_date: fmt(today.subtract(2, "month").startOf("month")),
        to_date: fmt(today),
      };
    case "last_12_months":
      return {
        from_date: fmt(today.subtract(11, "month").startOf("month")),
        to_date: fmt(today),
      };
    case "custom":
      return custom.from && custom.to
        ? { from_date: custom.from, to_date: custom.to }
        : null;
    default:
      return { from_date: fmt(today.startOf("year")), to_date: fmt(today) };
  }
}

// ---------- overview ----------

export interface DivisionRow {
  name: string;
  division_name: string;
  country: string;
  employees: number;
  leads: number;
  won_leads: number;
  conversion_rate: number | null;
  customers: number | null;
  quotations: number | null;
  quotation_value: number | null;
  sales_value: number | null;
  projects: number;
  active_projects: number;
  completed_projects: number;
  on_hold_projects: number;
  pending_tasks: number;
  overdue_tasks: number;
  done_tasks: number;
  erp_error: string | null;
}

export interface MonthRow {
  month: string;
  division: string;
  division_name: string;
  leads: number;
  won_leads: number;
  conversion_rate: number | null;
  quotations: number | null;
  quotation_value: number | null;
}

export interface PersonRow {
  division: string;
  user: string;
  full_name: string;
  role: string;
  done: number;
  open: number;
  overdue: number;
  hours: number;
}

/** helpdesk.api.division_overview.get_overview */
export interface Overview {
  currency: string | null;
  from_date: string;
  to_date: string;
  months: string[];
  kpis: Record<string, number | null>;
  rows: DivisionRow[];
  monthly: MonthRow[];
  project_status: Record<string, Record<string, number>>;
  top_people: PersonRow[];
  errors: { division: string; error: string }[];
}

export function chart(
  base: Pick<
    DashboardChart,
    "title" | "chart_type" | "dimension" | "dimension_label" | "metric"
  > & {
    columns?: DashboardChart["columns"];
    metric_label: string;
    kind?: MetricKind;
    compare_metric?: string;
    compare_label?: string;
    width?: "half" | "full";
    missing?: string | null;
  },
  items: ChartItem[]
): DashboardChart {
  return {
    kind: "count",
    compare_metric: null,
    compare_label: null,
    columns: [],
    width: "half",
    period_label: null,
    total_groups: items.length,
    missing: null,
    ...base,
    items,
  };
}

/** The overview's charts, in the shape DashboardChart draws. */
export function overviewCharts(data: Overview): DashboardChart[] {
  const byDivision = (
    value: (r: DivisionRow) => number | null,
    compare?: (r: DivisionRow) => number | null
  ) =>
    data.rows.map((r) => ({
      key: r.name,
      label: r.division_name,
      value: value(r),
      compare: compare ? compare(r) : undefined,
    }));
  const byMonth = (
    value: (rows: MonthRow[]) => number | null,
    compare?: (rows: MonthRow[]) => number | null
  ) =>
    data.months.map((month) => {
      const rows = data.monthly.filter((m) => m.month === month);
      return {
        key: month,
        label: monthLabel(month, true),
        value: value(rows),
        compare: compare ? compare(rows) : undefined,
      };
    });
  const sum = (rows: MonthRow[], key: keyof MonthRow) =>
    rows.reduce((total, r) => total + (Number(r[key]) || 0), 0);
  const erpMissing = data.rows.every((r) => r.erp_error)
    ? __("No division's ERP site answered, so there are no quotation figures.")
    : null;
  const many = data.rows.length > 1;

  return [
    chart(
      {
        title: many ? __("Leads by division") : __("Leads"),
        chart_type: "bar",
        dimension: "division",
        dimension_label: __("Division"),
        metric: "total_leads",
        metric_label: __("Leads"),
        compare_metric: "won_leads",
        compare_label: __("Won or converted"),
      },
      byDivision(
        (r) => r.leads,
        (r) => r.won_leads
      )
    ),
    chart(
      {
        title: many ? __("Sales by division") : __("Sales"),
        chart_type: "bar",
        dimension: "division",
        dimension_label: __("Division"),
        metric: "won_value",
        metric_label: __("Sales value"),
        kind: "money",
        missing: erpMissing,
      },
      byDivision((r) => r.sales_value)
    ),
    chart(
      {
        title: __("Quotations by month"),
        chart_type: "bar",
        dimension: "month",
        dimension_label: __("Month"),
        metric: "quotation_value",
        metric_label: __("Quoted value"),
        kind: "money",
        missing: erpMissing,
      },
      byMonth((rows) => sum(rows, "quotation_value"))
    ),
    chart(
      {
        title: __("Lead conversion by month"),
        chart_type: "line",
        dimension: "month",
        dimension_label: __("Month"),
        metric: "conversion_rate",
        metric_label: __("Conversion"),
        kind: "percent",
      },
      byMonth((rows) => {
        const leads = sum(rows, "leads");
        return leads
          ? Math.round((1000 * sum(rows, "won_leads")) / leads) / 10
          : null;
      })
    ),
    chart(
      {
        title: __("Business growth"),
        chart_type: "line",
        dimension: "month",
        dimension_label: __("Month"),
        metric: "total_leads",
        metric_label: __("New leads"),
        width: "full",
      },
      byMonth((rows) => sum(rows, "leads"))
    ),
    chart(
      {
        title: many ? __("Projects by division") : __("Projects"),
        chart_type: "table",
        dimension: "division",
        dimension_label: __("Division"),
        metric: "active_projects",
        metric_label: __("Open"),
        columns: [
          { metric: "active_projects", label: __("Open"), kind: "count" },
          { metric: "on_hold_projects", label: __("On hold"), kind: "count" },
          { metric: "completed", label: __("Completed"), kind: "count" },
          {
            metric: "overdue_tasks",
            label: __("Overdue tasks"),
            kind: "count",
          },
        ],
      },
      data.rows.map((r) => ({
        key: r.name,
        label: r.division_name,
        value: r.active_projects,
        columns: {
          active_projects: r.active_projects,
          on_hold_projects: r.on_hold_projects,
          completed: r.completed_projects,
          overdue_tasks: r.overdue_tasks,
        },
      }))
    ),
    chart(
      {
        title: __("Employee performance"),
        chart_type: "table",
        dimension: "employee",
        dimension_label: __("Employee"),
        metric: "completed",
        metric_label: __("Tasks done"),
        columns: [
          { metric: "completed", label: __("Tasks done"), kind: "count" },
          { metric: "active_projects", label: __("Open tasks"), kind: "count" },
          { metric: "overdue_tasks", label: __("Overdue"), kind: "count" },
        ],
      },
      data.top_people.map((p) => ({
        key: `${p.division}:${p.user}`,
        label: many
          ? `${p.full_name} · ${divisionName(data, p.division)}`
          : p.full_name,
        value: p.done,
        columns: {
          completed: p.done,
          active_projects: p.open,
          overdue_tasks: p.overdue,
        },
      }))
    ),
  ];
}

function divisionName(data: Overview, name: string) {
  return data.rows.find((r) => r.name === name)?.division_name || name;
}

// ---------- reports ----------

export type ReportKind = "text" | "int" | "money" | "percent" | "hours";

export interface ReportColumn {
  key: string;
  label: string;
  kind: ReportKind;
}

/** helpdesk.api.division_overview.get_report */
export interface Report {
  title: string;
  columns: ReportColumn[];
  rows: Record<string, any>[];
  currency: string | null;
  from_date: string;
  to_date: string;
  errors: { division: string; error: string }[];
}

/** A report cell as the page shows it; an unknown figure is "—", never 0. */
export function reportCell(
  kind: ReportKind,
  value: any,
  currency: string | null
): string {
  if (kind === "text") return value ?? "—";
  if (value === null || value === undefined) return "—";
  if (kind === "hours") return __("{0} h", Number(value).toFixed(1));
  if (kind === "int") return formatValue("count", value, currency);
  return formatValue(kind, value, currency);
}

/** A division's card on the Divisions home (helpdesk.division_overview.division_card). */
export interface DivisionCard {
  name: string;
  division_name: string;
  country: string;
  currency: string;
  admins: string[];
  people: number;
  site: {
    name: string;
    enabled: 0 | 1;
    last_synced_on: string | null;
    last_sync_status: string | null;
  } | null;
  leads: number;
  open_leads: number;
  won_leads: number;
  lost_leads: number;
  conversion_rate: number | null;
  won_value: number;
  projects: number;
  active_projects: number;
  on_hold_projects: number;
  pending_tasks: number;
  overdue_tasks: number;
  done_tasks: number;
}

/** How a division's ERP site stands, in words; a tone only when something is wrong. */
export function siteHealth(site: DivisionCard["site"]): {
  label: string;
  tone: "danger" | "warning" | null;
} {
  if (!site) return { label: __("No ERP site"), tone: "warning" };
  if (site.last_sync_status === "Failed") {
    return { label: __("{0}: last sync failed", site.name), tone: "danger" };
  }
  const when = site.last_synced_on
    ? __("synced {0}", dayjs(site.last_synced_on).fromNow())
    : __("never synced");
  return site.enabled
    ? { label: `${site.name} · ${when}`, tone: null }
    : { label: __("{0} · sync off, {1}", site.name, when), tone: "warning" };
}
