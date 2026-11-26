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
const WEEKS_BACK = 26;

/** The sheet fields kept on a KSA lead, as update_lead takes them. */
export interface SheetFields {
  designation: string;
  requirement: string;
  conversion: string;
  visits: number;
  follow_up: string;
  remarks: string;
}

/** One lead in the template's columns (get_week's rows, get_lead_sheet). */
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
  week_start: string;
  week_end: string;
  this_week: string;
  today: string;
  sees_team: boolean;
  people: { user: string; full_name: string }[];
  rows: WeekRow[];
}

/** "22 – 28 Nov 2026": a week from its Sunday. */
export function weekLabel(start: string): string {
  const from = dayjs(start);
  const to = from.add(6, "day");
  const fromText = from.format(from.month() === to.month() ? "D" : "D MMM");
  return `${fromText} – ${to.format("D MMM YYYY")}`;
}

/** The weeks a report may be read for, newest first, ending with the current one. */
export function weekOptions(thisWeek: string) {
  const start = dayjs(thisWeek);
  return Array.from({ length: WEEKS_BACK }, (_, i) => {
    const value = start.subtract(i, "week").format("YYYY-MM-DD");
    return { value, label: weekLabel(value) };
  });
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
