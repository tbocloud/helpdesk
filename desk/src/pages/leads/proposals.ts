// Proposals to a lead live on the ERP site; helpdesk.api.proposals reads and writes
// them there as the signed-in person (docs/proposals.md, TBO Smart's
// hub-proposals-api.md).
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { createResource, toast } from "frappe-ui";

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
  | "Business Objectives"
  | "Stakeholders"
  | "Current Process"
  | "Pain Points"
  | "Desired Process"
  | "Business Rules"
  | "Reports Needed"
  | "Integrations"
  | "Data Migration"
  | "Success Criteria"
  | "Constraints"
  | "Open Questions"
  | "Introduction"
  | "User Roles"
  | "Module Specification"
  | "Non-functional Requirements"
  | "Plan Overview"
  | "Phase Deliverables"
  | "RACI Matrix"
  | "Client Responsibilities"
  | "Image"
  | "Custom";

/** The client documents, one made from the accepted one before it (docs/proposals.md §Documents). */
export type DocumentTypeName =
  | "Proposal"
  | "Quotation"
  | "Work Order"
  | "BRD"
  | "SRS"
  | "Implementation Plan";

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
  /** the client answers questions on their own page (the BRD) */
  questionnaire: boolean;
}

/** A question for the client on a BRD's questionnaire page. */
export interface DocumentQuestion {
  name?: string;
  section_type: SectionType | null;
  question: string;
  answer?: string | null;
  answered_on?: string | null;
  /** the BRD was rebuilt with this answer */
  applied?: number;
  asked_by?: "Library" | "AI" | "Presales";
}

/** A BRD's questionnaire: its questions and the client link's state. */
export interface Questionnaire {
  questions: DocumentQuestion[];
  /** null until it is shared */
  url: string | null;
  open: boolean;
  sent_on?: string | null;
  answered_on?: string | null;
  /** answers not in the BRD yet */
  new_answers: number;
}

/** Skipped: this client doesn't need the step. Not used: the chain started after it. */
export type StepSkipStatus = "Skipped" | "Not used";
/** a proposal made and sent by hand, recorded with the file that went */
export const SENT_OUTSIDE = "Sent outside";

/** What the signed-in person may do with a step (the ERP site decides). */
export type StepAction = "open" | "create" | "skip" | "bring_back";

/** One step of the lead's chain of documents (after the plan: its project and the UAT). */
export interface DocumentStep {
  document_type: DocumentTypeName | "Project" | "UAT";
  label: string;
  name: string | null;
  title: string | null;
  /** the step's status: its document's, or Skipped / Not used / Sent outside */
  status:
    | ProposalStatus
    | StepSkipStatus
    | typeof SENT_OUTSIDE
    | "Created"
    | null;
  status_label: string | null;
  /** the document's own status, whatever the step shows */
  document_status?: ProposalStatus | null;
  done: boolean;
  view_count: number;
  /** where its ERPNext Quotation is (a priced document's) */
  quotation_status: string | null;
  /** the project's link (the Project step) */
  url?: string | null;
  /** skipped, marked not used or sent outside: who, when and why */
  skipped?: null | {
    status: StepSkipStatus | typeof SENT_OUTSIDE;
    reason: string;
    by: string;
    by_name: string | null;
    on: string;
    /** sent outside: the lead's file that went, while it is still on the lead */
    file?: string | null;
    file_name?: string | null;
  };
  /** shown Not used because a later step started; nothing is recorded yet */
  implicit?: boolean;
  actions?: StepAction[];
  /** making it: the accepted document it is made from (null: from the lead) */
  source?: string | null;
  /** it is the next step (anything else is out of order) */
  in_order?: boolean;
  /** why it can't be made now, in words */
  create_refused?: string | null;
}

/** The lead's documents in order and the one next action (get_lead's `documents`). */
export interface DocumentChain {
  steps: DocumentStep[];
  next: null | {
    action: "create_proposal" | "create" | "open" | "create_project" | "uat";
    document_type: DocumentStep["document_type"];
    label: string;
    /** create: the accepted document to make it from (null: from the lead) */
    source?: string | null;
    /** create_project: "Proposal" when the project comes from an accepted strategy
     *  proposal (Content / Digital Marketing leads), "Lead" when the steps before it
     *  were skipped, else an implementation plan */
    source_type?: "Proposal" | "Implementation Plan" | "Lead";
    /** open: the document in progress; uat: the project */
    name?: string;
  };
  /** the lead is lost: nothing moves, and this says why */
  blocked?: string | null;
  /** may skip, bring back and work out of order (the lead's owner, a head, a manager) */
  can_steer?: boolean;
  /** why nothing is next while a step is still to do */
  note?: string | null;
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
  "branches",
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
  branches: __("Additional branches"),
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
  /** a price set by hand; blank: priced by its days at the ERP site's day rate */
  price?: number | null;
}

