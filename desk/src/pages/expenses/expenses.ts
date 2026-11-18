import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import type { Component } from "vue";
import LucideBanknote from "~icons/lucide/banknote";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideClock from "~icons/lucide/clock";

/** One of the person's own claims (TBO Smart's hub_expenses, docs/expenses.md). */
export interface Claim {
  name: string;
  expense_type: string;
  amount: number;
  sanctioned_amount: number;
  date: string;
  description: string;
  status: "Pending" | "Approved" | "Rejected" | "Paid";
  approver: string;
  approver_id: string;
  receipt: string | null;
}

/** Someone else's claim waiting for the person. */
export interface Approval {
  ref: string;
  who: string;
  employee: string;
  title: string;
  detail: string;
  from_date: string;
  amount: number;
  submitted: string;
  can_reject: boolean;
  receipt: string | null;
}

export interface ExpensesPage {
  available: boolean;
  employee?: boolean;
  can_approve?: boolean;
  currency?: string | null;
  types?: string[];
  claims?: { data: Claim[]; page: number; has_more: boolean } | null;
  approvals?: Approval[];
}

/** How a claim's status reads; the colour always comes with its icon and word. */
export function claimLook(status: Claim["status"]): {
  label: string;
  tone: Tone;
  icon: Component;
} {
  switch (status) {
    case "Approved":
      return {
        label: __("Approved"),
        tone: "success",
        icon: LucideCircleCheck,
      };
    case "Paid":
      return { label: __("Paid"), tone: "success", icon: LucideBanknote };
    case "Rejected":
      return { label: __("Rejected"), tone: "danger", icon: LucideCircleX };
    default:
      return { label: __("Pending"), tone: "info", icon: LucideClock };
  }
}

/** The receipt, streamed from the ERP site (helpdesk.api.expenses.expense_receipt). */
export function receiptUrl(claim: string, filename: string | null) {
  const params = new URLSearchParams({ name: claim, filename: filename || "" });
  return `/api/method/helpdesk.api.expenses.expense_receipt?${params}`;
}
