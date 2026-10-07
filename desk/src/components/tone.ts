/**
 * The one set of status tones. Gray unless the colour says how something went,
 * and always next to an icon, number or label.
 */
export type Tone = "neutral" | "info" | "warning" | "success" | "danger";

// Full class strings (not interpolated) so Tailwind's scanner picks them up.

/** Text colour, on a tone's soft background or on the page. */
export const INK: Record<Tone, string> = {
  neutral: "text-ink-gray-8",
  info: "text-info",
  warning: "text-warning",
  success: "text-success",
  danger: "text-danger",
};

/** A meter's track. */
export const TRACK: Record<Tone, string> = {
  neutral: "bg-surface-gray-2",
  info: "bg-info-soft",
  warning: "bg-warning-soft",
  success: "bg-success-soft",
  danger: "bg-danger-soft",
};

/** A meter's or bar's fill. */
export const FILL: Record<Tone, string> = {
  neutral: "bg-surface-gray-7",
  info: "bg-info",
  warning: "bg-warning",
  success: "bg-success",
  danger: "bg-danger",
};

/** A badge or chip: soft background with the tone's text. */
export const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-surface-gray-2 text-ink-gray-7",
  info: "bg-info-soft text-info",
  warning: "bg-warning-soft text-warning",
  success: "bg-success-soft text-success",
  danger: "bg-danger-soft text-danger",
};
