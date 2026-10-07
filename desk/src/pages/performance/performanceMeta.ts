import type { Tone } from "@/components/tone";
import { __ } from "@/translation";

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

/**
 * Who does what on a post, in the order the content board lists them, translated.
 * Literal __() calls so the translation extractor finds each label.
 */
export function roles() {
  return [
    { role: "writer", label: __("Writer"), short: __("W") },
    { role: "designer", label: __("Designer"), short: __("D") },
    { role: "video_editor", label: __("Video editor"), short: __("V") },
    { role: "marketer", label: __("Digital marketer"), short: __("M") },
  ];
}
