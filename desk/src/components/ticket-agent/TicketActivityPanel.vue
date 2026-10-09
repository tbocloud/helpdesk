<template>
  <Tabs
    :modelValue="tabIndex"
    :tabs="tabs"
    @update:modelValue="changeTabTo"
    class="[&_[role='tab']]:px-0 [&_[role='tablist']]:px-5 [&_[role='tablist']]:gap-6 [&_[role='tablist']]:flex-shrink-0 [&_[role='tabpanel'][data-state='active']]:flex-1"
  >
    <template #tab-item="{ tab, selected }">
      <button
        type="button"
        class="flex h-10 shrink-0 items-center gap-2 whitespace-nowrap text-sm font-medium transition-colors"
        :class="
          selected ? 'text-ink-gray-9' : 'text-ink-gray-5 hover:text-ink-gray-9'
        "
      >
        <component :is="tab.icon" class="size-4" aria-hidden="true" />
        {{ __(tab.label) }}
        <span
          v-if="tab.name !== 'activity' && countFor(tab.name) > 0"
          class="rounded bg-surface-gray-2 px-1.5 font-mono text-2xs tabular-nums text-ink-gray-5"
        >
          {{ countFor(tab.name) }}
        </span>
      </button>
    </template>
    <template #tab-panel="{ tab }">
      <TicketAgentActivities
        v-if="Boolean(activities.data)"
        ref="ticketAgentActivitiesRef"
        :activities="filterActivities(tab.name as TicketTab)"
        :title="tab.label"
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
    </template>
  </Tabs>
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
import {
  ActivityIcon,
  CommentIcon,
  EmailIcon,
  PhoneIcon,
} from "@/components/icons";
import TaskyState from "@/components/TaskyState.vue";
import { useActiveTabManager } from "@/composables/useActiveTabManager";
import { useTicketActivities } from "@/composables/useTicketActivities";
import { useTelephonyStore } from "@/stores/telephony";
import { ActivitiesSymbol, TabObject, TicketSymbol, TicketTab } from "@/types";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, Tabs } from "frappe-ui";
import { storeToRefs } from "pinia";
import { computed, ComputedRef, inject, ref } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import { TicketAgentActivities } from "../ticket";

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

const tabs: ComputedRef<TabObject[]> = computed(() => {
  const _tabs: TabObject[] = [
    {
      name: "activity",
      label: "Activity",
      icon: ActivityIcon,
    },
    {
      name: "email",
      label: "Emails",
      icon: EmailIcon,
    },
    {
      name: "comment",
      label: "Comments",
      icon: CommentIcon,
    },
  ];

  if (isCallingEnabled.value) {
    _tabs.push({
      name: "call",
      label: "Calls",
      icon: PhoneIcon,
    });
  }
  return _tabs;
});

const { tabIndex, changeTabTo } = useActiveTabManager(tabs);

const { filterActivities } = useTicketActivities(
  activities,
  computed(() => ticket.value?.doc)
);

function countFor(eventType: TicketTab) {
  return filterActivities(eventType).length;
}
</script>
