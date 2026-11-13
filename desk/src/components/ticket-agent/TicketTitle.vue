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

      <div class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <button
          type="button"
          class="rounded font-mono text-sm tabular-nums text-ink-gray-6 hover:text-ink-gray-9"
          :title="__('Copy ticket ID')"
          @click="copyId"
        >
          #{{ ticket.doc.name }}
        </button>
        <TaskyBadge v-bind="status" />
        <TaskyBadge v-if="priority" v-bind="priority" />
        <Tooltip
          v-for="sla in slaChips"
          :key="sla.key"
          :text="sla.tooltip"
          :hover-delay="0.3"
          placement="bottom"
        >
          <TaskyBadge :tone="sla.badge.tone" :icon="sla.badge.icon">
            {{ sla.label }}: {{ sla.badge.label }}
            <span class="sr-only">, {{ sla.tooltip }}</span>
          </TaskyBadge>
        </Tooltip>
        <span class="inline-flex items-center gap-1 text-xs text-ink-gray-5">
          <GlobeIcon
            v-if="ticket.doc.via_customer_portal"
            class="size-3.5"
            aria-hidden="true"
          />
          <EmailIcon v-else class="size-3.5" aria-hidden="true" />
          {{
            ticket.doc.via_customer_portal ? __("via Portal") : __("via Email")
          }}
        </span>
      </div>

      <p
        class="mt-2 flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 text-sm text-ink-gray-6"
      >
        <RouterLink
          v-if="ticket.doc.customer"
          :to="{ name: 'Customer', params: { id: ticket.doc.customer } }"
          class="truncate rounded font-medium text-ink-gray-8 hover:underline"
        >
          {{ ticket.doc.customer }}
        </RouterLink>
        <span v-else class="text-ink-gray-5">{{ __("No customer") }}</span>
        <span aria-hidden="true">·</span>
        <span class="truncate">{{ contactName }}</span>
        <span aria-hidden="true">·</span>
        <span class="truncate">
          {{
            assigneeNames
              ? __("Assigned to {0}", assigneeNames)
              : __("Unassigned")
          }}
        </span>
      </p>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { EmailIcon, GlobeIcon } from "@/components/icons";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { useShortcut } from "@/composables/shortcuts";
import { SlaTimeLeftSymbol } from "@/composables/useSlaTimeLeft";
import {
  priorityBadge,
  resolutionSla,
  responseSla,
  slaBadge,
  slaHint,
  statusBadge,
  type BadgeMeta,
  type SlaState,
} from "@/pages/ticket/ticketMeta";
import { __ } from "@/translation";
import { AssigneeSymbol, TicketContactSymbol, TicketSymbol } from "@/types";
import { copyToClipboard } from "@/utils";
import { Tooltip } from "frappe-ui";
import { computed, inject } from "vue";

const emit = defineEmits<{ (e: "edit-subject"): void }>();

const ticket = inject(TicketSymbol)!;
const assignees = inject(AssigneeSymbol)!;
const contact = inject(TicketContactSymbol)!;
const slaClock = inject(SlaTimeLeftSymbol)!;

const status = computed(() =>
  statusBadge(ticket.value.doc.status, ticket.value.doc.status_category)
);
const priority = computed(() => priorityBadge(ticket.value.doc.priority));

const contactName = computed(
  () =>
    contact.value?.data?.name ||
    ticket.value.doc.contact ||
    ticket.value.doc.raised_by
);

const assigneeNames = computed(() =>
  (assignees.value?.data ?? []).map((a) => a.agent_name || a.name).join(", ")
);

interface SlaChip {
  key: string;
  label: string;
  badge: BadgeMeta;
  tooltip: string;
}

const slaChips = computed(() => {
  const doc = ticket.value.doc;
  const now = slaClock.now.value;
  const chips: SlaChip[] = [];
  const add = (
    key: "response" | "resolution",
    label: string,
    state: SlaState,
    deadline?: string
  ) => {
    const workingLeft =
      state === "due" ? slaClock.workingLeft(doc.name, key) : null;
    const badge = slaBadge(state, deadline, workingLeft, now);
    if (!badge || !deadline) return;
    chips.push({ key, label, badge, tooltip: slaHint(deadline, workingLeft) });
  };
  add(
    "response",
    __("First response"),
    responseSla(doc, doc.response_by, now),
    doc.response_by
  );
  add(
    "resolution",
    __("Resolution"),
    resolutionSla(
      doc,
      doc.resolution_by,
      doc.status_category === "Paused",
      now
    ),
    doc.resolution_by
  );
  return chips;
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
