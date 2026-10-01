<template>
  <div class="flex h-full min-h-0 flex-1 flex-col bg-surface-base">
    <div class="shrink-0">
      <!-- Contact card -->
      <section
        class="border-b border-outline-gray-1 px-5 py-4"
        :aria-label="__('Contact')"
      >
        <TicketContact />
      </section>

      <!-- Core fields -->
      <section
        class="border-b border-outline-gray-1 px-5 py-4"
        aria-labelledby="ticket-details-heading"
      >
        <h2
          id="ticket-details-heading"
          class="mb-2.5 text-2xs font-semibold uppercase tracking-[0.06em] text-ink-gray-5"
        >
          {{ __("Details") }}
        </h2>
        <div class="flex flex-col gap-0.5">
          <template v-for="field in flatCoreFields" :key="field.fieldname">
            <div
              v-if="field.visible"
              class="grid min-h-8 grid-cols-[96px_minmax(0,1fr)] items-center gap-2"
            >
              <span
                :id="`ticket-field-label-${field.fieldname}`"
                class="truncate text-xs font-medium text-ink-gray-6"
              >
                {{ __(field.label) }}
                <span v-if="field.required" class="text-ink-red-6">*</span>
              </span>
              <Link
                :ref="(el) => setFieldRef(field.fieldname, el)"
                class="form-control-core min-w-0"
                :id="field.fieldname"
                :page-length="10"
                :placeholder="field.placeholder"
                :doctype="field.doctype"
                :modelValue="field.value"
                :required="field.required"
                @update:model-value="
                  (val: string) => handleFieldUpdate(field.fieldname, val, true)
                "
              />
            </div>
          </template>

          <!-- Assignee -->
          <div
            class="grid min-h-8 grid-cols-[96px_minmax(0,1fr)] items-center gap-2"
          >
            <span class="truncate text-xs font-medium text-ink-gray-6">
              {{ __("Assignee") }}
            </span>
            <AssignTo hide-label quiet class="min-w-0" />
          </div>
        </div>
      </section>
    </div>

    <!-- Scrollable sections: Possible duplicates, AI suggested reply, Session replay, Ticket Info, Recent / Similar Tickets -->
    <div class="flex-1 min-h-0 overflow-y-auto divide-y divide-outline-gray-1">
      <DuplicateTicketsCard v-if="ticketId" :ticket-id="ticketId" />
      <AiSuggestedReplyCard v-if="ticketId" :ticket-id="ticketId" />
      <SessionReplayCard v-if="ticketId" :ticket-id="ticketId" />

      <!-- Ticket Info (custom fields) -->
      <div v-if="Boolean(customFields.length)">
        <Section label="Ticket Info" v-model:opened="openedSections.ticketInfo">
          <template #header="{ opened, toggle }">
            <div class="sticky top-0 z-10 bg-surface-base px-5 pt-4 pb-2.5">
              <button
                type="button"
                class="-mx-1 flex w-[calc(100%+0.5rem)] items-center justify-between gap-2.5 rounded px-1 text-2xs font-semibold uppercase tracking-[0.06em] text-ink-gray-5 hover:text-ink-gray-8"
                :aria-expanded="opened"
                @click="toggle"
              >
                <span class="select-none">{{ __("Ticket Info") }}</span>
                <LucideChevronRight
                  class="size-4 transition-transform"
                  :class="{ 'rotate-90': opened }"
                  aria-hidden="true"
                />
              </button>
            </div>
          </template>
          <div
            class="space-y-1.5 px-5 pb-4"
            v-if="Boolean(customFields.length)"
          >
            <template v-for="field in customFields">
              <TicketField
                v-if="field.visible"
                :key="field.fieldname"
                :field="field"
                :value="field.value"
                @change="
                  ({ fieldname, value }) => handleFieldUpdate(fieldname, value)
                "
              />
            </template>
          </div>
        </Section>
      </div>

      <!-- Recent / Similar Tickets -->
      <template v-if="showRecentSimilarTickets">
        <div v-for="section in sections" :key="section.label">
          <Section
            :label="section.label"
            :hideLabel="section.hideLabel"
            v-model:opened="openedSections[section.key]"
          >
            <template #header="{ opened, toggle }">
              <div class="sticky top-0 z-10 bg-surface-base px-5 pt-4 pb-2.5">
                <Tooltip :text="section.tooltipMessage">
                  <button
                    type="button"
                    class="-mx-1 flex w-[calc(100%+0.5rem)] items-center justify-between gap-2.5 rounded px-1 text-2xs font-semibold uppercase tracking-[0.06em] text-ink-gray-5 hover:text-ink-gray-8"
                    :aria-expanded="opened"
                    @click="toggle"
                  >
                    <span class="select-none">{{ __(section.label) }}</span>
                    <LucideChevronRight
                      class="size-4 transition-transform"
                      :class="{ 'rotate-90': opened }"
                      aria-hidden="true"
                    />
                  </button>
                </Tooltip>
              </div>
            </template>
            <ul class="px-5 pb-4">
              <li v-for="t in section.tickets" :key="t.name">
                <button
                  type="button"
                  class="-mx-2 block w-[calc(100%+1rem)] rounded-md px-2 py-2 text-start transition-colors hover:bg-surface-gray-2"
                  @click="openTicket(t.name)"
                >
                  <p class="mb-1 truncate text-sm font-medium text-ink-gray-9">
                    {{ t.subject }}
                  </p>
                  <div class="flex items-center justify-between gap-2">
                    <p class="shrink-0 text-xs text-ink-gray-5">
                      {{ formatDate(t.creation as string) + " · " }}
                      <span class="font-mono">{{ "#" + t.name }}</span>
                    </p>
                    <span
                      class="shrink-0 rounded-sm px-2 py-0.5 text-xs"
                      :class="getStatusColor(t.status as string)"
                    >
                      {{ t.status }}
                    </span>
                  </div>
                </button>
              </li>
            </ul>
          </Section>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import { parseField } from "@/composables/formCustomisation";