export interface Scoping {
  modules: string[];
  customisation: boolean;
  customisations: Customisation[];
  mobile_app: boolean;
  web_app: boolean;
  integrations: string;
  data_migration: boolean;
  /** a number (0: not said) or "Unlimited" */
  users: number | "Unlimited";
  companies: number | "Unlimited";
  /** branches rolled out beyond the head office and the first one, each priced at the branch rate */
  branches: number;
  /** a price per branch set on the proposal; blank: the ERP site's branch rate */
  branch_rate?: number | null;
  hosting: string | null;
  amc: boolean;
  timeline_weeks: number;
  source_code: boolean;
  architecture: "Simple" | "Detailed";
  /** the templates picked at the start (blank: suggested timeline, first payment terms) */
  timeline_template?: string | null;
  /** a custom period in calendar days, over the template (0: none) */
  timeline_days: number;
  payment_terms?: string | null;
  /** this proposal's own milestones (adding up to 100%), over the template; none: the template */
  payment_milestones: PaymentMilestone[];
  amc_plan?: string | null;
  /** how the quotation prices the modules (the Price card): a line each, per app, or one */
  price_basis: PriceBasis;
  /** by App, the price per app; an app not in it is its modules' prices added up */
  app_prices: Partial<Record<PriceGroup, number>>;
  /** by Custom, the one price for all the modules; null is their prices added up */
  custom_price: number | null;
}

export interface PaymentMilestone {
  label: string;
  /** in %, the milestones adding up to 100 */
  share: number;
}

/** As many milestones as the ERP site keeps. */
export const MAX_MILESTONES = 12;

export function milestoneTotal(milestones: PaymentMilestone[]) {
  return (
    Math.round(
      milestones.reduce((sum, m) => sum + (Number(m.share) || 0), 0) * 100
    ) / 100
  );
}

export function addsUp(milestones: PaymentMilestone[]) {
  return milestoneTotal(milestones) === 100;
}

/** A payment terms template's text ("Milestone | 30" a line) as milestones, and back. */
export function parseMilestones(body?: string | null): PaymentMilestone[] {
  return (
    (body || "")
      .split("\n")
      .map((l) => l.split("|"))
      .map(([label, share]) => ({
        label: (label || "").trim(),
        share: Number(
          String(share ?? "")
            .replace("%", "")
            .trim()
        ),
      }))
      // a header row ("Milestone | Share") has no number
      .filter((m) => m.label && Number.isFinite(m.share) && m.share > 0)
  );
}

export function milestonesBody(milestones: PaymentMilestone[]) {
  return milestones.map((m) => `${m.label.trim()} | ${m.share}`).join("\n");
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
    companies: 0,
    branches: 0,
    branch_rate: null,
    hosting: null,
    amc: false,
    timeline_weeks: 0,
    source_code: false,
    architecture: "Simple",
    timeline_template: null,
    timeline_days: 0,
    payment_terms: null,
    payment_milestones: [],
    amc_plan: null,
    price_basis: "Module",
    app_prices: {},
    custom_price: null,
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
    ) +
    scoping.customisations.reduce((sum, c) => sum + (Number(c.days) || 0), 0);
  const needed = Math.max(effort * 1.6, (scoping.timeline_weeks || 0) * 7);
  const sorted = [...timelines].sort((a, b) => a.days - b.days);
  return (sorted.find((t) => t.days >= needed) || sorted[sorted.length - 1])
    .title;
}

/**
 * The start page's implementation type (docs/proposals.md "Implementation type"): ERP is always
 * ERPNext, with any mix of a mobile app, a website and customisations; Digital is the Digital
 * Marketing strategy. Each maps onto the templates and catalogue modules the ERP site seeds.
 */
