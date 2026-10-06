export type Tone =
  | "brand"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "teal"
  | "pink";

export const TRACK: Record<Tone, string> = {
  brand: "bg-brand-soft",
  success: "bg-success-soft",
  warning: "bg-warning-soft",
  danger: "bg-danger-soft",
  info: "bg-info-soft",
  teal: "bg-teal-soft",
  pink: "bg-pink-soft",
};
export const FILL: Record<Tone, string> = {
  brand: "bg-brand",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-info",
  teal: "bg-teal",
  pink: "bg-pink",
};
/** Text colour on a tone's soft background. */
export const INK: Record<Tone, string> = {
  brand: "text-brand-ink",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  info: "text-info",
  teal: "text-teal",
  pink: "text-pink",
};

/** Score colour: green when strong, red when weak, brand in between. */
export function scoreTone(score: number | null | undefined): Tone {
  if (score == null) return "brand";
  if (score >= 90) return "success";
  if (score < 40) return "danger";
  return "brand";
}

/** On-time colour: green at 95% and up, red under 80%. */
export function onTimeTone(pct: number | null | undefined): Tone | null {
  if (pct == null) return null;
  if (pct >= 95) return "success";
  if (pct >= 80) return "brand";
  return "danger";
}

export const channelColor = (channel: string) =>
  `var(--channel-${channel.toLowerCase()}, var(--ink-gray-7))`;

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
