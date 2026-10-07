<template>
  <SectionCard
    :title="__('Open tickets by customer')"
    :to="ticketLinks.open()"
    :link-label="__('Tickets')"
  >
    <ul v-if="company.tickets.by_customer.length" role="list">
      <li
        v-for="row in company.tickets.by_customer"
        :key="row.customer || '-'"
        class="flex items-center justify-between gap-3 border-b border-outline-gray-1 px-4 py-2.5 text-sm last:border-b-0"
      >
        <RouterLink
          v-if="row.customer"
          :to="{ name: 'Customer', params: { id: row.customer } }"
          class="min-w-0 break-words rounded text-ink-gray-8 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          {{ row.customer }}
        </RouterLink>
        <span v-else class="text-ink-gray-6">{{ __("No customer") }}</span>
        <span class="shrink-0 font-mono tabular-nums text-ink-gray-8">
          {{ row.open }}
        </span>
      </li>
    </ul>
    <p v-else class="px-4 py-4 text-p-sm text-ink-gray-6">
      {{ __("No open tickets.") }}
    </p>
  </SectionCard>

  <SectionCard
    :title="__('Ending in the next 14 days')"
    :to="{ name: 'TaskyProjects' }"
    :link-label="__('Projects')"
  >
    <ul v-if="company.ending_soon.length" role="list">
      <li
        v-for="project in company.ending_soon"
        :key="project.name"
        class="border-b border-outline-gray-1 last:border-b-0"
      >
        <RouterLink
          :to="{ name: 'TaskyProject', params: { projectId: project.name } }"
          class="flex flex-col gap-1.5 px-4 py-3 hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
        >
          <span class="flex items-start justify-between gap-2">
            <span class="min-w-0 break-words text-sm text-ink-gray-9">
              {{ project.project_name }}
            </span>
            <span
              class="inline-flex shrink-0 items-center gap-1 whitespace-nowrap text-xs"
              :class="
                late(project) ? 'font-medium text-danger' : 'text-ink-gray-6'
              "
            >
              <LucideAlarmClock
                v-if="late(project)"
                class="size-3"
                aria-hidden="true"
              />
              {{ endingLabel(project.days_left) }}
            </span>
          </span>
          <span class="flex items-center gap-2">
            <span
              class="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-gray-2"
              role="progressbar"
              :aria-valuenow="project.progress"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-label="__('{0} done', project.project_name)"
            >
              <span
                class="block h-full rounded-full bg-surface-gray-7"
                :style="{ width: `${project.progress}%` }"
              />
            </span>
            <span
              class="w-9 text-right font-mono text-xs tabular-nums text-ink-gray-6"
            >
              {{ project.progress }}%
            </span>
          </span>
          <span class="text-p-xs text-ink-gray-5">
            {{ project.customer || project.lead_name || "" }}
            <template v-if="project.overdue">
              <span v-if="project.customer || project.lead_name">·</span>
              <span class="text-danger">
                {{ __("{0} overdue", String(project.overdue)) }}
              </span>
            </template>
          </span>
        </RouterLink>
      </li>
    </ul>
    <p v-else class="px-4 py-4 text-p-sm text-ink-gray-6">
      {{ __("No project ends in the next 14 days.") }}
    </p>
  </SectionCard>

  <SectionCard :title="__('Team load')" :to="{ name: 'TeamWorkload' }">
    <ul v-if="company.people.length" role="list">
      <li
        v-for="person in company.people"
        :key="person.user"
        class="flex items-start justify-between gap-3 border-b border-outline-gray-1 px-4 py-2.5 last:border-b-0"
      >
        <span class="min-w-0">
          <span class="block break-words text-sm text-ink-gray-9">
            {{ person.full_name }}
          </span>
          <span class="block break-words text-p-xs text-ink-gray-5">
            {{ person.projects.join(", ") }}
          </span>
        </span>
        <span class="shrink-0 text-right text-p-xs text-ink-gray-6">
          <span class="font-mono tabular-nums text-ink-gray-8">{{
            person.open
          }}</span>
          {{ __("open") }}
          <span v-if="person.working" class="block">
            <span class="font-mono tabular-nums">{{ person.working }}</span>
            {{ __("in progress") }}
          </span>
        </span>
      </li>
    </ul>
    <p v-else class="px-4 py-4 text-p-sm text-ink-gray-6">
      {{ __("Nobody has open project work.") }}
    </p>
    <p
      v-if="company.free_people.length"
      class="border-t border-outline-gray-2 px-4 py-2.5 text-p-xs text-ink-gray-6"
    >
      <span class="text-ink-gray-7">{{ __("Free:") }}</span>
      {{ freeLabel }}
    </p>
  </SectionCard>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed } from "vue";
import { RouterLink } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import {
  endingLabel,
  ticketLinks,
  type Company,
  type EndingProject,
} from "../homeMeta";
import SectionCard from "@/components/SectionCard.vue";

const props = defineProps<{ company: Company }>();

function late(project: EndingProject) {
  return project.days_left < 0;
}

const freeLabel = computed(() => {
  const names = props.company.free_people;
  const more = (props.company.people_free ?? names.length) - names.length;
  return more > 0
    ? `${names.join(", ")} ${__("+{0} more", String(more))}`
    : names.join(", ");
});
</script>
