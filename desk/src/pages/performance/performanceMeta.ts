export type Tone = "brand" | "success" | "warning" | "danger";

export const TRACK: Record<Tone, string> = {
  brand: "bg-brand-soft",
  success: "bg-success-soft",
  warning: "bg-warning-soft",
  danger: "bg-danger-soft",
};
export const FILL: Record<Tone, string> = {
  brand: "bg-brand",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
};

/** Below half of the working hours needs attention; most of them is healthy. */
export function utilTone(pct: number | null | undefined): Tone {
  if (pct == null) return "brand";
  if (pct < 50) return "danger";
  if (pct < 80) return "warning";
  return "success";
}

export function pctText(pct: number | null | undefined) {
  return pct == null ? "—" : `${pct}%`;
}
