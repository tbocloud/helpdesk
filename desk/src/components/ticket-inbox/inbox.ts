import {
  matchTicketFilter,
  ticketFilters,
  type TicketCondition,
  type TicketFilterKey,
} from "@/pages/ticket/ticketFilters";
import { __ } from "@/translation";
import { useStorage } from "@vueuse/core";
import { call } from "frappe-ui";
import { reactive } from "vue";

/**
 * The agent's ticket inbox (Phase 16): the queue, the search and the rows, kept at module level so the list keeps
 * its place while the agent moves from ticket to ticket. The rows come from helpdesk.api.ticket_area.inbox, through
 * the same filters as the queue counts, so a chip's number is the number of rows it shows.
 */

export type QueueKey = Extract<
  TicketFilterKey,
  | "open"
  | "needsReply"
  | "overdue"
  | "mine"
  | "unassigned"
  | "waiting"
  | "resolved"
>;

export interface Queue {
  key: QueueKey;
  label: string;
  hint: string;
  /** red count while it has tickets */
  urgent?: boolean;
}

export const QUEUES: Queue[] = [
  { key: "open", label: __("All open"), hint: __("Not resolved or closed") },
  {
    key: "needsReply",
    label: __("Needs reply"),
    hint: __("Open: the customer waits for the team"),
  },
  {
    key: "overdue",
    label: __("Overdue"),
    hint: __("Past the first reply (none sent yet) or the resolution time"),
    urgent: true,
  },
  { key: "mine", label: __("Mine"), hint: __("Open, and assigned to you") },
  {
    key: "unassigned",
    label: __("Unassigned"),
    hint: __("Open, and nobody has it"),
  },
  {
    key: "waiting",
    label: __("Waiting"),
    hint: __(
      "Waiting on the customer, a task or on hold: the SLA clock is paused"
    ),
  },
  { key: "resolved", label: __("Resolved"), hint: __("Resolved or closed") },
];

export interface InboxMessage {
  by: "customer" | "team" | "copilot";
  author: string;
  text: string;
  at: string;
  /** the customer's emails since our last reply */
  waiting: number;
  /** the name the customer's newest email gave (for a ticket with no contact) */
  customer_name?: string | null;
}

export interface InboxRow {
  name: string | number;
  subject: string;
  status: string;
  status_category: string;
  priority: string;
  customer: string | null;
  contact: string | null;
  raised_by: string | null;
  modified: string;
  creation: string;
  _assign: string | null;
  _seen: string | null;
  response_by: string | null;
  resolution_by: string | null;
  first_responded_on: string | null;
  resolution_date: string | null;
  last: InboxMessage | null;
  copilot: "approve" | "working" | null;
}

const PAGE = 50;

export const inbox = reactive({
  queue: "open" as QueueKey | "filtered",
  /** a link's own filters (from Home), shown as the Filtered chip */
  filtered: [] as TicketCondition[],
  search: "",
  rows: [] as InboxRow[],
  more: false,
  loading: false,
  loaded: false,
  failed: false,
  counts: {} as Partial<Record<QueueKey, number>>,
});

/** Inbox or the Phase 15 table, per browser. */
export const ticketsLayout = useStorage<"inbox" | "table">(
  "helpdesk-tickets-layout",
  "inbox"
);

function conditions(): TicketCondition[] {
  const base =
    inbox.queue === "filtered" ? inbox.filtered : ticketFilters[inbox.queue]();
  const words = inbox.search.trim();
  return words ? [...base, ["__search", "LIKE", `%${words}%`]] : base;
}

// each load numbers its request and keeps only the latest answer, so a slow one can't overwrite a newer one
let latest = 0;

export async function loadInbox(more = false) {
  const request = ++latest;
  inbox.loading = true;
  try {
    const data: { tickets: InboxRow[]; more: boolean } = await call(
      "helpdesk.api.ticket_area.inbox",
      {
        filters: conditions(),
        start: more ? inbox.rows.length : 0,
        // a refresh keeps as many rows as the agent has loaded
        page_length: more ? PAGE : Math.max(PAGE, inbox.rows.length),
      }
    );
    if (request !== latest) return;
    inbox.rows = more ? [...inbox.rows, ...data.tickets] : data.tickets;
    inbox.more = data.more;
    inbox.failed = false;
    inbox.loaded = true;
  } catch {
    if (request === latest) inbox.failed = true;
  } finally {
    if (request === latest) inbox.loading = false;
  }
}

const counting: Partial<Record<QueueKey, number>> = {};

/** Every queue's number, each its own request (helpdesk.api.ticket_area.count). */
export function countQueues() {
  for (const { key } of QUEUES) {
    const request = (counting[key] = (counting[key] ?? 0) + 1);
    call("helpdesk.api.ticket_area.count", { filters: ticketFilters[key]() })
      .then((n: number) => {
        if (request === counting[key]) inbox.counts[key] = n;
      })
      .catch(() => {});
  }
}

export function refreshInbox() {
  loadInbox();
  countQueues();
}

export function chooseQueue(key: QueueKey) {
  inbox.queue = key;
  inbox.filtered = [];
  inbox.rows = [];
  inbox.loaded = false;
  loadInbox();
}

/** A `?filters=` link (Home's cards, a queue link): its queue, or the Filtered chip. */
export function takeLinkFilters(raw: unknown) {
  if (typeof raw !== "string" || !raw) return false;
  const key = matchTicketFilter(raw);
  if (key && QUEUES.some((q) => q.key === key)) {
    if (inbox.queue !== key) chooseQueue(key as QueueKey);
    return true;
  }
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return false;
    inbox.queue = "filtered";
    inbox.filtered = parsed;
    inbox.rows = [];
    inbox.loaded = false;
    loadInbox();
    return true;
  } catch {
    return false;
  }
}

/** Opening a ticket marks it seen at once in the list (the server records it too). */
export function markSeenInList(ticket: string, user: string) {
  const row = inbox.rows.find((r) => String(r.name) === String(ticket));
  if (!row) return;
  const seen: string[] = row._seen ? JSON.parse(row._seen) : [];
  if (!seen.includes(user)) row._seen = JSON.stringify([...seen, user]);
}

export function isUnseen(row: InboxRow, user: string) {
  const seen: string[] = row._seen ? JSON.parse(row._seen) : [];
  return !seen.includes(user);
}

/** "Aisha" from the contact's name, or from the email before the @. */
export function firstName(name?: string | null) {
  const n = String(name || "").trim();
  if (!n) return __("the customer");
  const words = (n.includes("@") ? n.split("@")[0] : n).split(/[\s._-]+/);
  const first = words.find(Boolean) || n;
  return first.charAt(0).toUpperCase() + first.slice(1);
}
