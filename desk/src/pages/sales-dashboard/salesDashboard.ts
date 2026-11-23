// The sales dashboards (docs/sales-dashboard.md): helpdesk.api.sales_dashboard reads every
// figure live from the ERP site; these are its shapes and the small sums both pages share.
import { token } from "@/pages/performance/chartTheme";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import type { RouteLocationRaw } from "vue-router";
import type { MyCalls } from "../leads/callBatches";
import type { LeadRow } from "../leads/leads";

export interface LeadTotals {
  new: number;
  contacted: number;
  meetings: number;
  quotations_sent: number;
  won: number;
  lost: number;
  stale: number;
  overdue: number;
  hot: number;
  open: number;
  win_rate: number;
}

export interface PipelineStage {
  stage: string;
  /** Open, Ongoing, On Hold, Won or Lost */
  type: string;
  count: number;
}

/** One lead in the AI's plan for today: why it's there and the next step. */
export interface PlanRow {
  name: string;
  lead_name: string;
  tbo_stage: string;
  why: string;
  next_action?: string | null;
  next_due?: string | null;
}

/** Called and contacted per person, one value per day from Monday. */
export interface WeekCalls {
  days: string[];
  people: {
    user: string;
    full_name: string;
    called: number[];
    contacted: number[];
  }[];
}

export interface MyDashboard {
  calls: MyCalls | null;
  month: {
    from_date: string;
    to_date: string;
    totals: LeadTotals;
    pipeline: PipelineStage[];
    plan: PlanRow[];
  } | null;
  week: WeekCalls | null;
  follow_ups: {
    counts: Partial<Record<"overdue" | "today" | "week", number>> & {
      available: boolean;
    };
    rows: LeadRow[];
    total: number;
  } | null;
  errors: Record<string, string>;
}

export type TeamPeriod = "today" | "week" | "month";

export interface TeamCalls {
  user: string;
  full_name: string;
  given: number;
  called: number;
  contacted: number;
}

export interface TeamDashboard {
  period: TeamPeriod;
  overview: {
    from_date: string;
    to_date: string;
    stale_days: number;
    totals: LeadTotals;
    pipeline: PipelineStage[];
    funnel: { step: string; count: number; rate: number }[];
    ai: {
      enabled?: boolean;
      high_intent?: number;
      unhappy?: number;
      stage_suggested?: number;
    };
    people: { user: string; full_name: string }[];
  };
  people: TeamCalls[] | null;
  week: WeekCalls | null;
  handed_out:
    | { slot: string; department: string; size: number; called: number }[]
    | null;
  errors: Record<string, string>;
}

/** A colour as CSS: a theme variable ("--brand") or a colour as it is. */
export function cssColor(color: string) {
  return color.startsWith("--") ? `var(${color})` : color;
}

/** A colour ECharts can draw: a theme variable resolved, or a colour as it is. */
export function drawColor(color: string) {
  return color.startsWith("--") ? token(color) : color;
}

/** A share in whole percent; 0 when there is nothing to divide. */
export function percent(part: number, whole: number) {
  return whole ? Math.round((part / whole) * 100) : 0;
}

/** The sum of a series. */
export function total(values: number[]) {
  return values.reduce((sum, value) => sum + value, 0);
}

/** The pipeline's open stages that hold leads, in the ERP site's order. */
export function openStages(pipeline: PipelineStage[]) {
  return pipeline.filter(
    (row) => row.count > 0 && !["Won", "Lost"].includes(row.type)
  );
}

/** "Good morning" before noon, "Good afternoon" until 5 pm, else "Good evening". */
export function greeting(now = dayjs()) {
  const hour = now.hour();
  if (hour < 12) return __("Good morning");
  if (hour < 17) return __("Good afternoon");
  return __("Good evening");
}

/** The Leads list behind one of the Overview's numbers. */
export function metricLink(
  metric: string,
  query: Record<string, string | undefined> = {}
): RouteLocationRaw {
  return { name: "Leads", query: { view: "all", metric, ...query } };
}
