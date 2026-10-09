import { __ } from "@/translation";
import { dayjs } from "frappe-ui";

/** The periods the server knows (helpdesk.team_dashboard.PERIODS), in order. */
export const PERIODS = [
  { key: "today", label: __("Today"), previous: __("yesterday") },
  { key: "week", label: __("This week"), previous: __("last week") },
  { key: "month", label: __("This month"), previous: __("last month") },
  { key: "quarter", label: __("This quarter"), previous: __("last quarter") },
  { key: "half", label: __("Half year"), previous: __("the last half") },
  { key: "year", label: __("This year"), previous: __("last year") },
] as const;
export type PeriodKey = (typeof PERIODS)[number]["key"];

export const VIEWS = [
  { key: "departments", label: __("Departments") },
  { key: "people", label: __("People") },
  { key: "projects", label: __("Projects") },
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
}

export interface Totals {
  tasks: number;
  key: number;
  on_time_pct: number | null;
  hours: number;
  overdue: number;
  posts: number;
  posts_missed: number;
  previous: {
    tasks: number;
    on_time_pct: number | null;
    hours: number;
    posts: number;
  };
}

export interface DepartmentRow extends Partial<Totals> {
  department: string | null;
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
  key: number;
  on_time_pct: number | null;
  dated: number;
  hours: number;
  overdue: number;
  slips: number;
  sent_back: number;
  posts_on_time: number;
  posts_late: number;
  posts_missed: number;
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
  };
  access: {
    departments: string[];
    can_refresh: boolean;
  };
  department: string | null;
  summary: Totals;
  champion: Champion | null;
  departments: DepartmentRow[];
  people: PersonRow[];
  projects: ProjectRow[];
  trend: { bucket: "day" | "week" | "month"; dates: string[]; values: number[] } | null;
  history: HistoryRow[];
  analysis: Analysis | null;
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
