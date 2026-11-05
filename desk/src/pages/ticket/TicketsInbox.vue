<template>
  <!-- Tickets for agents (Phase 16): the inbox list with the open ticket beside it; or the Phase 15
       table (a saved view, or the agent's choice). Below 1024 px one of the two at a time -->
  <Tickets v-if="showTable" />
  <!-- the page wrapper gives its root flex-col; the list and the ticket sit in a row inside -->
  <div v-else class="flex min-h-0 flex-1 flex-col overflow-hidden">
    <LayoutHeader v-if="!ticketOpen">
      <template #left-header>
        <h1 class="text-lg font-semibold text-ink-gray-9">
          {{ __("Tickets") }}
        </h1>
      </template>
      <template #right-header>
        <Button
          :label="__('Table')"
          :tooltip="__('Show the tickets as a table')"
          @click="ticketsLayout = 'table'"
        >
          <template #prefix>
            <LucideTable class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          :label="__('New ticket')"
          theme="gray"
          variant="solid"
          :route="{ name: 'TicketAgentNew' }"
        >
          <template #prefix>
            <LucidePlus class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>
    <div class="flex min-h-0 flex-1 flex-row overflow-hidden">
      <div
        v-if="listShown"
        class="flex min-h-0 w-full shrink-0 flex-col border-e border-outline-gray-1 lg:w-80 xl:w-[22rem]"
      >
        <InboxList :show-heading="ticketOpen" />
      </div>
      <div v-if="middleShown" class="flex min-h-0 min-w-0 flex-1 flex-col">
        <RouterView />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import { markSeenInList, ticketsLayout } from "@/components/ticket-inbox/inbox";
import InboxList from "@/components/ticket-inbox/InboxList.vue";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { useMediaQuery } from "@vueuse/core";
import { Button, usePageMeta } from "frappe-ui";
import { computed, provide, watch } from "vue";
import { useRoute } from "vue-router";
import LucidePlus from "~icons/lucide/plus";
import LucideTable from "~icons/lucide/table";
import Tickets from "./Tickets.vue";

const route = useRoute();
const auth = useAuthStore();
const wide = useMediaQuery("(min-width: 1024px)");

const ticketOpen = computed(() => route.name === "TicketAgent");
// a saved view (?view=) has its own columns and sort: the table shows it
const tableLayout = computed(
  () => ticketsLayout.value === "table" || Boolean(route.query.view)
);
const showTable = computed(() => !ticketOpen.value && tableLayout.value);
// someone who may open a ticket but not work the list (a link from a notification) sees only the ticket
const listShown = computed(
  () =>
    auth.canWorkTickets &&
    !tableLayout.value &&
    (wide.value || !ticketOpen.value)
);
const middleShown = computed(() => ticketOpen.value || wide.value);

// the ticket page sizes its details panel by the room the list leaves
provide(
  "inboxListShown",
  computed(() => listShown.value && ticketOpen.value)
);

// the open ticket is seen: its row loses the dot at once
watch(
  () => route.params.ticketId,
  (id) => id && markSeenInList(String(id), String(auth.userId || "")),
  { immediate: true }
);

usePageMeta(() => (ticketOpen.value ? {} : { title: __("Tickets") }));
</script>
