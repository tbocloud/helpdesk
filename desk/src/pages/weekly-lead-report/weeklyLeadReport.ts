import { __ } from "@/translation";
import { dayjs } from "frappe-ui";

export const WEEKLY_API = "helpdesk.api.weekly_lead_report";

// the KSA Lead's sheet fields (weekly_lead_report.CONVERSIONS, FOLLOW_UPS, SEGMENT_LABELS)
export const CONVERSIONS = ["High", "Medium", "Low", "Not Possible"] as const;
export const FOLLOW_UPS = ["Yes", "No"] as const;
export const REQUIREMENTS = [
  { value: "Erpnext", label: "ERPNext" },
  { value: "Digital", label: "Digital Marketing" },
] as const;
export const MAX_VISITS = 99;
// a filter value that keeps the leads with the field empty (weekly_lead_report.NOT_SET)
export const NOT_SET = "not_set";

/** The sheet fields kept on a KSA lead, as update_lead takes them. */
export interface SheetFields {
  designation: string;
  requirement: string;
  conversion: string;
  visits: number;
  follow_up: string;
  remarks: string;
}

/** One lead in the template's columns (get_report's rows, get_lead_sheet). */
export interface WeekRow extends SheetFields {
  lead: string;
  salesperson: string;
  salesperson_name?: string;
  updated: string;
  company_name: string;
  contact_number: string;
  email: string;
  business: string;
  contact_name: string;
  requirement_label: string;
  quoted: boolean;
  quoted_value: number | null;
  currency: string | null;
  quotation: string;
  quotation_count: number;
}

export interface WeekData {
  division: string;
  division_name: string;
  from_date: string;
  to_date: string;
  sees_team: boolean;
  people: { user: string; full_name: string }[];
  rows: WeekRow[];
}

// the leads created or updated in the period; a week runs Sunday to Saturday, as KSA's
// work week (weekly_lead_report.week_start)
export const PERIODS = [
  { value: "today", label: __("Today") },
  { value: "yesterday", label: __("Yesterday") },
  { value: "this_week", label: __("This week") },
  { value: "last_week", label: __("Last week") },
  { value: "this_month", label: __("This month") },
  { value: "custom", label: __("Between dates…") },
];
export const DEFAULT_PERIOD = "this_week";

/** The first and last day of `period`; for "custom", `from` and `to` (null until both
 * are picked). */
export function periodRange(
  period: string,
  from: string,
  to: string
): { from_date: string; to_date: string } | null {
  const fmt = (d: ReturnType<typeof dayjs>) => d.format("YYYY-MM-DD");
  const today = dayjs();
  const sunday = today.subtract(today.day(), "day");
  const range = (a: ReturnType<typeof dayjs>, b: ReturnType<typeof dayjs>) => ({
    from_date: fmt(a),
    to_date: fmt(b),
  });
  switch (period) {
    case "today":
      return range(today, today);
    case "yesterday":
      return range(today.subtract(1, "day"), today.subtract(1, "day"));
    case "last_week":
      return range(sunday.subtract(7, "day"), sunday.subtract(1, "day"));
    case "this_month":
      return range(today.startOf("month"), today.endOf("month"));
    case "custom":
      return from && to ? { from_date: from, to_date: to } : null;
    default:
      return range(sunday, sunday.add(6, "day"));
  }
}

/** "22 – 28 Nov 2026", or one day as "Wed, 25 Nov 2026". */
export function rangeLabel(from: string, to: string): string {
  const a = dayjs(from);
  const b = dayjs(to);
  if (from === to) return b.format("ddd, D MMM YYYY");
  const sameYear = a.year() === b.year();
  const first = a.format(
    sameYear ? (a.month() === b.month() ? "D" : "D MMM") : "D MMM YYYY"
  );
  return `${first} – ${b.format("D MMM YYYY")}`;
}

/** A select's options, "Not set" first. */
export function optionsOf(
  values: readonly (string | { value: string; label: string })[]
) {
  return [
    { label: __("Not set"), value: "" },
    ...values.map((v) =>
      typeof v === "string"
        ? { label: __(v), value: v }
        : { label: __(v.label), value: v.value }
    ),
  ];
}
