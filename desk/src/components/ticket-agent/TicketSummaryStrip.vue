<template>
  <!-- the ticket list's queues (Phase 15): each tab narrows the list with the same conditions it
       counts (?filters=), so the number on a tab is the number of rows it opens -->
  <nav
    ref="navRef"
    class="flex shrink-0 gap-1 overflow-x-auto border-b border-outline-gray-1 px-3 sm:px-5"
    :aria-label="__('Queues')"
  >
    <button
      v-for="queue in QUEUES"
      :key="queue.key"
      type="button"
      :aria-current="active === queue.key ? 'page' : undefined"
      :title="queue.hint"
      class="-mb-px flex h-10 shrink-0 items-center gap-1.5 whitespace-nowrap border-b-2 px-2.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
      :class="
        active === queue.key
          ? 'border-ink-gray-9 font-medium text-ink-gray-9'
          : 'border-transparent text-ink-gray-6 hover:text-ink-gray-9'
      "
      @click="choose(queue.key)"
    >
      {{ queue.label }}
      <span
        v-if="queue.key !== 'all'"
        class="min-w-5 rounded px-1.5 text-center font-mono text-2xs tabular-nums"
        :class="countClass(queue)"
      >
        <span v-if="failed[queue.key]" :title="__('Couldn\'t count')">—</span>
        <span
          v-else-if="counts[queue.key] === undefined"
          class="inline-block h-2 w-3 animate-pulse rounded bg-surface-gray-3 align-middle"
          aria-hidden="true"
        />
        <template v-else>{{ counts[queue.key] }}</template>
      </span>
    </button>
  </nav>
</template>

<script setup lang="ts">
import {
  matchTicketFilter,
  ticketFilters,
  ticketsLink,
  type TicketFilterKey,
} from "@/pages/ticket/ticketFilters";
import { __ } from "@/translation";
import { call } from "frappe-ui";
import { computed, nextTick, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

type Key =
  | Extract<
      TicketFilterKey,
      | "needsReply"
      | "overdue"
      | "unassigned"
      | "mine"
      | "waiting"
      | "open"
      | "resolved"
    >
  | "all";

interface Queue {
  key: Key;
  label: string;
  hint: string;
  /** red count while it has tickets */
  urgent?: boolean;
}

const QUEUES: Queue[] = [
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
  {
    key: "unassigned",
    label: __("Unassigned"),
    hint: __("Open, and nobody has it"),
  },
  { key: "mine", label: __("Mine"), hint: __("Open, and assigned to you") },
  {
    key: "waiting",
    label: __("Waiting"),
    hint: __(
      "Waiting on the customer, a task or on hold: the SLA clock is paused"
    ),
  },
  { key: "open", label: __("All open"), hint: __("Not resolved or closed") },
  { key: "resolved", label: __("Resolved"), hint: __("Resolved or closed") },
  { key: "all", label: __("All"), hint: __("The list as this view shows it") },
];

const route = useRoute();
const router = useRouter();
const navRef = ref<HTMLElement | null>(null);

const counts = reactive<Partial<Record<Key, number>>>({});
const failed = reactive<Partial<Record<Key, boolean>>>({});

// no queue's filters in the address: the plain list (the view's own filters)
const active = computed<Key | null>(() => {
  if (!route.query.filters) return "all";
  const key = matchTicketFilter(route.query.filters);
  return QUEUES.some((q) => q.key === key) ? (key as Key) : null;
});

function conditions(key: Key) {
  return key === "all" ? [] : ticketFilters[key]();
}

function countClass(queue: Queue) {
  const n = counts[queue.key];
  if (queue.urgent && n) return "bg-danger-soft text-danger font-semibold";
  return active.value === queue.key
    ? "bg-surface-gray-3 text-ink-gray-8"
    : "bg-surface-gray-2 text-ink-gray-5";
}

// helpdesk.api.ticket_area.count goes through get_list, so a count only includes tickets the
// agent may read. Each queue numbers its requests and keeps only the latest answer, so a slow
// reply from before a reload can't overwrite a newer one.
const latest: Partial<Record<Key, number>> = {};

function count(key: Key) {
  const request = (latest[key] = (latest[key] ?? 0) + 1);
  failed[key] = false;
  call("helpdesk.api.ticket_area.count", { filters: conditions(key) })
    .then((value: number) => {
      if (request === latest[key]) counts[key] = value;
    })
    .catch(() => {
      if (request === latest[key]) failed[key] = true;
    });
}

// All is the view's own list (its filters may narrow it): it shows no number of its own
function reload() {
  for (const { key } of QUEUES) if (key !== "all") count(key);
}

function choose(key: Key) {
  if (failed[key]) count(key);
  if (active.value === key) return;
  if (key === "all") {
    const { filters: _, ...query } = route.query;
    router.push({ name: "TicketsAgent", query });
    return;
  }
  router.push(ticketsLink(ticketFilters[key]()));
}

// on a narrow screen the chosen queue stays in sight
watch(
  active,
  async () => {
    await nextTick();
    navRef.value
      ?.querySelector<HTMLElement>("[aria-current=page]")
      ?.scrollIntoView({ block: "nearest", inline: "nearest" });
  },
  { immediate: true }
);

reload();

defineExpose({ reload });
</script>
