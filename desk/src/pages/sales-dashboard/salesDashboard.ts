// The sales dashboards (docs/sales-dashboard.md): helpdesk.api.sales_dashboard reads every
// figure live from the ERP site; these are its shapes and the small sums both pages share.
import { token } from "@/pages/performance/chartTheme";
import { __ } from "@/translation";
import { useDocumentVisibility, useIntervalFn } from "@vueuse/core";
import { dayjs } from "frappe-ui";
import { onBeforeUnmount, watch } from "vue";
import type { RouteLocationRaw } from "vue-router";
import type { MyCalls } from "../leads/callBatches";
import type { LeadRow } from "../leads/leads";

export interface LeadTotals {
  new: number;
  contacted: number;
  meetings: number;
  quotations_sent: number;
  won: number;
  won_value: number;
  /** won leads with no amount, quotation, deal or Sales Order: not in `won_value` */
  won_unpriced?: number;
  lost: number;
  stale: number;
  overdue: number;
  hot: number;
  open: number;
  open_value: number;
  win_rate: number;
  /** % of the leads created in the period that are won now */
  conversion_rate?: number;
}

export interface PipelineStage {
  stage: string;
  /** Open, Ongoing, On Hold, Won or Lost */
  type: string;
  count: number;
  /** the stage's leads' expected value */
  value?: number;
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
  /** from the call log: dialled, missed, seconds talked */
  calls: number;
  missed: number;
  talk_seconds: number;
  overdue: number;
}

/** One salesperson's leads in the period, as the Overview counts them. */
export interface OwnerLeads {
  user: string;
  full_name: string;
  new: number;
  contacted: number;
  open: number;
  meetings_held: number;
  quotations_sent: number;
  won: number;
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
    currency?: string;
    by_owner: OwnerLeads[];
  };
  people: TeamCalls[] | null;
  /** the same days of the period before */
  previous: { from_date: string; to_date: string; totals: LeadTotals } | null;
  /** each salesperson who won something, most won value first; null for one person */
  revenue:
    | { user: string; full_name: string; won: number; won_value: number }[]
    | null;
  /** null with a department or source picked: the ERP site doesn't count it that way */
  money: {
    currency?: string;
    proposals_value: number;
    advances: number;
    to_collect: number;
    overdue: number;
  } | null;
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

/** The team dashboard's card colours (`--cc-*` in theme.css, docs/ui-guidelines.md). */
export type Accent =
  | "blue"
  | "violet"
  | "pink"
  | "red"
  | "orange"
  | "amber"
  | "green"
  | "cyan";

/** In the order a row of bars cycles through them. */
export const ACCENTS: Accent[] = [
  "blue",
  "violet",
  "cyan",
  "green",
  "amber",
  "orange",
  "pink",
  "red",
];

/** The style that gives a `cc-card` (and its `cc-*` parts) its colour. */
export function accentStyle(accent?: Accent) {
  return accent ? { "--accent": `var(--cc-${accent})` } : {};
}

/**
 * A running month's won value carried to its end at today's rate, and the rate per day the
 * target still needs (0: reached or no target). `day` counts today as begun.
 */
export function forecastOf(
  won: number,
  target: number | null,
  pace: { day: number; days: number }
) {
  const perDay = pace.day ? won / pace.day : 0;
  const daysLeft = pace.days - pace.day + 1;
  return {
    perDay,
    forecast: perDay * pace.days,
    needed: target && won < target ? (target - won) / daysLeft : 0,
  };
}

/** The parts of a frappe-ui resource the live reads below use. */
interface LiveResource {
  data: unknown;
  loading: boolean;
  reload: () => unknown;
  abort: () => void;
}

/**
 * Drops the reads still on their way when the page closes. The dashboards' reads take many
 * seconds (each asks the ERP site several times), and a browser keeps only six requests open
 * per site, across its tabs: left running, they queued the next page's requests behind them,
 * so a card opened onto a list that stayed loading.
 */
export function dropOnLeave(...resources: LiveResource[]) {
  onBeforeUnmount(() => resources.forEach((r) => r.loading && r.abort()));
}

const LIVE_EVERY = 120_000;

/**
 * A dashboard's figures kept live: read again every two minutes, and when the person comes
 * back to the tab only if they are older than that (switching tabs doesn't start a read
 * each time); `others` are dropped on leaving too.
 */
export function useLiveRead(main: LiveResource, ...others: LiveResource[]) {
  let readAt = Date.now();
  watch(
    () => main.data,
    () => (readAt = Date.now())
  );
  useIntervalFn(() => !main.loading && main.reload(), LIVE_EVERY);
  const visibility = useDocumentVisibility();
  watch(visibility, (state) => {
    if (
      state === "visible" &&
      !main.loading &&
      Date.now() - readAt > LIVE_EVERY
    )
      main.reload();
  });
  dropOnLeave(main, ...others);
}
