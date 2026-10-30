// Leads live in ERPNext on the CRM site; helpdesk.api.leads reads and writes
// them there as the signed-in person (docs/leads.md).
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import type { LeadProspect, ProspectingOptions } from "./prospects";
import { money } from "@/components/invoicing/invoices";
import { UNSAVED_NOTE_PREFIX, useAuthStore } from "@/stores/auth";
import { errorText } from "@/utils";
import { createResource, dayjs, toast } from "frappe-ui";
import type { LeadPlace } from "./place";
import type { DocumentChain, ProposalRow } from "./proposals";

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
  /** the categories (absent from an older TBO Smart: the category pickers stay out) */
  org_sizes?: string[];
  states?: string[];
  kerala_districts?: string[];
  /** districts used on leads, by state ("" for leads without a state) */
  districts_by_state?: Record<string, string[]>;
  /** MyOperator click-to-call is set up for the signed-in person on the ERP site */
  can_call?: boolean;
  /** the ERP site can log a call made outside MyOperator (TBO Smart's log_call) */
  can_log_call?: boolean;
  /** lead departments (absent from an older TBO Smart; the department UI stays out) */
  departments?: LeadDepartmentOption[];
  lead_types?: string[];
  /** the signed-in person may open the Business tab: System Manager or the TBO Management
   * role on the ERP site, which decides it (absent from an older TBO Smart) */
  can_view_business?: boolean;
  /** the signed-in person may open Find prospects (managers and department heads, while it is
   * on); absent from an older TBO Smart */
  can_find_prospects?: boolean;
  prospecting?: ProspectingOptions | null;
}

/** A department as `get_options` lists it, with the signed-in person's part in it. */
export interface LeadDepartmentOption {
  name: string;
  lead_type?: string;
  is_active?: boolean | number;
  is_head?: boolean | number;
  is_member?: boolean | number;
  /** members get daily call batches (Today's calls); absent from an older TBO Smart */
  call_batches_enabled?: boolean | number;
  /** how a lead with no owner is given one (absent from an older TBO Smart) */
  assignment?: LeadAssignment;
  stale_after_days?: number;
}

export type LeadAssignment = "Manual" | "Round robin";

/** A lead department with its people, as `get_lead_departments` answers (Settings → CRM). */
export interface LeadDepartment {
  name: string;
  department_name: string;
  lead_type: string;
  is_active: boolean | number;
  /** Manual: the creator picks the owner; Round robin: the ERP site picks one */
  assignment?: LeadAssignment;
  /** days without activity before a lead is chased (absent from an older TBO Smart) */
  stale_after_days?: number;
  heads: { user: string; full_name?: string }[];
  members: { user: string; full_name?: string }[];
}

/** A lead that shares an email, phone or company with the one being entered. */
export interface DuplicateLead {
  name: string;
  lead_name?: string;
  company_name?: string;
  email_id?: string;
  mobile_no?: string;
  lead_owner?: string;
  owner_name?: string | null;
  tbo_stage?: string;
  matched_on: ("email" | "phone" | "company")[];
}

/** A lead with no activity for longer than its department allows. */
export interface StaleLead {
  name: string;
  idle_days: number;
  last_activity_on?: string | null;
}

export const ASSIGNMENT_LABELS: Record<LeadAssignment, string> = {
  Manual: __("Manual"),
  "Round robin": __("Round robin"),
};

/** The department's own idle days, else the default the ERP site and the hub share. */
export const DEFAULT_STALE_DAYS = 3;

/** Whether the picked department hands out leads with no owner in turn. */
export function isRoundRobin(options: LeadOptions | undefined, name: string) {
  return (
    !!name &&
    options?.departments?.find((d) => d.name === name)?.assignment ===
      "Round robin"
  );
}

/** Leads of the signed-in person gone quiet, by lead name; empty on an older TBO Smart. */
export const staleLeads = createResource({
  url: "helpdesk.api.leads.get_stale_leads",
  // the chip is a bonus on the list: a failed read just leaves it out
  onError() {},
});

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
  tbo_department?: string | null;
  tbo_lead_type?: string | null;
  industry?: string | null;
  state?: string | null;
  district?: string | null;
  org_size?: string | null;
  score?: number | null;
  next_follow_up?: string | null;
  modified?: string;
  /** the newest quotation's latest revision (absent from an older TBO Smart) */
  latest_quotation?: {
    name: string;
    tbo_quote_status?: string | null;
    grand_total?: number;
    currency?: string;
    tbo_sent_on?: string | null;
  } | null;
  /** the newest priced client document's latest revision, while Proposals is on */
  latest_proposal?: {
    name: string;
    document_type?: string;
    status?: string;
    view_count?: number;
    sent_on?: string | null;
  } | null;
}

