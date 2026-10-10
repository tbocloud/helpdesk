import type { FollowUpSummary } from "@/components/followUps";
import type { Tone } from "@/components/tone";
import type { HealthBrief } from "@/composables/customerHealth";
import {
  ticketFilters,
  ticketsLink,
  type TicketFilterKey,
} from "@/pages/ticket/ticketFilters";
import type { WorkItem } from "@/pages/work/workMeta";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import type { Component } from "vue";
import type { RouteLocationRaw } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideClipboardCheck from "~icons/lucide/clipboard-check";
import LucideListTodo from "~icons/lucide/list-todo";
import LucidePause from "~icons/lucide/pause";
import LucideReply from "~icons/lucide/reply";

export interface DaySection<T> {
  count: number;
  items: T[];
}

export interface FileForMe {
  name: string;
  file_name: string;
  project: string;
  project_name: string;
  uploaded_by_name: string;
  creation: string;
}

/** A task on Home; tasks in progress also say whether their timer runs. */
export interface DayTask extends WorkItem {
  timer?: "running" | "paused";
  /** Tasks the user gave out: who has them now. */
  assignee_names?: string[];
}

/** The user's own open work, for the header line. */
export interface DaySummary {
  open: number;
  overdue: number;
  due_today: number;
  on_hold: number;
  in_review: number;
  in_progress: number;
  projects: number;
}

export interface MyProject {
  name: string;
  project_name: string;
  customer: string | null;
  /** The user's own open and overdue tasks in it. */
  open: number;
  overdue: number;
  /** The whole project's, only for people who run it. */
  team_open: number | null;
  team_overdue: number | null;
  next_milestone: { name: string; subject: string; due: string | null } | null;
}

export interface YourDay {
  summary: DaySummary;
  close_first: DaySection<DayTask>;
  in_progress: DaySection<DayTask>;
  waiting: DaySection<DayTask>;
  coming_up: DaySection<DayTask>;
  no_date: DaySection<DayTask>;
  given_out: DaySection<DayTask>;
  projects: DaySection<MyProject>;
  replies: DaySection<WorkItem>;
  approvals: DaySection<WorkItem>;
  files: DaySection<FileForMe>;
}

export interface PlanStep {
  text: string;
  /** Rule-built steps about one task link to it. */
  task?: string;
  project?: string | null;
}

export interface ActionPlan {
  source: "ai" | "rules";
  /** Why the plan was built without the AI, when it was. */
  reason: string | null;
  ai_enabled: boolean;
  steps: PlanStep[];
  generated_at?: string;
  /** The user's work changed since the AI wrote it. */
  stale: boolean;
}

export interface TicketSummary {
  open: number;
  new_today: number;
  unassigned: number;
  sla_breached: number;
  first_reply_overdue: number;
  waiting_on_customer: number;
  rating: { average: number | null; count: number; low: number };
  by_customer: { customer: string | null; open: number }[];
}

export interface AttentionItem extends WorkItem {
  /** Days since our last reply, on tickets waiting on the customer. */
  waiting_days?: number;
}

export type AttentionReason =
  | "overdue"
  | "at_risk"
  | "unassigned_tickets"
  | "waiting_on_customer";

export interface AttentionGroup {
  key: AttentionReason;
  count: number;
  items: AttentionItem[];
}

export interface EndingProject {
  name: string;
  project_name: string;
  customer: string | null;
  lead_name: string | null;
  progress: number;
  open: number;
  overdue: number;
  expected_end_date: string;
  days_left: number;
}

export interface Person {
  user: string;
  full_name: string;
  open: number;
  working: number;
  projects: string[];
}

export interface CustomerHealthSummary {
  /** customers at risk or to watch that the user may read */
  count: number;
  at_risk: number;
  items: ({ customer: string } & HealthBrief)[];
}

export interface Company {
  tickets: TicketSummary;
  work: Record<string, number>;
  attention_groups: AttentionGroup[];
  project_count: number;
  ending_soon: EndingProject[];
  customer_health: CustomerHealthSummary;
  people: Person[];
  people_busy: number;
  people_free: number | null;
  free_people: string[];
}

