<template>
  <!-- Teleport to App Header -->
  <teleport to="#app-header">
    <div class="mx-4 pb-3.5 md:mx-5">
      <h1
        class="mt-1 text-[22px] font-semibold leading-[30px] tracking-[-0.01em] text-ink-gray-9"
      >
        <button
          type="button"
          class="block max-w-full cursor-text truncate rounded text-start"
          :title="__('Rename ticket')"
          @click="emit('edit-subject')"
        >
          {{ ticket.doc.subject }}
        </button>
      </h1>

      <!-- each fact once (Phase 15): the number, the status and the assignee are in the header;
           here who it is from, where it came in, how old, how urgent and what is due next -->
      <p
        class="mt-2 flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1.5 text-sm text-ink-gray-6"
      >
        <span class="inline-flex min-w-0 items-center gap-1.5 text-ink-gray-8">
          <Avatar size="sm" :label="contactName" />
          <span class="truncate font-medium">{{ contactName }}</span>
        </span>
        <RouterLink
          v-if="ticket.doc.customer"
          :to="{ name: 'Customer', params: { id: ticket.doc.customer } }"
          class="truncate rounded text-ink-gray-7 hover:underline"
        >
          {{ ticket.doc.customer }}
        </RouterLink>
        <span v-else class="text-ink-gray-5">{{ __("No customer") }}</span>
        <span class="inline-flex items-center gap-1 text-ink-gray-5">
          <GlobeIcon
            v-if="ticket.doc.via_customer_portal"
            class="size-3.5"
            aria-hidden="true"
          />
          <EmailIcon v-else class="size-3.5" aria-hidden="true" />
          {{
            ticket.doc.via_customer_portal ? __("via Portal") : __("via Email")
          }}
          ·
          <Tooltip :text="dateFormat(ticket.doc.creation, dateTooltipFormat)">
            <span>{{ __("opened {0}", [timeAgo(ticket.doc.creation)]) }}</span>
          </Tooltip>
        </span>
        <TaskyBadge v-if="priority" v-bind="priority" />
        <Tooltip
          v-if="due"
          :text="due.hint"
          :hover-delay="0.3"
          placement="bottom"
        >
          <TaskyBadge :tone="due.tone" :icon="due.icon">
            {{ due.label }}
            <span class="sr-only">, {{ due.hint }}</span>
          </TaskyBadge>
        </Tooltip>
      </p>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { EmailIcon, GlobeIcon } from "@/components/icons";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { useShortcut } from "@/composables/shortcuts";
import { SlaTimeLeftSymbol } from "@/composables/useSlaTimeLeft";
import { dueBadge, priorityBadge } from "@/pages/ticket/ticketMeta";
import { __ } from "@/translation";
import { TicketContactSymbol, TicketSymbol } from "@/types";
import {
  copyToClipboard,
  dateFormat,
  dateTooltipFormat,
  timeAgo,
} from "@/utils";
import { Avatar, Tooltip } from "frappe-ui";
import { computed, inject } from "vue";

const emit = defineEmits<{ (e: "edit-subject"): void }>();

const ticket = inject(TicketSymbol)!;
const contact = inject(TicketContactSymbol)!;
const slaClock = inject(SlaTimeLeftSymbol)!;

const priority = computed(() => priorityBadge(ticket.value.doc.priority));

const contactName = computed(
  () =>
    contact.value?.data?.name ||
    ticket.value.doc.contact ||
    ticket.value.doc.raised_by
);

// the one SLA: the first reply until it is sent, then the resolution
const due = computed(() => {
  const doc = ticket.value.doc;
  return dueBadge(
    doc,
    doc.status_category === "Paused",
    (clock) => slaClock.workingLeft(doc.name, clock),
    slaClock.now.value
  );
});

function copyId() {
  copyToClipboard(
    ticket.value.doc.name,
    __("Ticket #{0} copied to clipboard", ticket.value.doc.name)
  );
}

useShortcut({ meta: true, shift: true, key: "." }, () => {
  copyToClipboard(window.location.href, __("Ticket URL copied to clipboard"));
});

useShortcut({ meta: true, key: "." }, copyId);
</script>
