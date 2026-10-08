import type { Tone } from "@/components/tone";
import { useConfigStore } from "@/stores/config";
import { useTicketStatusStore } from "@/stores/ticketStatus";
import { __ } from "@/translation";
import { formatTime, shortDuration } from "@/utils";
import { dayjs } from "frappe-ui";
import type { Component } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideClock from "~icons/lucide/clock";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideMessageSquareReply from "~icons/lucide/message-square-reply";
import LucidePause from "~icons/lucide/pause";

/**
 * Where a ticket stands for the customer who raised it:
 * - open: with the support team;
 * - awaiting: the team replied (the status an agent's reply sets) and waits on the customer;
 * - paused: on hold for another reason, e.g. a related task;
 * - resolved: resolved or closed.
 */
export type CustomerStage = "open" | "awaiting" | "paused" | "resolved";

export interface Fact {
  label: string;
  tone: Tone;
  icon: Component;
  /** the exact time behind a relative label, for a tooltip */
  at?: string;
}

const STAGE_LOOK: Record<CustomerStage, { tone: Tone; icon: Component }> = {
  open: { tone: "info", icon: LucideCircleDot },
  awaiting: { tone: "warning", icon: LucideMessageSquareReply },
  paused: { tone: "neutral", icon: LucideHourglass },
  resolved: { tone: "success", icon: LucideCircleCheck },
};

/** The customer-facing label, tone and icon of a ticket status, for TaskyBadge. */
export function useCustomerStatus() {
  const { getStatus } = useTicketStatusStore();
  const configStore = useConfigStore();

  function stage(status: string): CustomerStage {
    const s = getStatus(status);
    if (s?.category === "Resolved") return "resolved";
    if (s?.category === "Paused") {
      return s.label_agent === configStore.config.update_status_to
        ? "awaiting"
        : "paused";
    }
    return "open";
  }

  function badge(status: string): Fact {
    return {
      label: getStatus(status)?.label_customer || status,
      ...STAGE_LOOK[stage(status)],
    };
  }

  return { stage, badge };
}

interface SlaFields {
  creation?: string;
  response_by?: string;
  first_responded_on?: string;
  resolution_by?: string;
  resolution_date?: string;
}

/**
 * The first-reply promise as the customer sees it. A missed deadline reads "Overdue",
 * not the agents' "Failed".
 */
export function firstReplyFact(t: SlaFields): Fact | null {
  if (t.first_responded_on) {
    return {
      label: __("Replied in {0}", [
        formatTime(
          dayjs(t.first_responded_on).diff(dayjs(t.creation), "second"),
          { day: true, hour: true, minute: true, maxUnits: 2 }
        ) || __("under a minute"),
      ]),
      tone: "success",
      icon: LucideCircleCheck,
      at: t.first_responded_on,
    };
  }
  return deadlineFact(t.response_by);
}

export function resolutionFact(t: SlaFields, stage: CustomerStage): Fact | null {
  if (t.resolution_date) {
    return {
      label: __("Resolved"),
      tone: "success",
      icon: LucideCircleCheck,
      at: t.resolution_date,
    };
  }
  if (!t.resolution_by) return null;
  if (stage === "awaiting" || stage === "paused") {
    return {
      label: __("Paused"),
      tone: "neutral",
      icon: LucidePause,
      at: t.resolution_by,
    };
  }
  return deadlineFact(t.resolution_by);
}

function deadlineFact(deadline?: string): Fact | null {
  if (!deadline) return null;
  if (dayjs(deadline).isBefore(dayjs())) {
    return {
      label: __("Overdue"),
      tone: "danger",
      icon: LucideCircleAlert,
      at: deadline,
    };
  }
  return {
    label: __("Due in {0}", [shortDuration(deadline)]),
    tone: "neutral",
    icon: LucideClock,
    at: deadline,
  };
}
