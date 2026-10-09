import type { Tone } from "@/components/tone";
import { priorityIcon } from "@/pages/tasky/taskMeta";
import { __ } from "@/translation";
import { dateFormat, dateTooltipFormat } from "@/utils";
import type { Dayjs } from "dayjs";
import { dayjs, dayjsLocal } from "frappe-ui";
import type { Component } from "vue";
import LucideCheck from "~icons/lucide/check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideClock from "~icons/lucide/clock";
import LucidePause from "~icons/lucide/pause";

/** What a ticket's SLA clock says: shared by the tickets list and the ticket page. */
export type SlaState = "failed" | "fulfilled" | "paused" | "due" | "none";

export interface BadgeMeta {
  label: string;
  tone: Tone;
  icon: Component;
}

/**
 * A running deadline turns amber with this much working time left. Deadlines are set in
 * working hours, so the warning counts working time too (helpdesk.api.ticket
 * get_sla_time_left), not the hours on the clock.
 */
export const SLA_RISK_WORKING_SECONDS = 60 * 60;

// SLA datetimes are stored in the site's time zone, which dayjsLocal reads them in
export function responseSla(
  ticket: { first_responded_on?: string | null },
  deadline?: string | null,
  now: Dayjs = dayjsLocal()
): SlaState {
  if (!deadline) return "none";
  const due = dayjsLocal(deadline);
  if (!ticket.first_responded_on) return due.isBefore(now) ? "failed" : "due";
  return dayjsLocal(ticket.first_responded_on).isAfter(due)
    ? "failed"
    : "fulfilled";
}

/** `paused`: the ticket's status is in the Paused category, which stops the clock. */
export function resolutionSla(
  ticket: { resolution_date?: string | null },
  deadline: string | null | undefined,
  paused: boolean,
  now: Dayjs = dayjsLocal()
): SlaState {
  // no resolution SLA on this ticket: nothing to fulfil or fail
  if (!deadline) return "none";
  if (paused) return "paused";
  const due = dayjsLocal(deadline);
  if (ticket.resolution_date)
    return dayjsLocal(ticket.resolution_date).isBefore(due)
      ? "fulfilled"
      : "failed";
  return due.isBefore(now) ? "failed" : "due";
}

/**
 * When a deadline falls, said the short way: "10:30 AM" today, "Tomorrow 10:30 AM",
 * "Tue 2:30 PM" within six days, "13 Oct, 2:30 PM" later. A time rather than "in 2h"
 * because deadlines run on working hours, and a calendar countdown overstates the time
 * left across nights, weekends and holidays.
 */
export function deadlineLabel(
  deadline: string,
  now: Dayjs = dayjsLocal()
): string {
  const at = dayjsLocal(deadline);
  // calendar days in the display time zone, not elapsed 24-hour windows
  const days = dayjs(at.format("YYYY-MM-DD")).diff(
    dayjs(now.format("YYYY-MM-DD")),
    "day"
  );
  const time = at.format("h:mm A");
  if (days === 0) return time;
  if (days === 1) return __("Tomorrow {0}", [time]);
  if (days > 1 && days <= 6) return at.format("ddd h:mm A");
  return at.format(
    at.year() === now.year() ? "D MMM, h:mm A" : "D MMM YYYY, h:mm A"
  );
}

/** "30 working min left", "1.5 working h left", "19 working h left". */
export function workingTimeLeft(seconds: number): string {
  const minutes = Math.max(Math.ceil(seconds / 60), 0);
  if (minutes < 60) return __("{0} working min left", [minutes]);
  const hours = seconds / 3600;
  const shown = hours < 10 ? Math.floor(hours * 10) / 10 : Math.floor(hours);
  return __("{0} working h left", [shown]);
}

/** The exact deadline and, while its clock runs, the working time left: for tooltips and screen readers. */
export function slaHint(
  deadline: string,
  workingLeft?: number | null
): string {
  const due = __("Due {0}", [dateFormat(deadline, dateTooltipFormat)]);
  return workingLeft == null ? due : `${due} · ${workingTimeLeft(workingLeft)}`;
}

export const SLA_LABELS: Record<Exclude<SlaState, "due" | "none">, string> = {
  failed: __("Failed"),
  fulfilled: __("Fulfilled"),
  paused: __("Paused"),
};

const SLA_BADGES: Record<
  Exclude<SlaState, "due" | "none">,
  { tone: Tone; icon: Component }
> = {
  failed: { tone: "danger", icon: LucideCircleAlert },
  fulfilled: { tone: "neutral", icon: LucideCheck },
  paused: { tone: "neutral", icon: LucidePause },
};

/**
 * A running deadline shows when it falls (`deadlineLabel`) with a clock, amber with at most
 * SLA_RISK_WORKING_SECONDS of working time left; otherwise Failed (red), Fulfilled or
 * Paused. `workingLeft` is null until the server has counted it, and the badge stays
 * neutral meanwhile. Null without an SLA.
 */
export function slaBadge(
  state: SlaState,
  deadline?: string | null,
  workingLeft?: number | null,
  now: Dayjs = dayjsLocal()
): BadgeMeta | null {
  if (state === "none" || !deadline) return null;
  if (state !== "due") return { label: SLA_LABELS[state], ...SLA_BADGES[state] };
  return {
    label: deadlineLabel(deadline, now),
    icon: LucideClock,
    tone:
      workingLeft != null && workingLeft <= SLA_RISK_WORKING_SECONDS
        ? "warning"
        : "neutral",
  };
}

const PRIORITY_TONES: Record<string, Tone> = {
  Urgent: "danger",
  High: "warning",
};

/** Urgent red, High amber, the rest neutral; always with the signal icon. */
export function priorityBadge(priority?: string | null): BadgeMeta | null {
  if (!priority) return null;
  return {
    label: __(priority),
    icon: priorityIcon(priority),
    tone: PRIORITY_TONES[priority] ?? "neutral",
  };
}

const STATUS_CATEGORY: Record<string, { tone: Tone; icon: Component }> = {
  Open: { tone: "neutral", icon: LucideCircleDot },
  Paused: { tone: "warning", icon: LucidePause },
  Resolved: { tone: "success", icon: LucideCircleCheck },
};

/** A ticket status by its category: amber while paused, green once resolved. */
export function statusBadge(
  status: string,
  category?: string | null
): BadgeMeta {
  return {
    label: __(status),
    ...(STATUS_CATEGORY[category ?? ""] ?? STATUS_CATEGORY.Open),
  };
}