import { useNotifyTicketUpdate } from "@/composables/realtime";
import { useShortcut } from "@/composables/shortcuts";
import { getMeta } from "@/stores/meta";
import { useTicketStatusStore } from "@/stores/ticketStatus";
import {
  ActivitiesSymbol,
  AssigneeSymbol,
  CustomizationSymbol,
  FieldValue,
  RecentSimilarTicketsSymbol,
  TicketSymbol,
} from "@/types";
import { __ } from "@/translation";
import { useStorage } from "@vueuse/core";
import { dayjs, Tooltip } from "frappe-ui";
import { computed, inject, ref } from "vue";
import LucideChevronRight from "~icons/lucide/chevron-right";
import Section from "../Section.vue";
import TicketField from "../TicketField.vue";
import AiSuggestedReplyCard from "./AiSuggestedReplyCard.vue";
import AssignTo from "./AssignTo.vue";
import DuplicateTicketsCard from "./DuplicateTicketsCard.vue";
import SessionReplayCard from "./SessionReplayCard.vue";
import TicketContact from "./TicketContact.vue";

const ticket = inject(TicketSymbol)!;
const assignees = inject(AssigneeSymbol)!;
const customizations = inject(CustomizationSymbol)!;
const activities = inject(ActivitiesSymbol)!;
const recentSimilarTickets = inject(RecentSimilarTicketsSymbol)!;
const { getFields, getField } = getMeta("HD Ticket");
const { notifyTicketUpdate } = useNotifyTicketUpdate(ticket.value?.name);
const ticketId = computed(() => String(ticket.value?.doc?.name ?? ""));

const dateFormat = window.date_format;
const { getStatus, colorMap } = useTicketStatusStore();

// ticket_type, priority, customer, agent_group
const coreFields = computed(() => {
  // TODO: to confirm whether customizations should apply to core fields as well
  const fieldsMeta = getFields();
  if (!fieldsMeta || fieldsMeta.length === 0) {
    return [];
  }
  const _coreFields = [
    { group: true, fields: [getField("ticket_type"), getField("priority")] },
    { group: false, fields: [getField("customer")] },
    { group: true, fields: [getField("agent_group")] },
  ];

  _coreFields.forEach((section) => {
    section.fields = section.fields.map((f) => {
      f = parseField(f, ticket.value.doc);

      // cant handle required depends on as we directly set the value in DB on change
      f["required"] = f.reqd;
      f["ref"] = f.fieldname;

      f = getFieldInFormat(f, f);
      f["placeholder"] = coreFieldPlaceholders[f.fieldname] ?? f.placeholder;
      f["visible"] = true;
      return f;
    });
  });
  return _coreFields;
});

const flatCoreFields = computed(() =>
  coreFields.value.flatMap((section) => section.fields)
);

const coreFieldPlaceholders: Record<string, string> = {
  ticket_type: __("Select type"),
  priority: __("Set priority"),
  customer: __("Add customer"),
  agent_group: __("Assign team"),
};

const customFields = computed(() => {
  const fieldsMeta = getFields();
  if (!fieldsMeta || fieldsMeta.length === 0) {
    return [];
  }

  if (!customizations.value.data || customizations.value.loading) return [];
  let customFields = customizations.value.data?.custom_fields || [];
  const _coreFields = [
    "ticket_type",
    "priority",
    "customer",
    "agent_group",
    "subject",
    "status",
  ];
  customFields = customFields.filter((f) => !_coreFields.includes(f.fieldname));
  let _customFields = customFields
    .map((f) => {
      let fieldMeta = getField(f.fieldname);
      if (!fieldMeta) return null;

      fieldMeta = parseField(fieldMeta, ticket.value.doc);
      // cant handle required depends on as we directly set the value in DB
      fieldMeta["required"] = fieldMeta.reqd || f.required;

      return getFieldInFormat(f, fieldMeta);
    })
    .filter(Boolean);
  return _customFields;
});

const openedSections = useStorage(
  "openedSections",
  {
    ticketInfo: false,
    recentTickets: false,
    similarTickets: false,
  },
  localStorage,
  { mergeDefaults: true }
);