export type Implementation = "ERP" | "Digital";
export type ErpAddon = "mobile" | "website" | "customisation";
export const IMPLEMENTATION_LABELS: Record<Implementation, string> = {
  ERP: __("ERP"),
  Digital: __("Digital Marketing"),
};
export const ERP_ADDONS: { label: string; value: ErpAddon }[] = [
  { label: __("Mobile app"), value: "mobile" },
  { label: __("Website"), value: "website" },
  { label: __("ERPNext customisation"), value: "customisation" },
];

const ERP_SOLUTION = "ERPNext Implementation";
const ERP_MOBILE_SOLUTION = "ERPNext + Flutter Mobile App";
const DIGITAL_SOLUTION = "Digital Marketing";
export const MOBILE_MODULE = "Flutter Mobile App";
export const WEBSITE_MODULE = "Website & Portal";

export function implementationOf(
  solution?: string | null
): Implementation | null {
  if (solution === ERP_SOLUTION || solution === ERP_MOBILE_SOLUTION)
    return "ERP";
  if (solution?.startsWith(DIGITAL_SOLUTION)) return "Digital";
  return null;
}

function templateFor(
  templates: ProposalTemplate[],
  kind: Implementation,
  mobile = false
): ProposalTemplate | undefined {
  if (kind === "Digital")
    return templates.find((t) => implementationOf(t.solution_type) === kind);
  const wanted = mobile ? ERP_MOBILE_SOLUTION : ERP_SOLUTION;
  return (
    templates.find((t) => t.solution_type === wanted) ||
    templates.find((t) => t.solution_type === ERP_SOLUTION)
  );
}

/** The implementation types the enabled templates allow, in the picker's order. */
export function implementations(
  templates: ProposalTemplate[]
): Implementation[] {
  return (["ERP", "Digital"] as const).filter((k) => templateFor(templates, k));
}

export function erpAddons(scoping: Scoping): ErpAddon[] {
  const on: ErpAddon[] = [];
  if (scoping.mobile_app || scoping.modules.includes(MOBILE_MODULE))
    on.push("mobile");
  if (scoping.modules.includes(WEBSITE_MODULE)) on.push("website");
  if (scoping.customisation || scoping.customisations.length)
    on.push("customisation");
  return on;
}

export type ImplementationChoice = { template: string; scoping: Scoping };

/** Another implementation type: its template, with that template's default modules. */
export function withImplementation(
  kind: Implementation,
  scoping: Scoping,
  templates: ProposalTemplate[]
): ImplementationChoice | null {
  const template = templateFor(templates, kind);
  if (!template) return null;
  return {
    template: template.name,
    scoping: {
      ...scoping,
      modules: [...template.default_modules],
      mobile_app: false,
      customisation: false,
      customisations: [],
    },
  };
}

