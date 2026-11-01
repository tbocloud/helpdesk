// Sales commission lives on the ERP site; helpdesk.api.commission reads and writes it as the
// signed-in person (docs/leads.md, "Commission").
import { money } from "@/components/invoicing/invoices";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";

export type CommissionStatus = "Draft" | "Approved" | "Paid";
export type CommissionBasis = "Project collected" | "Collected (all)";

export interface CommissionSlabRow {
  from_amount: number;
  to_amount: number | null;
  rate: number;
}

export interface CommissionProject {
  project: string;
  plan: string | null;
  collected: number;
  share_percent: number;
  credited: number;
  target: number;
  commission: number;
}

export interface CommissionBreakdownRow {
  project: string;
  slab_no: number | null;
  from_amount: number;
  to_amount: number;
  amount: number;
  slab_rate: number;
  rate: number;
  above_target: number;
  commission: number;
}

export interface CommissionPayment {
  payment_entry: string;
  date: string;
  kind: string;
  amount: number;
  project: string;
  lead: string | null;
  customer: string | null;
}

export interface CommissionPerson {
  user: string;
  full_name: string;
  plans: string[];
  collected: number;
  target: number;
  achievement: number;
  reached: {
    slab_no: number | null;
    rate: number;
    above_target: number;
  } | null;
  commission: number;
  statement: string | null;
  status: CommissionStatus | null;
  frozen: number;
  approved_by: string | null;
  approved_on: string | null;
  paid_on: string | null;
  projects: CommissionProject[];
  breakdown: CommissionBreakdownRow[];
  payments: CommissionPayment[];
}

export interface CommissionUnattributed {
  amount: number;
  count: number;
  reasons: Record<string, number>;
  payments: {
    payment_entry: string;
    date: string;
    kind: string;
    amount: number;
    customer: string | null;
    lead: string | null;
    project: string | null;
    reason: string;
  }[];
}

/** helpdesk.api.commission.get_commission */
export interface CommissionMonth {
  available: boolean;
  month: string;
  currency: string;
  scope: "own" | "department" | "all";
  can_manage: boolean;
  rows: CommissionPerson[];
  totals: { collected: number; commission: number };
  unattributed: CommissionUnattributed | null;
}

export interface CommissionPlan {
  name: string;
  plan_name: string;
  is_active: number;
  basis: CommissionBasis;
  department: string | null;
  lead_type: string | null;
  project_type: string | null;
  user: string | null;
  monthly_target: number;
  above_target_rate: number;
  slabs: CommissionSlabRow[];
}

export interface CommissionEarner {
  user: string;
  share_percent: number;
}

export interface ProjectCommissionSetup {
  project: string;
  is_active: number;
  lead: string | null;
  project_type: string | null;
  earners: CommissionEarner[];
  plan: string | null;
  use_override: number;
  override_target: number;
  override_above_target_rate: number;
  override_slabs: CommissionSlabRow[];
}

export const STATUS_LABELS: Record<CommissionStatus, string> = {
  Draft: __("Draft"),
  Approved: __("Approved"),
  Paid: __("Paid"),
};

export const REASON_LABELS: Record<string, string> = {
  "No project": __("No project on the invoice or order"),
  "No one earns": __("No lead owner or project set-up"),
};

/** The first day of the month `offset` months from now, as YYYY-MM. */
export function monthValue(offset = 0) {
  return dayjs().add(offset, "month").format("YYYY-MM");
}

export function monthTitle(month: string) {
  return dayjs(month).format("MMMM YYYY");
}

export function fullAmount(value: number, currency: string) {
  return money(value, currency || "INR", true);
}

/** "2 slabs reached" style label for the slab a person got to. */
export function reachedText(person: CommissionPerson) {
  const r = person.reached;
  if (!r) return __("None yet");
  if (r.above_target) return __("Above target, {0}%", String(r.rate));
  return r.slab_no
    ? __("Slab {0}, {1}%", String(r.slab_no), String(r.rate))
    : __("{0}%", String(r.rate));
}

export interface SlabPiece {
  from: number;
  to: number;
  rate: number;
  above: boolean;
  commission: number;
}

/** The same progressive maths as the ERP site (TBO Smart's commission.apply_slabs), for the
 * plan editor's live example. Each slab's rate applies to the part of `collected` inside it;
 * the part above `target` earns `aboveRate` where that is higher than its slab's. */
export function previewCommission(
  collected: number,
  target: number,
  slabs: CommissionSlabRow[],
  aboveRate: number
): { total: number; pieces: SlabPiece[] } {
  if (!(collected > 0)) return { total: 0, pieces: [] };
  const sorted = slabs
    .map((s) => ({
      from: Number(s.from_amount) || 0,
      to: Number(s.to_amount) || null,
      rate: Number(s.rate) || 0,
    }))
    .sort((a, b) => a.from - b.from);
  const cuts = new Set<number>([0, collected]);
  for (const s of sorted)
    for (const edge of [s.from, s.to])
      if (edge && edge > 0 && edge < collected) cuts.add(edge);
  if (target > 0 && target < collected) cuts.add(target);
  const points = [...cuts].sort((a, b) => a - b);
  const pieces: SlabPiece[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const [low, high] = [points[i], points[i + 1]];
    const slab = sorted.find(
      (s) => s.from <= low && (s.to === null || high <= s.to)
    );
    const slabRate = slab?.rate ?? 0;
    const above = target > 0 && low >= target;
    const rate = above ? Math.max(slabRate, aboveRate) : slabRate;
    pieces.push({
      from: low,
      to: high,
      rate,
      above,
      commission: Math.round(((high - low) * rate) / 100 * 100) / 100,
    });
  }
  const total = pieces.reduce((sum, p) => sum + p.commission, 0);
  return { total, pieces };
}

/** What is wrong with a plan's slabs and rates, in words; "" when nothing. */
export function schemeProblem(
  slabs: CommissionSlabRow[],
  aboveRate: number
): string {
  const rows = slabs
    .map((s) => ({
      from: Number(s.from_amount) || 0,
      to: s.to_amount === null || s.to_amount === ("" as unknown) ? null : Number(s.to_amount),
      rate: Number(s.rate),
    }))
    .sort((a, b) => a.from - b.from);
  for (const r of rows) {
    if (r.from < 0) return __("A slab cannot start below 0.");
    if (r.to !== null && r.to <= r.from)
      return __("A slab must end above where it starts.");
    if (!(r.rate >= 0 && r.rate <= 100))
      return __("A slab's rate must be between 0 and 100.");
  }
  for (let i = 0; i < rows.length - 1; i++)
    if (rows[i].to === null || rows[i].to! > rows[i + 1].from)
      return __("Slabs overlap. Each slab must start where the one before ends.");
  if (!(Number(aboveRate) >= 0 && Number(aboveRate) <= 100))
    return __("The above-target rate must be between 0 and 100.");
  return "";
}

/** A slab as the editors hold it while it is typed. */
export interface SlabForm {
  from_amount: number | string;
  to_amount: number | string | null;
  rate: number | string;
}

/** The editor's rows as the ERP site takes them: blank rows dropped, a blank "to" as no limit. */
export function slabRows(rows: SlabForm[]): CommissionSlabRow[] {
  return rows
    .filter((s) => s.rate !== "" || s.to_amount !== "" || Number(s.from_amount))
    .map((s) => ({
      from_amount: Number(s.from_amount) || 0,
      to_amount:
        s.to_amount === "" || s.to_amount === null ? null : Number(s.to_amount),
      rate: Number(s.rate) || 0,
    }));
}
