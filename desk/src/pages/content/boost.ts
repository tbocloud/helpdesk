import type { Tone } from "@/components/tone";
import type { Component } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideClock from "~icons/lucide/clock";
import LucideFileText from "~icons/lucide/file-text";
import LucidePause from "~icons/lucide/pause";
import LucideRocket from "~icons/lucide/rocket";

export type BoostStatus =
  | "Draft"
  | "Pending approval"
  | "Active"
  | "Paused"
  | "Completed"
  | "Failed"
  | "Rejected";

export interface Boost {
  name: string;
  post: string;
  post_title?: string | null;
  target: "Facebook" | "Instagram";
  goal: string;
  status: BoostStatus;
  budget_type: string;
  budget_amount: number;
  total_budget: number;
  currency: string;
  start_date: string;
  end_date: string;
  days: number;
  spend: number;
  reach: number;
  impressions: number;
  clicks: number;
  results: number;
  cost_per_result: number;
  failure_reason?: string | null;
  rejection_note?: string | null;
  meta_status?: string | null;
  requested_by_name?: string | null;
  last_synced?: string | null;
  can_spend: boolean;
}

export interface AdAccount {
  name?: string | null;
  currency?: string | null;
  status?: string | null;
}

export interface MonthSpend {
  currency: string;
  cap: number;
  planned: number;
  left: number;
}

// Colour only where it says how the boost is going, always with the label and an icon
export const BOOST_STATUS: Record<
  BoostStatus,
  { label: string; tone: Tone; icon: Component }
> = {
  Draft: { label: "Draft", tone: "neutral", icon: LucideFileText },
  "Pending approval": {
    label: "Waiting for approval",
    tone: "warning",
    icon: LucideClock,
  },
  Active: { label: "Running", tone: "success", icon: LucideRocket },
  Paused: { label: "Paused", tone: "neutral", icon: LucidePause },
  Completed: { label: "Finished", tone: "neutral", icon: LucideCircleCheck },
  Failed: { label: "Didn't run", tone: "danger", icon: LucideCircleAlert },
  Rejected: { label: "Rejected", tone: "danger", icon: LucideCircleX },
};

export const GOAL_HINTS: Record<string, string> = {
  "More reach": "Show the post to as many new people as possible.",
  "More engagement": "Get more likes, comments and shares.",
  "More messages": "Get people to message the Page or Instagram account.",
  "More website visits": "Send people to the link in the post.",
};

export function formatMoney(amount: number, currency?: string | null) {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: currency || "INR",
      maximumFractionDigits: 2,
    }).format(amount || 0);
  } catch {
    return `${currency ?? ""} ${amount || 0}`.trim();
  }
}

export function formatCount(n: number) {
  return new Intl.NumberFormat().format(n || 0);
}