const sections = computed(() => {
  if (recentSimilarTickets.value.loading || !recentSimilarTickets.value.data) {
    return [];
  }
  const recentTickets = recentSimilarTickets.value?.data?.recent_tickets || [];
  const similarTickets =
    recentSimilarTickets.value?.data?.similar_tickets || [];
  const _sections = [];
  if (recentTickets.length) {
    _sections.push({
      key: "recentTickets" as const,
      label: "Recent Tickets",
      tooltipMessage: "Tickets recently raised by this contact/customer",
      hideLabel: false,
      tickets: recentTickets,
    });
  }
  if (similarTickets.length) {
    _sections.push({
      key: "similarTickets" as const,
      label: "Similar Tickets",
      tooltipMessage: "Tickets with similar queries",
      hideLabel: false,
      tickets: similarTickets,
    });
  }
  return _sections;
});

function getStatusColor(status: string) {
  const { color } = getStatus(status) ?? {};
  return colorMap[color] ?? colorMap["Default"];
}

function formatDate(date: string) {
  return dayjs(date).format(dateFormat.toUpperCase());
}
function openTicket(name: string) {
  let url = window.location.origin + "/helpdesk/tickets/" + name;
  window.open(url, "_blank");
}

function getFieldInFormat(fieldTemplate, fieldMeta) {
  return {
    label: fieldMeta?.label || fieldTemplate.fieldname,
    value: ticket.value.doc[fieldTemplate.fieldname],
    fieldtype: fieldMeta?.fieldtype,
    doctype: fieldMeta?.options || "",
    options: fieldMeta?.options || "",
    placeholder:
      fieldTemplate.placeholder ||
      `Enter ${fieldMeta?.label || fieldTemplate.fieldname}`,
    readonly: Boolean(fieldMeta.read_only),
    disabled: Boolean(fieldMeta.read_only),
    url_method: fieldTemplate.url_method || "",
    fieldname: fieldTemplate.fieldname,
    required: fieldTemplate.required || fieldMeta?.required || false,
    visible:
      fieldMeta.display_via_depends_on &&
      !fieldMeta.hidden &&
      (!!ticket.value.doc[fieldTemplate.fieldname] || !fieldMeta.read_only),
  };
}

const normalize = (v: string | FieldValue) =>
  v === null || v === undefined ? "" : v;

function handleFieldUpdate(
  fieldname: string,
  value: FieldValue,
  isCoreFieldUpdated = false
) {
  if (normalize(ticket.value.doc[fieldname]) == normalize(value)) return;
  if (isCoreFieldUpdated) {
    const label = getField(fieldname)?.label || fieldname;
    notifyTicketUpdate(label, value as string);
  }
  ticket.value.setValue.submit(
    { [fieldname]: value },
    {
      onSuccess: () => {
        // TODO: emit the event for notification to listeners
        if (fieldname === "agent_group") {
          assignees.value.reload();
        }
        activities.value.reload();
      },
    }

    //show error toast
  );
}

const fieldRefs = ref<Record<string, any>>({});

const setFieldRef = (fieldname: string, el: any) => {
  if (el) {
    fieldRefs.value[fieldname] = el;
  }
};

const showRecentSimilarTickets = computed(() => {
  return (
    !recentSimilarTickets.value.loading &&
    (recentSimilarTickets.value?.data?.recent_tickets?.length ||
      recentSimilarTickets.value?.data?.similar_tickets?.length)
  );
});

useShortcut("t", () => {
  fieldRefs.value?.ticket_type?.$el?.querySelector("button")?.click();
});

useShortcut("p", () => {
  fieldRefs.value?.priority?.$el?.querySelector("button")?.click();
});

useShortcut({ key: "t", shift: true }, () => {
  fieldRefs.value?.agent_group?.$el?.querySelector("button")?.click();
});
</script>

<style scoped>
/* Core fields read as quiet selects: no chrome until hovered or focused */
:deep(.form-control-core button) {
  @apply h-[30px] w-full gap-2 rounded-md border border-transparent bg-transparent px-2 py-0 text-sm font-medium text-ink-gray-9 transition-colors hover:bg-surface-gray-2 dark:[color-scheme:dark];
}
:deep(.form-control-core button[aria-expanded="true"]) {
  @apply bg-surface-gray-2;
}
:deep(.form-control-core button > div) {
  @apply truncate;
}
:deep(.form-control-core button span) {
  @apply text-sm;
}
/* Empty value: muted placeholder ("Add customer") */
:deep(.form-control-core button span.text-ink-gray-4) {
  @apply font-normal text-ink-gray-5;
}
:deep(.form-control-core button > svg) {
  @apply ml-auto shrink-0 opacity-0 transition-opacity;
}
:deep(.form-control-core button:hover > svg),
:deep(.form-control-core button:focus-visible > svg),
:deep(.form-control-core button[aria-expanded="true"] > svg) {
  @apply opacity-100;
}

:deep(.form-control-core div) {
  width: 100%;
  display: flex;
}
</style>
