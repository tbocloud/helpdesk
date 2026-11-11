/** Assign leads: who in a department is handed which product and how many calls per slot
 * (docs/leads.md, "Assign leads"; TBO Smart's call-batches.md §11). The ERP site keeps the
 * plans and hands out the batches; the hub only shows and saves them. */

import { __ } from "@/translation";

export interface PlanSlot {
  label: string;
  /** "HH:mm" */
  start_time: string;
  end_time: string;
  /** the slot's own size: what a person without a plan gets */
  size: number;
}

export interface PlanMember {
  user: string;
  full_name: string;
  /** the product they are handed; null: any of the department's */
  product: string | null;
  /** a department without products plans by industry; null: any (absent from an older TBO Smart) */
  industry?: string | null;
  /** calls per slot label: the plan's, else the slot's size */
  sizes: Record<string, number>;
  total: number;
  has_plan: boolean;
  /** today's batches: calls handed and called, retries not counted */
  today: { size: number; called: number };
  /** open leads they own in the department */
  leads: number;
}

/** One open lead of a department, as the hand-out list shows it. */
export interface DepartmentLead {
  name: string;
  lead_name?: string;
  company_name?: string;
  product: string | null;
  industry?: string | null;
  stage?: string;
  temperature?: string;
  phone?: string;
}

export interface DepartmentLeads {
  rows: DepartmentLead[];
  total: number;
  /** open leads per product ("" for none), whatever the product and search */
  products: Record<string, number>;
  /** open leads per industry ("" for none), whatever the filters (absent from an older TBO Smart) */
  industries?: Record<string, number>;
}

export interface PlanDepartment {
  department: string;
  slots: PlanSlot[];
  products: { product_name: string; intro_line?: string }[];
  /** a manager's limit on the department: the only product a plan can take */
  campaign_product: string | null;
  /** batches pull unassigned leads; off: people only get their own */
  pull_unassigned: number;
  /** open unassigned leads with a phone, per product ("" for none) */
  unassigned: Record<string, number>;
  /** the industries its open leads are in (absent from an older TBO Smart) */
  industries?: string[];
  /** open unassigned leads with a phone, per industry ("" for none) */
  unassigned_industries?: Record<string, number>;
  members: PlanMember[];
  /** the daily auto-assign (TBO Smart's call-batches.md §14; absent from an older TBO Smart) */
  auto_assign?: {
    auto_assign: number;
    /** "HH:mm" */
    auto_assign_at: string;
    auto_assign_skip_sunday: number;
    auto_assign_skip_saturdays: "None" | "2nd" | "2nd and 4th" | "All";
    /** the last day it ran */
    auto_assigned_on: string | null;
  };
}

/** When the department tops up the people nobody handed leads to, in words; "" when it doesn't. */
export function autoAssignText(department: PlanDepartment) {
  const rules = department.auto_assign;
  if (!rules?.auto_assign) return "";
  const off: string[] = [];
  if (rules.auto_assign_skip_sunday) off.push(__("Sundays"));
  const saturdays = {
    None: "",
    "2nd": __("the 2nd Saturday"),
    "2nd and 4th": __("the 2nd and 4th Saturdays"),
    All: __("Saturdays"),
  }[rules.auto_assign_skip_saturdays];
  if (saturdays) off.push(saturdays);
  const when = __(
    "At {0}, anyone with a plan who wasn't given leads here today is topped up to their plan automatically.",
    rules.auto_assign_at
  );
  return off.length ? `${when} ${__("Not on {0}.", off.join(__(" or ")))}` : when;
}

export interface CallPlans {
  /** false while the ERP site is older than call plans */
  available: boolean;
  date?: string;
  departments: PlanDepartment[];
}

/** A department without products plans and hands out by industry (once the ERP site has it). */
export function byIndustry(department: PlanDepartment | undefined) {
  return (
    !!department &&
    !department.products.length &&
    Array.isArray(department.industries)
  );
}

/** The unassigned leads a plan for `industry` can be handed ("" or null: every industry). */
export function industryReady(
  department: PlanDepartment,
  industry: string | null
) {
  const counts = department.unassigned_industries || {};
  if (industry) return counts[industry] ?? 0;
  return Object.values(counts).reduce((sum, count) => sum + count, 0);
}

/** The unassigned leads a plan for `product` can be handed ("" or null: every product). */
export function leadsReady(department: PlanDepartment, product: string | null) {
  const counts = department.unassigned || {};
  if (product) return counts[product] ?? 0;
  return Object.values(counts).reduce((sum, count) => sum + count, 0);
}

/** Why leads waiting in the pool will not be handed to anyone, or null when someone gets them. */
export function poolStuck(department: PlanDepartment): string | null {
  if (!leadsReady(department, null)) return null;
  if (!department.pull_unassigned) return "off";
  const nobody = department.members.every(
    (m) => !Object.values(m.sizes).some((calls) => calls > 0)
  );
  return nobody ? "zero" : null;
}
