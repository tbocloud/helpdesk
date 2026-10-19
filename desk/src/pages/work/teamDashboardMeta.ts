import { __ } from "@/translation";
import { dayjs } from "frappe-ui";

/** The periods the server knows (helpdesk.team_dashboard.PERIODS), in order. */
export const PERIODS = [
  {
    key: "today",
    label: __("Day"),
    previous: __("yesterday"),
    current: __("today"),
  },
  {
    key: "week",
    label: __("Week"),
    previous: __("last week"),
    current: __("this week"),
  },
  {
    key: "month",
    label: __("Month"),
    previous: __("last month"),
    current: __("this month"),
  },
  {
    key: "quarter",
    label: __("Quarter"),
    previous: __("last quarter"),
    current: __("this quarter"),
  },
  {
    key: "half",
    label: __("Half year"),
    previous: __("the last half"),
    current: __("this half year"),
  },
  {
    key: "year",
    label: __("Year"),
    previous: __("last year"),
    current: __("this year"),
  },
] as const;
export type PeriodKey = (typeof PERIODS)[number]["key"];

export const VIEWS = [
  { key: "departments", label: __("Departments") },
  { key: "people", label: __("People") },
  { key: "projects", label: __("Projects") },
  { key: "repeats", label: __("Repeat issues") },
] as const;
export type ViewKey = (typeof VIEWS)[number]["key"];

export interface BreakdownPart {
  key: string;
  points: number;
  detail: string;
}

export interface Champion {
  user: string;
  name: string;
  image: string | null;
  score: number;
  reasons: string[];
  breakdown: BreakdownPart[];
  /** Read from the record kept when the period closed (HD Team Champion). */
  stored?: boolean;
  /** The stored record's period. */
  start?: string;
  end?: string;
}

/** One month of the Year view (helpdesk.api.team_dashboard.year_months). */
export interface MonthRow {
  month: string;
  end: string;
  future: boolean;
  tasks?: number;
  weight?: number;
  on_time_pct?: number | null;
  quality?: number | null;
  champion?: Champion | null;
}

/** A person's month in the Year view; null for a month to come. */
export type PersonMonth = {
  month: string;
  score: number;
  tasks: number;
  weight: number;
} | null;

/** A person's or a scope's CRM activity from the ERP site (helpdesk.sales_scoreboard). */
export interface SalesFigures {
  contacted: number;
  moms_submitted: number;
  quotations_sent: number;
  follow_ups_done: number;
  follow_ups_on_time: number;
  won: number;
  won_value: number;
  new: number;
  /** answered MyOperator calls (0 without telephony on the ERP site) */
  calls: number;
  mom_pending: number;
  follow_ups_overdue: number;
  /** won of new, %; null without new leads */
  conversion: number | null;
}

/** Whether the ERP site's sales numbers are in: off while Leads aren't set up. */
export interface SalesStatus {
  status: "ok" | "off" | "unavailable";
  message: string | null;
  currency: string | null;
  /** where sales activity counts: CRM, under Sales */
  department: string;
}

/** "12 contacted · 30 calls · 2 meetings · 1 proposal · 1 won" */
export function salesText(s: SalesFigures) {
  const parts = [__("{0} contacted", String(s.contacted))];
  if (s.calls) parts.push(__("{0} calls", String(s.calls)));
  if (s.moms_submitted)
    parts.push(__("{0} meetings", String(s.moms_submitted)));
  if (s.quotations_sent)
    parts.push(__("{0} proposals", String(s.quotations_sent)));
  if (s.won) parts.push(__("{0} won", String(s.won)));
  return parts.join(" · ");
}

export interface Totals {
  tasks: number;
  /** The tasks' weights added up (helpdesk.team_dashboard.task_weight). */
  weight: number;
  key: number;
  on_time_pct: number | null;
  hours: number;
  overdue: number;
  posts: number;
  posts_missed: number;
  sales: SalesFigures | null;
  previous: {
    tasks: number;
    weight: number;
    on_time_pct: number | null;
    hours: number;
    posts: number;
  };
}

export interface DepartmentRow extends Partial<Totals> {
  department: string | null;
  /** A group row adds up a main department and its sub-departments. */
  kind: "group" | "department";
  /** The group a department row sits under. */
  parent: string | null;
  people?: number;
  champion: Champion | null;
}

