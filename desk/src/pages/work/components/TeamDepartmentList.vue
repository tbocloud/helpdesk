<template>
  <!-- one row per department -->
  <SectionCard
    :title="__('Departments')"
    :count="departments.length"
    :description="__('Open a department to see its people and projects.')"
    class="overflow-hidden"
  >
    <TaskyState
      v-if="!departments.length"
      :icon="LucideBuilding2"
      :title="__('No departments yet')"
      :message="__('Add them in Settings → Departments.')"
    />
    <template v-else>
      <div
        class="hidden gap-3 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2 text-xs text-ink-gray-5 lg:grid"
        :class="GRID"
        aria-hidden="true"
      >
        <span>{{ __("Department") }}</span>
        <span class="text-right">{{ __("People") }}</span>
        <span class="text-right">{{ __("Done") }}</span>
        <span class="text-right">{{ __("On time") }}</span>
        <span class="text-right">{{ __("Overdue") }}</span>
        <span class="text-right">{{ __("Hours") }}</span>
        <span>{{ __("Champion") }}</span>
      </div>
      <ul role="list">
        <li
          v-for="row in departments"
          :key="row.department || ''"
          class="border-b border-outline-gray-1 last:border-b-0"
        >
          <component
            :is="row.department ? NativeButton : 'div'"
            v-bind="row.department ? { type: 'button' } : {}"
            class="flex w-full flex-col gap-1.5 px-4 py-3 text-left lg:grid lg:items-center lg:gap-3"
            :class="[
              GRID,
              row.department
                ? 'transition-colors hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4'
                : '',
            ]"
            :aria-label="
              row.department
                ? __('Show the {0} department', row.department)
                : undefined
            "
            @click="row.department && emit('open', row.department)"
          >
            <span class="flex min-w-0 items-center justify-between gap-2">
              <span class="truncate text-base text-ink-gray-9">
                {{ departmentLabel(row.department) }}
              </span>
              <LucideChevronRight
                v-if="row.department"
                class="size-4 shrink-0 text-ink-gray-4 lg:hidden"
                aria-hidden="true"
              />
            </span>

            <!-- small screens: one labelled line -->
            <span
              class="flex flex-wrap gap-x-3 gap-y-0.5 text-p-sm tabular-nums text-ink-gray-6 lg:hidden"
            >
              <span>{{ __("{0} people", String(row.people)) }}</span>
              <span>{{ __("{0} done", String(row.tasks)) }}</span>
              <span>{{ __("{0} on time", pctText(row.on_time_pct)) }}</span>
              <span
                v-if="row.overdue"
                class="inline-flex items-center gap-1 text-danger"
              >
                <LucideAlarmClock class="size-3.5" aria-hidden="true" />
                {{ __("{0} overdue", String(row.overdue)) }}
              </span>
              <span>{{ hoursText(row.hours || 0) }}</span>
            </span>

            <span class="hidden text-right font-mono tabular-nums lg:block">
              {{ row.people }}
            </span>
            <span class="hidden text-right font-mono tabular-nums lg:block">
              {{ row.tasks }}
            </span>
            <span class="hidden text-right font-mono tabular-nums lg:block">
              {{ pctText(row.on_time_pct) }}
            </span>
            <span
              class="hidden items-center justify-end gap-1 font-mono tabular-nums lg:flex"
              :class="row.overdue ? 'text-danger' : 'text-ink-gray-5'"
            >
              <LucideAlarmClock
                v-if="row.overdue"
                class="size-3.5"
                aria-hidden="true"
              />
              {{ row.overdue }}
            </span>
            <span
              class="hidden text-right font-mono tabular-nums text-ink-gray-6 lg:block"
            >
              {{ hoursText(row.hours || 0) }}
            </span>

            <span class="flex min-w-0 items-center gap-2 text-sm">
              <template v-if="row.champion">
                <LucideAward
                  class="size-3.5 shrink-0 text-ink-gray-5"
                  aria-hidden="true"
                />
                <span class="sr-only">{{ __("Champion") }}</span>
                <span class="truncate text-ink-gray-8">{{
                  row.champion.name
                }}</span>
                <span class="font-mono text-xs tabular-nums text-ink-gray-5">
                  {{ row.champion.score }}
                </span>
              </template>
              <span v-else-if="row.department" class="text-ink-gray-5">
                {{ __("No champion yet") }}
              </span>
            </span>
          </component>
        </li>
      </ul>
    </template>
  </SectionCard>
</template>

<script setup lang="ts">
import NativeButton from "@/components/NativeButton";
import SectionCard from "@/components/SectionCard.vue";
import TaskyState from "@/components/TaskyState.vue";
import { pctText } from "@/pages/performance/performanceMeta";
import { __ } from "@/translation";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideAward from "~icons/lucide/award";
import LucideBuilding2 from "~icons/lucide/building-2";
import LucideChevronRight from "~icons/lucide/chevron-right";
import {
  departmentLabel,
  hoursText,
  type DepartmentRow,
} from "../teamDashboardMeta";

defineProps<{ departments: DepartmentRow[] }>();
const emit = defineEmits<{ open: [department: string] }>();

const GRID =
  "lg:grid-cols-[minmax(0,1.6fr)_repeat(5,minmax(0,0.6fr))_minmax(0,1.6fr)]";
</script>
