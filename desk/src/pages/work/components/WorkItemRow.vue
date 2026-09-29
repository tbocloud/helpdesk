<template>
  <component
    :is="to ? RouterLink : 'div'"
    v-bind="to ? { to } : {}"
    class="grid w-full grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 px-4 py-3 text-left transition-colors focus-visible:outline-none"
    :class="[
      to ? 'hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1' : '',
      showAssignees
        ? 'md:grid-cols-[1fr_9rem_8rem_9rem]'
        : 'md:grid-cols-[1fr_8rem_9rem]',
    ]"
  >
    <div class="flex min-w-0 items-start gap-3">
      <component
        :is="item.kind === 'ticket' ? LucideTicket : LucideSquareCheck"
        class="mt-0.5 size-4 shrink-0 text-ink-gray-6"
        aria-hidden="true"
      />
      <div class="min-w-0">
        <div class="flex min-w-0 items-center gap-1.5">
          <span class="sr-only">{{
            item.kind === "ticket" ? __("Ticket") : __("Task")
          }}</span>
          <span class="truncate text-base text-ink-gray-9">
            {{ item.title }}
          </span>
          <template v-if="item.is_key">
            <LucideStar
              class="size-3.5 shrink-0 fill-current text-warning"
              aria-hidden="true"
            />
            <span class="sr-only">{{ __("Key") }}</span>
          </template>
          <MilestoneMark v-if="item.kind === 'task' && item.is_milestone" />
          <SlipBadge
            v-if="item.kind === 'task' && item.slip_count"
            :count="item.slip_count"
          />
        </div>
        <div
          class="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-1.5 text-sm text-ink-gray-5"
        >
          <span v-if="context" class="truncate">{{ context }}</span>
          <span v-if="context" aria-hidden="true">·</span>
          <span class="font-mono text-xs tabular-nums">{{ reference }}</span>
          <template v-if="item.kind === 'task' && item.hd_ticket">
            <span aria-hidden="true">·</span>
            <span class="inline-flex items-center gap-1">
              <LucideTicket class="size-3" aria-hidden="true" />
              <span class="sr-only">{{ __("From ticket") }}</span>
              <span class="font-mono text-xs tabular-nums"
                >#{{ item.hd_ticket }}</span
              >
            </span>
          </template>
          <template v-if="item.kind === 'task' && item.waiting_on">
            <span aria-hidden="true">·</span>
            <WaitingOn :subject="item.waiting_on" />
          </template>
          <span class="md:hidden" aria-hidden="true">·</span>
          <span class="md:hidden" :class="onHold ? 'min-w-0 max-w-full' : ''">
            <TaskyBadge
              v-if="onHold"
              tone="warning"
              :icon="LucidePause"
              class="max-w-full"
              :title="holdChip"
            >
              <span class="truncate">{{ holdChip }}</span>
            </TaskyBadge>
            <TaskStatusBadge
              v-else-if="item.kind === 'task'"
              :status="item.status"
            />
            <TaskyBadge
              v-else
              :tone="ticketTone"
              :icon="ticketIcon"
              :label="item.status"
            />
          </span>
        </div>
        <div
          v-if="risks.length"
          class="mt-1 flex min-w-0 items-center gap-1 text-xs text-warning"
          :title="risks.join('\n')"
        >
          <LucideTriangleAlert class="size-3 shrink-0" aria-hidden="true" />
          <span class="sr-only">{{ __("At risk:") }}</span>
          <span class="truncate">{{ risks[0] }}</span>
          <template v-if="risks.length > 1">
            <span class="shrink-0 font-mono tabular-nums" aria-hidden="true">
              +{{ risks.length - 1 }}
            </span>
            <span class="sr-only">{{ risks.slice(1).join("; ") }}</span>
          </template>
        </div>
      </div>
    </div>

    <div v-if="showAssignees" class="hidden min-w-0 items-center gap-2 md:flex">
      <template v-if="item.assignees.length">
        <div class="flex shrink-0 -space-x-1.5">
          <Avatar
            v-for="user in item.assignees.slice(0, 3)"
            :key="user"
            shape="circle"
            size="sm"
            class="ring-2 ring-[var(--surface-base)]"
            :image="userStore.getUser(user)?.user_image"
            :label="userStore.getUser(user)?.full_name || user"
            aria-hidden="true"
          />
        </div>
        <span class="truncate text-sm text-ink-gray-7" :title="allAssignees">
          {{ assigneeLabel }}
        </span>
      </template>
      <span v-else class="text-sm text-ink-gray-5">{{ __("Unassigned") }}</span>
    </div>

    <div class="hidden min-w-0 md:block">
      <TaskyBadge
        v-if="onHold"
        tone="warning"
        :icon="LucidePause"
        class="max-w-full"
        :title="holdChip"
      >
        <span class="truncate">{{ holdChip }}</span>
      </TaskyBadge>
      <TaskStatusBadge v-else-if="item.kind === 'task'" :status="item.status" />
      <TaskyBadge
        v-else
        :tone="ticketTone"
        :icon="ticketIcon"
        :label="item.status"
      />
    </div>

    <div
      v-if="onHold"
      class="flex items-center justify-end gap-1 whitespace-nowrap text-sm tabular-nums text-ink-gray-5"
      :title="deadlineTitle ? __('Due {0}', deadlineTitle) : undefined"
    >
      {{ holdDuration }}
    </div>
    <div
      v-else
      class="flex items-center justify-end gap-1 whitespace-nowrap text-sm tabular-nums"
      :class="deadline.overdue ? 'font-medium text-danger' : 'text-ink-gray-5'"
      :title="deadlineTitle"
    >
      <LucideAlarmClock
        v-if="deadline.overdue"
        class="size-3.5 shrink-0"
        aria-hidden="true"
      />
      {{ deadline.label }}
    </div>
  </component>
