import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";

/** One line of a stand-up (helpdesk.standup.item_shape). */
export interface StandupItem {
  id: string | null;
  kind: "task" | "ticket" | "post" | "plan" | "note";
  title: string;
  detail: string | null;
  reference_doctype: string | null;
  reference_name: string | null;
  project: string | null;
  auto: boolean;
  /** where it opens in /helpdesk, or null for text */
  route: string | null;
  helper: string | null;
  helper_name: string | null;
  help_task: string | null;
}

export type Section = "yesterday" | "today" | "blockers";
/** sections with a free-text note; a blocker is always its own row */
export type NoteSection = "yesterday" | "today";
export const SECTIONS: Section[] = ["yesterday", "today", "blockers"];

export type StandupStatus = "Draft" | "Submitted" | "Auto-posted";

export interface Standup {
  name: string | null;
  user: string;
  full_name: string;
  date: string;
  department: string | null;
  status: StandupStatus;
  submitted_on: string | null;
  needs_help: boolean;
  /** hours logged on the previous working day; null when the setting hides them */
  hours: number | null;
  yesterday: StandupItem[];
  today: StandupItem[];
  blockers: StandupItem[];
  notes: Record<NoteSection, string>;
  /** team view only: linked work planned on the previous working day, and done */
  plan_vs_done?: { planned: number; done: number; unplanned: number } | null;
}

export interface MyStandupData {
  enabled: boolean;
  date: string;
  previous_day: string;
  is_working_day: boolean;
  editable: boolean;
  post_at: string;
  posted: boolean;
  standup: Standup | null;
  teams: string[];
  department: string | null;
}

export interface TeamBlocker extends StandupItem {
  standup: string;
  user: string;
  full_name: string;
  needs_help: boolean;
}

export interface TeamStandupData {
  team: string;
  teams: string[];
  can_lead: boolean;
  date: string;
  previous_day: string;
  editable: boolean;
  post_at: string;
  posted: boolean;
  people: Standup[];
  blockers: TeamBlocker[];
  needs_help: string[];
  counts: {
    people: number;
    submitted: number;
    pending: number;
    auto: number;
    blockers: number;
  };
  on_leave: {
    user: string;
    full_name: string;
    to_date: string;
    half_day: boolean;
  }[];
}

export interface HistoryRow {
  name: string;
  date: string;
  department: string | null;
  status: StandupStatus;
  needs_help: boolean;
  yesterday: number;
  today: number;
  blockers: number;
}

/** The team name for people in no department (admins only). */
export const NO_DEPARTMENT = "__none__";

export function teamLabel(team: string | null | undefined) {
  return !team || team === NO_DEPARTMENT ? __("No department") : team;
}

export function sectionTitle(section: Section, previousDay?: string) {
  if (section === "today") return __("Today");
  if (section === "blockers") return __("Blockers");
  // "yesterday" is the previous working day: Friday, on a Monday
  if (
    previousDay &&
    !dayjs(previousDay).isSame(dayjs().subtract(1, "day"), "day")
  )
    return __("Last working day · {0}", dayjs(previousDay).format("ddd D MMM"));
  return __("Yesterday");
}

export const STATUS_TONES: Record<StandupStatus, Tone> = {
  Draft: "neutral",
  Submitted: "success",
  "Auto-posted": "neutral",
};

export function statusLabel(status: StandupStatus) {
  return {
    Draft: __("Not submitted"),
    Submitted: __("Submitted"),
    "Auto-posted": __("Posted as filled in"),
  }[status];
}

export function dayLabel(date: string) {
  return dayjs(date).format("dddd, D MMMM");
}
