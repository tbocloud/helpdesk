// Outreach: AI first messages that a person approves before they go (docs/leads.md,
// "Outreach"). helpdesk.api.outreach proxies TBO Smart's hub_outreach API.
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { createResource, toast } from "frappe-ui";
import type { Component } from "vue";
import LucideBan from "~icons/lucide/ban";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCheckCheck from "~icons/lucide/check-check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleHelp from "~icons/lucide/circle-help";
import LucideClock from "~icons/lucide/clock";
import LucideMessageCircleReply from "~icons/lucide/message-circle-reply";
import LucideMoon from "~icons/lucide/moon";
import LucidePencil from "~icons/lucide/pencil";
import LucideThumbsDown from "~icons/lucide/thumbs-down";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUserX from "~icons/lucide/user-x";

export type OutreachStatus =
  | "Draft"
  | "Approved"
  | "Sent"
  | "Failed"
  | "Cancelled";
export type OutreachChannel = "Email" | "WhatsApp";

export const OUTREACH_STATUSES: OutreachStatus[] = [
  "Draft",
  "Approved",
  "Sent",
  "Failed",
  "Cancelled",
];

export interface OutreachMessage {
  name: string;
  lead: string;
  lead_name?: string | null;
  company_name?: string | null;
  lead_stage?: string | null;
  unsubscribed: number;
  last_reply_class?: ReplyClass | null;
  channel: OutreachChannel;
  status: OutreachStatus;
  subject?: string | null;
  body: string;
  recipient?: string | null;
  drafted_by: "AI" | "User";
  owner: string;
  owner_name?: string | null;
  approved_by?: string | null;
  approved_on?: string | null;
  sent_on?: string | null;
  error?: string | null;
  prospect_run?: string | null;
  /** WhatsApp: wa.me link with the message filled in */
  url?: string | null;
  /** an approved email waiting for the send window or the daily limit */
  queued: boolean;
  creation: string;
}

export interface Outbox {
  /** false while the ERP site is older than Outreach */
  available: boolean;
  enabled: boolean;
  /** the ERP site has an outgoing email account */
  email_ready: boolean;
  rows: OutreachMessage[];
  counts: Partial<Record<OutreachStatus, number>>;
  cap: { limit: number; used: number; left: number; queued: number } | null;
  window: { start: string; end: string; open: boolean; next: string } | null;
  drafting: {
    batch: string;
    total: number;
    done: number;
    failed: number;
  } | null;
  /** the line added under every email when it is sent */
  opt_out: string;
}

export interface OutreachResult {
  name: string;
  status: OutreachStatus | null;
  message: string;
}

export interface DraftResult {
  batch: string;
  queued: number;
  skipped: { lead: string; lead_name?: string | null; reason: string }[];
}

/** How the ERP site sorted a lead's last email reply. */
export type ReplyClass =
  | "Interested"
  | "Question"
  | "Objection"
  | "Not now"
  | "Not interested"
  | "Unsubscribe"
  | "Out of office"
  | "New reply";

/** A tone only where the reply means something to the salesperson; "New reply" is the
 * one accent, for a reply nobody has sorted yet. */
export const REPLY_LOOK: Record<
  ReplyClass,
  { label: string; icon: Component; tone: Tone | "brand" }
> = {
  Interested: {
    label: __("Interested"),
    icon: LucideCircleCheck,
    tone: "success",
  },
  Question: { label: __("Question"), icon: LucideCircleHelp, tone: "info" },
  Objection: {
    label: __("Objection"),
    icon: LucideTriangleAlert,
    tone: "warning",
  },
  "Not now": {
    label: __("Not now"),
    icon: LucideCalendarClock,
    tone: "neutral",
  },
  "Not interested": {
    label: __("Not interested"),
    icon: LucideThumbsDown,
    tone: "danger",
  },
  Unsubscribe: { label: __("Unsubscribe"), icon: LucideUserX, tone: "danger" },
  "Out of office": {
    label: __("Out of office"),
    icon: LucideMoon,
    tone: "neutral",
  },
  "New reply": {
    label: __("New reply"),
    icon: LucideMessageCircleReply,
    tone: "brand",
  },
};

/** What the ERP site did about each kind of reply, for the lead page. */
export const REPLY_HINT: Record<ReplyClass, string> = {
  Interested: __("A follow-up is set for today."),
  Question: __("A follow-up is set for today."),
  Objection: __("A follow-up is set for today."),
  "Not now": __("A follow-up is set for 30 days after the reply."),
  "Not interested": __("The lead was marked Not interested."),
  Unsubscribe: __("The lead unsubscribed. Nothing more will be sent."),
  "Out of office": __("An automatic reply. Nothing changed."),
  "New reply": __("Read it and decide the next step."),
};

export const REPLY_CLASSES = Object.keys(REPLY_LOOK) as ReplyClass[];

export const STATUS_LOOK: Record<
  OutreachStatus,
  { label: string; icon: Component; tone: Tone }
> = {
  Draft: { label: __("Draft"), icon: LucidePencil, tone: "neutral" },
  Approved: { label: __("Approved"), icon: LucideClock, tone: "info" },
  Sent: { label: __("Sent"), icon: LucideCheckCheck, tone: "success" },
  Failed: { label: __("Failed"), icon: LucideCircleAlert, tone: "danger" },
  Cancelled: { label: __("Cancelled"), icon: LucideBan, tone: "neutral" },
};

/** What an approved message is waiting for, in words. */
export function approvedLabel(message: OutreachMessage) {
  if (message.channel === "WhatsApp") return __("Ready to send");
  return message.queued ? __("Approved, waiting to go") : __("Approved");
}

/** An outreach action that reports what became of each message. */
export function useOutreachAction(
  url: string,
  onDone: (results: OutreachResult[]) => void
) {
  return createResource({
    url,
    method: "POST",
    onSuccess(results: OutreachResult[] | OutreachResult) {
      onDone(Array.isArray(results) ? results : [results]);
    },
    onError(e: unknown) {
      toast.error(errorText(e, __("That didn't work. Try again.")));
    },
  });
}