export interface PersonRow {
  user: string;
  name: string;
  image: string | null;
  department: string | null;
  rank: number;
  score: number;
  eligible: boolean;
  breakdown: BreakdownPart[];
  reasons: string[];
  tasks: number;
  weight: number;
  key: number;
  self_made: number;
  on_time_pct: number | null;
  dated: number;
  hours: number;
  overdue: number;
  slips: number;
  excellent: number;
  good: number;
  rework: number;
  sent_back: number;
  came_back: number;
  posts_on_time: number;
  posts_late: number;
  posts_missed: number;
  sales: SalesFigures | null;
  months: PersonMonth[] | null;
}

export interface ProjectRow {
  project: string;
  project_name: string;
  customer: string | null;
  department: string | null;
  status: string;
  members: number;
  done: number;
  total: number;
  tasks: number;
  hours: number;
  overdue: number;
  contributors: {
    user: string;
    name: string;
    image: string | null;
    tasks: number;
    weight: number;
    hours: number;
    overdue: number;
  }[];
}

export interface HistoryRow {
  period_type: string;
  start: string;
  end: string;
  user: string;
  name: string;
  image: string | null;
  score: number;
}

export interface Analysis {
  status: "ready" | "none" | "unavailable";
  reason?: string;
  summary?: string;
  risks?: string[];
  needs_help?: string[];
  generated_at?: string;
  period_start?: string;
  period_end?: string;
  current?: boolean;
}

export interface Dashboard {
  period: {
    key: PeriodKey;
    start: string;
    end: string;
    compare_start: string;
    compare_end: string;
    /** Ended before today: champions are the stored ones, nothing is overdue. */
    closed: boolean;
    /** Today falls in it. */
    current: boolean;
    /** The first day the month picker offers. */
    earliest: string;
  };
  access: {
    departments: string[];
    /** Main departments with their sub-departments, the main one first. */
    groups: { group: string; departments: string[] }[];
    can_refresh: boolean;
  };
  department: string | null;
  group: string | null;
  summary: Totals;
  champion: Champion | null;
  /** The period before's champion, as stored when it closed. */
  previous_champion: Champion | null;
  months: MonthRow[] | null;
  departments: DepartmentRow[];
  people: PersonRow[];
  projects: ProjectRow[];
  trend: { bucket: "day" | "week" | "month"; dates: string[]; values: number[] } | null;
  history: HistoryRow[];
  analysis: Analysis | null;
  rules: ScoreRules;
  sales: SalesStatus;
}

/** The numbers behind weight, quality and the score (team_dashboard.score_rules). */
export interface ScoreRules {
  weight: {
    base: number;
    self_made_base: number;
    key: number;
    size_per_hour: number;
    size_cap: number;
    self_made_size_cap: number;
    priority: Record<string, number>;
    min: number;
    max: number;
  };
  quality: {
    rating: Record<string, number>;
    unrated: number;
    sent_back: number;
    came_back: number;
    floor: number;
    ceiling: number;
  };
  score: {
    done_share: number;
    overdue: number;
    slip: number;
    hour: number;
    hours_cap_share: number;
  };
  /** points for sales activity (helpdesk.sales_scoreboard.WEIGHTS) */
  sales: {
    contacted: number;
    follow_up_on_time: number;
    meeting: number;
    proposal: number;
    won: number;
    won_per_lakh: number;
    won_value_cap: number;
    mom_pending: number;
    follow_up_overdue: number;
  };
  champion_minimum: number;
  min_delivered: number;
}

/** One ticket or task in a repeat issue. */
export interface RepeatItem {
  kind: "ticket" | "task";
  doctype: string;
  name: string;
  subject: string;
  date: string;
  status: string;
  project: string | null;
  in_period: boolean;
}

/** Look-alike tickets and tasks one customer keeps raising (helpdesk.repeat_issues). */
export interface RepeatCluster {
  id: string;
  customer: string;
  title: string;
  title_source: "ai" | "subjects";
  cause: string | null;
  fix: string | null;
  subject: string;
  tickets: number;
  tasks: number;
  in_period: number;
  earlier: number;
  total: number;
  first_seen: string;
  last_seen: string;
  trend: "rising" | "steady";
  kinds: { label: string; count: number }[];
  people: { user: string; name: string; count: number }[];
  avg_resolution_hours: number | null;
  departments: string[];
  items: RepeatItem[];
  article: { name: string; title: string; status: string } | null;
  root_cause: {
    issue: string;
    task: string;
    subject: string | null;
    status: string | null;
    project: string | null;
  } | null;
}