</template>

<script setup lang="ts">
import { useUserStore } from "@/stores/user";
import { __ } from "@/translation";
import { Avatar, dayjs } from "frappe-ui";
import { computed } from "vue";
import { RouterLink } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideHourglass from "~icons/lucide/hourglass";
import LucidePause from "~icons/lucide/pause";
import LucideSquareCheck from "~icons/lucide/square-check";
import LucideStar from "~icons/lucide/star";
import LucideTicket from "~icons/lucide/ticket";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import MilestoneMark from "@/pages/tasky/components/MilestoneMark.vue";
import SlipBadge from "@/pages/tasky/components/SlipBadge.vue";
import TaskStatusBadge from "@/pages/tasky/components/TaskStatusBadge.vue";
import TaskyBadge from "@/pages/tasky/components/TaskyBadge.vue";
import WaitingOn from "@/pages/tasky/components/WaitingOn.vue";
import type { Tone } from "@/pages/tasky/taskMeta";
import {
  deadlineInfo,
  isHeldTask,
  itemRoute,
  type WorkItem,
} from "../workMeta";

const props = defineProps<{
  item: WorkItem;
  showAssignees?: boolean;
}>();

const userStore = useUserStore();

const to = computed(() => itemRoute(props.item));
const risks = computed(() => props.item.risks ?? []);
const deadline = computed(() => deadlineInfo(props.item));

const onHold = computed(() => isHeldTask(props.item));
const holdChip = computed(() =>
  props.item.hold_reason
    ? __("On hold · {0}", __(props.item.hold_reason))
    : __("On hold")
);
const holdDuration = computed(() => {
  const days = props.item.hold_days ?? 0;
  if (days <= 0) return __("Since today");
  return days === 1 ? __("1 day") : __("{0} days", String(days));
});

const context = computed(() =>
  props.item.kind === "ticket"
    ? props.item.customer
    : props.item.project_name || props.item.project
);

const reference = computed(() =>
  props.item.kind === "ticket" ? `#${props.item.name}` : props.item.name
);

const isWaiting = computed(() => props.item.status === "Waiting on Task");
const ticketTone = computed<Tone>(() => (isWaiting.value ? "info" : "neutral"));
const ticketIcon = computed(() =>
  isWaiting.value ? LucideHourglass : LucideCircleDot
);

const deadlineTitle = computed(() => {
  if (!props.item.deadline) return undefined;
  return props.item.kind === "ticket"
    ? dayjs(props.item.deadline).format("D MMM YYYY, h:mm A")
    : dayjs(props.item.deadline).format("D MMM YYYY");
});

const assigneeLabel = computed(() => {
  const [first, ...rest] = props.item.assignees;
  const name = userStore.getUser(first)?.full_name || first;
  return rest.length ? `${name} +${rest.length}` : name;
});

const allAssignees = computed(() =>
  props.item.assignees
    .map((u) => userStore.getUser(u)?.full_name || u)
    .join(", ")
);
</script>
