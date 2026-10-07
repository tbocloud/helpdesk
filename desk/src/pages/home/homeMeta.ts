import type { WorkItem } from "@/pages/work/workMeta";
import type { Tone } from "@/pages/tasky/taskMeta";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import type { RouteLocationRaw } from "vue-router";

export interface DaySection<T> {
  count: number;
  items: T[];
}

export interface FileForMe {
  name: string;
  file_name: string;
  project: string;
  project_name: string;
  uploaded_by_name: string;
  creation: string;
}

export interface YourDay {
  tasks: DaySection<WorkItem>;
  replies: DaySection<WorkItem>;
  approvals: DaySection<WorkItem>;
  files: DaySection<FileForMe>;
}

export interface TicketSummary {
  open: number;
  new_today: number;
  unassigned: number;
  sla_breached: number;
  first_reply_overdue: number;
  waiting_on_customer: number;
  rating: { average: number | null; count: number; low: number };
  by_customer: { customer: string | null; open: number }[];
}

export interface AttentionItem extends WorkItem {
  /** Days since our last reply, on tickets waiting on the customer. */
  waiting_days?: number;
}

export type AttentionReason =
  | "overdue"
  | "at_risk"
  | "unassigned_tickets"
  | "waiting_on_customer";

export interface AttentionGroup {
  key: AttentionReason;
  count: number;
  items: AttentionItem[];
}

export interface EndingProject {
  name: string;
  project_name: string;
  customer: string | null;
  lead_name: string | null;
  progress: number;
  open: number;
  overdue: number;
  expected_end_date: string;
  days_left: number;
}

export interface Person {
  user: string;
  full_name: string;
  open: number;
  working: number;
  projects: string[];
}

export interface Company {
  tickets: TicketSummary;
  work: Record<string, number>;
  attention_groups: AttentionGroup[];
  project_count: number;
  ending_soon: EndingProject[];
  people: Person[];
  people_busy: number;
  people_free: number | null;
  free_people: string[];
}

export interface Systems {
  connections: {
    name: string;
    customer_name: string | null;
    site_url: string | null;
    connection_status: string | null;
    last_error: string | null;
  }[];
  mailboxes: {
    name: string;
    email_id: string;
    enable_incoming: number;
    no_failed: number;
  }[];
  teams: { enabled: boolean; platform: string | null };
  chat: { enabled: boolean; open: number };
  ai: { calls_today: number; triage_failed: number };
}

export interface HomeData {
  mine: {
    counts: { total: number; overdue: number; key: number; at_risk: number };
  };
  day: YourDay;
  company: Company | null;
  systems: Systems | null;
}

/** One fact in the header's status line; a tone other than neutral means it needs action. */
export interface StatusPart {
  key: string;
  label: string;
  tone: Tone;
}

/** `one` for a count of 1, else `many` with {0} filled in; both already translated. */
export function countLabel(count: number, one: string, many: string) {
  return count === 1 ? one : many.replace("{0}", String(count));
}

/**
 * The header's one-line status: problems and things waiting for the user, most
 * urgent first. An empty list means nothing needs action ("All clear").
 */
export function statusParts(data: HomeData): StatusPart[] {
  const parts: StatusPart[] = [];
  const add = (
    key: string,
    count: number,
    one: string,
    many: string,
    tone: Tone
  ) => {
    if (count > 0)
      parts.push({ key, label: countLabel(count, one, many), tone });
  };
  const company = data.company;
  if (company) {
    const t = company.tickets;
    const w = company.work;
    add(
      "sla",
      t.sla_breached,
      __("1 SLA breached"),
      __("{0} SLAs breached"),
      "danger"
    );
    add(
      "first_reply",
      t.first_reply_overdue,
      __("1 first reply overdue"),
      __("{0} first replies overdue"),
      "danger"
    );
    add(
      "overdue",
      w.overdue ?? 0,
      __("1 item overdue"),
      __("{0} items overdue"),
      "danger"
    );
    add(
      "at_risk",
      w.at_risk ?? 0,
      __("1 item at risk"),
      __("{0} items at risk"),
      "warning"
    );
    add(
      "unassigned",
      t.unassigned,
      __("1 ticket unassigned"),
      __("{0} tickets unassigned"),
      "warning"
    );
  } else {
    add(
      "my_overdue",
      data.mine.counts.overdue,
      __("1 of your items overdue"),
      __("{0} of your items overdue"),
      "danger"
    );
  }
  add(
    "replies",
    data.day.replies.count,
    __("1 ticket waiting for your reply"),
    __("{0} tickets waiting for your reply"),
    "neutral"
  );
  add(
    "approvals",
    data.day.approvals.count,
    __("1 task waiting for your review"),
    __("{0} tasks waiting for your review"),
    "neutral"
  );
  return parts;
}

