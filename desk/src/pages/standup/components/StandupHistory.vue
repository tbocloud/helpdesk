<template>
  <TaskyState
    v-if="resource.error && !data"
    :icon="LucideCircleAlert"
    :title="__('Couldn\'t load the history')"
    :message="
      errorText(resource.error, __('Check your connection and try again.'))
    "
    error
  >
    <Button :label="__('Retry')" @click="resource.reload()" />
  </TaskyState>
  <div
    v-else-if="!data"
    class="h-48 animate-pulse rounded-xl bg-surface-gray-2"
    aria-busy="true"
  />
  <SectionCard
    v-else
    :title="
      person ? __('{0}\'s stand-ups', data.full_name) : __('Your stand-ups')
    "
    :count="data.items.length"
  >
    <ul v-if="data.items.length" role="list">
      <li
        v-for="row in data.items"
        :key="row.name"
        class="border-b border-outline-gray-1 last:border-b-0"
      >
        <RouterLink
          :to="link(row)"
          class="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
        >
          <span class="min-w-32 text-base text-ink-gray-9">{{
            dayLabel(row.date)
          }}</span>
          <TaskyBadge
            :tone="STATUS_TONES[row.status]"
            :icon="row.status === 'Submitted' ? LucideCircleCheck : undefined"
            :label="statusLabel(row.status)"
          />
          <TaskyBadge
            v-if="row.needs_help"
            tone="warning"
            :icon="LucideLifeBuoy"
            :label="__('Asked for help')"
          />
          <span class="ml-auto font-mono text-sm tabular-nums text-ink-gray-6">
            {{
              __(
                "{0} done · {1} planned · {2} blockers",
                row.yesterday,
                row.today,
                row.blockers
              )
            }}
          </span>
        </RouterLink>
      </li>
    </ul>
    <p v-else class="px-4 py-3 text-p-sm text-ink-gray-6">
      {{ __("No stand-ups yet.") }}
    </p>
  </SectionCard>
</template>

<script setup lang="ts">
import SectionCard from "@/components/SectionCard.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource } from "frappe-ui";
import { computed, watch } from "vue";
import { RouterLink } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideLifeBuoy from "~icons/lucide/life-buoy";
import {
  dayLabel,
  NO_DEPARTMENT,
  STATUS_TONES,
  statusLabel,
  type HistoryRow,
} from "../standupMeta";

const props = defineProps<{ person: string | null }>();

const resource = createResource({
  url: "helpdesk.api.standup.get_standup_history",
  makeParams: () => (props.person ? { user: props.person } : {}),
  auto: true,
});
watch(
  () => props.person,
  () => resource.reload()
);

const data = computed<{ full_name: string; items: HistoryRow[] } | null>(
  () => resource.data ?? null
);

// your own day opens in My stand-up; a teammate's in their team's view
function link(row: HistoryRow) {
  return props.person
    ? {
        query: {
          tab: "team",
          team: row.department || NO_DEPARTMENT,
          date: row.date,
        },
      }
    : { query: { tab: "mine", date: row.date } };
}
</script>