/** Where a lead stands with the client, as one chip on its row: the proposal's
 * status (else the quotation's), its value and when it went out. Colour only for an
 * outcome: accepted is success, declined, rejected and expired danger. */
export function clientStatus(
  row: LeadRow
): { label: string; tone: Tone; title: string } | null {
  const quote = row.latest_quotation;
  const proposal = row.latest_proposal;
  if (!quote && !proposal) return null;
  const isQuote = !proposal;
  const status = (proposal?.status || quote?.tbo_quote_status || "") as string;
  const look = (isQuote ? QUOTE_STATUS : PROPOSAL_STATUS)[status] || {
    label: status,
    tone: "neutral" as Tone,
  };
  let label = look.label;
  if (status === "Viewed" && (proposal?.view_count || 0) > 1)
    label = __("Viewed {0}×", String(proposal!.view_count));
  const parts = [label];
  if (quote?.grand_total && quote.currency)
    parts.push(money(quote.grand_total, quote.currency, true));
  const sent = proposal?.sent_on || quote?.tbo_sent_on;
  if (sent && look.open) parts.push(dayjs(sent).fromNow());
  const doc = isQuote ? __("Quotation {0}", quote!.name) : proposal!.name;
  return { label: parts.join(" · "), tone: look.tone, title: doc };
}

interface StatusLook {
  label: string;
  tone: Tone;
  /** still with the client: say how long ago it went */
  open?: boolean;
}

const PROPOSAL_STATUS: Record<string, StatusLook> = {
  Draft: { label: __("Proposal draft"), tone: "neutral" },
  Sent: { label: __("Proposal sent"), tone: "neutral", open: true },
  Viewed: { label: __("Viewed"), tone: "neutral", open: true },
  Accepted: { label: __("Accepted"), tone: "success" },
  Declined: { label: __("Declined"), tone: "danger" },
  Expired: { label: __("Expired"), tone: "danger" },
};

// TBO Smart's tbo_quote_status
const QUOTE_STATUS: Record<string, StatusLook> = {
  Draft: { label: __("Quote draft"), tone: "neutral" },
  "Pending Approval": { label: __("Quote awaiting approval"), tone: "neutral" },
  Approved: { label: __("Quote approved"), tone: "neutral" },
  "Sent to Client": { label: __("Quote sent"), tone: "neutral", open: true },
  "Viewed / Acknowledged": {
    label: __("Quote viewed"),
    tone: "neutral",
    open: true,
  },
  "Under Negotiation": {
    label: __("Negotiating"),
    tone: "neutral",
    open: true,
  },
  "Revision Required": {
    label: __("Revision asked"),
    tone: "neutral",
    open: true,
  },
  Accepted: { label: __("Accepted"), tone: "success" },
  Rejected: { label: __("Rejected"), tone: "danger" },
  Expired: { label: __("Expired"), tone: "danger" },
};

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
  state: string;
  district: string;
  org_size: string;
  lead_owner: string;
  next_follow_up: string;
  tbo_department: string;
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
  "state",
  "district",
  "org_size",
  "lead_owner",
  "next_follow_up",
  "tbo_department",
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
  /** the client document it prices (PROP-…, QUOT-…): the client's reference */
  tbo_proposal?: string | null;
  /** staff only: its desk form on the ERP site */
  url?: string | null;
}