/** "All clear on tickets" when the ticket stats are clean but other work isn't. */
export function ticketsClear(data: HomeData) {
  const t = data.company?.tickets;
  return !!t && !t.sla_breached && !t.first_reply_overdue && !t.unassigned;
}

function nowParam() {
  return dayjs().format("YYYY-MM-DD HH:mm:ss");
}

const OPEN_CATEGORIES = ["status_category", "in", ["Open", "Paused"]];

/** The agent tickets list, narrowed by filters in the URL (ListViewBuilder reads `?filters=`). */
export function ticketsLink(filters: unknown[][] = []): RouteLocationRaw {
  return filters.length
    ? { name: "TicketsAgent", query: { filters: JSON.stringify(filters) } }
    : { name: "TicketsAgent" };
}

export const ticketLinks = {
  open: () => ticketsLink([OPEN_CATEGORIES]),
  newToday: () =>
    ticketsLink([["creation", ">=", dayjs().format("YYYY-MM-DD")]]),
  unassigned: () => ticketsLink([OPEN_CATEGORIES, ["_assign", "is", "not set"]]),
  slaBreached: () =>
    ticketsLink([
      ["status_category", "=", "Open"],
      ["resolution_by", "<", nowParam()],
    ]),
  firstReplyOverdue: () =>
    ticketsLink([
      ["status_category", "=", "Open"],
      ["first_responded_on", "is", "not set"],
      ["response_by", "<", nowParam()],
    ]),
  waitingOnCustomer: () =>
    ticketsLink([
      ["status_category", "=", "Paused"],
      ["status", "!=", "Waiting on Task"],
    ]),
  rated: () => ticketsLink([["feedback_rating", ">", 0]]),
};

/** The Overview opened on one of its buckets ("overdue" is its default). */
export function overviewLink(bucket: string): RouteLocationRaw {
  return bucket === "overdue"
    ? { name: "WorkOverview" }
    : { name: "WorkOverview", query: { bucket } };
}

export function reasonLabel(key: AttentionReason) {
  return {
    overdue: __("Overdue"),
    at_risk: __("At risk"),
    unassigned_tickets: __("Unassigned tickets"),
    waiting_on_customer: __("Waiting on the customer"),
  }[key];
}

export function reasonLink(key: AttentionReason): RouteLocationRaw {
  if (key === "unassigned_tickets") return ticketLinks.unassigned();
  if (key === "waiting_on_customer") return ticketLinks.waitingOnCustomer();
  return overviewLink(key);
}

export function reasonTone(key: AttentionReason): Tone {
  return key === "overdue" ? "danger" : key === "at_risk" ? "warning" : "info";
}

export function endingLabel(days: number) {
  if (days < 0) {
    const late = -days;
    return late === 1
      ? __("Ended 1 day ago")
      : __("Ended {0} days ago", String(late));
  }
  if (days === 0) return __("Ends today");
  if (days === 1) return __("Ends tomorrow");
  return __("Ends in {0} days", String(days));
}

export function greeting(name: string, hour = dayjs().hour()) {
  if (hour < 12) return __("Good morning, {0}", name);
  if (hour < 17) return __("Good afternoon, {0}", name);
  return __("Good evening, {0}", name);
}
