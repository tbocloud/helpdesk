import { money } from "@/components/invoicing/invoices";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import type { Component } from "vue";
import type { RouteLocationRaw } from "vue-router";
import LucideHash from "~icons/lucide/hash";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideFileText from "~icons/lucide/file-text";
import LucideIndianRupee from "~icons/lucide/indian-rupee";
import LucidePercent from "~icons/lucide/percent";
import LucideTrendingDown from "~icons/lucide/trending-down";
import LucideTrendingUp from "~icons/lucide/trending-up";
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
  /** with no targets: whether they already asked a Sales Head for them */
  asked: boolean;
}

/** Each kind's icon and colour, as the owner's mockups draw them (2026-11-22), so a kind
 * reads at a glance: money green, rates violet, counts blue, written targets amber. `tile`
 * is the soft square and the pill (always with the kind's name), `bar` a card's top edge. */
export const VALUE_TYPE_LOOK: Record<
  ValueType,
  { label: string; icon: Component; tile: string; bar: string }
> = {
  Amount: {
    label: __("Amount"),
    icon: LucideIndianRupee,
    tile: "bg-success-soft text-success",
    bar: "bg-success",
  },
  Number: {
    label: __("Number"),
    icon: LucideHash,
    tile: "bg-info-soft text-info",
    bar: "bg-info",
  },
  Percent: {
    label: __("Percent"),
    icon: LucidePercent,
    tile: "bg-violet-soft text-violet",
    bar: "bg-violet",
  },
  Text: {
    label: __("Text"),
    icon: LucideFileText,
    tile: "bg-warning-soft text-warning",
    bar: "bg-warning",
  },
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
 * Each standing's colour and icon, so a cell, a bar and a line all read the same way:
 * reached green, on pace blue, behind amber (never red: a target not reached yet isn't a
 * failure, ui-guidelines §8), nothing counted gray. Always next to the standing in words.
 */
export const STANDING_LOOK: Record<
  Standing,
  { fill: string; ink: string; cell: string; icon: Component }
> = {
  done: {
    fill: "bg-success",
    ink: "text-success",
    cell: "border-[color-mix(in_srgb,var(--success)_30%,transparent)] bg-success-soft",
    icon: LucideCircleCheck,
  },
  on_pace: {
    fill: "bg-info",
    ink: "text-info",
    cell: "border-[color-mix(in_srgb,var(--info)_30%,transparent)] bg-info-soft",
    icon: LucideTrendingUp,
  },
  behind: {
    fill: "bg-warning",
    ink: "text-warning",
    cell: "border-[color-mix(in_srgb,var(--warning)_30%,transparent)] bg-warning-soft",
    icon: LucideTrendingDown,
  },
  short: {
    fill: "bg-warning",
    ink: "text-warning",
    cell: "border-[color-mix(in_srgb,var(--warning)_30%,transparent)] bg-warning-soft",
    icon: LucideTrendingDown,
  },
  below: {
    fill: "bg-warning",
    ink: "text-warning",
    cell: "border-[color-mix(in_srgb,var(--warning)_30%,transparent)] bg-warning-soft",
    icon: LucideTrendingDown,
  },
  none: {
    fill: "bg-surface-gray-5",
    ink: "text-ink-gray-6",
    cell: "border-outline-gray-2 bg-surface-gray-1",
    icon: LucideCircleDashed,
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
 * 100%) and each KPI (confirmed 100%, else 0), averaged; how many are behind and how many
 * are reached (a confirmed KPI is reached). Targets that are information only (Industry,
 * Location) are left out.
 */
export function overallOf(
  target: Target,
  progress: Progress,
  currency: string
) {
  const shares: number[] = [];
  let behind = 0;
  let reached = 0;
  for (const criterion of target.criteria) {
    if (criterion.value_type === "Text") {
      if (!isKpi(criterion)) continue;
      const confirmed = criterion.kpi_status === "Confirmed";
      shares.push(confirmed ? 100 : 0);
      if (confirmed) reached++;
      continue;
    }
    const measured =
      criterion.measure && progress.criteria?.[criterion.criterion];
    if (!measured) continue;
    const result = progressOf(criterion, measured, progress, currency);
    if (result.percent !== null) shares.push(Math.min(result.percent, 100));
    if (["behind", "short", "below"].includes(result.standing)) behind++;
    if (result.standing === "done") reached++;
  }
  const percent = shares.length
    ? Math.round(shares.reduce((a, b) => a + b, 0) / shares.length)
    : null;
  return { percent, behind, reached, counted: shares.length };
}

/**
 * How far into the month today is: a running month has a pace (the share of its days gone),
 * a past one is over, a later one hasn't begun.
 */
export function monthPace(month: string) {
  const start = dayjs(`${month}-01`);
  const days = start.daysInMonth();
  const today = dayjs();
  if (today.isBefore(start, "month"))
    return { state: "ahead" as const, day: 0, days, percent: 0 };
  if (today.isAfter(start, "month"))
    return { state: "over" as const, day: days, days, percent: 100 };
  const day = today.date();
  return {
    state: "running" as const,
    day,
    days,
    percent: Math.round((day / days) * 100),
  };
}

/** One person's target in the team's grid: the figure, what it is out of, and how it stands. */
export interface TargetCell {
  value: string;
  of: string;
  /** share of the target reached; null with no bar to draw */
  percent: number | null;
  standing: Standing;
  /** the standing in words, for the cell's title and screen readers */
  text: string;
  counting: boolean;
}

export function targetCell(
  criterion: Criterion,
  progress: Progress | null,
  currency: string
): TargetCell {
  const base = {
    percent: null,
    standing: "none" as Standing,
    counting: false,
  };
  if (criterion.value_type === "Text") {
    const status = criterion.kpi_status;
    const text =
      status === "Confirmed"
        ? __("Confirmed")
        : status === "Done"
        ? __("Done, to confirm")
        : __("Not done yet");
    return {
      ...base,
      value: __("KPI"),
      of: text,
      text,
      standing:
        status === "Confirmed"
          ? "done"
          : status === "Done"
          ? "on_pace"
          : "none",
    };
  }
  const target = targetText(criterion, currency);
  if (!criterion.measure)
    return { ...base, value: target, of: __("Target only"), text: "" };
  if (!progress)
    return { ...base, value: "—", of: "", text: "", counting: true };
  const measured =
    progress.state === "counted"
      ? progress.criteria?.[criterion.criterion]
      : null;
  if (!measured)
    return {
      ...base,
      value: "—",
      of: __("of {0}", target),
      text: __("Nothing counted"),
    };
  const result = progressOf(criterion, measured, progress, currency);
  return {
    value:
      result.achieved === null
        ? "—"
        : figureText(criterion, result.achieved, currency),
    of: __("of {0}", target),
    percent: result.percent,
    standing: result.standing,
    text: result.standingText,
    counting: false,
  };
}

/** Where a person's month stands on Team targets: behind first, not set last. */
export type TeamStanding = "behind" | "on_track" | "uncounted" | "unset";

/** One person on Team targets: their month's progress (null while read) and overall standing. */
export interface TeamRow {
  person: TargetPerson;
  progress: Progress | null;
  overall: ReturnType<typeof overallOf> | null;
  standing: TeamStanding;
}

/** Who Team targets shows: everyone, those with targets, those behind, those without. */
export type TeamFilter = "all" | "with" | "behind" | "unset";

/** Why a numeric target shows no progress, in words; "" while it is being counted. */
export function uncountedNote(criterion: Criterion, progress: Progress | null) {
  const { measure } = criterion;
  if (!measure) return __("Target only: not counted from the leads.");
  if (!progress) return "";
  const label = MEASURE_LOOK[measure].label.toLowerCase();
  if (progress.state === "not_started")
    return __("Counts {0} once the month begins.", label);
  if (progress.state === "unavailable")
    return __("Couldn't count it: {0}", progress.reason || "");
  return __("Counts {0}.", label);
}

/** Why a person's month has no overall, in a few words. */
export function uncountedText(progress: Progress) {
  if (progress.state === "not_started") return __("Not begun");
  if (progress.state === "unavailable") return __("Couldn't count");
  return __("Nothing counted");
}

/** One person on the Scoreboard: their counted month overall and their rank. */
export interface RankedRow {
  row: TeamRow;
  overall: ReturnType<typeof overallOf> & { percent: number };
  rank: number;
}

/**
 * The Scoreboard's order: highest month overall first; level on that, more targets reached
 * first. People level on both share a rank (1, 2, 2, 4). Only those with an overall.
 */
export function rankRows(rows: TeamRow[]): RankedRow[] {
  const sorted = rows
    .filter((r) => r.overall?.percent != null)
    .map((row) => ({ row, overall: row.overall as RankedRow["overall"] }))
    .sort(
      (a, b) =>
        b.overall.percent - a.overall.percent ||
        b.overall.reached - a.overall.reached ||
        a.row.person.full_name.localeCompare(b.row.person.full_name)
    );
  const ranked: RankedRow[] = [];
  sorted.forEach((entry, i) => {
    const before = ranked[i - 1];
    const level =
      before &&
      before.overall.percent === entry.overall.percent &&
      before.overall.reached === entry.overall.reached;
    ranked.push({ ...entry, rank: level ? before.rank : i + 1 });
  });
  return ranked;
}

/**
 * A ranked person against the month: behind (any target behind pace), ahead (none behind
 * and the overall at or past today's pace), else on pace. A month over has no pace.
 */
export function paceStatus(
  overall: RankedRow["overall"],
  pace: ReturnType<typeof monthPace>
): "behind" | "ahead" | "on_pace" {
  if (overall.behind) return "behind";
  if (pace.state === "running" && overall.percent >= pace.percent)
    return "ahead";
  return "on_pace";
}

/** "1st", "2nd", "3rd", "4th"… */
export function ordinal(rank: number) {
  if (rank === 1) return __("1st");
  if (rank === 2) return __("2nd");
  if (rank === 3) return __("3rd");
  return __("{0}th", String(rank));
}
