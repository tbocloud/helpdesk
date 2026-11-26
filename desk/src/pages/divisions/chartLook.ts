import { money } from "@/components/invoicing/invoices";
import type { Tone } from "@/components/tone";
import { shortAmount } from "@/pages/leads/business/businessFormat";
import { __ } from "@/translation";
import type { Component } from "vue";
import LucideBanknote from "~icons/lucide/banknote";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideFileText from "~icons/lucide/file-text";
import LucideFolderOpen from "~icons/lucide/folder-open";
import LucidePause from "~icons/lucide/pause";
import LucidePercent from "~icons/lucide/percent";
import LucideTrophy from "~icons/lucide/trophy";
import LucideUsers from "~icons/lucide/users";

/**
 * How each figure of the division overview looks, the same on its chart and its table
 * column (docs/ui-guidelines.md, "the division overview is colourful"). `tone` colours a
 * chart card's heading, always beside words: brand for leads and open work, info for
 * rates, success for what was won or done, danger for what was lost or overdue, warning
 * for money still to win and work on hold. `slot` is the figure's own series colour in
 * chartTheme's validated palette, so a figure keeps its colour from chart to chart.
 */
export const METRIC_LOOK: Record<
  string,
  { icon: Component; tone: Exclude<Tone, "neutral"> | "brand"; slot: number }
> = {
  total_leads: { icon: LucideUsers, tone: "brand", slot: 0 },
  won_leads: { icon: LucideTrophy, tone: "success", slot: 2 },
  conversion_rate: { icon: LucidePercent, tone: "info", slot: 4 },
  won_value: { icon: LucideBanknote, tone: "success", slot: 2 },
  quotation_value: { icon: LucideFileText, tone: "warning", slot: 3 },
  active_projects: { icon: LucideFolderOpen, tone: "brand", slot: 0 },
  on_hold_projects: { icon: LucidePause, tone: "warning", slot: 3 },
  completed: { icon: LucideCircleCheck, tone: "success", slot: 2 },
  overdue_tasks: { icon: LucideCircleX, tone: "danger", slot: 1 },
  // the Lead status page's open and lost leads
  open: { icon: LucideUsers, tone: "warning", slot: 3 },
  lost: { icon: LucideCircleX, tone: "danger", slot: 1 },
};

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

/** How a figure is measured. */
export type MetricKind = "count" | "percent" | "money" | "days";
export type ValueFormat = "full" | "short";

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

const counts = new Intl.NumberFormat();

/**
 * A figure as written on a card, an axis or a table cell. Money is short (₹12.4L) or
 * full (₹12,40,000) as asked; nothing to show is a dash.
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
