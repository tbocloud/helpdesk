import type { Tone } from "@/components/tone";
import { fullAmount } from "@/pages/leads/commission";
import { __ } from "@/translation";

/** The Lead Bank's contract with TBO Smart: hub-leads-api.md §2.21 on the ERP site. */
export type Region = "India" | "UAE" | "KSA";
export const REGIONS: Region[] = ["India", "UAE", "KSA"];

/** The five words a collector sees; the ERP site maps its sixteen stages to them. */
export type CollectorStatus =
  | "New"
  | "Being called"
  | "Meeting"
  | "Won"
  | "Not interested";

export interface RegionInfo {
  region: Region;
  prefix: string;
  country: string;
  rate: number;
  has_department: boolean;
}

export interface LeadBankOptions {
  regions: RegionInfo[];
  cap: number;
  currency: string;
  is_manager: boolean;
  max_photos: number;
}

/** What the form holds, under the ERP site's names. */
export interface LeadBankForm {
  company_name: string;
  contact_name: string;
  mobile_no: string;
  phone: string;
  email_id: string;
  website: string;
  business_type: string;
  address: string;
  state: string;
  note: string;
}

export interface Duplicate {
  duplicate: boolean;
  mine: boolean;
  message: string | null;
}

export interface ScanResult {
  fields: Partial<LeadBankForm>;
  message: string | null;
  region: Region | null;
  region_by: "phone" | "gps" | null;
  duplicate: Duplicate | null;
}

export interface SubmitResult {
  created: boolean;
  duplicate: boolean;
  mine: boolean;
  lead: string | null;
  region: Region | null;
  department: string | null;
  in_pool: boolean;
  message: string;
}

export interface MyLead {
  id: string;
  title: string;
  collected_on: string | null;
  region: Region | null;
  status: CollectorStatus;
  earned: number;
  pending: number;
}

export interface MyLeads {
  rows: MyLead[];
  total: number;
  summary: { leads: number; won: number; earned: number; pending: number };
  currency: string;
}

export interface DashboardRegion {
  region: Region;
  department: string | null;
  collected: number;
  won: number;
}

export interface DashboardCollector {
  user: string;
  full_name: string;
  collected: number;
  won: number;
}

export interface Dashboard {
  month: string;
  currency: string;
  collected: number;
  won: number;
  conversion: number;
  by_region: DashboardRegion[];
  collectors: DashboardCollector[];
  referral: {
    earned: number;
    paid: number;
    due: number;
    by_collector: { user: string; full_name: string; due: number }[];
  };
  pool: {
    count: number;
    leads: {
      lead: string;
      title: string;
      region: Region | null;
      collected_on: string | null;
      collected_by_name: string;
    }[];
  };
}

export interface ReferralSettingsRegion {
  region: Region;
  rate: number;
  department: string | null;
  effective_department: string | null;
}

export interface ReferralSettings {
  regions: ReferralSettingsRegion[];
  cap: number;
  currency: string;
  departments: string[];
}

/** A status's tone: only Won says anything good; the rest stay neutral gray or info blue. */
export const STATUS_TONE: Record<CollectorStatus, Tone> = {
  New: "neutral",
  "Being called": "info",
  Meeting: "info",
  Won: "success",
  "Not interested": "neutral",
};

export const STATUS_LABEL: Record<CollectorStatus, string> = {
  New: __("New"),
  "Being called": __("Being called"),
  Meeting: __("Meeting"),
  Won: __("Won"),
  "Not interested": __("Not interested"),
};

export const REGION_LABEL: Record<Region, string> = {
  India: __("India"),
  UAE: __("UAE"),
  KSA: __("KSA"),
};

export const blankForm = (): LeadBankForm => ({
  company_name: "",
  contact_name: "",
  mobile_no: "",
  phone: "",
  email_id: "",
  website: "",
  business_type: "",
  address: "",
  state: "",
  note: "",
});

/** One line telling a collector what they earn, in plain words. */
export function earnText(options: LeadBankOptions | undefined): string {
  if (!options) return "";
  const rates = new Map<number, string[]>();
  for (const r of options.regions)
    rates.set(r.rate, [...(rates.get(r.rate) ?? []), r.region]);
  const parts = [...rates].map(
    ([rate, regions]) => `${rate}% (${regions.join(", ")})`
  );
  const cap = options.cap > 0 ? fullAmount(options.cap, options.currency) : "";
  return cap
    ? __(
        "When a lead you add becomes a client and pays, you earn {0} of what they pay, up to {1} per lead.",
        parts.join(", "),
        cap
      )
    : __(
        "When a lead you add becomes a client and pays, you earn {0} of what they pay.",
        parts.join(", ")
      );
}
