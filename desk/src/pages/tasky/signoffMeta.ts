import LucideCircle from "~icons/lucide/circle";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideCircleHelp from "~icons/lucide/circle-help";
import LucideEye from "~icons/lucide/eye";
import LucidePenLine from "~icons/lucide/pen-line";
import LucideRotateCcw from "~icons/lucide/rotate-ccw";
import LucideSend from "~icons/lucide/send";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import type { StatusMeta } from "./taskMeta";

// what a sign-off's mail can say, filled in from the sign-off (helpdesk/helpdesk/doctype/
// hd_project_signoff/hd_project_signoff.py, mail_values; docs/project-signoff.md, Mail)
export const PLACEHOLDERS = [
  "contact_salutation",
  "contact_name",
  "customer_name",
  "project_name",
  "modules",
  "training_date",
  "trainer_name",
  "sign_off_link",
  "sender_name",
  "sender_designation",
  "company_name",
];
const PLACEHOLDER = /{{\s*([a-zA-Z_]+)\s*}}/g;

/** The placeholders `text` still has, but the link's (filled as the mail goes out). */
export function unfilledPlaceholders(text: string): string[] {
  return [...new Set([...text.matchAll(PLACEHOLDER)].map((m) => m[1]))].filter(
    (name) => name !== "sign_off_link"
  );
}

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
  // Sent, and the customer opened the link with their code (customer_status)
  Viewed: { label: "Viewed", icon: LucideEye, tone: "info" },
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

// a UAT's answers read as test results (docs/project-signoff.md, UAT)
const UAT_LABELS: Record<string, string> = {
  Done: "Pass",
  "Not clear": "Fail",
  Escalated: "Blocker",
};

export function responseMeta(response: string, uat = false): StatusMeta {
  const meta = RESPONSE[response] ?? RESPONSE.Pending;
  return uat && UAT_LABELS[response]
    ? { ...meta, label: UAT_LABELS[response] }
    : meta;
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
