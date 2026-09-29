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
      </div>
      <div
        class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-gray-5 md:hidden"
      >
        <span v-if="task.category">{{ task.category }}</span>
        <span
          v-if="task.due_date"
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
      v-if="task.due_date"
      class="hidden w-28 shrink-0 items-center justify-end gap-1 text-xs tabular-nums md:flex"
      :class="overdue ? 'font-medium text-danger' : 'text-ink-gray-5'"
    >
      <component
        :is="overdue ? LucideAlarmClock : LucideCalendar"
        class="size-3.5"
        aria-hidden="true"
      />
      {{ shortDate(task.due_date) }}
      <span v-if="overdue" class="sr-only">{{ __("Overdue") }}</span>
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
  </div>
</template>

<script setup lang="ts">
import { UserAvatar } from "@/components";
import { __ } from "@/translation";
import { computed } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCalendar from "~icons/lucide/calendar";
import LucideCheck from "~icons/lucide/check";
import LucideStar from "~icons/lucide/star";
import { isOverdue, priorityIcon, shortDate } from "../taskMeta";
import TaskStatusBadge from "./TaskStatusBadge.vue";

const props = defineProps<{ task: Record<string, any> }>();
const emit = defineEmits<{ toggle: [] }>();

const done = computed(() => props.task.status === "Completed");
const overdue = computed(() => isOverdue(props.task));
</script>
