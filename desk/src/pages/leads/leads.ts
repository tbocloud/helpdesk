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

/** One entry of a lead's timeline: a note, a stage move, a call or an edit. */
export interface LeadTimelineEntry {
  name?: string;
  type?: string;
  note?: string;
  content?: string;
  from_stage?: string;
  to_stage?: string;
  owner?: string;
  owner_name?: string;
  creation?: string;
}

export interface LeadQuotation {
  name: string;
  transaction_date?: string;
  valid_till?: string;
  status?: string;
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
