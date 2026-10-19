// Leads live in ERPNext on the CRM site; helpdesk.api.leads reads and writes
// them there as the signed-in person (docs/leads.md).
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { createResource, toast } from "frappe-ui";
import type { ProposalRow } from "./proposals";

export interface LeadStage {
  name: string;
  label?: string;
  /** e.g. Open, Won, Lost: only Won and Lost carry a colour here */
  type?: string;
  color?: string;
}

export interface LeadOptions {
  stages: LeadStage[];
  sources: string[];
  segments: string[];
  owners: { email: string; full_name?: string }[];
  territories: string[];
  industries: string[];
  /** MyOperator click-to-call is set up for the signed-in person on the ERP site */
  can_call?: boolean;
}

export interface LeadRow {
  name: string;
  lead_name?: string;
  company_name?: string;
  email_id?: string;
  mobile_no?: string;
  tbo_stage?: string;
  segment?: string;
  lead_owner?: string;
  owner_name?: string;
  score?: number | null;
  next_follow_up?: string | null;
  modified?: string;
}

export type LeadView = "all" | "mine" | "call_today" | "follow_up";

export const LEAD_VIEWS: { value: LeadView; label: string }[] = [
  { value: "all", label: __("All") },
  { value: "mine", label: __("Mine") },
  { value: "call_today", label: __("Call today") },
  { value: "follow_up", label: __("Follow-up") },
];

/** What the New lead and Edit lead dialog sends as `data`. */
export interface LeadForm {
  lead_name: string;
  company_name: string;
  email_id: string;
  mobile_no: string;
  source: string;
  segment: string;
  territory: string;
  industry: string;
  lead_owner: string;
  next_follow_up: string;
}

export const LEAD_FORM_FIELDS: (keyof LeadForm)[] = [
  "lead_name",
  "company_name",
  "email_id",
  "mobile_no",
  "source",
  "segment",
  "territory",
  "industry",
  "lead_owner",
  "next_follow_up",
];

/** One entry of a lead's timeline, newest first (TBO Smart's hub-leads-api.md). */
export interface LeadTimelineEntry {
  /** ai: what TBO AI did on the lead (read it, planned a follow-up, …) */
  kind:
    | "note"
    | "call"
    | "activity"
    | "meeting"
    | "stage"
    | "quotation"
    | "ai"
    | "proposal";
  /** when it happened (a date only for a quotation) */
  at?: string | null;
  who?: string | null;
  who_name?: string | null;
  /** plain text; a stage move reads "Contacted → Proposal Sent" */
  text?: string;
  /** the record behind it: Comment, Event, meeting, stage change, Quotation or proposal */
  ref?: string;
  /** a call through MyOperator (TBO Smart's docs/telephony-myoperator.md §4.1) */
  call?: string;
  /** talk time in seconds */
  duration?: number;
  direction?: "incoming" | "outgoing" | null;
  status?: "answered" | "missed" | "voicemail" | null;
  /** the call's name when it has a recording (played through call_recording) */
  recording?: string | null;
  summary?: CallSummary | null;
}

/** What TBO AI made of a recorded call. */
export interface CallSummary {
  text: string;
  language?: string;
  interest?: string | null;
  sentiment?: "Positive" | "Neutral" | "Negative";
  intent?: "High" | "Medium" | "Low" | "None";
  objections?: string[];
  next_step?: {
    what: string;
    channel?: string;
    due: string;
  } | null;
}

export interface LeadQuotation {
  name: string;
  transaction_date?: string;
  valid_till?: string;
  /** Draft, Awaiting approval, Sent, Accepted, … (TBO Smart's quotation status) */
  tbo_quote_status?: string;
  grand_total?: number;
  currency?: string;
}

export interface LeadDetail {
  lead: LeadRow & Partial<LeadForm> & Record<string, unknown>;
  timeline: LeadTimelineEntry[];
  quotations: LeadQuotation[];
  /** the lead's proposals (empty while proposals are off on the ERP site) */
  proposals?: ProposalRow[];
  /** stage names, or stages, this lead may move to */
  allowed_stages: (string | LeadStage)[];
}

/** Fetched once per session and shared by the list, the dialog and the lead. */
export const leadOptions = createResource({
  url: "helpdesk.api.leads.get_options",
  cache: "hd-lead-options",
});

// the cached copy shows at once, but it is fetched again once per page load: a setting
// changed on the ERP site (e.g. Proposals switched on) must show without clearing the browser
let leadOptionsFetched = false;
export function loadLeadOptions() {
  if (leadOptionsFetched || leadOptions.loading) return;
  leadOptionsFetched = true;
  leadOptions.fetch();
}

/** Asks MyOperator to ring the signed-in person's phone, then the lead. */
export function useClickToCall() {
  return createResource({
    url: "helpdesk.api.leads.click_to_call",
    method: "POST",
    onSuccess(data: { message?: string }) {
      toast.success(data?.message || __("MyOperator is calling your phone…"));
    },
    onError(e: unknown) {
      toast.error(
        errorText(e, __("Couldn't place the call. Try again in a minute."))
      );
    },
  });
}

