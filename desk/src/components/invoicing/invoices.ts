import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import type { Component } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideCircleSlash from "~icons/lucide/circle-slash";
import LucideClock from "~icons/lucide/clock";
import LucideUnlink from "~icons/lucide/unlink";

/** "extra": hours beyond the contract's included hours; "all": every billable hour. */
export type InvoiceMode = "extra" | "all";

/** A period the dialog offers: a contract period, or a calendar month (no contract). */
export interface InvoicePeriodChoice {
  start: string;
  end: string;
  contract: string | null;
  contract_name: string | null;
}

export interface InvoiceLine {
  project: string | null;
  task: string | null;
  label: string;
  hours: number;
  rate: number;
  amount: number;
  description: string;
}

/** helpdesk.integrations.crm.invoices.get_preview */
export interface InvoicePreview {
  customer: string;
  start: string;
  end: string;
  period_label: string;
  mode: InvoiceMode;
  contract: {
    name: string;
    contract_name: string;
    allowance: number;
    included_left: number;
  } | null;
  rate: number;
  rate_from: "contract" | "default";
  currency: string;
  hours_logged: number;
  hours_covered: number;
  hours_billed: number;
  amount: number;
  lines: InvoiceLine[];
  periods: InvoicePeriodChoice[];
}

/** An HD Customer Invoice: a draft the hub created in ERPNext. */
export interface CustomerInvoice {
  name: string;
  customer: string;
  invoice: string;
  invoice_url: string;
  status: "Linked" | "Unlinked";
  posting_date: string;
  currency: string;
  amount: number;
  period_start: string;
  period_end: string;
  mode: "Extra hours" | "All billable hours";
  hours_billed: number;
  hours_covered: number;
}

export function money(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(amount || 0);
  } catch {
    // an unknown currency code
    return `${currency} ${(amount || 0).toFixed(2)}`;
  }
}

interface StatusLook {
  label: string;
  tone: Tone;
  icon: Component;
}

/** How an invoice's ERPNext status reads; colour always comes with an icon and label. */
export function statusLook(status: string | undefined): StatusLook {
  switch (status) {
    case "Draft":
      return { label: __("Draft"), tone: "neutral", icon: LucideCircleDashed };
    case "Paid":
      return { label: __("Paid"), tone: "success", icon: LucideCircleCheck };
    case "Overdue":
      return { label: __("Overdue"), tone: "danger", icon: LucideCircleAlert };
    case "Cancelled":
      return { label: __("Cancelled"), tone: "neutral", icon: LucideCircleSlash };
    case "Not found":
      return {
        label: __("Deleted in ERPNext"),
        tone: "warning",
        icon: LucideCircleAlert,
      };
    case "Unlinked":
      return { label: __("Unlinked"), tone: "neutral", icon: LucideUnlink };
    default:
      // Unpaid, Partly Paid, Submitted, Return…
      return { label: __(status || "Submitted"), tone: "info", icon: LucideClock };
  }
}
