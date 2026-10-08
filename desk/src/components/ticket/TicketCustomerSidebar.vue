<template>
  <!-- the customer's ticket facts: a side panel on desktop, the Details tab on phones -->
  <aside
    class="flex min-w-0 flex-col overflow-y-auto"
    :class="
      inline
        ? 'w-full'
        : 'w-[340px] shrink-0 border-l border-outline-gray-2 bg-surface-base'
    "
    :aria-label="__('Ticket details')"
  >
    <section class="flex flex-col gap-3 px-5 py-4">
      <h2 class="text-base-medium text-ink-gray-9">
        {{ __("Ticket details") }}
      </h2>
      <dl
        class="grid grid-cols-[7.5rem_minmax(0,1fr)] items-center gap-x-3 gap-y-3 text-sm"
      >
        <dt class="text-ink-gray-5">{{ __("Ticket") }}</dt>
        <dd class="font-mono tabular-nums text-ink-gray-8">
          #{{ ticket.data.name }}
        </dd>

        <dt class="text-ink-gray-5">{{ __("Status") }}</dt>
        <dd>
          <TaskyBadge v-bind="customerStatus.badge(ticket.data.status)" />
        </dd>

        <dt class="text-ink-gray-5">{{ __("Raised by") }}</dt>
        <dd class="min-w-0 truncate text-ink-gray-8" :title="contactLabel">
          {{ contactLabel }}
        </dd>

        <template v-for="fact in slaFacts" :key="fact.label">
          <dt class="text-ink-gray-5">{{ fact.label }}</dt>
          <dd class="flex min-w-0 flex-col items-start gap-1">
            <Tooltip
              :text="
                fact.value.at
                  ? dateFormat(fact.value.at, dateTooltipFormat)
                  : ''
              "
            >
              <TaskyBadge v-bind="fact.value" />
            </Tooltip>
          </dd>
        </template>

        <template v-for="field in fields" :key="field.fieldname">
          <dt class="text-ink-gray-5">{{ field.label }}</dt>
          <dd
            class="min-w-0 break-words"
            :class="field.value ? 'text-ink-gray-8' : 'text-ink-gray-4'"
          >
            {{ field.value || "—" }}
          </dd>
        </template>
      </dl>
      <p v-if="longResolution" class="text-p-xs text-ink-gray-5">
        {{
          __(
            "Dates follow our working hours and holidays, so they can be a few days out."
          )
        }}
      </p>
    </section>

    <section
      v-if="ticket.data.feedback_rating"
      class="flex flex-col gap-3 border-t border-outline-gray-2 px-5 py-4"
    >
      <h2 class="text-base-medium text-ink-gray-9">
        {{ __("Your rating") }}
      </h2>
      <dl
        class="grid grid-cols-[7.5rem_minmax(0,1fr)] items-start gap-x-3 gap-y-3 text-sm"
      >
        <dt class="text-ink-gray-5">{{ __("Rating") }}</dt>
        <dd><StarRating :rating="ticket.data.feedback_rating" /></dd>
        <template v-if="ticket.data.feedback">
          <dt class="text-ink-gray-5">{{ __("Feedback") }}</dt>
          <dd class="text-ink-gray-8">{{ ticket.data.feedback }}</dd>
        </template>
        <template v-if="ticket.data.feedback_extra">
          <dt class="text-ink-gray-5">{{ __("Comment") }}</dt>
          <dd class="whitespace-pre-line break-words text-ink-gray-8">
            {{ ticket.data.feedback_extra }}
          </dd>
        </template>
      </dl>
    </section>
  </aside>
</template>

<script setup lang="ts">
import StarRating from "@/components/StarRating.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import {
  firstReplyFact,
  resolutionFact,
  useCustomerStatus,
  type Fact,
} from "@/pages/ticket/customerStatus";
import { ITicket } from "@/pages/ticket/symbols";
import { __ } from "@/translation";
import { Field } from "@/types";
import { dateFormat, dateTooltipFormat } from "@/utils";
import { dayjs, Tooltip } from "frappe-ui";
import { computed, inject } from "vue";

withDefaults(defineProps<{ inline?: boolean }>(), { inline: false });

const ticket = inject(ITicket);
const customerStatus = useCustomerStatus();

const contactLabel = computed(
  () => ticket.data.contact?.name || ticket.data.raised_by
);

const slaFacts = computed(() => {
  const facts: { label: string; value: Fact }[] = [];
  const firstReply = firstReplyFact(ticket.data);
  if (firstReply) facts.push({ label: __("First reply"), value: firstReply });
  const resolution = resolutionFact(
    ticket.data,
    customerStatus.stage(ticket.data.status)
  );
  if (resolution) facts.push({ label: __("Resolution"), value: resolution });
  return facts;
});

// a resolution date days away surprises people; say why
const longResolution = computed(
  () =>
    !ticket.data.resolution_date &&
    ticket.data.resolution_by &&
    dayjs(ticket.data.resolution_by).diff(dayjs(), "day", true) > 4
);

function display(field: Field, value: unknown) {
  if (!value) return value;
  if (field.fieldtype === "Date" || field.fieldtype === "Datetime") {
    return dayjs(value as string).isValid()
      ? dateFormat(
          value,
          field.fieldtype === "Date" ? "D MMM YYYY" : dateTooltipFormat
        )
      : value;
  }
  return value;
}

// priority, team and the template's fields the customer may see
const fields = computed(() => [
  {
    fieldname: "priority",
    label: __("Priority"),
    value: ticket.data.priority,
  },
  {
    fieldname: "agent_group",
    label: __("Team"),
    value: ticket.data.agent_group,
  },
  ...(ticket.data.template?.fields || [])
    .filter(
      (field: Field) =>
        !field.hide_from_customer &&
        !["subject", "team", "agent_group", "priority"].includes(
          field.fieldname
        )
    )
    .map((field: Field) => ({
      fieldname: field.fieldname,
      label: field.label,
      value: display(field, ticket.data[field.fieldname]),
    })),
]);
</script>
