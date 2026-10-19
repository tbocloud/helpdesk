// Proposals to a lead live on the ERP site; helpdesk.api.proposals reads and writes
// them there as the signed-in person (docs/proposals.md, TBO Smart's
// hub-proposals-api.md).
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { createResource } from "frappe-ui";

export type ProposalStatus =
  | "Draft"
  | "Sent"
  | "Viewed"
  | "Accepted"
  | "Declined"
  | "Expired";

/**
 * The Universal IT Proposal's sections (TBO Smart's MASTER_SECTIONS), the project agreement's
 * own (Parties … Termination), plus Image and Custom.
 */
export type SectionType =
  | "Cover"
  | "Executive Summary"
  | "Company Overview"
  | "Client Background"
  | "Business Challenges"
  | "Proposed Solution"
  | "Scope of Work"
  | "Modules & Features"
  | "Proposed Workflow"
  | "Technical Architecture"
  | "Deliverables"
  | "Implementation Plan"
  | "Project Timeline"
  | "Project Team"
  | "Investment"
  | "Payment Terms"
  | "Warranty & Support"
  | "AMC"
  | "Assumptions"
  | "Out of Scope"
  | "Risks & Mitigation"
  | "Terms & Conditions"
  | "Acceptance"
  | "Parties"
  | "Purpose"
  | "Change Requests"
  | "Intellectual Property"
  | "Confidentiality"
  | "Termination"
  | "Image"
  | "Custom";

/** The client documents, one made from the accepted one before it (docs/proposals.md §Documents). */
export type DocumentTypeName = "Proposal" | "Quotation" | "Work Order";

/** A switched-on type of client document, as the ERP site describes it. */
export interface DocumentType {
  name: DocumentTypeName;
  /** "Project Agreement" for the work order */
  label: string;
  /** what Accepted reads as: "Signed" for the agreement */
  accepted_label: string;
  follows: DocumentTypeName | null;
  section_types: SectionType[];
  default_headings: Record<string, string>;
  ai_sections: SectionType[];
  /** its quotation is its price, edited and sent with it */
  priced: boolean;
  /** the client signs it with their designation */
  signature: boolean;
}

/** One step of the lead's chain of documents. */
export interface DocumentStep {
  document_type: DocumentTypeName;
  label: string;
  name: string | null;
  title: string | null;
  status: ProposalStatus | null;
  status_label: string | null;
  done: boolean;
  view_count: number;
  /** where its ERPNext Quotation is (a priced document's) */
  quotation_status: string | null;
}

/** The lead's documents in order and the one next action (get_lead's `documents`). */
export interface DocumentChain {
  steps: DocumentStep[];
  next: null | {
    action: "create_proposal" | "create" | "open";
    document_type: DocumentTypeName;
    label: string;
    /** create: the accepted document to make it from */
    source?: string;
    /** open: the document in progress */
    name?: string;
  };
}

/** Every section may carry an image but these two: the price and the signatures. */
export const NO_IMAGE: SectionType[] = ["Investment", "Acceptance"];
export const PRICING_SECTION: SectionType = "Investment";

/** Where each part starts, as the page and its contents show it. */
export const PART_STARTS: Partial<Record<SectionType, string>> = {
  "Executive Summary": __("Part A — Business Proposal"),
  "Scope of Work": __("Part B — Technical & Implementation Proposal"),
  Investment: __("Part C — Commercial Proposal"),
};

export interface ProposalSection {
  section_type: SectionType;
  /** 0: off (kept, but not on the page or the PDF) */
  enabled?: number;
  /** edited by hand: regenerating asks first */
  edited?: number;
  /** written by the AI (Regenerate); else built from the libraries (Reset to library) */
  ai?: boolean;
  rebuildable?: boolean;
  heading?: string | null;
  body?: string | null;
  /** a File of the proposal on the ERP site */
  image?: string | null;
  /** the token-gated link the preview loads it from */
  image_url?: string | null;
  image_alt?: string | null;
  image_caption?: string | null;
  image_size?: "Full" | "Half";
}

