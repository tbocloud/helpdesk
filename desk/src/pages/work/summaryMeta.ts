import { __ } from "@/translation";
import { dayjs } from "frappe-ui";

export interface SummaryListItem {
  name: string;
  customer: string;
  period_start: string;
  period_end: string;
  generated_by_ai: 0 | 1 | boolean;
  creation: string;
}

export interface SummaryTicket {
  name: string;
  subject: string;
  priority: string;
  resolution_by: string | null;
}

export interface SummaryTask {
  subject: string;
  project: string;
  status: string;
  due: string | null;
  is_key: boolean;
  hold_reason?: string | null;
  hold_since?: string | null;
}

export interface SummaryProject {
  project: string;
  status: string;
  tasks: number;
  completed: number;
  progress: number;
}

/** Shape written by helpdesk.work_summary.collect_customer_stats. */
export interface SummaryStats {
  customer?: string;
  period_start?: string;
  period_end?: string;
  as_of?: string;
  tickets?: {
    opened: number;
    resolved: number;
    open: number;
    sla_breached: number;
    sla_breached_open: SummaryTicket[];
    urgent_high_open: number;
    urgent_high_open_list: SummaryTicket[];
  };
  tasks?: {
    completed: number;
    completed_list: SummaryTask[];
    open: number;
    overdue: number;
    overdue_list: SummaryTask[];
    on_hold: number;
    on_hold_list: SummaryTask[];
    key_open: number;
    key_open_list: SummaryTask[];
    due_next_7_days: number;
    due_next_7_days_list: SummaryTask[];
  };
  projects?: SummaryProject[];
}

export interface SummaryDetail extends SummaryListItem {
  summary: string;
  stats: SummaryStats;
}

/** "12 Sep", with the year added when it isn't the current one. */
export function formatDay(value: string | null | undefined): string {
  if (!value) return "";
  const date = dayjs(value);
  return date.format(date.year() === dayjs().year() ? "D MMM" : "D MMM YYYY");
}

export function formatPeriod(start: string, end: string): string {
  return `${formatDay(start)} – ${formatDay(end)}`;
}

export function errorText(err: any, fallback: string): string {
  if (!err) return "";
  return err.messages?.length
    ? err.messages.join(" ")
    : err.message || fallback;
}

export function kindLabel(generatedByAi: SummaryListItem["generated_by_ai"]) {
  return generatedByAi ? __("AI") : __("Plain");
}
