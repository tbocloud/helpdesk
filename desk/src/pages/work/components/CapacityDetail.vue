<template>
  <!-- one person's plan: each working day, and where the hours come from -->
  <div class="flex flex-col gap-4 bg-surface-gray-1 px-4 py-3">
    <div class="min-w-0">
      <h3 class="text-xs text-ink-gray-5">{{ __("Each working day") }}</h3>
      <ul
        role="list"
        class="mt-2 flex gap-1 overflow-x-auto pb-1"
        :aria-label="__('Planned hours by day')"
      >
        <li
          v-for="day in person.days"
          :key="day.date"
          class="flex min-w-7 flex-1 flex-col items-center gap-1"
          :title="dayTitle(day)"
        >
          <span
            class="relative block h-10 w-full overflow-hidden rounded bg-surface-gray-3"
            aria-hidden="true"
          >
            <span
              class="absolute inset-x-0 bottom-0 block"
              :class="isOver(day) ? 'bg-danger' : 'bg-surface-gray-7'"
              :style="{ height: `${meterWidth(day)}%` }"
            />
          </span>
          <span
            class="font-mono text-2xs tabular-nums"
            :class="isOver(day) ? 'text-danger' : 'text-ink-gray-5'"
            aria-hidden="true"
          >
            {{ dayjs(day.date).format("dd D") }}
          </span>
          <span class="sr-only">{{ dayTitle(day) }}</span>
        </li>
      </ul>
    </div>

    <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
      <div class="min-w-0">
        <h3 class="text-xs text-ink-gray-5">{{ __("By project") }}</h3>
        <p v-if="!person.projects.length" class="mt-1 text-sm text-ink-gray-6">
          {{ __("No planned work in these weeks.") }}
        </p>
        <ul v-else role="list" class="mt-1 flex flex-col gap-1">
          <li
            v-for="project in person.projects"
            :key="project.project ?? ''"
            class="flex items-baseline justify-between gap-3 text-sm"
          >
            <span
              class="min-w-0 truncate"
              :class="project.project ? 'text-ink-gray-8' : 'text-ink-gray-5'"
            >
              {{ project.project_name ?? __("Other projects") }}
            </span>
            <span class="shrink-0 font-mono tabular-nums text-ink-gray-7">
              {{ formatHours(project.hours) }} h
            </span>
          </li>
        </ul>
      </div>

      <div class="min-w-0">
        <h3 class="text-xs text-ink-gray-5">{{ __("Biggest tasks") }}</h3>
        <p v-if="!person.tasks.length" class="mt-1 text-sm text-ink-gray-6">
          {{ __("None on your projects in these weeks.") }}
        </p>
        <ul v-else role="list" class="mt-1 flex flex-col gap-1">
          <li
            v-for="task in person.tasks"
            :key="task.name"
            class="flex items-baseline justify-between gap-3 text-sm"
          >
            <span
              class="min-w-0 truncate text-ink-gray-8"
              :title="taskTitle(task)"
            >
              {{ task.title }}
              <span v-if="task.project_name" class="text-ink-gray-5">
                · {{ task.project_name }}
              </span>
            </span>
            <span class="shrink-0 font-mono tabular-nums text-ink-gray-7">
              <span
                v-if="task.typical"
                :title="__('Standard estimate: no hours set')"
                >~</span
              >{{ formatHours(task.hours) }} h
            </span>
          </li>
        </ul>
      </div>
    </div>

    <p
      v-if="person.typical_estimates"
      class="flex items-center gap-1.5 text-p-sm text-ink-gray-6"
    >
      <LucideInfo class="size-3.5 shrink-0" aria-hidden="true" />
      {{
        person.typical_estimates === 1
          ? __("1 task has no hours set, so it counts at a standard estimate.")
          : __(
              "{0} tasks have no hours set, so they count at a standard estimate.",
              String(person.typical_estimates)
            )
      }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import LucideInfo from "~icons/lucide/info";
import {
  formatHours,
  isOver,
  loadText,
  meterWidth,
  type Load,
  type PersonCapacity,
} from "./capacity";

defineProps<{ person: PersonCapacity }>();

function dayTitle(day: Load & { date: string }) {
  return `${dayjs(day.date).format("ddd D MMM")}: ${loadText(day)}`;
}

function taskTitle(task: PersonCapacity["tasks"][number]) {
  const due = task.due ? dayjs(task.due).format("D MMM") : __("no due date");
  return __("{0} h in these weeks, due {1}", formatHours(task.hours), due);
}
</script>
