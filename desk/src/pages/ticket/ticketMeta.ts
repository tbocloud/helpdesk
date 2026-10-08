import type { Tone } from "@/components/tone";
import { priorityIcon } from "@/pages/tasky/taskMeta";
import { __ } from "@/translation";
import { shortDuration } from "@/utils";
import { dayjs } from "frappe-ui";
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

// same window as SLA_RISK_HOURS in helpdesk/api/work.py ("at risk" tickets)
export const SLA_RISK_HOURS = 4;

export function responseSla(
  ticket: { first_responded_on?: string | null },
  deadline?: string | null
): SlaState {
  if (!deadline) return "none";
  if (!ticket.first_responded_on && dayjs(deadline).isBefore(new Date()))
    return "failed";
  if (
    ticket.first_responded_on &&
    dayjs(ticket.first_responded_on).isBefore(deadline)
  )
    return "fulfilled";
  if (dayjs(ticket.first_responded_on).isAfter(deadline)) return "failed";
  return "due";
}

/** `paused`: the ticket's status is in the Paused category, which stops the clock. */
export function resolutionSla(
  ticket: { resolution_date?: string | null },
  deadline: string | null | undefined,
  paused: boolean
): SlaState {
  // no resolution SLA on this ticket: nothing to fulfil or fail
  if (!deadline) return "none";
  if (paused) return "paused";
  if (ticket.resolution_date)
    return dayjs(ticket.resolution_date).isBefore(dayjs(deadline))
      ? "fulfilled"
      : "failed";
  return dayjs(deadline).isBefore(dayjs()) ? "failed" : "due";
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

/** "in 3h" (amber within SLA_RISK_HOURS), Failed (red), Fulfilled, Paused; null without an SLA. */
export function slaBadge(
  state: SlaState,
  deadline?: string | null
): BadgeMeta | null {
  if (state === "none" || !deadline) return null;
  if (state !== "due") return { label: SLA_LABELS[state], ...SLA_BADGES[state] };
  return {
    label: __("in {0}", [shortDuration(deadline)]),
    icon: LucideClock,
    tone:
      dayjs(deadline).diff(dayjs(), "hour", true) <= SLA_RISK_HOURS
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
