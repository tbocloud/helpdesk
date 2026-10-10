import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import type { Component } from "vue";
import LucideCalendarX from "~icons/lucide/calendar-x";
import LucideCoffee from "~icons/lucide/coffee";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";

/** helpdesk.api.capacity.load_flag: over 100%, from 80%, under 80% */
export type Flag = "overloaded" | "busy" | "available";
export const FLAGS: Flag[] = ["overloaded", "busy", "available"];

export interface Load {
  available: number;
  planned: number;
  utilisation: number | null;
  flag: Flag | null;
}

export interface PersonCapacity extends Load {
  user: string;
  full_name: string;
  free: number;
  /** working days of approved leave in the window (a half day counts 0.5) */
  leave_days: number;
  weeks: (Load & { start: string })[];
  /** leave: 1, or 0.5 for a half day; its hours are taken off `available` */
  days: (Load & { date: string; leave: number })[];
  /** project null: work on projects the viewer doesn't run */
  projects: { project: string | null; project_name: string | null; hours: number }[];
  tasks: {
    name: string;
    title: string;
    project_name: string | null;
    hours: number;
    due: string | null;
    typical: boolean;
  }[];
  typical_estimates: number;
}

export interface Capacity {
  /** the server's today */
  today: string;
  start: string;
  end: string;
  hours_per_day: number;
  weeks: { start: string; end: string }[];
  people: PersonCapacity[];
  totals: Load & { people: number; flags: Record<Flag, number> };
  /** other: work on projects the viewer doesn't run */
  by_department: {
    department: string | null;
    hours: number;
    other: boolean;
  }[];
  by_project: {
    project: string | null;
    project_name: string | null;
    hours: number;
    people: number;
  }[];
}

const BADGES: Record<Flag, { label: string; tone: Tone; icon: Component }> = {
  overloaded: {
    label: __("Overloaded"),
    tone: "danger",
    icon: LucideTriangleAlert,
  },
  busy: { label: __("Busy"), tone: "warning", icon: LucideHourglass },
  available: { label: __("Available"), tone: "neutral", icon: LucideCoffee },
};

/** TaskyBadge props for a load flag; no flag means no working days in the window. */
export function flagBadge(flag: Flag | null) {
  return flag
    ? BADGES[flag]
    : {
        label: __("No working days"),
        tone: "neutral" as Tone,
        icon: LucideCalendarX,
      };
}

export function formatHours(hours: number) {
  return Number.isInteger(hours) ? String(hours) : hours.toFixed(1);
}

/** "28 / 40 h": planned of available */
export function hoursOf(load: Load) {
  return `${formatHours(load.planned)} / ${formatHours(load.available)} h`;
}

export function isOver(load: Load) {
  return load.flag === "overloaded";
}

export function meterWidth(load: Load) {
  if (load.utilisation == null) return load.planned ? 100 : 0;
  return Math.min(load.utilisation, 100);
}

export function loadText(load: Load) {
  const hours = __(
    "{0} of {1} hours planned",
    formatHours(load.planned),
    formatHours(load.available)
  );
  return load.flag ? `${hours}, ${flagBadge(load.flag).label}` : hours;
}