/** An ERP add-on on or off: the mobile app also moves between the two ERPNext templates. */
export function withAddon(
  addon: ErpAddon,
  on: boolean,
  current: ImplementationChoice,
  templates: ProposalTemplate[]
): ImplementationChoice {
  const scoping = { ...current.scoping };
  const toggle = (name: string) => {
    const rest = scoping.modules.filter((m) => m !== name);
    scoping.modules = on ? [...rest, name] : rest;
  };
  let template = current.template;
  if (addon === "mobile") {
    scoping.mobile_app = on;
    toggle(MOBILE_MODULE);
    template = templateFor(templates, "ERP", on)?.name || template;
  } else if (addon === "website") {
    toggle(WEBSITE_MODULE);
  } else {
    scoping.customisation = on;
    scoping.customisations = on
      ? scoping.customisations.length
        ? scoping.customisations
        : [{ item: "", days: 1 }]
      : [];
  }
  return { template, scoping };
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

/**
 * How the quotation prices the modules (kept in the scoping, priced by the ERP site): a line per
 * module, a line per app (ERPNext, Mobile app, Website), or one line for them all.
 */
export type PriceBasis = "Module" | "App" | "Custom";
export type PriceGroup = "main" | "mobile" | "website";

/** The modules by app, in the Price card's order (as the ERP site groups them); an app with none is left out. */
export function priceGroups(modules: string[]) {
  return (
    [
      {
        key: "main",
        names: modules.filter(
          (m) => m !== MOBILE_MODULE && m !== WEBSITE_MODULE
        ),
      },
      { key: "mobile", names: modules.filter((m) => m === MOBILE_MODULE) },
      { key: "website", names: modules.filter((m) => m === WEBSITE_MODULE) },
    ] as { key: PriceGroup; names: string[] }[]
  ).filter((g) => g.names.length);
}

/** What the Price card calls the main app: the modules other than the mobile app and the website. */
export function mainAppLabel(solution?: string | null) {
  const kind = implementationOf(solution);
  return kind === "ERP"
    ? __("ERPNext")
    : kind === "Digital"
    ? __("Digital Marketing")
    : __("Modules");
}

/**
 * Says so when the ERP site didn't keep a choice sent in the scoping (the price by app or one
 * price, a custom timeline period, custom payment milestones): it runs a TBO Smart without them
 * and drops what it doesn't know, so the proposal falls back to module prices and the templates.
 */
export function warnDropped(sent: Scoping, kept?: Partial<Scoping> | null) {
  const k = kept || {};
  const dropped = [
    sent.price_basis !== "Module" && k.price_basis !== sent.price_basis
      ? __("the price by app or custom price")
      : "",
    sent.timeline_days && !k.timeline_days
      ? __("the custom timeline period")
      : "",
    sent.payment_milestones?.length && !k.payment_milestones?.length
      ? __("the custom payment milestones")
      : "",
  ].filter(Boolean);
  if (dropped.length)
    toast.warning(
      __(
        "The ERP site didn't keep {0}: it needs the TBO Smart update. Until then the proposal uses the module prices and the templates.",
        dropped.join(", ")
      )
    );
}

export function listPrice(catalogue: CatalogueModule[], name: string) {
  return catalogue.find((m) => m.module_name === name)?.default_price || 0;
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
  /** the ERP site's default currency (older sites don't send it: INR) */
  currency?: string | null;
  /** TBO Smart Settings' branch rate (0 or missing: not set) */
  branch_rate?: number | null;
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
  /** staff only: the ERPNext Quotation's desk form (the client never sees its number) */
  desk_url?: string | null;
  /** each tax line as the client's page shows it ("GST 18%") */
  taxes?: { label: string; amount: number }[];
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
  /** what its cover calls it ("Business Requirements Document") */
  kicker: string;
  accepted_label: string;
  /** the accepted document it was made from */
  source_document?: string | null;
  /** priced here (a proposal or a quotation); else it shows the accepted price */
  can_price: boolean;
  /** the client signs with a designation (the agreement) */
  signature: boolean;
  /** its dates follow from the start date (the agreement, the plan) */
  dated: boolean;
  /** the agreement's or the plan's start: the dates follow from it */
  start_date?: string | null;
  /** the BRD's questions for the client */
  questionnaire: Questionnaire | null;
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
  /** marked ready to send: the content and numbers are fixed until reopened */
  ready_on?: string | null;
  /** a save's: why the quotation couldn't be priced again */
  warnings?: string[];
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
  /** a revision made after the client asked for changes on the version before */
  changes_asked?: null | {
    name: string;
    reason: string | null;
    by: string | null;
    on: string | null;
  };
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
  "Business Objectives": __("Business Objectives"),
  Stakeholders: __("Stakeholders"),
  "Current Process": __("Current Process (As-Is)"),
  "Pain Points": __("Pain Points"),
  "Desired Process": __("Desired Process (To-Be)"),
  "Business Rules": __("Business Rules"),
  "Reports Needed": __("Reports Needed"),
  Integrations: __("Integrations"),
  "Data Migration": __("Data Migration"),
  "Success Criteria": __("Success Criteria"),
  Constraints: __("Constraints"),
  "Open Questions": __("Open Questions"),
  Introduction: __("Introduction"),
  "User Roles": __("User Roles & Permissions"),
  "Module Specification": __("Module Specification"),
  "Non-functional Requirements": __("Non-functional Requirements"),
  "Plan Overview": __("Plan Overview"),
  "Phase Deliverables": __("Deliverables by Phase"),
  "RACI Matrix": __("RACI Matrix"),
  "Client Responsibilities": __("Client Responsibilities"),
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
  | { kind: "chain"; steps: string[] }
  | { kind: "callout"; title: string; tag: string; lines: string[] };

/**
 * Plain text as the client's page lays it out (TBO Smart's text_parts): a blank line starts a
 * part; "## " a subheading; lines starting "- " a list; lines with " | " a table (the first its
 * header); a line with " → " a chain of steps; lines starting "> " a highlight (its first line
 * the title, "title | tag" for a tag); anything else a paragraph.
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
    if (lines.every((l) => l.startsWith(">"))) {
      const said = lines.map((l) => l.replace(/^>\s*/, ""));
      const [title, ...tag] = said[0].split(" | ");
      parts.push({
        kind: "callout",
        title: title.trim(),
        tag: tag.join(" | ").trim(),
        lines: said.slice(1),
      });
    } else if (lines.every((l) => l.startsWith("- ") || l.startsWith("• ")))
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

