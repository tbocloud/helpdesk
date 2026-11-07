/** Assign leads: who in a department is handed which product and how many calls per slot
 * (docs/leads.md, "Assign leads"; TBO Smart's call-batches.md §11). The ERP site keeps the
 * plans and hands out the batches; the hub only shows and saves them. */

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
  stage?: string;
  temperature?: string;
  phone?: string;
}

export interface DepartmentLeads {
  rows: DepartmentLead[];
  total: number;
  /** open leads per product ("" for none), whatever the product and search */
  products: Record<string, number>;
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
  members: PlanMember[];
}

export interface CallPlans {
  /** false while the ERP site is older than call plans */
  available: boolean;
  date?: string;
  departments: PlanDepartment[];
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
