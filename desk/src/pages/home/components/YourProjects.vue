<template>
  <SectionCard
    :title="__('Your projects')"
    :count="projects.count"
    :to="{ name: 'TaskyProjects' }"
    :link-label="
      projects.count > projects.items.length
        ? __('See all {0}', String(projects.count))
        : __('Projects')
    "
  >
    <ul role="list">
      <li
        v-for="project in projects.items"
        :key="project.name"
        class="border-b border-outline-gray-2 last:border-b-0"
      >
        <RouterLink
          :to="{ name: 'TaskyProject', params: { projectId: project.name } }"
          class="flex items-start gap-3 px-4 py-3 hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
        >
          <LucideFolderKanban
            class="mt-0.5 size-4 shrink-0 text-ink-gray-6"
            aria-hidden="true"
          />
          <span class="min-w-0 flex-1">
            <span class="flex flex-wrap items-baseline justify-between gap-x-3">
              <span class="min-w-0 break-words text-base text-ink-gray-9">
                {{ project.project_name }}
              </span>
              <span class="whitespace-nowrap text-sm tabular-nums">
                <span class="text-ink-gray-7">{{
                  __("{0} open for you", String(project.open))
                }}</span>
                <template v-if="project.overdue">
                  <span class="text-ink-gray-4" aria-hidden="true"> · </span>
                  <span class="inline-flex items-center gap-1 text-danger">
                    <LucideAlarmClock class="size-3.5" aria-hidden="true" />
                    {{ __("{0} overdue", String(project.overdue)) }}
                  </span>
                </template>
              </span>
            </span>
            <span
              v-if="project.customer"
              class="mt-0.5 block truncate text-sm text-ink-gray-5"
              :title="project.customer"
            >
              {{ project.customer }}
            </span>
            <span
              v-if="project.next_milestone"
              class="mt-0.5 flex min-w-0 items-center gap-1 text-sm text-ink-gray-6"
            >
              <LucideFlag class="size-3.5 shrink-0" aria-hidden="true" />
              <span class="truncate" :title="project.next_milestone.subject">
                {{
                  project.next_milestone.due
                    ? __(
                        "Next milestone: {0}, {1}",
                        project.next_milestone.subject,
                        dayjs(project.next_milestone.due).format("D MMM")
                      )
                    : __("Next milestone: {0}", project.next_milestone.subject)
                }}
              </span>
            </span>
            <span
              v-if="project.team_open !== null"
              class="mt-0.5 block text-sm tabular-nums text-ink-gray-5"
            >
              {{
                project.team_overdue
                  ? __(
                      "Whole project: {0} open, {1} overdue",
                      String(project.team_open),
                      String(project.team_overdue)
                    )
                  : __("Whole project: {0} open", String(project.team_open))
              }}
            </span>
          </span>
        </RouterLink>
      </li>
    </ul>
  </SectionCard>
</template>

<script setup lang="ts">
import SectionCard from "@/components/SectionCard.vue";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import { RouterLink } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideFlag from "~icons/lucide/flag";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import type { DaySection, MyProject } from "../homeMeta";

defineProps<{ projects: DaySection<MyProject> }>();
</script>
