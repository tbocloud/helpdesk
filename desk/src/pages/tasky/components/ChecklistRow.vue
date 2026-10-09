<template>
  <div
    class="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-surface-gray-1"
  >
    <button
      type="button"
      role="checkbox"
      :aria-checked="done"
      :aria-label="
        done
          ? __('Reopen {0}', task.subject)
          : __('Mark {0} complete', task.subject)
      "
      class="flex size-[18px] shrink-0 items-center justify-center rounded border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
      :class="
        done
          ? 'border-transparent bg-success text-ink-base'
          : 'border-outline-gray-4 bg-surface-base hover:border-outline-gray-5'
      "
      @click="emit('toggle')"
    >
      <LucideCheck v-if="done" class="size-3" aria-hidden="true" />
    </button>

    <div class="min-w-0 flex-1">
      <div class="flex min-w-0 items-center gap-1.5">
        <span
          class="truncate text-sm"
          :class="done ? 'text-ink-gray-5 line-through' : 'text-ink-gray-9'"
        >
          {{ task.subject }}
        </span>
        <template v-if="task.is_key">
          <LucideStar
            class="size-3.5 shrink-0 fill-current text-warning"
            aria-hidden="true"
          />
          <span class="sr-only">{{ __("Key task") }}</span>
        </template>
        <MilestoneMark v-if="task.is_milestone" />
        <SlipBadge
          v-if="task.slip_count > 0 && !done"
          :count="task.slip_count"
        />
      </div>
      <div v-if="task.blocked && !done" class="mt-0.5 flex min-w-0">
        <WaitingOn :subject="task.depends_on_subject" />
      </div>
      <div
        v-if="onHold"
        class="mt-0.5 flex min-w-0 items-center gap-1 text-xs text-ink-gray-6"
      >
        <LucidePause class="size-3 shrink-0 text-warning" aria-hidden="true" />
        <span class="sr-only">{{ __("On hold:") }}</span>
        <span class="truncate">{{ __(task.hold_reason || "On hold") }}</span>
      </div>
      <HoldNote
        v-if="onHold"
        :note="task.hold_note"
        :by-name="task.hold_by_name"
        class="mt-0.5 pl-4"
      />
      <div
        class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-gray-5 md:hidden"
      >
        <span v-if="task.category">{{ task.category }}</span>
        <span
          v-if="onHold"
          class="font-medium tabular-nums text-warning"
          :title="dueTitle"
        >
          {{ holdLabel }}
        </span>
        <span
          v-else-if="task.due_date"
          class="tabular-nums"
          :class="overdue ? 'font-medium text-danger' : ''"
        >
          {{ shortDate(task.due_date)
          }}<template v-if="overdue"> · {{ __("Overdue") }}</template>
        </span>
      </div>
    </div>

    <span
      v-if="task.category"
      class="hidden shrink-0 rounded bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-6 md:inline"
    >
      {{ task.category }}
    </span>

    <span
      v-if="onHold"
      class="hidden w-28 shrink-0 items-center justify-end gap-1 text-xs font-medium tabular-nums text-warning md:flex"
      :title="dueTitle"
    >
      <LucidePause class="size-3.5" aria-hidden="true" />
      {{ holdLabel }}
    </span>
    <span
      v-else-if="task.due_date"
      class="hidden w-28 shrink-0 items-center justify-end gap-1 text-xs tabular-nums md:flex"
      :class="overdue ? 'font-medium text-danger' : 'text-ink-gray-5'"
      :title="aiTitle"
    >
      <LucideSparkles
        v-if="task.ai_estimated"
        class="size-3 text-ink-gray-4"
        aria-hidden="true"
      />
      <component
        :is="overdue ? LucideAlarmClock : LucideCalendar"
        class="size-3.5"
        aria-hidden="true"
      />
      {{ shortDate(task.due_date) }}
      <span v-if="overdue" class="sr-only">{{ __("Overdue") }}</span>
      <span v-if="task.ai_estimated" class="sr-only">{{
        __("Due date set by AI")
      }}</span>
    </span>
    <span v-else class="hidden w-28 shrink-0 md:block" />

    <component
      :is="priorityIcon(task.priority)"
      class="size-4 shrink-0"
      :class="task.priority === 'Urgent' ? 'text-danger' : 'text-ink-gray-5'"
      role="img"
      :aria-label="__('{0} priority', __(task.priority || 'Low'))"
    />

    <div class="flex w-6 shrink-0 justify-center">
      <UserAvatar v-if="task.assigned_to" :name="task.assigned_to" size="sm" />
    </div>

    <div class="hidden w-28 shrink-0 justify-end sm:flex">
      <TaskStatusBadge :status="task.status" />
    </div>

    <div class="flex w-7 shrink-0 justify-center">
      <Dropdown v-if="actions.length" :options="actions" align="end">
        <Button
          variant="ghost"
          size="sm"
          :aria-label="__('Actions for {0}', task.subject)"
        >
          <template #icon>
            <LucideMoreHorizontal class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </Dropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
