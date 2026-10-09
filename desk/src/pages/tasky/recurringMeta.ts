import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleStop from "~icons/lucide/circle-stop";
import LucidePause from "~icons/lucide/pause";
import LucideRepeat from "~icons/lucide/repeat";
import type { StatusMeta } from "./taskMeta";

/** What the schedule builder edits; the server's helpdesk.api.recurring_tasks.EDITABLE. */
export interface RecurringValues {
  subject: string;
  description: string;
  category: string;
  priority: string;
  estimated_hours: number;
  assignee: string | null;
  is_key: boolean;
  frequency: string;
  interval: number;
  weekdays: string[];
  month_day: number | null;
  last_day_of_month: boolean;
  start_date: string;
  ends: string;
  end_date: string | null;
  max_occurrences: number | null;
  lead_days: number;
  due_time: string | null;
  skip_non_working_days: boolean;
}

export type RecurringState = "active" | "paused" | "finished" | "stopped";

export interface RecurringRule extends RecurringValues {
  name: string;
  state: RecurringState;
  is_active: boolean;
  inactive_reason?: string | null;
  schedule: string;
  next_due_date?: string | null;
  next_create_on?: string | null;
  occurrences_created: number;
  assignee_name?: string | null;
  owner_name?: string | null;
  /** The latest task it created, when the viewer may open it. */
  last_task: {
    name: string;
    subject: string;
    status: string;
    due_date?: string | null;
  } | null;
  has_last_task: boolean;
}

export const WEEKDAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

/** The unit after "Every N", singular and plural; labels are untranslated keys. */
export const FREQUENCY_UNIT: Record<string, [string, string]> = {
  Daily: ["day", "days"],
  Weekly: ["week", "weeks"],
  Monthly: ["month", "months"],
  Quarterly: ["quarter", "quarters"],
  Yearly: ["year", "years"],
};

export function usesDayOfMonth(frequency: string) {
  return ["Monthly", "Quarterly", "Yearly"].includes(frequency);
}

// Labels are untranslated keys; callers pass them through __() at render time.
const STATE: Record<RecurringState, StatusMeta> = {
  active: { label: "Active", icon: LucideRepeat, tone: "neutral" },
  paused: { label: "Paused", icon: LucidePause, tone: "warning" },
  finished: { label: "Finished", icon: LucideCircleCheck, tone: "success" },
  stopped: { label: "Stopped", icon: LucideCircleStop, tone: "neutral" },
};

export function recurringStateMeta(state: RecurringState): StatusMeta {
  return STATE[state] ?? STATE.active;
}