/** A letter head part: an image, or HTML sanitised on the ERP site and the hub. */
export interface LetterHeadPart {
  image?: string;
  align?: "left" | "center" | "right";
  html?: string;
}

export interface LetterHeadPreview {
  name: string;
  header: LetterHeadPart | null;
  footer: LetterHeadPart | null;
}

export interface TemplateSection extends ProposalSection {
  guidance?: string | null;
}

export interface ProposalTemplate {
  name: string;
  template_name: string;
  solution_type?: string | null;
  description?: string | null;
  enabled: number;
  page_guide?: string | null;
  /** the scoping questions this template asks (QUESTIONS keys) */
  questions: string[];
  default_modules: string[];
  sections: TemplateSection[];
  packages: string[];
}

/** The scoping form's questions, in order. */
export const QUESTIONS = [
  "modules",
  "customisation",
  "mobile_app",
  "web_app",
  "integrations",
  "data_migration",
  "users",
  "hosting",
  "amc",
  "timeline_weeks",
  "source_code",
  "architecture",
] as const;
export type Question = (typeof QUESTIONS)[number];

export const QUESTION_LABELS: Record<Question, string> = {
  modules: __("Modules"),
  customisation: __("Customisations"),
  mobile_app: __("Mobile app"),
  web_app: __("Web app"),
  integrations: __("Integrations"),
  data_migration: __("Data migration"),
  users: __("Number of users"),
  hosting: __("Hosting"),
  amc: __("AMC"),
  timeline_weeks: __("Target timeline"),
  source_code: __("Source code handed over"),
  architecture: __("Architecture detail"),
};

export interface Customisation {
  item: string;
  days: number;
  /** what the AI wrote about it, editable */
  detail?: string | null;
}

export interface Scoping {
  modules: string[];
  customisation: boolean;
  customisations: Customisation[];
  mobile_app: boolean;
  web_app: boolean;
  integrations: string;
  data_migration: boolean;
  users: number;
  hosting: string | null;
  amc: boolean;
  timeline_weeks: number;
  source_code: boolean;
  architecture: "Simple" | "Detailed";
  /** the templates picked at the start (blank: suggested timeline, first payment terms) */
  timeline_template?: string | null;
  payment_terms?: string | null;
  amc_plan?: string | null;
}

/** Who the client is: presales confirms it before a proposal is generated. */
export interface ClientProfile {
  name: string;
  website: string;
  about: string;
  industry: string;
  size: string;
  locations: string;
  current_software: string;
  key_processes: string;
  pain_points: string;
}

export function emptyProfile(): ClientProfile {
  return {
    name: "",
    website: "",
    about: "",
    industry: "",
    size: "",
    locations: "",
    current_software: "",
    key_processes: "",
    pain_points: "",
  };
}

export function emptyScoping(): Scoping {
  return {
    modules: [],
    customisation: false,
    customisations: [],
    mobile_app: false,
    web_app: false,
    integrations: "",
    data_migration: false,
    users: 0,
    hosting: null,
    amc: false,
    timeline_weeks: 0,
    source_code: false,
    architecture: "Simple",
    timeline_template: null,
    payment_terms: null,
    amc_plan: null,
  };
}

/**
 * The shortest timeline template that fits the effort: about 1.6 calendar days a person-day of
 * module and customisation effort, or the client's target if longer (as the ERP site suggests).
 */
export function suggestTimeline(
  timelines: { title: string; days: number }[],
  scoping: Scoping,
  catalogue: CatalogueModule[]
): string | null {
  if (!timelines.length) return null;
  const effort =
    scoping.modules.reduce(
      (sum, name) =>
        sum + (catalogue.find((c) => c.module_name === name)?.effort_days || 0),
      0
    ) + scoping.customisations.reduce((sum, c) => sum + (Number(c.days) || 0), 0);
  const needed = Math.max(effort * 1.6, (scoping.timeline_weeks || 0) * 7);
  const sorted = [...timelines].sort((a, b) => a.days - b.days);
  return (sorted.find((t) => t.days >= needed) || sorted[sorted.length - 1]).title;
}