export interface LeadDetail {
  lead: LeadRow &
    Partial<LeadForm> &
    Record<string, unknown> & {
      /** absent from an older TBO Smart */
      place?: LeadPlace;
      photo_count?: number;
      /** what the lead's website says, for a lead found by Find prospects */
      prospect?: LeadProspect | null;
    };
  timeline: LeadTimelineEntry[];
  quotations: LeadQuotation[];
  /** the lead's proposals (empty while proposals are off on the ERP site) */
  proposals?: ProposalRow[];
  /** the chain of client documents and the next action (null while proposals are off) */
  documents?: DocumentChain | null;
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

// Remarks the New lead dialog couldn't save as the lead's first note, kept per person and
// lead until the note is added: in this browser, so neither a reload nor reopening the
// dialog loses them, and in memory too, so blocked or full storage still hands them to the
// lead's page. Logout clears the stored ones.
const unsavedNotes = new Map<string, string>();
const unsavedNoteKey = (lead: string) =>
  `${UNSAVED_NOTE_PREFIX}${useAuthStore().userId}:${lead}`;

/** Whether the browser kept them too: when not, a reload loses them. */
export function keepUnsavedNote(lead: string, note: string) {
  // a failure that lands after logout began: logout has cleared the drafts already
  if (!useAuthStore().isLoggedIn) return false;
  unsavedNotes.set(unsavedNoteKey(lead), note);
  try {
    localStorage.setItem(unsavedNoteKey(lead), note);
    return true;
  } catch {
    return false;
  }
}

export function unsavedNote(lead: string) {
  const key = unsavedNoteKey(lead);
  try {
    return localStorage.getItem(key) ?? unsavedNotes.get(key) ?? "";
  } catch {
    return unsavedNotes.get(key) ?? "";
  }
}

export function dropUnsavedNote(lead: string) {
  unsavedNotes.delete(unsavedNoteKey(lead));
  try {
    localStorage.removeItem(unsavedNoteKey(lead));
  } catch {}
}

/** The departments the signed-in person can put a lead in: active ones, and the one a
 * lead already has. Empty while the ERP site has none (or is too old), so the pickers stay out. */
export function usableDepartments(options: LeadOptions | undefined, keep = "") {
  return (options?.departments ?? []).filter(
    (d) => d.is_active || d.name === keep
  );
}

/** The department a new lead starts in: the only one the person belongs to. */
export function ownDepartment(options: LeadOptions | undefined) {
  const own = usableDepartments(options).filter(
    (d) => d.is_head || d.is_member
  );
  return own.length === 1 ? own[0].name : "";
}

/** "GrowthX · ERP / Software" for a lead's row; empty without a department. */
export function departmentLabel(row: LeadRow) {
  return [row.tbo_department, row.tbo_lead_type].filter(Boolean).join(" · ");
}

/** The bulk Set category choice that empties a field (an empty choice leaves it alone). */
export const CLEAR = "__clear__";

/** The category filters of the list; each is any of its values. */
export interface LeadCategories {
  industry: string[];
  state: string[];
  district: string[];
  org_size: string[];
}

/** "Resorts · Kozhikode" for a lead's row; empty without either. */
export function categoryLabel(row: LeadRow) {
  return [row.industry, row.district || row.state].filter(Boolean).join(" · ");
}

// each department's heads and members: the form prefers them as owner, Settings edits them
export const leadDepartments = createResource({
  url: "helpdesk.api.leads.get_lead_departments",
});

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

export type OverviewPeriod =
  | "today"
  | "yesterday"
  | "week"
  | "month"
  | "quarter"
  | "custom";

/** The numbers on the Overview that open their own list (TBO Smart's metrics). */
export type LeadMetric =
  | "new"
  // created in the period, imports left out: the "Created" filter and the intake strip
  | "intake"
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
  intake: __("Leads taken"),
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

/** helpdesk.api.leads.get_lead_intake: today's and yesterday's new leads by salesperson. */
export interface LeadIntake {
  /** false while the ERP site's TBO Smart is older than this */
  available: boolean;
  /** new leads each salesperson should take a day; 0: none */
  target?: number;
  days?: {
    date: string;
    total: number;
    by_owner: {
      user: string | null;
      full_name: string | null;
      count: number;
    }[];
  }[];
  /** the sales team, so someone who took none still shows */
  people?: { user: string; full_name: string }[];
  /** no enabled user has the Sales Employee role yet */
  team_empty?: boolean;
}

export type DailyMetric = "leads" | "meetings" | "proposals" | "follow_ups";

export interface DailyLeadRef {
  name: string;
  lead_name?: string | null;
  company_name?: string | null;
}

/** One salesperson's day and week (helpdesk.api.leads.get_daily_report). */
export interface DailyPerson {
  user: string;
  full_name: string;
  calls_total: number;
  calls_connected: number;
  fresh_leads: number;
  follow_up_leads: number;
  positive_leads: DailyLeadRef[];
  new_quotations: {
    count: number;
    value: number;
    items: {
      kind: "quotation" | "proposal";
      name: string;
      lead: string;
      lead_name?: string | null;
      value: number;
    }[];
  };
  meetings_held: number;
  follow_ups_done: number;
  follow_ups_overdue: number;
  new_leads: DailyLeadRef[];
  week_to_date: Record<DailyMetric, number>;
  /** each targeted metric's week so far against what the working days passed call for */
  pace: Partial<
    Record<
      DailyMetric,
      { actual: number; target: number; expected: number; behind: number }
    >
  >;
  behind: { metric: DailyMetric; by: number }[];
  on_track: boolean;
  /** the plain text to paste into WhatsApp */
  text: string;
}

export interface DailyReport {
  /** false while the ERP site's TBO Smart is older than this */
  available: boolean;
  date?: string;
  week_from?: string;
  currency?: string;
  people?: DailyPerson[];
  /** per day for leads, per week for the rest; 0: none */
  targets?: Record<DailyMetric, number>;
  working_days?: { elapsed: number; total: number };
  team_text?: string;
  /** no enabled user has the Sales Employee role yet */
  team_empty?: boolean;
}

/** The name a lead goes by in the report. */
export function leadTitle(lead: DailyLeadRef) {
  return lead.lead_name || lead.company_name || lead.name;
}

/** Copies `text`: the clipboard, else a hidden field; false when neither worked. */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const field = document.createElement("textarea");
    field.value = text;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.appendChild(field);
    field.select();
    try {
      return document.execCommand("copy");
    } catch {
      return false;
    } finally {
      field.remove();
    }
  }
}

