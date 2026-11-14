<template>
  <!-- managers: whether the follow-ups are getting work moved (docs/follow-ups.md) -->
  <section :aria-label="__('Follow-ups')" class="flex flex-col gap-4">
    <div class="flex items-baseline justify-between gap-3">
      <h2 class="text-base font-semibold text-ink-gray-9">
        {{ __("Follow-ups") }}
      </h2>
      <span class="text-p-sm text-ink-gray-5">
        {{
          __(
            "All projects and tickets: the filters above don't apply here. Escalated work, the oldest overdue and who has most of it."
          )
        }}
      </span>
    </div>

    <div
      v-if="control.error && !data"
      class="rounded-xl border border-outline-gray-2 bg-surface-base"
    >
      <TaskyState
        class="py-10"
        :icon="LucideCircleAlert"
        :title="__('Couldn\'t load the follow-ups')"
        :message="__('Check your connection and try again.')"
        error
      >
        <Button :label="__('Retry')" @click="control.reload()" />
      </TaskyState>
    </div>

    <template v-else>
      <div class="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4">
        <StatTile
          :label="__('Escalated to head or managers')"
          :value="data?.counts.escalated ?? 0"
          :icon="LucideChevronsUp"
          :icon-tone="data?.counts.escalated ? 'danger' : 'neutral'"
          :loading="!data"
        />
        <StatTile
          :label="__('SLA breached')"
          :value="data?.counts.breached ?? 0"
          :icon="LucideTimerOff"
          :icon-tone="data?.counts.breached ? 'danger' : 'neutral'"
          :loading="!data"
        />
        <StatTile
          :label="__('Overdue tasks')"
          :value="data?.counts.overdue ?? 0"
          :icon="LucideAlarmClock"
          :icon-tone="data?.counts.overdue ? 'danger' : 'neutral'"
          :loading="!data"
        />
      </div>

      <div v-if="data" class="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <SectionCard
          :title="__('Escalated')"
          :count="data.escalated.length"
          class="lg:col-span-5"
        >
          <FollowUpList
            :rows="data.escalated"
            :empty="__('Nothing has reached a head or the managers.')"
          />
        </SectionCard>
        <SectionCard
          :title="__('Oldest overdue')"
          :count="data.oldest_overdue.length"
          class="lg:col-span-4"
        >
          <FollowUpList
            :rows="data.oldest_overdue"
            :empty="__('No overdue tasks.')"
          />
        </SectionCard>
        <SectionCard :title="__('Most open escalations')" class="lg:col-span-3">
          <ul v-if="data.people.length" role="list">
            <li
              v-for="person in data.people"
              :key="person.user"
              class="flex items-center gap-3 border-b border-outline-gray-1 px-5 py-3 last:border-b-0"
            >
              <PersonAvatar :name="person.full_name" size="md" />
              <span
                class="min-w-0 flex-1 truncate text-[13px] font-medium text-ink-gray-9"
              >
                {{ person.full_name }}
              </span>
              <span class="font-mono text-sm tabular-nums text-ink-gray-7">
                {{ person.count }}
              </span>
            </li>
          </ul>
          <p v-else class="px-5 py-6 text-p-sm text-ink-gray-6">
            {{ __("Nobody has escalated work.") }}
          </p>
        </SectionCard>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import type { FollowUpRow } from "@/components/followUps";
import PersonAvatar from "@/components/PersonAvatar.vue";
import SectionCard from "@/components/SectionCard.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { Button, createResource } from "frappe-ui";
import { computed } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideChevronsUp from "~icons/lucide/chevrons-up";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideTimerOff from "~icons/lucide/timer-off";
import FollowUpList from "./FollowUpList.vue";

interface ControlData {
  counts: { escalated: number; breached: number; overdue: number };
  escalated: FollowUpRow[];
  oldest_overdue: FollowUpRow[];
  people: { user: string; full_name: string; count: number }[];
}

const control = createResource({
  url: "helpdesk.api.follow_ups.get_follow_up_overview",
  auto: true,
});

const data = computed(() => control.data as ControlData | undefined);
</script>
