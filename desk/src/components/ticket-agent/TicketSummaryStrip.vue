<template>
  <!-- each tile toggles the list's ?filters= with the same conditions it counts -->
  <div
    class="flex gap-2 overflow-x-auto px-3 pt-3 sm:grid sm:grid-cols-3 sm:gap-3 sm:overflow-visible sm:px-5 lg:grid-cols-5"
    role="group"
    :aria-label="__('Tickets at a glance')"
  >
    <StatTile
      v-for="tile in TILES"
      :key="tile.key"
      compact
      class="w-36 shrink-0 sm:w-auto"
      :label="tile.label"
      :value="failed[tile.key] ? '—' : counts[tile.key] ?? 0"
      :sub="failed[tile.key] ? __('Couldn\'t count') : undefined"
      :icon="tile.icon"
      :icon-tone="tile.tone"
      :value-tone="
        tile.tone === 'danger' && counts[tile.key] ? 'danger' : 'neutral'
      "
      :loading="counts[tile.key] === undefined && !failed[tile.key]"
      :pressed="active === tile.key"
      @click="toggle(tile.key)"
    />
  </div>
</template>

<script setup lang="ts">
import StatTile from "@/components/StatTile.vue";
import type { Tone } from "@/pages/performance/performanceMeta";
import {
  matchTicketFilter,
  ticketFilters,
  ticketsLink,
  type TicketFilterKey,
} from "@/pages/ticket/ticketFilters";
import { __ } from "@/translation";
import { call } from "frappe-ui";
import { computed, reactive, type Component } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideInbox from "~icons/lucide/inbox";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUserX from "~icons/lucide/user-x";

type Key = Extract<
  TicketFilterKey,
  | "open"
  | "unassigned"
  | "firstReplyOverdue"
  | "slaBreached"
  | "waitingOnCustomer"
>;

const TILES: { key: Key; label: string; icon: Component; tone: Tone }[] = [
  { key: "open", label: __("Open"), icon: LucideInbox, tone: "neutral" },
  {
    key: "unassigned",
    label: __("Unassigned"),
    icon: LucideUserX,
    tone: "warning",
  },
  {
    key: "firstReplyOverdue",
    label: __("First reply overdue"),
    icon: LucideAlarmClock,
    tone: "danger",
  },
  {
    key: "slaBreached",
    label: __("SLA breached"),
    icon: LucideTriangleAlert,
    tone: "danger",
  },
  {
    key: "waitingOnCustomer",
    label: __("Waiting on customer"),
    icon: LucideHourglass,
    tone: "neutral",
  },
];

const route = useRoute();
const router = useRouter();

const counts = reactive<Partial<Record<Key, number>>>({});
const failed = reactive<Partial<Record<Key, boolean>>>({});

const active = computed(() => matchTicketFilter(route.query.filters));

// frappe.client.get_count goes through get_list, so each count only includes
// tickets the agent may read, under the exact filters the tile applies
function reload() {
  for (const { key } of TILES) {
    call("frappe.client.get_count", {
      doctype: "HD Ticket",
      filters: ticketFilters[key](),
    })
      .then((count: number) => {
        counts[key] = count;
        failed[key] = false;
      })
      .catch(() => {
        failed[key] = true;
      });
  }
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