/** helpdesk.api.leads.log_call: a call made outside MyOperator, logged on the lead. */
export function useLogCall() {
  return createResource({
    url: "helpdesk.api.leads.log_call",
    method: "POST",
  });
}

export type SplitStatus = "Received" | "Due" | "Overdue" | "Upcoming";

/** One payment split still being collected (TBO Smart's hub-leads-api.md §2.8). */
export interface MoneySplit {
  lead: string;
  lead_name?: string;
  company_name?: string;
  lead_owner?: string;
  owner_name?: string | null;
  document_type: "Sales Order" | "Quotation";
  document: string;
  quote_status?: string;
  idx: number;
  /** payment term, description or milestone; null: the whole amount */
  label: string | null;
  percent: number;
  amount: number;
  received: number;
  outstanding: number;
  /** null: when a milestone is reached */
  due_date: string | null;
  source: "schedule" | "quotation" | "proposal" | "whole";
  status: SplitStatus;
}

/** helpdesk.api.leads.get_proposal_money: the Overview's "Proposals & money". */
export interface ProposalMoney {
  available: boolean;
  currency?: string;
  totals?: {
    proposals_sent: number;
    proposals_value: number;
    unpriced_sent: number;
    won: number;
    won_value: number;
    advances: number;
    to_collect: number;
    overdue: number;
  };
  by_month?: {
    overdue: number;
    later: number;
    undated: number;
    months: { month: string; amount: number }[];
  };
  splits?: MoneySplit[];
  splits_total?: number;
}

/** helpdesk.api.leads.get_overview_page: the Overview, its money and the intake in one
 * request; a part that failed is null with its message in `errors`. */
export interface OverviewPage {
  overview: LeadOverview;
  money: ProposalMoney | null;
  intake: LeadIntake | null;
  errors: { money?: string; intake?: string };
}

export type BusinessPeriod =
  | "month"
  | "last_month"
  | "quarter"
  | "fy"
  | "custom";

export interface BusinessStage {
  stage: string;
  color: string;
  count: number;
  value: number;
}

export interface BusinessDepartment {
  /** null: leads with no department, or (with the label) money not traced to a lead */
  department: string | null;
  label: string;
  open: number;
  open_value: number;
  won: number;
  won_value: number;
  invoiced: number;
  collected: number;
}

/** helpdesk.api.leads.get_business_overview (TBO Smart's get_business_overview): the
 * company-wide figures, management only. Amounts are in `currency`. */
export interface BusinessOverview {
  available: boolean;
  period?: BusinessPeriod;
  from_date: string;
  to_date: string;
  department: string | null;
  currency: string;
  pipeline: {
    count: number;
    value: number;
    /** open leads without a quotation: no value */
    unpriced: number;
    /** false: lead stages have no probability, so the value is not weighted */
    weighted: boolean;
    stages: BusinessStage[];
  };
  proposals: {
    sent: { count: number; value: number; unpriced: number };
    accepted: { count: number; value: number };
    declined: number;
    acceptance_rate: number;
  };
  onboarding: {
    won: { count: number; value: number; unpriced: number };
    projects_started: number;
  };
  revenue: {
    invoiced: number;
    collected: number;
    outstanding: number;
    months: { month: string; invoiced: number; collected: number }[];
  };
  funnel: { step: string; count: number; rate: number }[];
  new_leads: number;
  meetings_held: number;
  trend: {
    month: string;
    new: number;
    won: number;
    invoiced: number;
    collected: number;
  }[];
  top_clients: { customer: string; name: string; invoiced: number }[];
  by_department: BusinessDepartment[];
  profit: {
    available: boolean;
    reason: string | null;
    income: number | null;
    expense: number | null;
    profit: number | null;
  };
}
