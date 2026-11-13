<template>
  <!-- the conversation with the customer (filters) or everything that happened (Phase 12) -->
  <div
    v-if="mode === 'customer'"
    class="flex shrink-0 flex-wrap gap-1.5 border-b border-outline-gray-1 px-5 py-2.5"
    role="group"
    :aria-label="__('Show')"
  >
    <Button
      v-for="chip in chips"
      :key="chip.value"
      size="sm"
      :variant="kind === chip.value ? 'solid' : 'subtle'"
      :aria-pressed="kind === chip.value"
      @click="kind = chip.value"
    >
      {{ chip.label }}
      <span
        v-if="chip.value !== 'all' && chip.count"
        class="ms-1 font-mono text-2xs tabular-nums opacity-70"
      >
        {{ chip.count }}
      </span>
    </Button>
  </div>
  <div class="flex min-h-0 flex-1 flex-col">
    <TicketAgentActivities
      v-if="Boolean(activities.data)"
      ref="ticketAgentActivitiesRef"
      :activities="shown"
      :title="title"
      :ticket-status="ticket.doc.status"
      @email:reply="
        (e) => {
          communicationAreaRef?.replyToEmail(e);
        }
      "
      @update="
        () => {
          activities.reload();
          ticketAgentActivitiesRef?.scrollToLatestActivity();
        }
      "
    />
    <TaskyState
      v-else-if="activities.error"
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the conversation')"
      :message="errorText(activities.error, __('Check your connection.'))"
      error
    >
      <Button :label="__('Retry')" @click="activities.reload()" />
    </TaskyState>
    <div
      v-else
      class="flex flex-col gap-4 px-5 py-6"
      aria-busy="true"
      :aria-label="__('Loading conversation')"
    >
      <div
        v-for="i in 3"
        :key="i"
        class="h-24 animate-pulse rounded-xl bg-surface-gray-2"
        aria-hidden="true"
      />
    </div>
  </div>
  <!-- Comm Area -->
  <CommunicationArea
    ref="communicationAreaRef"
    :ticketId="String(ticket.doc?.name)"
    :to-emails="[ticket.doc?.raised_by]"
    :cc-emails="[]"
    :bcc-emails="[]"
    :key="ticket.doc?.name"
    @update="
      () => {
        activities.reload();
        ticketAgentActivitiesRef?.scrollToLatestActivity();
      }
    "
  />
</template>

<script setup lang="ts">
import CommunicationArea from "@/components/CommunicationArea.vue";
import TaskyState from "@/components/TaskyState.vue";
import { useTicketActivities } from "@/composables/useTicketActivities";
import { useTelephonyStore } from "@/stores/telephony";
import { ActivitiesSymbol, TicketSymbol } from "@/types";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button } from "frappe-ui";
import { storeToRefs } from "pinia";
import { computed, inject, ref } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import { TicketAgentActivities } from "../ticket";

const props = withDefaults(
  defineProps<{
    /** customer: the conversation with the customer; activity: everything */
    mode?: "customer" | "activity";
  }>(),
  { mode: "activity" }
);

const ticket = inject(TicketSymbol)!;
const activities = inject(ActivitiesSymbol)!;

const ticketAgentActivitiesRef = ref<InstanceType<
  typeof TicketAgentActivities
> | null>(null);
const communicationAreaRef = ref<InstanceType<typeof CommunicationArea> | null>(
  null
);
const telephonyStore = useTelephonyStore();
const { isCallingEnabled } = storeToRefs(telephonyStore);

const { filterActivities, filterConversation } = useTicketActivities(
  activities,
  computed(() => ticket.value?.doc)
);

type Kind = "all" | "email" | "comment" | "call";
const kind = ref<Kind>("all");
const chips = computed(() => {
  const list: { value: Kind; label: string; count: number }[] = [
    { value: "all", label: __("All"), count: 0 },
    {
      value: "email",
      label: __("Emails"),
      count: filterConversation("email").length,
    },
    {
      value: "comment",
      label: __("Comments"),
      count: filterConversation("comment").length,
    },
  ];
  if (isCallingEnabled.value)
    list.push({
      value: "call",
      label: __("Calls"),
      count: filterConversation("call").length,
    });
  return list;
});

const shown = computed(() =>
  props.mode === "customer"
    ? filterConversation(kind.value)
    : filterActivities("activity")
);
const title = computed(() =>
  props.mode === "customer"
    ? chips.value.find((c) => c.value === kind.value)?.label || __("All")
    : __("Activity")
);
</script>
