import type { Tone } from "@/components/tone";
import { ticketsLink, type TicketCondition } from "@/pages/ticket/ticketFilters";
import { __ } from "@/translation";
import type { Component } from "vue";
import type { RouteLocationRaw } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";

/** A customer's health (helpdesk/customer_health.py, docs/customer-health.md). */
export type HealthStatus = "at_risk" | "watch" | "healthy" | "no_data";
export type SignalState = "at_risk" | "watch" | "ok" | "skipped";

/** What a list row gets: the status and the signals against it, worst first. */
export interface HealthBrief {
  status: HealthStatus;
  points: number;
  reasons: string[];
}

export type SignalLink =
  | { kind: "tickets"; filters: TicketCondition[] }
  | { kind: "work" }
  | { kind: "tab"; hash: string }
  | { kind: "signoff"; project: string };

export interface HealthSignal {
  key: string;
  state: SignalState;
  weight: number;
  points: number;
  label: string;
  value: string;
  rule: string;
  link: SignalLink | null;
}

export interface CustomerHealth extends HealthBrief {
  signals: HealthSignal[];
  thresholds: { watch: number; at_risk: number };
}

const STATUS: Record<
  HealthStatus,
  { label: string; tone: Tone; icon: Component }
> = {
  at_risk: {
    label: __("At risk"),
    tone: "danger",
    icon: LucideTriangleAlert,
  },
  watch: { label: __("Watch"), tone: "warning", icon: LucideCircleAlert },
  healthy: { label: __("Healthy"), tone: "success", icon: LucideCircleCheck },
  no_data: { label: __("No data"), tone: "neutral", icon: LucideCircleDashed },
};

/** TaskyBadge props for a status: the words, a tone and an icon. */
export function healthBadge(status: HealthStatus) {
  return STATUS[status] ?? STATUS.no_data;
}

/** The ink and icon of a signal's state; only watch and at risk carry colour. */
export function signalLook(state: SignalState): {
  tone: Tone;
  icon: Component;
} {
  if (state === "at_risk") return { tone: "danger", icon: LucideTriangleAlert };
  if (state === "watch") return { tone: "warning", icon: LucideCircleAlert };
  if (state === "ok") return { tone: "neutral", icon: LucideCircleCheck };
  return { tone: "neutral", icon: LucideCircleDashed };
}

export function signalStateLabel(state: SignalState) {
  return {
    at_risk: __("At risk"),
    watch: __("Watch"),
    ok: __("Fine"),
    skipped: __("No data"),
  }[state];
}

/** The Customers list's health filter (`health` in the URL). */
export const HEALTH_FILTERS = [
  { value: "", label: __("Any health") },
  { value: "attention", label: __("At risk or watch") },
  { value: "at_risk", label: __("At risk") },
  { value: "watch", label: __("Watch") },
  { value: "healthy", label: __("Healthy") },
] as const;

/**
 * Where a signal's records are. Project work opens the Overview for people who
 * can see it, else the customer's projects.
 */
export function signalRoute(
  link: SignalLink,
  customer: string,
  canSeeOverview: boolean
): { to: RouteLocationRaw; label: string } {
  switch (link.kind) {
    case "tickets":
      return { to: ticketsLink(link.filters), label: __("Tickets") };
    case "work":
      return canSeeOverview
        ? {
            to: { name: "WorkOverview", query: { customer } },
            label: __("Tasks"),
          }
        : { to: { hash: "#projects" }, label: __("Projects") };
    case "signoff":
      return {
        to: { name: "TaskySignoffs", params: { projectId: link.project } },
        label: __("Sign-offs"),
      };
    case "tab":
      return {
        to: { hash: `#${link.hash}` },
        label:
          link.hash === "support-hours" ? __("Support hours") : __("Projects"),
      };
  }
}