/** The client document's accents in turn (TBO Smart's .t0–.t3): teal, green, orange, red. */
export const DOC_TONES = ["#3a748d", "#0b7d6b", "#e8962a", "#c4452f"];
/** Each accent dark enough for text on white (4.5:1). */
export const DOC_TONE_INK = ["#2c5d72", "#0b7d6b", "#a85a0c", "#b03a26"];

type Toned = { tone: number };
export type DrawnPart =
  | TextPart
  | {
      kind: "stats";
      items: ({ figure: string; label: string; detail: string } & Toned)[];
    }
  | { kind: "cards"; items: ({ title: string; text: string } & Toned)[] }
  | {
      kind: "numbered";
      items: { number: number; title: string; text: string }[];
    };

const SHORT_TEXT = 240;

function leadAndText(item: string) {
  const at = item.indexOf(": ");
  return at > 0 && at <= 60
    ? { title: item.slice(0, at).trim(), text: item.slice(at + 2).trim() }
    : { title: item, text: "" };
}

/**
 * As TBO Smart's draw_parts: a "Figure | label | detail" table as big-number tiles; two or more
 * short subsections in a row as cards; the deliverables as cards; out of scope and assumptions as
 * numbered rows with their lead words in bold.
 */
export function drawParts(parts: TextPart[], sectionType: string): DrawnPart[] {
  const short = (i: number) => {
    const head = parts[i];
    const body = parts[i + 1];
    return (
      head?.kind === "heading" &&
      body?.kind === "text" &&
      body.lines.join(" ").length <= SHORT_TEXT &&
      (i + 2 >= parts.length || parts[i + 2].kind === "heading")
    );
  };
  const drawn: DrawnPart[] = [];
  let i = 0;
  while (i < parts.length) {
    const part = parts[i];
    if (
      part.kind === "table" &&
      ["Figure", __("Figure")].includes(part.header[0]?.trim())
    ) {
      drawn.push({
        kind: "stats",
        items: part.rows
          .filter((r) => r[0])
          .map((r, k) => ({
            figure: r[0],
            label: r[1] || "",
            detail: r[2] || "",
            tone: k % DOC_TONES.length,
          })),
      });
    } else if (short(i)) {
      const cards: { title: string; text: string }[] = [];
      const from = i;
      while (short(i)) {
        const head = parts[i] as { text: string };
        const body = parts[i + 1] as { lines: string[] };
        cards.push({ title: head.text, text: body.lines.join(" ") });
        i += 2;
      }
      if (cards.length > 1)
        drawn.push({
          kind: "cards",
          items: cards.map((c, k) => ({ ...c, tone: k % DOC_TONES.length })),
        });
      else drawn.push(...parts.slice(from, i));
      continue;
    } else if (part.kind === "list" && sectionType === "Deliverables") {
      drawn.push({
        kind: "cards",
        items: part.items.map((item, k) => ({
          ...leadAndText(item),
          tone: k % DOC_TONES.length,
        })),
      });
    } else if (
      part.kind === "list" &&
      ["Out of Scope", "Assumptions"].includes(sectionType)
    ) {
      drawn.push({
        kind: "numbered",
        items: part.items.map((item, k) => ({
          number: k + 1,
          ...leadAndText(item),
        })),
      });
    } else drawn.push(part);
    i++;
  }
  return drawn;
}

function words(text: string) {
  return text.split(/\s+/).filter(Boolean).length;
}

/**
 * About how many A4 pages the PDF runs to: the cover with the contents (one page), then the
 * words (about 450 a page in the compact layout) and the table rows (about 26 a page) of the
 * sections that are on. A guide, not a promise: the PDF itself is the count.
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
      else if (part.kind === "callout")
        text += words([part.title, ...part.lines].join(" "));
      else text += 12;
    }
    if (s.section_type === "Investment") rows += 10;
    if (s.section_type === "Acceptance") text += 150;
  }
  return 1 + Math.max(1, Math.ceil(text / 450 + rows / 26));
}
