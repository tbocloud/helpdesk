<template>
  <!-- each tab toggles the list's ?filters= with the same conditions it counts;
       ViewTabs' pills, kept as buttons so they stay reachable when no tab matches -->
  <nav
    class="inline-flex max-w-full gap-1 overflow-x-auto rounded-full border border-outline-gray-2 bg-surface-base p-1"
    :aria-label="__('Ticket views')"
  >
    <button
      v-for="tab in TABS"
      :key="tab.key"
      type="button"
      class="inline-flex h-10 shrink-0 items-center gap-2 whitespace-nowrap rounded-full px-3.5 text-[13px] font-medium transition-colors"
      :class="
        active === tab.key
          ? 'bg-surface-gray-10 text-ink-base'
          : 'text-ink-gray-7 hover:bg-surface-gray-3'
      "
      :aria-current="active === tab.key ? 'page' : undefined"
      @click="failed[tab.key] ? count(tab.key) : toggle(tab.key)"
    >
      {{ tab.label }}
      <span
        v-if="tab.counted"
        class="min-w-[22px] rounded-full px-[7px] py-px text-center text-xs font-semibold tabular-nums"
        :class="
          active === tab.key
            ? 'bg-white/20 text-ink-base'
            : tab.key === 'slaBreached' && counts[tab.key]
            ? 'bg-danger-soft text-danger'
            : 'bg-surface-gray-4 text-ink-gray-7'
        "
        :title="
          failed[tab.key] ? __('Couldn\'t count. Select to retry.') : undefined
        "
      >
        {{ failed[tab.key] ? "—" : counts[tab.key] ?? "…" }}
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
import { computed, reactive } from "vue";
import { useRoute, useRouter } from "vue-router";

type Key = Extract<
  TicketFilterKey,
  "open" | "mine" | "unassigned" | "slaBreached" | "closed"
>;

// Closed is a plain filter: counting every resolved ticket says nothing a day-to-day agent acts on
const TABS: { key: Key; label: string; counted: boolean }[] = [
  { key: "open", label: __("All open"), counted: true },
  { key: "mine", label: __("Mine"), counted: true },
  { key: "unassigned", label: __("Unassigned"), counted: true },
  { key: "slaBreached", label: __("Past SLA"), counted: true },
  { key: "closed", label: __("Closed"), counted: false },
];

const route = useRoute();
const router = useRouter();

const counts = reactive<Partial<Record<Key, number>>>({});
const failed = reactive<Partial<Record<Key, boolean>>>({});

const active = computed(() => matchTicketFilter(route.query.filters));

// frappe.client.get_count goes through get_list, so each count only includes
// tickets the agent may read, under the exact filters the tab applies
// Each tab numbers its requests and keeps only the latest answer (count or
// failure), so a slow reply from before a reload can't overwrite a newer one.
const latest: Partial<Record<Key, number>> = {};

function count(key: Key) {
  const request = (latest[key] = (latest[key] ?? 0) + 1);
  failed[key] = false;
  call("frappe.client.get_count", {
    doctype: "HD Ticket",
    filters: ticketFilters[key](),
  })
    .then((value: number) => {
      if (request !== latest[key]) return;
      counts[key] = value;
    })
    .catch(() => {
      if (request !== latest[key]) return;
      failed[key] = true;
    });
}

function reload() {
  for (const { key, counted } of TABS) if (counted) count(key);
}

function toggle(key: Key) {
  if (active.value === key) {
    const { filters: _, ...query } = route.query;
    router.push({ name: "TicketsAgent", query });
    return;
  }
  router.push(ticketsLink(ticketFilters[key]()));
}

reload();

defineExpose({ reload });
</script>
