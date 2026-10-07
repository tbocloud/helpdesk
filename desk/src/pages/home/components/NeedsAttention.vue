<template>
  <HomeCard
    :title="__('Needs attention')"
    :to="{ name: 'WorkOverview' }"
    :link-label="__('Overview')"
  >
    <p
      v-if="!groups.length"
      class="flex items-center gap-2 px-4 py-5 text-p-sm text-ink-gray-6"
    >
      <LucideCircleCheck
        class="size-4 shrink-0 text-success"
        aria-hidden="true"
      />
      {{ __("Nothing is overdue, at risk, unassigned or stuck waiting.") }}
    </p>
    <div
      v-for="group in groups"
      :key="group.key"
      class="border-b border-outline-gray-2 last:border-b-0"
      role="group"
      :aria-labelledby="`${uid}-${group.key}`"
    >
      <div class="flex items-center justify-between gap-2 px-4 pb-1 pt-3">
        <h3 :id="`${uid}-${group.key}`" class="flex items-center gap-2">
          <TaskyBadge
            :tone="reasonTone(group.key)"
            :icon="REASON_ICON[group.key]"
            :label="reasonLabel(group.key)"
          />
          <span class="font-mono text-xs tabular-nums text-ink-gray-6">
            {{ group.count }}
          </span>
        </h3>
        <RouterLink
          v-if="group.count > group.items.length"
          :to="reasonLink(group.key)"
          class="shrink-0 rounded text-p-sm text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          {{ __("See all {0}", String(group.count)) }}
        </RouterLink>
      </div>
      <ul role="list">
        <li v-for="item in group.items" :key="itemKey(item)">
          <HomeItemRow :item="item" show-assignee>
            <template v-if="canTake(group.key, item)" #action>
              <Button
                size="sm"
                :label="__('Take it')"
                :icon-left="LucideUserPlus"
                :loading="taking === item.name"
                :aria-label="__('Assign to me: {0}', item.title)"
                @click="take(item)"
              />
            </template>
          </HomeItemRow>
        </li>
      </ul>
    </div>
  </HomeCard>
</template>

<script setup lang="ts">
import TaskyBadge from "@/pages/tasky/components/TaskyBadge.vue";
import { errorText } from "@/pages/tasky/taskMeta";
import { itemKey, type WorkItem } from "@/pages/work/workMeta";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { Button, createResource, toast } from "frappe-ui";
import { ref, useId, type Component } from "vue";
import { RouterLink } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideUserPlus from "~icons/lucide/user-plus";
import LucideUserX from "~icons/lucide/user-x";
import {
  reasonLabel,
  reasonLink,
  reasonTone,
  type AttentionGroup,
  type AttentionReason,
} from "../homeMeta";
import HomeCard from "./HomeCard.vue";
import HomeItemRow from "./HomeItemRow.vue";

defineProps<{ groups: AttentionGroup[] }>();
const emit = defineEmits<{ changed: [] }>();

const REASON_ICON: Record<AttentionReason, Component> = {
  overdue: LucideAlarmClock,
  at_risk: LucideCircleAlert,
  unassigned_tickets: LucideUserX,
  waiting_on_customer: LucideHourglass,
};

const uid = useId();
const authStore = useAuthStore();
const taking = ref<string | null>(null);

// tickets can only be assigned to agents, so only agents get "Take it"
function canTake(reason: AttentionReason, item: WorkItem) {
  return (
    reason === "unassigned_tickets" &&
    item.kind === "ticket" &&
    !item.assignees.length &&
    authStore.hasAgentRecord
  );
}

// the same endpoint the ticket page's assign control uses
const assign = createResource({
  url: "frappe.desk.form.assign_to.add",
  onSuccess() {
    toast.success(__("Assigned to you"));
    taking.value = null;
    emit("changed");
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't assign the ticket.")));
    taking.value = null;
  },
});

function take(item: WorkItem) {
  if (assign.loading) return;
  taking.value = item.name;
  assign.submit({
    doctype: "HD Ticket",
    name: item.name,
    assign_to: [authStore.userId],
  });
}
</script>
