// Leads live in ERPNext on the CRM site; helpdesk.api.leads reads and writes
// them there as the signed-in person (docs/leads.md).
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { createResource } from "frappe-ui";

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
  kind: "note" | "call" | "activity" | "meeting" | "stage" | "quotation";
  /** when it happened (a date only for a quotation) */
  at?: string | null;
  who?: string | null;
  who_name?: string | null;
  /** plain text; a stage move reads "Contacted → Proposal Sent" */
  text?: string;
  /** the record behind it: Comment, Event, meeting, stage change or Quotation */
  ref?: string;
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
  /** stage names, or stages, this lead may move to */
  allowed_stages: (string | LeadStage)[];
}

/** Fetched once per session and shared by the list, the dialog and the lead. */
export const leadOptions = createResource({
  url: "helpdesk.api.leads.get_options",
  cache: "hd-lead-options",
});

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
  | "open";

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
}
