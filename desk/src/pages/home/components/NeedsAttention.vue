<template>
  <SectionCard
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
              <div class="flex items-center gap-2">
                <!-- frappe-ui's Button swaps aria-label for `label`: the name is sr-only text -->
                <Button
                  size="sm"
                  :icon-left="LucideUserPlus"
                  :loading="saving?.ticket === item.name && saving.self"
                  @click="assign(item, authStore.userId, '')"
                >
                  <span aria-hidden="true">{{ __("Take it") }}</span>
                  <span class="sr-only">{{
                    __("Assign to me: {0}", item.title)
                  }}</span>
                </Button>
                <AssignPicker
                  :title="item.title"
                  :customer="item.customer"
                  :loading="saving?.ticket === item.name && !saving.self"
                  @pick="(user, name) => assign(item, user, name)"
                />
              </div>
            </template>
          </HomeItemRow>
        </li>
      </ul>
    </div>
  </SectionCard>
</template>

<script setup lang="ts">
import { assignTicket } from "@/composables/ticketAssignment";
import { errorText } from "@/utils";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { itemKey, type WorkItem } from "@/pages/work/workMeta";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { Button, toast } from "frappe-ui";
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
import SectionCard from "@/components/SectionCard.vue";
import AssignPicker from "./AssignPicker.vue";
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
// one assignment at a time; `self` tells which button spins
const saving = ref<{ ticket: string; self: boolean } | null>(null);

// tickets can only be assigned to agents, and every agent may assign a ticket on
// its page, so agents get both "Take it" and "Assign"
function canTake(reason: AttentionReason, item: WorkItem) {
  return (
    reason === "unassigned_tickets" &&
    item.kind === "ticket" &&
    !item.assignees.length &&
    authStore.hasAgentRecord
  );
}

/** `name` is the assignee's name for the toast; empty when it's the viewer. */
async function assign(item: WorkItem, user: string, name: string) {
  if (saving.value) return;
  saving.value = { ticket: item.name, self: !name };
  try {
    await assignTicket(item.name, [user]);
    toast.success(name ? __("Assigned to {0}", name) : __("Assigned to you"));
    emit("changed");
  } catch (e) {
    toast.error(errorText(e, __("Couldn't assign the ticket.")));
  } finally {
    saving.value = null;
  }
}
</script>
