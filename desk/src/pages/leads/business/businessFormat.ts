import { money } from "@/components/invoicing/invoices";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import type { BusinessOverview } from "../leads";

export const FUNNEL_LABELS: Record<string, string> = {
  created: __("Came in"),
  contacted: __("Contacted"),
  meeting: __("Meeting held"),
  proposal: __("Proposal"),
  won: __("Won"),
};

/** An amount in full, in the company currency. */
export function fullAmount(value: number, currency: string) {
  return currency ? money(value, currency, true) : String(Math.round(value));
}

/** An amount short enough for a tile or an axis (₹12.4L, ₹1.2Cr); the full figure is
 * always on the tile's title or in the table below. */
export function shortAmount(value: number, currency: string) {
  try {
    return new Intl.NumberFormat(currency === "INR" ? "en-IN" : undefined, {
      style: "currency",
      currency,
      notation: "compact",
      maximumFractionDigits: 1,
    })
      .format(value || 0)
      .replace(/\s?(Cr|L|K|M|B)$/i, "$1");
  } catch {
    return String(Math.round(value || 0));
  }
}

export function monthLabel(month: string, withYear = false) {
  return dayjs(month).format(withYear ? "MMM YY" : "MMM");
}

/** "1 Oct – 30 Oct 2026" */
export function rangeText(data: Pick<BusinessOverview, "from_date" | "to_date">) {
  const from = dayjs(data.from_date);
  const to = dayjs(data.to_date);
  if (from.isSame(to, "day")) return to.format("D MMM YYYY");
  return from.isSame(to, "year")
    ? `${from.format("D MMM")} – ${to.format("D MMM YYYY")}`
    : `${from.format("D MMM YYYY")} – ${to.format("D MMM YYYY")}`;
}

export interface BusinessRow {
  key?: string;
  label: string;
  /** the bar's length, against the largest row (or `max`) */
  value: number;
  /** the number as written */
  text: string;
  sub?: string;
}