/** A module in the catalogue, written once and assembled into every proposal. */
export interface CatalogueModule {
  name: string;
  module_name: string;
  solution_types?: string | null;
  description?: string | null;
  features?: string | null;
  effort_days: number;
  default_price: number;
  item?: string | null;
  fit?: string | null;
}

/** A module included in a proposal: its own copy, edited without touching the catalogue. */
export interface ProposalModule {
  module?: string | null;
  module_name: string;
  fit: "Standard" | "Configured" | "Customised";
  features?: string | null;
  description?: string | null;
  effort_days: number;
  rate: number;
  rate_overridden: number;
  item?: string | null;
}

export interface LibraryImage {
  name: string;
  title: string;
  alt_text: string;
  sections: string[];
  solution_types: string[];
  url: string | null;
}

export interface ProposalOptions {
  enabled: boolean;
  ai?: boolean;
  can_edit_templates?: boolean;
  templates?: ProposalTemplate[];
  packages?: string[];
  section_types?: SectionType[];
  default_headings?: Record<string, string>;
  ai_sections?: SectionType[];
  pricing_modes?: string[];
  questions?: string[];
  hosting?: string[];
  /** the client profile fields presales must fill */
  profile_required?: string[];
  timelines?: { title: string; days: number }[];
  payment_terms?: string[];
  amc_plans?: string[];
  catalogue?: CatalogueModule[];
  images?: LibraryImage[];
  letter_heads?: { name: string; is_default: number }[];
  /** what a proposal without its own pick uses; null: the site has none */
  default_letter_head?: string | null;
  /** TBO Smart Settings → Proposal letter head; null: the one marked default */
  proposal_letter_head?: string | null;
  /** the switched-on client document types, in the chain's order */
  document_types?: DocumentType[];
}

/** A row of the lead's proposals (get_lead's `proposals`). */
export interface ProposalRow {
  name: string;
  document_type?: DocumentTypeName;
  title: string;
  status: ProposalStatus;
  revision_no: number;
  is_latest: number;
  sent_on?: string | null;
  view_count?: number | null;
  last_viewed_on?: string | null;
  decided_on?: string | null;
  modified?: string;
}

export interface QuotationLine {
  item_code: string;
  item_name?: string;
  qty: number;
  price_list_rate: number;
  discount_percentage: number;
  description?: string | null;
  amount?: number;
}

export interface ApprovalNeed {
  kind: string;
  percent: number;
  /** null: no limit; 0: not set */
  limit: number | null;
}

export interface ProposalQuotation {
  name: string;
  docstatus: number;
  currency: string;
  quote_status?: string;
  revision?: number;
  items: QuotationLine[];
  total: number;
  discount_amount: number;
  net_total: number;
  total_taxes_and_charges: number;
  grand_total: number;
  additional_discount_percentage: number;
  taxes_and_charges?: string | null;
  valid_till?: string | null;
  needs_approval: ApprovalNeed[];
}

export interface SegmentPricing {
  segment?: string | null;
  price_list?: string | null;
  /** the discount anyone may give without approval; null: none */
  discount_band?: number | null;
}

