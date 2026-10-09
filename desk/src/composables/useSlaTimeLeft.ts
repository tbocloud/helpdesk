import { useIntervalFn } from "@vueuse/core";
import { call, dayjsLocal } from "frappe-ui";
import {
  computed,
  shallowRef,
  toValue,
  watch,
  type InjectionKey,
  type MaybeRefOrGetter,
} from "vue";

export interface SlaTicket {
  name: string | number;
  response_by?: string | null;
  resolution_by?: string | null;
}

type Clock = "response" | "resolution";
type TimeLeft = Record<string, Record<Clock, number | null>>;

// MAX_SLA_TICKETS in helpdesk/api/ticket.py; rows past it keep a neutral badge
const MAX_TICKETS = 500;
const REFRESH_MS = 60_000;

/**
 * Working seconds left before the SLA deadlines of `tickets`, counted on each ticket's own
 * SLA calendar by the server, in one request for all of them. Refreshed every minute, with
 * `now`, so badges and their tones move with the clock.
 */
export function useSlaTimeLeft(tickets: MaybeRefOrGetter<SlaTicket[]>) {
  const now = shallowRef(dayjsLocal());
  const timeLeft = shallowRef<TimeLeft>({});
  // only the latest request may set the counts: an older one finishing last is dropped
  let generation = 0;

  const names = computed(() =>
    toValue(tickets)
      .filter((t) => t.response_by || t.resolution_by)
      .slice(0, MAX_TICKETS)
      .map((t) => String(t.name))
  );
  // a changed deadline (a reply, a pause ending) needs a new count too
  const key = computed(() =>
    toValue(tickets)
      .map((t) => `${t.name}|${t.response_by ?? ""}|${t.resolution_by ?? ""}`)
      .join(",")
  );

  async function refresh() {
    now.value = dayjsLocal();
    const current = ++generation;
    if (!names.value.length) {
      timeLeft.value = {};
      return;
    }
    try {
      const result = await call("helpdesk.api.ticket.get_sla_time_left", {
        tickets: names.value,
      });
      if (current === generation) timeLeft.value = result ?? {};
    } catch {
      // no toast every minute: the badges still show each deadline, and drop back to
      // neutral rather than keep a stale count until a later refresh succeeds
      if (current === generation) timeLeft.value = {};
    }
  }

  watch(key, refresh, { immediate: true });
  useIntervalFn(refresh, REFRESH_MS);

  function workingLeft(name: string | number, clock: Clock): number | null {
    return timeLeft.value[String(name)]?.[clock] ?? null;
  }

  return { now, workingLeft };
}

export type SlaTimeLeft = ReturnType<typeof useSlaTimeLeft>;

/** One count per ticket page, shared by its header and its SLA panel. */
export const SlaTimeLeftSymbol: InjectionKey<SlaTimeLeft> =
  Symbol("slaTimeLeft");