export interface RepeatCustomer {
  customer: string;
  issues: number;
  in_period: number;
  total: number;
  rising: number;
  projects: { name: string; project_name: string; department: string | null }[];
  clusters: RepeatCluster[];
}

/** Which repeat issues: the Scoreboard's period, day and department or group. */
export interface RepeatScope {
  period: PeriodKey;
  department: string | null;
  group: string | null;
  day: string | null;
}

export interface RepeatIssues {
  period: { key: PeriodKey; start: string; end: string; lookback_start: string };
  rules: { lookback_days: number; min_occurrences: number; min_in_period: number };
  summary: {
    issues: number;
    customers: number;
    rising: number;
    tickets_in_period: number;
    tasks_in_period: number;
  };
  customers: RepeatCustomer[];
  department: string | null;
  access: { can_act: boolean; can_draft_kb: boolean };
}

/** "5 – 11 Oct 2026", or one day. */
export function rangeText(start: string, end: string) {
  const from = dayjs(start);
  const to = dayjs(end);
  if (from.isSame(to, "day")) return to.format("D MMM YYYY");
  if (from.year() !== to.year())
    return `${from.format("D MMM YYYY")} – ${to.format("D MMM YYYY")}`;
  if (from.month() === to.month())
    return `${from.format("D")} – ${to.format("D MMM YYYY")}`;
  return `${from.format("D MMM")} – ${to.format("D MMM YYYY")}`;
}

/** A closed period's name in the champions history: "Week of 5 Oct", "Q3", "H1". */
export function historyLabel(row: HistoryRow) {
  const start = dayjs(row.start);
  switch (row.period_type) {
    case "Week":
      return __("Week of {0}", start.format("D MMM"));
    case "Month":
      return start.format("MMMM");
    case "Quarter":
      return __("Q{0}", String(Math.floor(start.month() / 3) + 1));
    case "Half year":
      return start.month() < 6 ? __("First half") : __("Second half");
    default:
      return start.format("YYYY");
  }
}

/** The change since the comparison period; null when either side has no value. */
export function delta(now: number | null, before: number | null) {
  if (now == null || before == null) return null;
  return Math.round((now - before) * 10) / 10;
}

export function hoursText(value: number) {
  return `${Number.isInteger(value) ? value : value.toFixed(1)}h`;
}

export function departmentLabel(department: string | null) {
  return department || __("No department");
}

/** Which week of its month a week clipped to the month is: 1 for the one with the 1st. */
export function weekOfMonth(start: string) {
  const day = dayjs(start);
  const first = day.startOf("month");
  // Monday is 0: the first week ends on the month's first Sunday
  const firstSunday = first.date() + ((7 - first.day()) % 7);
  return day.date() <= firstSunday
    ? 1
    : 2 + Math.floor((day.date() - firstSunday - 1) / 7);
}

/** The period's name: "Today", "Week 2 of October 2026", "October 2026", "Q4 2026", … */
export function periodTitle(
  period: PeriodKey,
  start: string,
  end: string,
  current = false
) {
  const from = dayjs(start);
  if (period === "today")
    return current ? __("Today") : from.format("ddd D MMM YYYY");
  if (period === "week")
    return __(
      "Week {0} of {1}",
      String(weekOfMonth(start)),
      from.format("MMMM YYYY")
    );
  if (period === "month") return from.format("MMMM YYYY");
  if (period === "quarter")
    return __("Q{0} {1}", String(Math.floor(from.month() / 3) + 1), from.format("YYYY"));
  if (period === "half")
    return __("H{0} {1}", from.month() < 6 ? "1" : "2", from.format("YYYY"));
  return dayjs(end).format("YYYY");
}

/** The months the picker offers, newest first, from `earliest` to `today`. */
export function monthOptions(earliest: string, today: string) {
  const options: { label: string; value: string }[] = [];
  let month = dayjs(today).startOf("month");
  const first = dayjs(earliest).startOf("month");
  while (!month.isBefore(first)) {
    options.push({ label: month.format("MMMM YYYY"), value: month.format("YYYY-MM") });
    month = month.subtract(1, "month");
  }
  return options;
}

/** "×1.04", or a dash when nothing was finished. */
export function qualityText(value: number | null | undefined) {
  return value == null ? "—" : `×${Math.round(value * 100) / 100}`;
}

/** "31" or "4.5": weighted work never shows a trailing ".0". */
export function weightText(value: number | undefined) {
  const v = value ?? 0;
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

/** The department filter's value for a group, so it can't clash with a department. */
export const GROUP_PREFIX = "group:";
