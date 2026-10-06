/** Gray unless the colour says how something went; always next to a number or label. */
export type Tone = "neutral" | "success" | "warning" | "danger";

export const TRACK: Record<Tone, string> = {
  neutral: "bg-surface-gray-2",
  success: "bg-success-soft",
  warning: "bg-warning-soft",
  danger: "bg-danger-soft",
};
export const FILL: Record<Tone, string> = {
  neutral: "bg-surface-gray-7",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
};
/** Text colour, on a tone's soft background or on the page. */
export const INK: Record<Tone, string> = {
  neutral: "text-ink-gray-8",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
};

/** Score colour: green when on time, amber when late or reworked, red when missed. */
export function scoreTone(score: number | null | undefined): Tone {
  if (score == null) return "neutral";
  if (score >= 90) return "success";
  if (score < 40) return "danger";
  return "warning";
}

/** On-time colour: green at 95% and up, amber from 80%, red under that. */
export function onTimeTone(pct: number | null | undefined): Tone {
  if (pct == null) return "neutral";
  if (pct >= 95) return "success";
  if (pct >= 80) return "warning";
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

/** Who does what on a post, in the order the content board lists them. */
export const ROLES = [
  { role: "writer", label: "Writer", short: "W" },
  { role: "designer", label: "Designer", short: "D" },
  { role: "video_editor", label: "Video editor", short: "V" },
  { role: "marketer", label: "Digital marketer", short: "M" },
] as const;
