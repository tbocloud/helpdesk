/**
 * Where the content board and sheet open, so today's and the coming days' posts are on
 * screen instead of below a month of past days. Pure functions: dates are "YYYY-MM-DD"
 * strings, which compare correctly as text.
 */

export interface DayGroup {
  date: string;
  /** The day has a post that isn't published or cancelled and has passed its time. */
  needsAction: boolean;
}

export interface DayPlan<D extends DayGroup> {
  /** Past days folded into the "Earlier this month" row. */
  earlier: D[];
  /** The days listed, in date order. */
  shown: D[];
  /** Show the "Today: nothing scheduled" marker. */
  todayMarker: boolean;
  /** The first day after today: where the marker sits and what it names. */
  next: string | null;
  /** The day to open on: today, else the marker ("today"), else the next day. */
  target: string | null;
}

/**
 * Splits a period's days around today.
 *
 * - `collapsePast` (the All filter in a Week or Month view) folds past days into one row,
 *   except days that still need action: missed posts stay listed, as the "needs action"
 *   banner points at them. Nothing folds when no day is today or later, so a past month
 *   (or a month with nothing left) still lists everything.
 * - `markToday` (today is in the period and the filter can show today's posts) adds the
 *   marker when today has no posts.
 */
export function planDays<D extends DayGroup>(
  days: D[],
  today: string,
  opts: { collapsePast: boolean; markToday: boolean }
): DayPlan<D> {
  const ahead = days.some((d) => d.date >= today);
  const earlier =
    opts.collapsePast && ahead
      ? days.filter((d) => d.date < today && !d.needsAction)
      : [];
  const shown = earlier.length
    ? days.filter((d) => !earlier.includes(d))
    : days;
  const hasToday = days.some((d) => d.date === today);
  const next = days.find((d) => d.date > today)?.date ?? null;
  // an empty period already says "Nothing planned", so it needs no marker
  const todayMarker = opts.markToday && days.length > 0 && !hasToday;
  return {
    earlier,
    shown,
    todayMarker,
    next,
    target: hasToday ? today : todayMarker ? "today" : next,
  };
}

/** The first date on or after today, for the sheet's rows; null when all are past. */
export function firstFromToday(dates: string[], today: string): string | null {
  return dates.find((d) => d >= today) ?? null;
}

/**
 * Scrolls an element to the top of its list unless it already sits in the top part of
 * the screen, so opening the board doesn't jump away from the summary when today is
 * already in view.
 */
export function revealIfLow(el: Element | null, smooth = false) {
  if (!el) return;
  if (el.getBoundingClientRect().top < window.innerHeight * 0.6) return;
  el.scrollIntoView({ block: "start", behavior: smooth ? "smooth" : "auto" });
}

/** Smooth scrolling only for people who haven't asked for less motion. */
export function prefersMotion() {
  return !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}