export interface Proposal {
  name: string;
  document_type: DocumentTypeName;
  /** "Proposal", "Quotation", "Project Agreement" */
  document_label: string;
  accepted_label: string;
  /** the accepted document it was made from */
  source_document?: string | null;
  /** priced here (a proposal or a quotation); else it shows the accepted price */
  can_price: boolean;
  /** the client signs with a designation (the agreement) */
  signature: boolean;
  /** the agreement's project start: the timeline's dates follow from it */
  start_date?: string | null;
  title: string;
  lead: string;
  lead_name?: string;
  /** the lead's company, else its name: what the client's page calls them */
  client: string;
  lead_email?: string | null;
  template?: string | null;
  solution_type?: string | null;
  page_guide?: string | null;
  prepared_by?: string | null;
  status: ProposalStatus;
  pricing_mode: "Itemised" | "Consolidated";
  scoping: Scoping;
  requirements?: string | null;
  client_profile: ClientProfile;
  /** the assistant's transcript (kept; never sent to the AI) */
  chat: { role: "assistant" | "presales"; text: string; at?: string }[];
  modules: ProposalModule[];
  /** the proposal's own letter head; null: the default */
  letter_head?: string | null;
  letter_head_preview?: LetterHeadPreview | null;
  valid_till?: string | null;
  sections: ProposalSection[];
  quotation: ProposalQuotation | null;
  pricing: SegmentPricing;
  public_url: string | null;
  preview_url: string;
  revision_no: number;
  is_latest: number;
  revisions: {
    name: string;
    revision_no: number;
    status: ProposalStatus;
    is_latest: number;
  }[];
  tracking: {
    sent_on?: string | null;
    sent_to?: string | null;
    first_viewed_on?: string | null;
    last_viewed_on?: string | null;
    view_count?: number | null;
    decided_on?: string | null;
    decided_by_name?: string | null;
    decided_by_email?: string | null;
    decided_by_designation?: string | null;
    decline_reason?: string | null;
  };
  can_write: boolean;
  /** why Send is off now, in words; empty when it can be sent */
  send_blockers: string[];
  /** the same without the email account: why Share link is off */
  share_blockers: string[];
  /** the AI's runs and cost on this proposal, for editors only */
  ai: {
    runs: number;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
    estimate_tokens: number;
    daily_limit: number;
  } | null;
}

/** The quotation builder's catalogue (TBO Smart's get_quotation_form). */
export interface PricingForm {
  catalogue: {
    packages: {
      name: string;
      package_name: string;
      items: {
        item_code: string;
        description?: string | null;
        qty: number;
        rate: number;
      }[];
    }[];
    services: {
      item_code: string;
      item_name: string;
      item_group?: string;
      rate: number;
    }[];
  };
  pricing: SegmentPricing;
  tax_templates: string[];
  tax_rates: Record<string, number>;
  currency?: string | null;
  valid_till?: string | null;
  taxes_and_charges?: string | null;
  additional_discount_percentage?: number;
  items: QuotationLine[];
}

export const SECTION_LABELS: Record<SectionType, string> = {
  Cover: __("Cover"),
  "Executive Summary": __("Executive Summary"),
  "Company Overview": __("Company Overview"),
  "Client Background": __("Client Background & Business Understanding"),
  "Business Challenges": __("Business Challenges"),
  "Proposed Solution": __("Proposed Solution"),
  "Scope of Work": __("Scope of Work"),
  "Modules & Features": __("Functional Modules & Features"),
  "Proposed Workflow": __("Proposed Workflow"),
  "Technical Architecture": __("Technical Architecture"),
  Deliverables: __("Project Deliverables"),
  "Implementation Plan": __("Implementation Plan"),
  "Project Timeline": __("Project Timeline"),
  "Project Team": __("Project Team & Responsibilities"),
  Investment: __("Investment"),
  "Payment Terms": __("Payment Terms"),
  "Warranty & Support": __("Warranty & Post-Implementation Support"),
  AMC: __("Annual Maintenance Contract (AMC)"),
  Assumptions: __("Assumptions & Dependencies"),
  "Out of Scope": __("Out of Scope"),
  "Risks & Mitigation": __("Risks & Mitigation"),
  "Terms & Conditions": __("Terms & Conditions"),
  Acceptance: __("Acceptance & Approval"),
  Parties: __("Parties"),
  Purpose: __("Purpose of this Agreement"),
  "Change Requests": __("Change Request Process"),
  "Intellectual Property": __("Intellectual Property & Source Code"),
  Confidentiality: __("Confidentiality"),
  Termination: __("Termination"),
  Image: __("Image"),
  Custom: __("Custom"),
};

