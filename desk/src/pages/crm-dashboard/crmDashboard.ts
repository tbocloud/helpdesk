import { money } from "@/components/invoicing/invoices";
import type { Tone } from "@/components/tone";
import { shortAmount } from "@/pages/leads/business/businessFormat";
import { __ } from "@/translation";
import type { Component } from "vue";
import LucideBadgeCheck from "~icons/lucide/badge-check";
import LucideBanknote from "~icons/lucide/banknote";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideClock from "~icons/lucide/clock";
import LucideHourglass from "~icons/lucide/hourglass";
import LucidePercent from "~icons/lucide/percent";
import LucideScale from "~icons/lucide/scale";
import LucideTrendingUp from "~icons/lucide/trending-up";
import LucideTrophy from "~icons/lucide/trophy";
import LucideUsers from "~icons/lucide/users";

/**
 * How each metric looks, the same on its card, its charts and its table column
 * (docs/ui-guidelines.md, "the CRM dashboards are colourful"). `tone` colours the
 * card's icon circle and a chart card's heading, always beside words: brand for
 * leads (as on the Daily report), info for rates and time, success for what was won,
 * danger for what was lost, warning for money still to win. `slot` is the metric's own series colour in chartTheme's
 * validated palette, so a metric keeps its colour from chart to chart.
 */
export const METRIC_LOOK: Record<
  string,
  {
    icon: Component;
    tone: Exclude<Tone, "neutral"> | "brand";
    slot: number;
    /** which way is good news; null when a change is neither */
    better: "up" | "down" | null;
  }
> = {
  total_leads: { icon: LucideUsers, tone: "brand", slot: 0, better: "up" },
  open_leads: {
    icon: LucideCircleDashed,
    tone: "brand",
    slot: 0,
    better: null,
  },
  won_leads: { icon: LucideTrophy, tone: "success", slot: 2, better: "up" },
  lost_leads: { icon: LucideCircleX, tone: "danger", slot: 1, better: "down" },
  converted_leads: {
    icon: LucideBadgeCheck,
    tone: "success",
    slot: 2,
    better: "up",
  },
  conversion_rate: { icon: LucidePercent, tone: "info", slot: 4, better: "up" },
  won_value: { icon: LucideBanknote, tone: "success", slot: 2, better: "up" },
  expected_revenue: {
    icon: LucideTrendingUp,
    tone: "warning",
    slot: 3,
    better: "up",
  },
  pending_value: {
    icon: LucideHourglass,
    tone: "warning",
    slot: 3,
    better: null,
  },
  average_deal_value: {
    icon: LucideScale,
    tone: "success",
    slot: 2,
    better: "up",
  },
  avg_closing_days: {
    icon: LucideClock,
    tone: "info",
    slot: 4,
    better: "down",
  },
};

/**
 * A card's change against the stretch before its period, in words and a tone: success
 * when it got better, warning (never danger) when worse, neutral when it's neither or
 * didn't move. Null when there is nothing to compare.
 */
export function kpiChange(
  card: KpiCard,
  currency: string | null,
  format: ValueFormat
): { delta: number; text: string; tone: Tone } | null {
  if (card.value === null || card.previous === null || !card.compared_to)
    return null;
  const delta = card.value - card.previous;
  if (Math.abs(delta) < 1e-9)
    return {
      delta: 0,
      text: __("No change {0}", card.compared_to),
      tone: "neutral",
    };
  const size =
    card.kind === "percent"
      ? __("{0} pts", Math.abs(delta).toFixed(1))
      : formatValue(card.kind, Math.abs(delta), currency, format);
  const better = METRIC_LOOK[card.metric]?.better;
  const good = better === (delta > 0 ? "up" : "down");
  return {
    delta,
    text: `${delta > 0 ? "+" : "−"}${size} ${card.compared_to}`,
    tone: !better ? "neutral" : good ? "success" : "warning",
  };
}

/** A chart card's heading in its tone: full class strings, so Tailwind finds them. */
export const TONE_SECTION: Record<
  Exclude<Tone, "neutral"> | "brand",
  { border: string; head: string; ink: string }
> = {
  brand: {
    border: "border-l-brand",
    head: "bg-brand-soft",
    ink: "text-brand-ink",
  },
  info: { border: "border-l-info", head: "bg-info-soft", ink: "text-info" },
  success: {
    border: "border-l-success",
    head: "bg-success-soft",
    ink: "text-success",
  },
  warning: {
    border: "border-l-warning",
    head: "bg-warning-soft",
    ink: "text-warning",
  },
  danger: {
    border: "border-l-danger",
    head: "bg-danger-soft",
    ink: "text-danger",
  },
};

// Pairs of palette slots that pass the colour-vision checks in both themes when two
// series share a chart (blue 0, orange 1, green 2, amber 3, pink 4). Orange with
// amber and green with pink don't, so such a chart falls back to blue and orange.
const SAFE_PAIRS = new Set(["0-1", "0-2", "0-3", "0-4", "1-2", "2-3"]);

/** The palette slots of a chart's series: each metric its own, or blue and orange. */
export function seriesSlots(metric: string, compare?: string | null) {
  const first = METRIC_LOOK[metric]?.slot ?? 0;
  if (!compare) return [first];
  const second = METRIC_LOOK[compare]?.slot ?? 1;
  const pair = [first, second].sort().join("-");
  return SAFE_PAIRS.has(pair) ? [first, second] : [0, 1];
}

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
  /** the same figure for the stretch before the period; null for all time */
  previous: number | null;
  /** how to say that stretch, e.g. "vs last month" */
  compared_to: string | null;
  /** the figure in each month of the page's `trend_months`; null where it can't be had */
  trend: (number | null)[];
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
  /** the months of every card's mini trend, oldest first ("2026-06") */
  trend_months: string[];
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
    return days === 1 ? __("1 day") : __("{0} days", counts.format(days));
  }
  if (kind === "money" && currency) {
    return format === "short"
      ? shortAmount(value, currency)
      : money(value, currency, true);
  }
  return counts.format(Math.round(value));
}
