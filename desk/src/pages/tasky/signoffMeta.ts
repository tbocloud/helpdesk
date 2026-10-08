import LucideCircle from "~icons/lucide/circle";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideCircleHelp from "~icons/lucide/circle-help";
import LucidePenLine from "~icons/lucide/pen-line";
import LucideRotateCcw from "~icons/lucide/rotate-ccw";
import LucideSend from "~icons/lucide/send";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import type { StatusMeta } from "./taskMeta";

/** A question on a sign-off or a template; `name` is set once it is saved. */
export interface SignoffQuestion {
  name?: string;
  section: string;
  question: string;
  help_text: string;
  response?: string;
}

// Labels are untranslated keys; callers pass them through __() at render time.
const SIGNOFF_STATUS: Record<string, StatusMeta> = {
  Draft: { label: "Draft", icon: LucideCircleDashed, tone: "neutral" },
  Sent: { label: "Sent", icon: LucideSend, tone: "neutral" },
  "In progress": { label: "In progress", icon: LucideCircleDot, tone: "info" },
  "Needs clarification": {
    label: "Needs clarification",
    icon: LucideCircleHelp,
    tone: "warning",
  },
  "Ready to sign": {
    label: "Ready to sign",
    icon: LucidePenLine,
    tone: "info",
  },
  Signed: { label: "Signed", icon: LucideCircleCheck, tone: "success" },
  Reopened: { label: "Reopened", icon: LucideRotateCcw, tone: "warning" },
};

const RESPONSE: Record<string, StatusMeta> = {
  Pending: { label: "Pending", icon: LucideCircle, tone: "neutral" },
  Done: { label: "Done", icon: LucideCircleCheck, tone: "success" },
  "Not clear": { label: "Not clear", icon: LucideCircleHelp, tone: "warning" },
  Escalated: { label: "Escalated", icon: LucideTriangleAlert, tone: "danger" },
};

export function signoffStatusMeta(status: string): StatusMeta {
  return SIGNOFF_STATUS[status] ?? SIGNOFF_STATUS.Draft;
}

export function responseMeta(response: string): StatusMeta {
  return RESPONSE[response] ?? RESPONSE.Pending;
}

export function needsFollowUp(response?: string): boolean {
  return response === "Not clear" || response === "Escalated";
}

/** Questions grouped by section, in their order; a blank section is "General". */
export function groupBySection<T extends { section?: string }>(
  items: T[],
  general: string
): { section: string; items: (T & { n: number })[] }[] {
  const groups: { section: string; items: (T & { n: number })[] }[] = [];
  items.forEach((item, i) => {
    const section = item.section || general;
    let group = groups.find((g) => g.section === section);
    if (!group) groups.push((group = { section, items: [] }));
    group.items.push({ ...item, n: i + 1 });
  });
  return groups;
}
