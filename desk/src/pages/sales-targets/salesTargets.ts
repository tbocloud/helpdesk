import { money } from "@/components/invoicing/invoices";
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import type { Component } from "vue";
import type { RouteLocationRaw } from "vue-router";
import LucideHash from "~icons/lucide/hash";
import LucideBanknote from "~icons/lucide/banknote";
import LucidePercent from "~icons/lucide/percent";
import LucideText from "~icons/lucide/text";
import { monthTitle, monthValue } from "../leads/commission";

export { monthTitle, monthValue };

/** How a criterion's target is read; the server's `VALUE_TYPES`. */
export type ValueType = "Amount" | "Number" | "Percent" | "Text";

/** What a target counts from the person's leads; the server's `MEASURES`. "" is not counted. */
export type Measure =
  | "won_value"
  | "collected"
  | "meetings"
  | "proposals"
  | "won"
  | "contacted"
  | "new_leads"
  | "meeting_rate"
  | "win_rate";

/** A KPI (a Text target): "" open, Done by the person, Confirmed by a Sales Head. */
export type KpiStatus = "" | "Done" | "Confirmed";

export interface Criterion {
  criterion: string;
  value_type: ValueType;
  /** a number, or text for a Text criterion; null while not filled in */
  target: number | string | null;
  measure?: Measure | "";
  /** a Text target that only says where to focus (Industry, Location): no tick-off, and
   * left out of the month's progress */
  info_only?: number | boolean;
  kpi_status?: KpiStatus;
  kpi_note?: string;
  kpi_done_on?: string | null;
  kpi_confirmed_by?: string | null;
  kpi_confirmed_by_name?: string | null;
}

export interface Target {
  criteria: Criterion[];
  assigned_by: string;
  assigned_by_name: string;
  modified: string;
}

export interface TargetPerson {
  user: string;
  full_name: string;
  user_image: string | null;
  roles: string[];
  target: Target | null;
}

export interface TeamTargets {
  month: string;
  currency: string;
  value_types: ValueType[];
  defaults: {
    criterion: string;
    value_type: ValueType;
    measure: Measure | "";
  }[];
  /** the measures that fit each value type */
  measures: Record<ValueType, Measure[]>;
  people: TargetPerson[];
}

export interface MyTargets {
  month: string;
  currency: string;
  months: string[];
  target: Target | null;
  /** the standard criteria; each one not assigned for the month shows as 0 */
  defaults?: Omit<Criterion, "target">[];
}

/** A criterion on a person's page: assigned, or a standard one not assigned (shown as 0). */
export type ShownCriterion = Criterion & { unassigned?: boolean };

/**
 * The month's criteria as the person sees them: what was assigned, in the head's order, then
 * every standard criterion that wasn't, at 0 (a Text one blank), so nothing reads as missing.
 */
export function withUnassigned(
  target: Target | null,
  defaults: Omit<Criterion, "target">[]
): ShownCriterion[] {
  const assigned = target?.criteria ?? [];
  const names = new Set(assigned.map((c) => c.criterion.toLowerCase()));
  return [
    ...assigned,
    ...defaults
      .filter((d) => !names.has(d.criterion.toLowerCase()))
      .map((d) => ({
        ...d,
        target: d.value_type === "Text" ? null : 0,
        unassigned: true,
      })),
  ];
}

/** Each kind's icon, and the colour of its circle on a person's target cards, so a kind
 * reads at a glance: money green, rates blue, counts the brand teal, written targets amber
 * (the owner's ask, 2026-11-20). */
export const VALUE_TYPE_LOOK: Record<
  ValueType,
  { label: string; icon: Component; tone: Tone | "brand" }
> = {
  Amount: { label: __("Amount"), icon: LucideBanknote, tone: "success" },
  Number: { label: __("Number"), icon: LucideHash, tone: "brand" },
  Percent: { label: __("Percent"), icon: LucidePercent, tone: "info" },
  Text: { label: __("Text"), icon: LucideText, tone: "warning" },
};

/** A Text target that is a KPI to tick off, not information only. */
export function isKpi(criterion: Criterion) {
  return criterion.value_type === "Text" && !criterion.info_only;
}

/** "₹5,00,000", "90%", "20", or the text itself. */
export function targetText(criterion: Criterion, currency: string) {
  const { target, value_type } = criterion;
  if (target === null || target === "") return "—";
  if (value_type === "Text") return String(target);
  const value = Number(target);
  if (value_type === "Amount") return money(value, currency, true);
  const number = value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return value_type === "Percent" ? `${number}%` : number;
}

