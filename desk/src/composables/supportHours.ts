import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import type { Component } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";

/** How a period's usage reads; the server decides it from the contract's alert level. */
export type UsageStage = "ok" | "warning" | "over";

export const CONTRACT_TYPES = ["AMC", "Support block", "Retainer"] as const;
export const BILLING_PERIODS = [
  "Monthly",
  "Quarterly",
  "Yearly",
  "One-off block",
] as const;
export const CONTRACT_STATUSES = ["Active", "Expired", "Cancelled"] as const;

/** One period of a contract, as helpdesk.support_contracts.period_usage sends it. */
export interface UsagePeriod {
  start: string;
  end: string;
  included: number;
  carried_in: number;
  allowance: number;
  used: number;
  /** negative once the hours are used up */
  remaining: number;
  percent: number;
  stage: UsageStage;
  is_current: boolean;
}

export interface SupportContract {
  name: string;
  contract_name: string;
  customer: string;
  contract_type: (typeof CONTRACT_TYPES)[number];
  status: (typeof CONTRACT_STATUSES)[number];
  account_manager: string | null;
  start_date: string;
  end_date: string;
  billing_period: (typeof BILLING_PERIODS)[number];
  hours_per_period: number;
  rollover_unused: 0 | 1;
  alert_threshold: number;
  rate_per_extra_hour: number | null;
  currency: string | null;
  notes: string | null;
}

export const STAGE_TONE: Record<UsageStage, Tone> = {
  ok: "neutral",
  warning: "warning",
  over: "danger",
};

/** The icon that goes with a stage's colour, so colour is never the only signal. */
export const STAGE_ICON: Record<UsageStage, Component | null> = {
  ok: null,
  warning: LucideTriangleAlert,
  over: LucideCircleAlert,
};

export const STAGE_LABEL: Record<UsageStage, string> = {
  ok: __("Within hours"),
  warning: __("Running low"),
  over: __("Used up"),
};

export function hours(value: number | null | undefined): string {
  const n = Math.round((Number(value) || 0) * 10) / 10;
  return `${n} h`;
}

/** "32 of 40 h used · 8 h left", or "· 4 h over" once the hours are used up. */
export function usageText(period: UsagePeriod): string {
  const used = __(
    "{0} of {1} used",
    String(Math.round(period.used * 10) / 10),
    hours(period.allowance)
  );
  const rest =
    period.remaining >= 0
      ? __("{0} left", hours(period.remaining))
      : __("{0} over", hours(-period.remaining));
  return `${used} · ${rest}`;
}

export function periodText(period: { start: string; end: string }): string {
  const start = dayjs(period.start);
  const end = dayjs(period.end);
  const startFormat = start.year() === end.year() ? "D MMM" : "D MMM YYYY";
  return `${start.format(startFormat)} – ${end.format("D MMM YYYY")}`;
}
