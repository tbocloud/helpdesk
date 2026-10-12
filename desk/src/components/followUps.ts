/** Follow-ups (docs/follow-ups.md): the ladder's words and the banner's parts. */
import { __ } from "@/translation";

/** helpdesk.follow_ups.summary_for */
export interface FollowUpSummary {
  overdue: number;
  escalated: number;
  breached: number;
  waiting_on_you: number;
  total: number;
}

export function escalationLabel(level: number): string {
  if (level >= 3) return __("Escalated to managers");
  if (level === 2) return __("Escalated to head");
  if (level === 1) return __("Escalated to lead");
  return "";
}

export interface SummaryPart {
  key: keyof FollowUpSummary;
  label: string;
  danger: boolean;
}

/** "3 overdue · 1 escalated to your head · 2 waiting on you", only the non-zero parts. */
export function summaryParts(s: FollowUpSummary | null | undefined): SummaryPart[] {
  if (!s) return [];
  const parts: SummaryPart[] = [
    { key: "breached", label: __("{0} SLA breached", String(s.breached)), danger: true },
    { key: "overdue", label: __("{0} overdue", String(s.overdue)), danger: true },
    {
      key: "escalated",
      label: __("{0} escalated to your head", String(s.escalated)),
      danger: true,
    },
    {
      key: "waiting_on_you",
      label: __("{0} waiting on you", String(s.waiting_on_you)),
      danger: false,
    },
  ];
  return parts.filter((p) => s[p.key] > 0);
}

/** helpdesk.follow_ups._row: one item in the managers' Follow-ups section */
export interface FollowUpRow {
  doctype: string;
  name: string;
  title: string;
  level: number;
  days: number;
  /** a path inside /helpdesk */
  link: string;
  owners: { user: string; full_name: string }[];
}