/** The first amount in a person's targets, e.g. "₹5,00,000": the figure a team list leads with. */
export function headlineAmount(target: Target, currency: string) {
  const amount = target.criteria.find((c) => c.value_type === "Amount");
  return amount ? targetText(amount, currency) : "";
}

/** The months a Sales Head may set targets for: three ahead and a year back. */
export function monthOptions(ahead = 3, back = 12) {
  return Array.from({ length: ahead + back + 1 }, (_v, i) => {
    const value = monthValue(ahead - i);
    return { label: monthTitle(value), value };
  });
}

/** "₹" for INR: the sign an amount field shows before the figure. */
export function currencySymbol(currency: string) {
  try {
    return (
      new Intl.NumberFormat(currency === "INR" ? "en-IN" : undefined, {
        style: "currency",
        currency,
      })
        .formatToParts(0)
        .find((part) => part.type === "currency")?.value ?? currency
    );
  } catch {
    return currency;
  }
}

// ---------- progress: what a target counts, and how far the person is ----------

/** One counted criterion as the server works it out; a rate carries what it divides. */
export interface Measured {
  achieved: number | null;
  parts?: Record<string, number>;
}

export interface Progress {
  state: "counted" | "not_started" | "unavailable" | "no_targets";
  /** why the ERP site couldn't count, in words */
  reason?: string;
  from_date?: string;
  to_date?: string;
  month_over?: boolean;
  /** by criterion name */
  criteria?: Record<string, Measured>;
}

/**
 * Each measure in words: its name, what it counts (TBO Smart hub-leads-api.md §2.4 and §2.8)
 * and the Leads list metric that lists the leads behind it (null: none lists them).
 */
export const MEASURE_LOOK: Record<
  Measure,
  { label: string; counts: string; metric: string | null }
> = {
  won_value: {
    label: __("Won value"),
    counts: __(
      "The value of leads that reached Closed – Won: each lead's latest quotation total, else the deal's amount, else its Sales Orders' total."
    ),
    metric: "won",
  },
  collected: {
    label: __("Money collected"),
    counts: __(
      "Payments received from customers against the leads' Sales Orders, by the day they were posted."
    ),
    metric: null,
  },
  meetings: {
    label: __("Meetings held"),
    counts: __(
      "Meetings held: a meeting record (MOM) submitted, or a lead reaching First, Second or Third Meeting Completed."
    ),
    metric: "meetings",
  },
  proposals: {
    label: __("Proposals sent"),
    counts: __(
      "Leads a proposal went to, each once: a quotation or proposal sent, or the lead reaching Proposal Sent."
    ),
    metric: "quotations",
  },
  won: {
    label: __("Leads won"),
    counts: __("Leads that reached Closed – Won."),
    metric: "won",
  },
  contacted: {
    label: __("Leads contacted"),
    counts: __(
      "Leads touched: a call, a note, an email, a stage change or a follow-up done."
    ),
    metric: "contacted",
  },
  new_leads: {
    label: __("New leads"),
    counts: __("Leads created."),
    metric: "new",
  },
  meeting_rate: {
    label: __("Meeting rate"),
    counts: __("Meetings held ÷ leads contacted × 100."),
    metric: "meetings",
  },
  win_rate: {
    label: __("Win rate"),
    counts: __("Leads won ÷ (leads won + leads lost) × 100."),
    metric: "won",
  },
};

/**
 * Where a person stands on one target:
 * done (reached), on_pace / behind (a running month, against an even pace),
 * short (the month ended below it), below (a rate under its target), none (nothing to count yet).
 */
export type Standing =
  | "done"
  | "on_pace"
  | "behind"
  | "short"
  | "below"
  | "none";

export interface CriterionProgress {
  achieved: number | null;
  /** achieved of the target, 0–100+; null with nothing to count */
  percent: number | null;
  /** where an even pace would have it by today, as a share of the target (0–100) */
  pacePercent: number | null;
  standing: Standing;
  /** the standing in words, e.g. "Behind pace by 2" */
  standingText: string;
  /** the sums, one line each: what is counted, the rate, the progress and the pace */
  lines: { label: string; text: string }[];
}

/** A figure in the criterion's own kind: "₹1,20,000", "17.5%" or "7". */
export function figureText(
  criterion: Criterion,
  value: number,
  currency: string
) {
  return targetText({ ...criterion, target: round(value) }, currency);
}

const round = (value: number) => Math.round(value * 10) / 10;

