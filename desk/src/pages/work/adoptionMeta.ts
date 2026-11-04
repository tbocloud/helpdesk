import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import type { Component } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";

export type Period = "this_week" | "last_week" | "last_30";
export type Severity = "attention" | "watch" | "good";

export interface AdoptionPerson {
  user: string;
  name: string;
}

/** helpdesk.adoption.finding */
export interface Finding {
  id: string;
  severity: Severity;
  area: "Sales" | "Delivery" | "Content" | "Support" | "Accounts";
  title: string;
  detail: string;
  action_hint: string;
  /** a page in the app where it can be fixed */
  link: string;
  who: AdoptionPerson[];
}

/** helpdesk.adoption.people_rows */
export interface PersonRow {
  user: string;
  name: string;
  tasks_done: number;
  hours: number;
  last_activity: string | null;
  standups_written: number;
  is_sales: boolean;
  calls: number | null;
  outcomes: number | null;
  on_leave: boolean;
  quiet: boolean;
}

/** helpdesk.api.adoption.get_adoption */
export interface AdoptionReport {
  period: Period;
  from_date: string;
  to_date: string;
  findings: Finding[];
  counts: Partial<Record<Severity, number>>;
  people: PersonRow[];
  sales_available: boolean;
}

export const PERIODS: { key: Period; label: string }[] = [
  { key: "this_week", label: __("This week") },
  { key: "last_week", label: __("Last week") },
  { key: "last_30", label: __("Last 30 days") },
];

export const SEVERITIES: {
  key: Severity;
  label: string;
  icon: Component;
  tone: Tone;
}[] = [
  {
    key: "attention",
    label: __("Needs attention"),
    icon: LucideCircleAlert,
    tone: "danger",
  },
  {
    key: "watch",
    label: __("Worth watching"),
    icon: LucideTriangleAlert,
    tone: "warning",
  },
  {
    key: "good",
    label: __("Going well"),
    icon: LucideCircleCheck,
    tone: "success",
  },
];

/** What the button on a finding says, by the page it opens. */
export const LINK_LABELS: Record<string, string> = {
  "/leads": __("Open Leads"),
  "/overview": __("Open Overview"),
  "/projects": __("Open Projects"),
  "/team": __("Open Team"),
  "/standup": __("Open Stand-up"),
  "/timesheets": __("Open Timesheets"),
  "/content": __("Open the content calendar"),
  "/tickets": __("Open Tickets"),
  "/agents": __("Open Agents"),
};

export const AREA_LABELS: Record<Finding["area"], string> = {
  Sales: __("Sales"),
  Delivery: __("Delivery"),
  Content: __("Content"),
  Support: __("Support"),
  Accounts: __("Accounts"),
};

/** The empty state's sentence, for the period being shown. */
export const EVERYONE_USING: Record<Period, string> = {
  this_week: __("Everyone is using the system this week."),
  last_week: __("Everyone used the system last week."),
  last_30: __("Everyone used the system in the last 30 days."),
};
