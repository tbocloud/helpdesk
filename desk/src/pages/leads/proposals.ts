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

export type SectionType =
  | "Cover"
  | "About us"
  | "Challenge"
  | "Solution"
  | "Scope"
  | "Timeline"
  | "Pricing"
  | "Terms"
  | "Custom";

export interface ProposalSection {
  section_type: SectionType;
  heading?: string | null;
  body?: string | null;
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
  sections: TemplateSection[];
  packages: string[];
}

export interface ProposalOptions {
  enabled: boolean;
  ai?: boolean;
  can_edit_templates?: boolean;
  templates?: ProposalTemplate[];
  packages?: string[];
  section_types?: SectionType[];
  themes?: string[];
}

/** A row of the lead's proposals (get_lead's `proposals`). */
export interface ProposalRow {
  name: string;
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
  title: string;
  lead: string;
  lead_name?: string;
  /** the lead's company, else its name: what the client's page calls them */
  client: string;
  lead_email?: string | null;
  template?: string | null;
  status: ProposalStatus;
  theme: string;
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
    decline_reason?: string | null;
  };
  can_write: boolean;
  /** why Send is off now, in words; empty when it can be sent */
  send_blockers: string[];
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
  "About us": __("About us"),
  Challenge: __("Challenge"),
  Solution: __("Solution"),
  Scope: __("Scope"),
  Timeline: __("Timeline"),
  Pricing: __("Pricing"),
  Terms: __("Terms"),
  Custom: __("Custom"),
};

/** Accepted is done, Declined and Expired ended badly, Viewed is news; the rest neutral. */
export function proposalTone(status?: ProposalStatus): Tone {
  if (status === "Accepted") return "success";
  if (status === "Declined" || status === "Expired") return "danger";
  if (status === "Viewed") return "info";
  return "neutral";
}

/** Fetched once per session: whether proposals are on, templates, block types. */
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

/** Plain text as paragraphs and bullet lists, as the client's page lays it out. */
export function textParts(
  body?: string | null
): ({ kind: "text"; lines: string[] } | { kind: "list"; items: string[] })[] {
  return (body || "")
    .trim()
    .split(/\n\s*\n/)
    .map((chunk) =>
      chunk
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean)
    )
    .filter((lines) => lines.length)
    .map((lines) =>
      lines.every((l) => l.startsWith("- ") || l.startsWith("• "))
        ? { kind: "list" as const, items: lines.map((l) => l.slice(2).trim()) }
        : { kind: "text" as const, lines }
    );
}