/** One counted target worked out against its figure, with the sums that show how. */
export function progressOf(
  criterion: Criterion,
  measured: Measured,
  progress: Progress,
  currency: string
): CriterionProgress {
  const measure = criterion.measure as Measure;
  const look = MEASURE_LOOK[measure];
  const target = Number(criterion.target) || 0;
  const achieved = measured.achieved;
  const fmt = (value: number) => figureText(criterion, value, currency);
  const isRate = criterion.value_type === "Percent";
  const lines = [{ label: __("Counts"), text: look.counts }];

  if (measure === "meeting_rate" && measured.parts) {
    const { meetings, contacted } = measured.parts;
    lines.push({
      label: look.label,
      text:
        achieved === null
          ? __("No leads contacted yet, so there's nothing to divide.")
          : `${meetings} ÷ ${contacted} × 100 = ${fmt(achieved)}`,
    });
  } else if (measure === "win_rate" && measured.parts) {
    const { won, lost } = measured.parts;
    lines.push({
      label: look.label,
      text:
        achieved === null
          ? __("No leads won or lost yet, so there's nothing to divide.")
          : `${won} ÷ (${won} + ${lost}) × 100 = ${fmt(achieved)}`,
    });
  }

  if (achieved === null)
    return {
      achieved,
      percent: null,
      pacePercent: null,
      standing: "none",
      standingText: __("Nothing to count yet"),
      lines,
    };

  const percent = target > 0 ? (achieved / target) * 100 : 100;
  lines.push({
    label: __("Progress"),
    text: isRate
      ? __("{0} against a target of {1}", fmt(achieved), fmt(target))
      : `${fmt(achieved)} ÷ ${fmt(target)} × 100 = ${Math.round(percent)}%`,
  });

  // a sum builds up over the month, so it is measured against an even pace; a rate isn't
  let pacePercent: number | null = null;
  let expected = 0;
  if (!isRate && !progress.month_over && progress.to_date) {
    const day = dayjs(progress.to_date);
    const days = day.daysInMonth();
    pacePercent = (day.date() / days) * 100;
    expected = (target * day.date()) / days;
    lines.push({
      label: __("Expected by today"),
      text: __(
        "{0} × {1} days so far ÷ {2} days = {3}",
        fmt(target),
        String(day.date()),
        String(days),
        fmt(expected)
      ),
    });
  }

  let standing: Standing;
  let standingText: string;
  if (achieved >= target) {
    standing = "done";
    standingText = __("Target reached");
  } else if (isRate) {
    standing = "below";
    standingText = __(
      "{0} points below target",
      String(round(target - achieved))
    );
  } else if (progress.month_over) {
    standing = "short";
    standingText = __("Ended {0} short", fmt(target - achieved));
  } else if (achieved >= expected) {
    standing = "on_pace";
    standingText = __("On pace");
  } else {
    standing = "behind";
    standingText = __("Behind pace by {0}", fmt(expected - achieved));
  }
  return { achieved, percent, pacePercent, standing, standingText, lines };
}

/** The period a progress was counted over, in words: "1 – 18 Nov 2026". */
export function countedOver(progress: Progress) {
  if (!progress.from_date || !progress.to_date) return "";
  const from = dayjs(progress.from_date);
  const to = dayjs(progress.to_date);
  return `${from.format("D")} – ${to.format("D MMM YYYY")}`;
}

/** The Leads list of the leads behind a counted target (null: no list for it). */
export function leadsLink(
  criterion: Criterion,
  progress: Progress,
  owner: string
): RouteLocationRaw | null {
  const metric = criterion.measure && MEASURE_LOOK[criterion.measure].metric;
  if (!metric || !progress.from_date || !progress.to_date) return null;
  return {
    name: "Leads",
    query: {
      view: "all",
      metric,
      period: "custom",
      from: progress.from_date,
      to: progress.to_date,
      owner,
    },
  };
}

/**
 * The month overall, for the team list: each counted target's share reached (capped at
 * 100%) and each KPI (confirmed 100%, else 0), averaged; and how many are behind. Targets
 * that are information only (Industry, Location) are left out.
 */
export function overallOf(
  target: Target,
  progress: Progress,
  currency: string
) {
  const shares: number[] = [];
  let behind = 0;
  for (const criterion of target.criteria) {
    if (criterion.value_type === "Text") {
      if (isKpi(criterion))
        shares.push(criterion.kpi_status === "Confirmed" ? 100 : 0);
      continue;
    }
    const measured =
      criterion.measure && progress.criteria?.[criterion.criterion];
    if (!measured) continue;
    const result = progressOf(criterion, measured, progress, currency);
    if (result.percent !== null) shares.push(Math.min(result.percent, 100));
    if (["behind", "short", "below"].includes(result.standing)) behind++;
  }
  const percent = shares.length
    ? Math.round(shares.reduce((a, b) => a + b, 0) / shares.length)
    : null;
  return { percent, behind };
}