/** 125 → "2:05" */
export function callLength(seconds?: number | null) {
  const total = Math.max(0, Math.round(seconds || 0));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function stageLabel(options: LeadOptions | undefined, stage?: string) {
  if (!stage) return "";
  return options?.stages.find((s) => s.name === stage)?.label || stage;
}

/** Won and Lost say how a lead went; every other stage stays neutral. */
export function stageTone(options: LeadOptions | undefined, stage?: string) {
  const type = (
    options?.stages.find((s) => s.name === stage)?.type || ""
  ).toLowerCase();
  if (type === "won") return "success" as Tone;
  if (type === "lost") return "danger" as Tone;
  return "neutral" as Tone;
}

export function ownerName(options: LeadOptions | undefined, email?: string) {
  if (!email) return "";
  return options?.owners.find((o) => o.email === email)?.full_name || email;
}

/** Plain strings as picker options, with an empty "none" first when given. */
export function choices(values: string[] | undefined, none?: string) {
  const list = (values ?? []).map((v) => ({ label: v, value: v }));
  return none !== undefined ? [{ label: none, value: "" }, ...list] : list;
}

export type OverviewPeriod = "week" | "month" | "quarter" | "custom";

/** The numbers on the Overview that open their own list (TBO Smart's metrics). */
export type LeadMetric =
  | "new"
  | "contacted"
  | "meetings"
  | "quotations"
  | "won"
  | "lost"
  | "stale"
  | "overdue"
  | "hot"
  | "open"
  // what AI runs leads read in the open leads
  | "high_intent"
  | "unhappy"
  | "stage_suggested";

export const METRIC_LABELS: Record<LeadMetric, string> = {
  new: __("New leads"),
  contacted: __("Contacted"),
  meetings: __("Meetings held"),
  quotations: __("Proposals sent"),
  won: __("Won"),
  lost: __("Lost"),
  stale: __("Gone quiet"),
  overdue: __("Overdue follow-ups"),
  hot: __("Hot leads"),
  open: __("Open leads"),
  high_intent: __("High intent (AI)"),
  unhappy: __("Unhappy customers (AI)"),
  stage_suggested: __("Stage moves to check (AI)"),
};

interface OverviewBreakdown {
  /** null: leads with no segment or source */
  value: string | null;
  new: number;
  open: number;
  won: number;
}

/** TBO Smart's hub_leads.get_overview (hub-leads-api.md §2.4). */
export interface LeadOverview {
  period: OverviewPeriod;
  from_date: string;
  to_date: string;
  scope: "own" | "team" | "all";
  people: { user: string; full_name: string }[];
  stale_days: number;
  currency?: string;
  totals: {
    new: number;
    contacted: number;
    meetings: number;
    mom_pending: number;
    quotations_sent: number;
    won: number;
    won_value: number;
    lost: number;
    stale: number;
    overdue: number;
    hot: number;
    open: number;
    open_value: number;
    win_rate: number;
    conversion_rate: number;
  };
  pipeline: {
    stage: string;
    type: string;
    color?: string;
    count: number;
    value: number;
  }[];
  funnel: {
    step: "created" | "contacted" | "meeting" | "proposal" | "won";
    count: number;
    rate: number;
  }[];
  lost_reasons: { reason: string; count: number }[];
  hot: {
    count: number;
    rows: {
      name: string;
      lead_name?: string;
      organization?: string;
      status?: string;
      lead_score?: number;
      lead_owner?: string;
    }[];
  };
  by_owner: {
    user: string;
    full_name: string;
    new: number;
    contacted: number;
    open: number;
    meetings_held: number;
    quotations_sent: number;
    won: number;
  }[];
  by_segment: OverviewBreakdown[];
  by_source: OverviewBreakdown[];
  /** with AI runs leads on the ERP site */
  ai?: OverviewAI;
}

/** TBO Smart's get_lead_ai (hub-leads-api.md §2.6): what the AI proposes for a lead. */
export interface LeadAI {
  enabled: boolean;
  ai_ready: boolean;
  open: boolean;
  /** when the AI last read the lead */
  at?: string | null;
  /** the lead changed since that read */
  stale?: boolean;
  score: { score: number; temperature?: string; reason?: string } | null;
  insight: {
    summary?: string | null;
    sentiment: "Positive" | "Neutral" | "Negative";
    intent: "High" | "Medium" | "Low" | "None";
    signals: string[];
    next_action: {
      what: string;
      why?: string | null;
      channel: "call" | "whatsapp" | "email" | "meeting";
      due: string;
    } | null;
    suggested_stage?: string | null;
    stage_reason?: string | null;
    message: {
      channel: "whatsapp" | "email";
      subject?: string | null;
      text: string;
    } | null;
  } | null;
  health: {
    status: "healthy" | "watch" | "at_risk";
    signals: { key: string; state: "watch" | "at_risk"; text: string }[];
  } | null;
  duplicates: {
    name: string;
    lead_name?: string;
    company_name?: string;
    tbo_stage?: string;
    owner_name?: string | null;
    match: ("phone" | "email" | "company")[];
  }[];
  /** where a draft is sent from: the lead's WhatsApp number (wa.me digits) and email */
  contact: { whatsapp: string | null; email: string | null };
}

/** The Overview's AI part: the day's plan and what the AI sees in the scope. */
export interface OverviewAI {
  enabled: boolean;
  ai_ready?: boolean;
  plan?: {
    user: string;
    rows: {
      name: string;
      lead_name?: string;
      company_name?: string;
      tbo_stage?: string;
      score?: number;
      temperature?: string;
      why?: string;
      next_action?: string | null;
      next_due?: string | null;
      intent?: string | null;
    }[];
  };
  high_intent?: number;
  unhappy?: number;
  stage_suggested?: number;
  read?: number;
}

/** A message the AI drafted, for the person to edit and send themselves. */
export interface LeadDraft {
  channel: "whatsapp" | "email";
  subject?: string | null;
  text: string;
  /** the lead's email, for an email draft */
  to?: string;
  /** wa.me link with the text, for a WhatsApp draft */
  url?: string | null;
}
