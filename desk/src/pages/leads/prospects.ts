// Find prospects: businesses found by industry and district land in a department's
// unassigned pool (docs/leads.md). helpdesk.api.prospects proxies TBO Smart's hub leads API.
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import type { Component } from "vue";
import LucideCalculator from "~icons/lucide/calculator";
import LucideCalendarCheck from "~icons/lucide/calendar-check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideGlobe from "~icons/lucide/globe";
import LucideGlobeLock from "~icons/lucide/globe-lock";
import LucideLoader from "~icons/lucide/loader";
import LucideMessageCircle from "~icons/lucide/message-circle";
import LucideUsers from "~icons/lucide/users";

export type RunStatus = "Draft" | "Estimated" | "Running" | "Done" | "Failed";
export type ProspectProvider = "OpenStreetMap" | "DataForSEO" | "Serper";

export interface ProviderOption {
  key: ProspectProvider;
  label: string;
  paid: boolean;
  /** switched on and set up with its login or key */
  available: boolean;
  coverage: string;
}

export interface ProspectingOptions {
  providers: ProviderOption[];
  default_department?: string | null;
  max_results: number;
  max_districts: number;
  /** USD */
  monthly_cap: number;
  month_spend: number;
}

export interface ProspectValues {
  industry: string;
  state: string;
  districts: string[];
  provider: ProspectProvider | "";
  max_results: number;
  department: string;
  require_phone: number;
}

export interface ProspectRun {
  name: string;
  industry: string;
  state: string;
  districts: string[];
  provider: ProspectProvider;
  department: string;
  max_results: number;
  require_phone: number;
  status: RunStatus;
  /** USD */
  estimated_cost: number;
  expected_count: number;
  estimate_note?: string | null;
  actual_cost: number;
  count_found: number;
  count_duplicates: number;
  count_skipped: number;
  count_created: number;
  started_at?: string | null;
  finished_at?: string | null;
  creation: string;
  owner_name?: string;
}

export interface ProspectRunLead {
  name: string;
  company_name?: string;
  phone?: string;
  website?: string;
  city?: string;
  stage?: string;
  owner?: string | null;
  why_call?: string | null;
}

export interface ProspectRunDetail extends ProspectRun {
  log?: string | null;
  leads: ProspectRunLead[];
}

/** What the lead's own website says: a Why call line and a few findings. */
export interface LeadProspect {
  why_call?: string | null;
  signals: {
    has_website?: boolean;
    unreadable?: boolean;
    online_booking?: boolean;
    booking_tool?: string | null;
    whatsapp?: boolean;
    hiring?: boolean;
    email?: string | null;
    phone?: string | null;
    social?: string[];
    tech?: string[];
    software?: string[];
    last_updated_year?: number | null;
  };
  read_on?: string;
}

export const STATUS: Record<
  RunStatus,
  { label: string; tone: Tone; icon: Component }
> = {
  Draft: { label: __("Draft"), tone: "neutral", icon: LucideCircleDashed },
  Estimated: { label: __("Estimated"), tone: "neutral", icon: LucideCalculator },
  Running: { label: __("Running"), tone: "info", icon: LucideLoader },
  Done: { label: __("Done"), tone: "success", icon: LucideCircleCheck },
  Failed: { label: __("Failed"), tone: "danger", icon: LucideCircleAlert },
};

/** USD, with the cents a search costs: "USD 0.05", "Free" for nothing. */
export function usd(amount: number | undefined | null) {
  const value = Number(amount) || 0;
  if (!value) return __("Free");
  return `USD ${value < 1 ? value.toFixed(3) : value.toFixed(2)}`;
}

export function runTitle(run: Pick<ProspectRun, "industry" | "districts">) {
  return __("{0} in {1}", run.industry, run.districts.join(", "));
}

export interface Chip {
  key: string;
  label: string;
  icon: Component;
  /** true: the business has it */
  on: boolean;
}

/** The four chips of a lead page: what the site has or lacks. Each says so in words, so the
 * state never rests on a colour. Empty while the site was not read or could not be. */
export function signalChips(prospect: LeadProspect | null | undefined): Chip[] {
  const s = prospect?.signals;
  if (!s || s.unreadable) return [];
  if (s.has_website === false)
    return [
      { key: "website", label: __("No website"), icon: LucideGlobeLock, on: false },
    ];
  return [
    { key: "website", label: __("Website"), icon: LucideGlobe, on: true },
    {
      key: "booking",
      label: s.online_booking ? __("Online booking") : __("No online booking"),
      icon: LucideCalendarCheck,
      on: !!s.online_booking,
    },
    {
      key: "whatsapp",
      label: s.whatsapp ? __("WhatsApp") : __("No WhatsApp"),
      icon: LucideMessageCircle,
      on: !!s.whatsapp,
    },
    {
      key: "hiring",
      label: s.hiring ? __("Hiring") : __("Not hiring"),
      icon: LucideUsers,
      on: !!s.hiring,
    },
  ];
}
