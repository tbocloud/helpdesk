<template>
  <!-- the ticket's main area (Phase 12): it opens on the chat with Copilot and the team; the
       conversation with the customer and everything that happened are beside it -->
  <div class="flex min-h-0 flex-1 flex-col overflow-hidden">
    <div
      role="tablist"
      :aria-label="__('Ticket views')"
      class="flex shrink-0 gap-6 border-b border-outline-gray-1 px-5"
    >
      <button
        v-for="(view, i) in views"
        :id="`ticket-view-${view.value}`"
        :key="view.value"
        :ref="(el) => (tabRefs[i] = el as HTMLElement)"
        type="button"
        role="tab"
        :aria-selected="ticketView === view.value"
        aria-controls="ticket-view-panel"
        :tabindex="ticketView === view.value ? 0 : -1"
        class="flex h-10 shrink-0 items-center gap-2 whitespace-nowrap border-b-2 text-sm font-medium transition-colors"
        :class="
          ticketView === view.value
            ? 'border-ink-gray-9 text-ink-gray-9'
            : 'border-transparent text-ink-gray-5 hover:text-ink-gray-9'
        "
        @click="ticketView = view.value"
        @keydown.right.prevent="move(i, 1)"
        @keydown.left.prevent="move(i, -1)"
      >
        <component :is="view.icon" class="size-4" aria-hidden="true" />
        {{ view.label }}
        <span
          v-if="view.count"
          class="rounded bg-surface-gray-2 px-1.5 font-mono text-2xs tabular-nums text-ink-gray-5"
        >
          {{ view.count }}
        </span>
      </button>
    </div>
    <div
      id="ticket-view-panel"
      role="tabpanel"
      :aria-labelledby="`ticket-view-${ticketView}`"
      class="flex min-h-0 flex-1 flex-col overflow-hidden"
    >
      <!-- both stay mounted, so a half-written message or reply survives a switch -->
      <CopilotThread
        v-show="ticketView === 'chat'"
        :ticket="String(ticket.doc.name)"
        :request="request"
        wide
      />
      <div
        v-show="ticketView !== 'chat'"
        class="flex min-h-0 flex-1 flex-col overflow-hidden"
      >
        <TicketActivityPanel
          :mode="ticketView === 'customer' ? 'customer' : 'activity'"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ActivityIcon, EmailIcon } from "@/components/icons";
import { useTicketActivities } from "@/composables/useTicketActivities";
import { ticketView, type TicketView } from "@/pages/ticket/modalStates";
import { ActivitiesSymbol, TicketSymbol } from "@/types";
import { __ } from "@/translation";
import { computed, inject, nextTick, ref } from "vue";
import LucideMessagesSquare from "~icons/lucide/messages-square";
import CopilotThread from "./CopilotThread.vue";
import TicketActivityPanel from "./TicketActivityPanel.vue";
import { ticketRequest } from "./ticketRequest";

const ticket = inject(TicketSymbol)!;
const activities = inject(ActivitiesSymbol)!;
const { filterConversation } = useTicketActivities(
  activities,
  computed(() => ticket.value?.doc)
);

const views = computed(() => [
  {
    value: "chat" as TicketView,
    label: __("Chat"),
    icon: LucideMessagesSquare,
  },
  {
    value: "customer" as TicketView,
    label: __("Customer"),
    icon: EmailIcon,
    count: filterConversation("all").filter((a) => a.type !== "feedback")
      .length,
  },
  {
    value: "activity" as TicketView,
    label: __("Activity"),
    icon: ActivityIcon,
  },
]);

const tabRefs = ref<HTMLElement[]>([]);
async function move(i: number, step: number) {
  const next = (i + step + views.value.length) % views.value.length;
  ticketView.value = views.value[next].value;
  await nextTick();
  tabRefs.value[next]?.focus();
}

// the customer's request opens the chat: who, when, their words
const request = computed(() => ticketRequest(ticket.value?.doc));
</script>
