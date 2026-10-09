import type { Tone } from "@/components/tone";
import { useConfigStore } from "@/stores/config";
import { useTicketStatusStore } from "@/stores/ticketStatus";
import { __ } from "@/translation";
import { formatTime } from "@/utils";
import { dayjs, dayjsLocal } from "frappe-ui";
import type { Component } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideClock from "~icons/lucide/clock";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideMessageSquareReply from "~icons/lucide/message-square-reply";
import LucidePause from "~icons/lucide/pause";
import { deadlineLabel } from "./ticketMeta";

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
  return deadlineFact(t.response_by, "reply");
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
  return deadlineFact(t.resolution_by, "resolve");
}

/**
 * A deadline still ahead reads as when it falls ("Reply by 10:30 AM", the agents' wording),
 * never as a countdown: deadlines run on working hours, so "in 3h" would overstate the time
 * across nights and weekends.
 */
function deadlineFact(
  deadline: string | undefined,
  promise: "reply" | "resolve"
): Fact | null {
  if (!deadline) return null;
  if (dayjsLocal(deadline).isBefore(dayjsLocal())) {
    return {
      label: __("Overdue"),
      tone: "danger",
      icon: LucideCircleAlert,
      at: deadline,
    };
  }
  const when = deadlineLabel(deadline);
  return {
    label:
      promise === "reply"
        ? __("Reply by {0}", [when])
        : __("Resolve by {0}", [when]),
    tone: "neutral",
    icon: LucideClock,
    at: deadline,
  };
}