import { UserAvatar } from "@/components";
import { __ } from "@/translation";
import { Button, Dropdown, dayjs } from "frappe-ui";
import { computed } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideCalendar from "~icons/lucide/calendar";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCheck from "~icons/lucide/check";
import LucideCheckCheck from "~icons/lucide/check-check";
import LucideMoreHorizontal from "~icons/lucide/more-horizontal";
import LucideSparkles from "~icons/lucide/sparkles";
import LucidePause from "~icons/lucide/pause";
import LucidePencil from "~icons/lucide/pencil";
import LucidePlay from "~icons/lucide/play";
import LucideStar from "~icons/lucide/star";
import LucideUndo2 from "~icons/lucide/undo-2";
import LucideUserPlus from "~icons/lucide/user-plus";
import {
  holdDays,
  holdDurationLabel,
  isClosed,
  isOnHold,
  isPendingReview,
  isOverdue,
  priorityIcon,
  shortDate,
} from "../taskMeta";
import HoldNote from "./HoldNote.vue";
import MilestoneMark from "./MilestoneMark.vue";
import SlipBadge from "./SlipBadge.vue";
import TaskStatusBadge from "./TaskStatusBadge.vue";
import WaitingOn from "./WaitingOn.vue";

const props = defineProps<{
  task: Record<string, any>;
  /** The viewer is the project's manager or lead: show plan and review actions. */
  canManage?: boolean;
  /** The viewer may edit the task (manager, lead, or its assignee). */
  canEdit?: boolean;
}>();
const emit = defineEmits<{
  toggle: [];
  hold: [];
  resume: [];
  plan: [];
  edit: [];
  approve: [];
  sendBack: [];
  askHelp: [];
  handOver: [];
}>();

const done = computed(() => props.task.status === "Completed");
const overdue = computed(() => isOverdue(props.task));
const onHold = computed(() => isOnHold(props.task));
const holdLabel = computed(() => holdDurationLabel(holdDays(props.task)));
const dueTitle = computed(() =>
  props.task.due_date
    ? __("Due {0}", dayjs(props.task.due_date).format("D MMM YYYY"))
    : undefined
);

const aiTitle = computed(() =>
  props.task.ai_estimated
    ? __("Due date set by AI: {0}", props.task.estimate_note || "")
    : dueTitle.value
);

// the assignee (or lead) brings in a teammate or passes the task on
const teamwork = computed(() => {
  if (!props.canEdit || isClosed(props.task)) return [];
  return [
    // a task waits on one other task, so asking for help needs it free
    ...(props.task.blocked
      ? []
      : [
          {
            label: __("Ask a teammate for help"),
            icon: LucideUserPlus,
            onClick: () => emit("askHelp"),
          },
        ]),
    {
      label: __("Hand over"),
      icon: LucideArrowRight,
      onClick: () => emit("handOver"),
    },
  ];
});

const actions = computed(() => {
  const edit = props.canEdit
    ? [{ label: __("Edit"), icon: LucidePencil, onClick: () => emit("edit") }]
    : [];
  const review =
    props.canManage && isPendingReview(props.task)
      ? [
          {
            label: __("Approve"),
            icon: LucideCheckCheck,
            onClick: () => emit("approve"),
          },
          {
            label: __("Send back"),
            icon: LucideUndo2,
            onClick: () => emit("sendBack"),
          },
        ]
      : [];
  const plan =
    props.canManage && !isClosed(props.task)
      ? [
          {
            label: __("Plan"),
            icon: LucideCalendarClock,
            onClick: () => emit("plan"),
          },
        ]
      : [];
  if (onHold.value)
    return [
      ...edit,
      ...plan,
      ...teamwork.value,
      { label: __("Resume"), icon: LucidePlay, onClick: () => emit("resume") },
    ];
  if (isClosed(props.task)) return edit;
  return [
    ...edit,
    ...review,
    ...plan,
    ...teamwork.value,
    {
      label: __("Put on hold"),
      icon: LucidePause,
      onClick: () => emit("hold"),
    },
  ];
});
</script>