export interface Systems {
  connections: {
    name: string;
    customer_name: string | null;
    site_url: string | null;
    connection_status: string | null;
    last_error: string | null;
  }[];
  mailboxes: {
    name: string;
    email_id: string;
    enable_incoming: number;
    no_failed: number;
  }[];
  teams: { enabled: boolean; platform: string | null };
  chat: { enabled: boolean; open: number };
  ai: { calls_today: number; triage_failed: number };
}

export interface HomeData {
  day: YourDay;
  follow_ups: FollowUpSummary;
  company: Company | null;
  systems: Systems | null;
}

/** One fact in the header's line; its icon carries the meaning along with the colour. */
export interface StatusPart {
  key: string;
  label: string;
  tone: Tone;
  icon: Component;
}

/** `one` for a count of 1, else `many` with {0} filled in; both already translated. */
export function countLabel(count: number, one: string, many: string) {
  return count === 1 ? one : many.replace("{0}", String(count));
}

/**
 * The header's facts about the user's own work, most urgent first, ending with
 * how much is open. Empty only when nothing is open or waiting for their review
 * ("All clear").
 */
export function statusParts(day: YourDay): StatusPart[] {
  const s = day.summary;
  const facts: [string, number, string, Tone, Component][] = [
    [
      "overdue",
      s.overdue,
      __("{0} overdue", String(s.overdue)),
      "danger",
      LucideAlarmClock,
    ],
    [
      "due_today",
      s.due_today,
      __("{0} due today", String(s.due_today)),
      "neutral",
      LucideCalendarClock,
    ],
    [
      "on_hold",
      s.on_hold,
      __("{0} on hold", String(s.on_hold)),
      "neutral",
      LucidePause,
    ],
    [
      "replies",
      day.replies.count,
      countLabel(
        day.replies.count,
        __("1 ticket waiting for your reply"),
        __("{0} tickets waiting for your reply")
      ),
      "neutral",
      LucideReply,
    ],
    [
      "approvals",
      day.approvals.count,
      countLabel(
        day.approvals.count,
        __("1 task waiting for your review"),
        __("{0} tasks waiting for your review")
      ),
      "neutral",
      LucideClipboardCheck,
    ],
    [
      "open",
      s.open,
      s.projects > 1
        ? __("{0} open across {1} projects", String(s.open), String(s.projects))
        : s.projects === 1
        ? __("{0} open in 1 project", String(s.open))
        : __("{0} open", String(s.open)),
      "neutral",
      LucideListTodo,
    ],
  ];
  return facts
    .filter(([, count]) => count > 0)
    .map(([key, , label, tone, icon]) => ({ key, label, tone, icon }));
}

export const ticketLinks = Object.fromEntries(
  (Object.keys(ticketFilters) as TicketFilterKey[]).map((key) => [
    key,
    () => ticketsLink(ticketFilters[key]()),
  ])
) as Record<TicketFilterKey, () => RouteLocationRaw>;

/** The Overview opened on one of its buckets ("overdue" is its default). */
export function overviewLink(bucket: string): RouteLocationRaw {
  return bucket === "overdue"
    ? { name: "WorkOverview" }
    : { name: "WorkOverview", query: { bucket } };
}

export function reasonLabel(key: AttentionReason) {
  return {
    overdue: __("Overdue"),
    at_risk: __("At risk"),
    unassigned_tickets: __("Unassigned tickets"),
    waiting_on_customer: __("Waiting on the customer"),
  }[key];
}

export function reasonLink(key: AttentionReason): RouteLocationRaw {
  if (key === "unassigned_tickets") return ticketLinks.unassigned();
  if (key === "waiting_on_customer") return ticketLinks.waitingOnCustomer();
  return overviewLink(key);
}

export function reasonTone(key: AttentionReason): Tone {
  return key === "overdue" ? "danger" : key === "at_risk" ? "warning" : "info";
}

export function endingLabel(days: number) {
  if (days < 0) {
    const late = -days;
    return late === 1
      ? __("Ended 1 day ago")
      : __("Ended {0} days ago", String(late));
  }
  if (days === 0) return __("Ends today");
  if (days === 1) return __("Ends tomorrow");
  return __("Ends in {0} days", String(days));
}

export function greeting(name: string, hour = dayjs().hour()) {
  if (hour < 12) return __("Good morning, {0}", name);
  if (hour < 17) return __("Good afternoon, {0}", name);
  return __("Good evening, {0}", name);
}