/** Accepted is done, Declined and Expired ended badly, Viewed is news; the rest neutral. */
export function proposalTone(status?: ProposalStatus): Tone {
  if (status === "Accepted") return "success";
  if (status === "Declined" || status === "Expired") return "danger";
  if (status === "Viewed") return "info";
  return "neutral";
}

/** A document's type from the options (null until they load or while it is switched off). */
export function documentType(
  options: ProposalOptions | undefined,
  name: DocumentTypeName | undefined
): DocumentType | null {
  return options?.document_types?.find((t) => t.name === name) ?? null;
}

/** Fetched once per session: whether proposals are on, templates, catalogue, block types. */
export const proposalOptions = createResource({
  url: "helpdesk.api.proposals.get_proposal_options",
  cache: "hd-proposal-options",
});

// the cached copy shows at once, but it is fetched again once per page load: a setting
// changed on the ERP site (e.g. Proposals switched on) must show without clearing the browser
let proposalOptionsFetched = false;
export function loadProposalOptions() {
  if (proposalOptionsFetched || proposalOptions.loading) return;
  proposalOptionsFetched = true;
  proposalOptions.fetch();
}

/** A catalogue module (or a library row) suits a solution type when it names none. */
export function suits(
  types: string | null | undefined,
  solution?: string | null
): boolean {
  const list = (types || "")
    .split("\n")
    .map((t) => t.trim())
    .filter(Boolean);
  return !list.length || !solution || list.includes(solution);
}

export type TextPart =
  | { kind: "text"; lines: string[] }
  | { kind: "list"; items: string[] }
  | { kind: "heading"; text: string }
  | { kind: "table"; header: string[]; rows: string[][] }
  | { kind: "chain"; steps: string[] };

/**
 * Plain text as the client's page lays it out (TBO Smart's text_parts): a blank line starts a
 * part; "## " a subheading; lines starting "- " a list; lines with " | " a table (the first its
 * header); a line with " → " a chain of steps; anything else a paragraph.
 */
export function textParts(body?: string | null): TextPart[] {
  const parts: TextPart[] = [];
  for (const chunk of (body || "").trim().split(/\n\s*\n/)) {
    const lines = chunk
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    while (lines.length && lines[0].startsWith("## "))
      parts.push({ kind: "heading", text: lines.shift()!.slice(3).trim() });
    if (!lines.length) continue;
    if (lines.every((l) => l.startsWith("- ") || l.startsWith("• ")))
      parts.push({ kind: "list", items: lines.map((l) => l.slice(2).trim()) });
    else if (lines.length > 1 && lines.every((l) => l.includes(" | "))) {
      const rows = lines.map((l) => l.split(" | ").map((c) => c.trim()));
      parts.push({ kind: "table", header: rows[0], rows: rows.slice(1) });
    } else if (lines.length === 1 && lines[0].includes(" → "))
      parts.push({
        kind: "chain",
        steps: lines[0]
          .split("→")
          .map((s) => s.trim())
          .filter(Boolean),
      });
    else parts.push({ kind: "text", lines });
  }
  return parts;
}

function words(text: string) {
  return text.split(/\s+/).filter(Boolean).length;
}

/**
 * About how many A4 pages the PDF runs to: the cover and the contents, then the words (about
 * 380 a page) and the table rows (about 22 a page) of the sections that are on. A guide, not a
 * promise: the PDF itself is the count.
 */
export function estimatePages(sections: ProposalSection[]): number {
  let text = 0;
  let rows = 0;
  for (const s of sections) {
    if (!(s.enabled ?? 1) || s.section_type === "Cover") continue;
    text += 30;
    for (const part of textParts(s.body)) {
      if (part.kind === "table") rows += part.rows.length + 1;
      else if (part.kind === "list")
        text += words(part.items.join(" ")) + 4 * part.items.length;
      else if (part.kind === "text") text += words(part.lines.join(" "));
      else text += 12;
    }
    if (s.section_type === "Investment") rows += 10;
    if (s.section_type === "Acceptance") text += 150;
  }
  return 2 + Math.max(1, Math.ceil(text / 380 + rows / 22));
}
