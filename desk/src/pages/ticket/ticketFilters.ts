import { dayjs } from "frappe-ui";
import type { RouteLocationRaw } from "vue-router";

export type TicketCondition = [string, string, unknown];

const OPEN_CATEGORIES: TicketCondition = [
  "status_category",
  "in",
  ["Open", "Paused"],
];

// deadline filters compare against the moment they're built
const NOW_FIELDS = new Set(["response_by", "resolution_by"]);

function nowParam() {
  return dayjs().format("YYYY-MM-DD HH:mm:ss");
}

/**
 * The ticket filters Home links to and the tickets summary counts, in one place
 * so a count and the list it opens always use the same conditions.
 */
export const ticketFilters = {
  open: (): TicketCondition[] => [OPEN_CATEGORIES],
  newToday: (): TicketCondition[] => [
    ["creation", ">=", dayjs().format("YYYY-MM-DD")],
  ],
  unassigned: (): TicketCondition[] => [
    OPEN_CATEGORIES,
    ["_assign", "is", "not set"],
  ],
  // paused tickets (waiting on the customer or a task) don't run the SLA clock
  slaBreached: (): TicketCondition[] => [
    ["status_category", "=", "Open"],
    ["resolution_by", "<", nowParam()],
  ],
  firstReplyOverdue: (): TicketCondition[] => [
    ["status_category", "=", "Open"],
    ["first_responded_on", "is", "not set"],
    ["response_by", "<", nowParam()],
  ],
  waitingOnCustomer: (): TicketCondition[] => [
    ["status_category", "=", "Paused"],
    ["status", "!=", "Waiting on Task"],
  ],
  rated: (): TicketCondition[] => [["feedback_rating", ">", 0]],
};

export type TicketFilterKey = keyof typeof ticketFilters;

/** The agent tickets list, narrowed by filters in the URL (ListViewBuilder reads `?filters=`). */
export function ticketsLink(filters: TicketCondition[] = []): RouteLocationRaw {
  return filters.length
    ? { name: "TicketsAgent", query: { filters: JSON.stringify(filters) } }
    : { name: "TicketsAgent" };
}

function signature(conditions: unknown[]) {
  return JSON.stringify(
    conditions.map((c) =>
      Array.isArray(c) && NOW_FIELDS.has(c[0]) ? [c[0], c[1]] : c
    )
  );
}

/** Which shared filter a `?filters=` value was built from, if any. */
export function matchTicketFilter(raw: unknown): TicketFilterKey | null {
  if (typeof raw !== "string" || !raw) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!Array.isArray(parsed)) return null;
  const wanted = signature(parsed);
  const keys = Object.keys(ticketFilters) as TicketFilterKey[];
  return keys.find((key) => signature(ticketFilters[key]()) === wanted) ?? null;
}
