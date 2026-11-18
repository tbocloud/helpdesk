import { money } from "@/components/invoicing/invoices";
import { __ } from "@/translation";
import type { Component } from "vue";
import LucideHash from "~icons/lucide/hash";
import LucideBanknote from "~icons/lucide/banknote";
import LucidePercent from "~icons/lucide/percent";
import LucideText from "~icons/lucide/text";
import { monthTitle, monthValue } from "../leads/commission";

export { monthTitle, monthValue };

/** How a criterion's target is read; the server's `VALUE_TYPES`. */
export type ValueType = "Amount" | "Number" | "Percent" | "Text";

export interface Criterion {
  criterion: string;
  value_type: ValueType;
  /** a number, or text for a Text criterion; null while not filled in */
  target: number | string | null;
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
  defaults: { criterion: string; value_type: ValueType }[];
  people: TargetPerson[];
}

export interface MyTargets {
  month: string;
  currency: string;
  months: string[];
  target: Target | null;
}

export const VALUE_TYPE_LOOK: Record<
  ValueType,
  { label: string; icon: Component }
> = {
  Amount: { label: __("Amount"), icon: LucideBanknote },
  Number: { label: __("Number"), icon: LucideHash },
  Percent: { label: __("Percent"), icon: LucidePercent },
  Text: { label: __("Text"), icon: LucideText },
};

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
