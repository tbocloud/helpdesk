<template>
  <SectionCard
    :title="__('Projects')"
    :count="projects.length"
    :description="
      __(
        'Projects with more than one person: progress, and who did what this period.'
      )
    "
    class="overflow-hidden"
  >
    <TaskyState
      v-if="!projects.length"
      :icon="LucideFolderKanban"
      :title="__('No shared projects here')"
      :message="
        __(
          'Open projects with two or more members, or ones with work this period, show up here.'
        )
      "
    />
    <ul v-else role="list">
      <li
        v-for="p in projects"
        :key="p.project"
        class="flex flex-col gap-3 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0 lg:grid lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1.7fr)] lg:items-start lg:gap-6"
        :class="highlight === p.project ? 'bg-surface-gray-1' : ''"
      >
        <!-- project -->
        <div class="min-w-0">
          <RouterLink
            :to="{ name: 'TaskyProject', params: { projectId: p.project } }"
            class="rounded text-base text-ink-gray-9 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          >
            {{ p.project_name }}
          </RouterLink>
          <div class="mt-0.5 truncate text-xs text-ink-gray-5">
            {{
              [p.customer, departmentLabel(p.department), memberText(p)]
                .filter(Boolean)
                .join(" · ")
            }}
          </div>
          <TaskyBadge
            v-if="p.status !== 'Open'"
            class="mt-1.5"
            :label="__(p.status)"
          />
        </div>

        <!-- progress and the period's numbers -->
        <div class="flex min-w-0 flex-col gap-1.5">
          <div class="flex items-center gap-2">
            <span
              class="block h-1.5 flex-1 overflow-hidden rounded-full bg-surface-gray-2"
              role="meter"
              :aria-valuenow="percent(p)"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-label="__('Progress of {0}', p.project_name)"
            >
              <span
                class="block h-full rounded-full bg-surface-gray-7"
                :style="{ width: `${percent(p)}%` }"
              />
            </span>
            <span class="font-mono text-xs tabular-nums text-ink-gray-6">
              {{ p.done }}/{{ p.total }}
            </span>
          </div>
          <div
            class="flex flex-wrap gap-x-3 gap-y-0.5 text-p-sm tabular-nums text-ink-gray-6"
          >
            <span>{{ __("{0} done this period", String(p.tasks)) }}</span>
            <span
              v-if="p.overdue"
              class="inline-flex items-center gap-1 text-danger"
            >
              <LucideAlarmClock class="size-3.5" aria-hidden="true" />
              {{ __("{0} overdue", String(p.overdue)) }}
            </span>
            <span>{{ hoursText(p.hours) }}</span>
          </div>
        </div>

        <!-- contribution per person -->
        <div class="min-w-0">
          <p v-if="!p.contributors.length" class="text-p-sm text-ink-gray-5">
            {{ __("No one finished or logged anything here this period.") }}
          </p>
          <ul
            v-else
            class="flex flex-wrap gap-1.5"
            :aria-label="__('Contribution per person')"
          >
            <li
              v-for="c in p.contributors"
              :key="c.user"
              class="inline-flex min-w-0 items-center gap-1.5 rounded-md border border-outline-gray-2 py-0.5 pl-0.5 pr-2 text-xs"
            >
              <Avatar :label="c.name" :image="c.image || undefined" size="sm" />
              <span class="max-w-[9rem] truncate text-ink-gray-8">{{
                c.name
              }}</span>
              <span class="font-mono tabular-nums text-ink-gray-6">
                {{ __("{0} done", String(c.tasks)) }} ·
                {{ hoursText(c.hours) }}
              </span>
              <span
                v-if="c.overdue"
                class="inline-flex items-center gap-0.5 font-mono tabular-nums text-danger"
              >
                <LucideAlarmClock class="size-3" aria-hidden="true" />
                {{ c.overdue }}
                <span class="sr-only">{{ __("overdue") }}</span>
              </span>
            </li>
          </ul>
        </div>
      </li>
    </ul>
  </SectionCard>
</template>

<script setup lang="ts">
import SectionCard from "@/components/SectionCard.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { Avatar } from "frappe-ui";
import { RouterLink } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import {
  departmentLabel,
  hoursText,
  type ProjectRow,
} from "../teamDashboardMeta";

defineProps<{
  projects: ProjectRow[];
  /** a project picked from the URL, shown highlighted */
  highlight?: string;
}>();

const percent = (p: ProjectRow) =>
  p.total ? Math.round((p.done / p.total) * 100) : 0;
const memberText = (p: ProjectRow) => __("{0} members", String(p.members));
</script>
