import { money } from "@/components/invoicing/invoices";
import { shortAmount } from "@/pages/leads/business/businessFormat";
import { __ } from "@/translation";

/** How a metric is measured (helpdesk/crm_dashboard/registry.py). */
export type MetricKind = "count" | "percent" | "money" | "days";
export type ValueFormat = "full" | "short";

export interface FilterOption {
  value: string;
  label: string;
}

export interface DashboardFilter {
  key: string;
  label: string;
  value: string;
  /** the filters above this one; changing one of them clears this one */
  parents: string[];
  options: FilterOption[];
}

export interface KpiCard {
  metric: string;
  label: string;
  kind: MetricKind;
  aggregation: string;
  value: number | null;
  /** why it can't be shown, e.g. a field no source maps */
  missing: string | null;
  /** set when the card keeps its own period instead of the page's */
  period_label: string | null;
}

export interface ChartItem {
  key: string;
  label: string;
  value: number | null;
  compare?: number | null;
  columns?: Record<string, number | null>;
}

export interface DashboardChart {
  title: string;
  chart_type: "bar" | "line" | "donut" | "table";
  dimension: string;
  dimension_label: string;
  metric: string;
  metric_label: string;
  kind: MetricKind;
  compare_metric: string | null;
  compare_label: string | null;
  columns: { metric: string; label: string; kind: MetricKind }[];
  width: "half" | "full";
  period_label: string | null;
  items: ChartItem[];
  total_groups: number;
  missing: string | null;
}

export interface DashboardNotice {
  kind: "unmapped_statuses" | "sync_failed";
  tone: "warning" | "danger";
  text: string;
}

/** helpdesk.api.crm_dashboard.get_dashboard */
export interface DashboardPage {
  name: string;
  dashboard_name: string;
  description: string | null;
  is_active: 0 | 1;
  value_format: ValueFormat;
  currency: string | null;
  can_configure: boolean;
  periods: Record<string, string>;
  period: {
    key: string;
    from_date: string | null;
    to_date: string | null;
  };
  synced_on: string | null;
  setup_needed: boolean;
  not_placed: boolean;
  notices: DashboardNotice[];
  filters: DashboardFilter[];
  kpis: KpiCard[];
  charts: DashboardChart[];
}

export interface DashboardSummary {
  name: string;
  dashboard_name: string;
  description: string | null;
  is_default: 0 | 1;
  is_active: 0 | 1;
}

const counts = new Intl.NumberFormat();

/**
 * A metric's value as written on a card, an axis or a table cell. Money is short
 * (₹12.4L) or full (₹12,40,000) as the dashboard says; nothing to show is a dash.
 */
export function formatValue(
  kind: MetricKind,
  value: number | null | undefined,
  currency: string | null,
  format: ValueFormat = "full"
): string {
  if (value === null || value === undefined) return "—";
  if (kind === "percent") {
    return `${Number.isInteger(value) ? value : value.toFixed(1)}%`;
  }
  if (kind === "days") {
    const days = Math.round(value);
    return days === 1 ? __("1 day") : __("{0} days", [counts.format(days)]);
  }
  if (kind === "money" && currency) {
    return format === "short"
      ? shortAmount(value, currency)
      : money(value, currency, true);
  }
  return counts.format(Math.round(value));
}
