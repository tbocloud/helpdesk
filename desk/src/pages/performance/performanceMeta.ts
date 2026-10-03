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

export function pctText(pct: number | null | undefined) {
  return pct == null ? "—" : `${pct}%`;
}

/** How a content post went, in the order charts stack them. */
export const TIMINGS = ["On time", "Late", "Missed", "Upcoming"] as const;
export type Timing = (typeof TIMINGS)[number];

/** Chart colour of each timing: status colours, with "not due yet" neutral. */
export function timingColor(
  c: { success: string; warning: string; danger: string; other: string },
  timing: Timing
) {
  return {
    "On time": c.success,
    Late: c.warning,
    Missed: c.danger,
    Upcoming: c.other,
  }[timing];
}

export function scoreText(score: number | null | undefined) {
  return score == null ? "—" : String(score);
}
