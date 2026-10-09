<template>
  <SectionCard
    :title="__('People')"
    :count="people.length"
    :description="
      __('Best score first. Open a row to see how the score adds up.')
    "
    class="overflow-hidden"
  >
    <template v-if="people.length > 1" #actions>
      <FormControl
        v-model="sort"
        type="select"
        class="w-44"
        :options="SORTS"
        :aria-label="__('Sort people')"
      />
    </template>

    <TaskyState
      v-if="!people.length"
      :icon="LucideUsers"
      :title="__('No one in this department yet')"
      :message="
        __(
          'People show up here once they are on an open project or finish work in it.'
        )
      "
    />

    <template v-else>
      <div
        class="hidden gap-3 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2 text-xs text-ink-gray-5 lg:grid"
        :class="grid"
        aria-hidden="true"
      >
        <span>{{ __("Person") }}</span>
        <span class="text-right">{{ __("Score") }}</span>
        <span class="text-right">{{ __("Done") }}</span>
        <span class="text-right">{{ __("On time") }}</span>
        <span class="text-right">{{ __("Key") }}</span>
        <span class="text-right">{{ __("Overdue") }}</span>
        <span class="text-right">{{ __("Slips") }}</span>
        <span v-if="showPosts" class="text-right">{{ __("Posts") }}</span>
        <span class="text-right">{{ __("Hours") }}</span>
      </div>

      <ul role="list">
        <li
          v-for="person in sorted"
          :key="person.user"
          class="border-b border-outline-gray-1 last:border-b-0"
        >
          <NativeButton
            type="button"
            class="flex w-full flex-col gap-1.5 px-4 py-3 text-left transition-colors hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4 lg:grid lg:items-center lg:gap-3"
            :class="grid"
            :aria-expanded="open === person.user"
            :aria-controls="`breakdown-${person.user}`"
            @click="emit('toggle', open === person.user ? '' : person.user)"
          >
            <!-- Person, and the score on small screens -->
            <span class="flex min-w-0 items-center gap-3">
              <span
                class="w-6 shrink-0 text-right font-mono text-xs tabular-nums text-ink-gray-5"
              >
                <template v-if="person.score > 0">{{ person.rank }}</template>
                <span v-else class="sr-only">{{ __("Not ranked") }}</span>
              </span>
              <Avatar
                :label="person.name"
                :image="person.image || undefined"
                size="md"
              />
              <span class="min-w-0 flex-1">
                <span class="block truncate text-base text-ink-gray-9">
                  {{ person.name }}
                </span>
                <span class="block truncate text-xs text-ink-gray-5">
                  {{ departmentLabel(person.department) }}
                </span>
              </span>
              <span
                class="shrink-0 font-mono text-base tabular-nums text-ink-gray-9 lg:hidden"
              >
                {{ person.score }}
              </span>
              <LucideChevronDown
                class="size-4 shrink-0 text-ink-gray-4 transition-transform motion-reduce:transition-none lg:hidden"
                :class="open === person.user ? 'rotate-180' : ''"
                aria-hidden="true"
              />
            </span>

            <!-- Small screens: one labelled line -->
            <span
              class="flex flex-wrap gap-x-3 gap-y-0.5 pl-9 text-p-sm tabular-nums text-ink-gray-6 lg:hidden"
            >
              <span>{{ __("{0} done", String(person.tasks)) }}</span>
              <span>{{ __("{0} on time", pctText(person.on_time_pct)) }}</span>
              <span
                v-if="person.overdue"
                class="inline-flex items-center gap-1 text-danger"
              >
                <LucideAlarmClock class="size-3.5" aria-hidden="true" />
                {{ __("{0} overdue", String(person.overdue)) }}
              </span>
              <span v-if="postsOf(person)">{{
                __("{0} posts", String(postsOf(person)))
              }}</span>
              <span>{{ hoursText(person.hours) }}</span>
            </span>

            <!-- Large screens: columns -->
            <span
              class="hidden text-right font-mono text-base font-medium tabular-nums text-ink-gray-9 lg:block"
            >
              {{ person.score }}
            </span>
            <span class="hidden text-right font-mono tabular-nums lg:block">
              {{ person.tasks }}
            </span>
            <span class="hidden text-right font-mono tabular-nums lg:block">
              {{ pctText(person.on_time_pct) }}
            </span>
            <span class="hidden text-right font-mono tabular-nums lg:block">
              {{ person.key }}
            </span>
            <span
              class="hidden items-center justify-end gap-1 font-mono tabular-nums lg:flex"
              :class="person.overdue ? 'text-danger' : 'text-ink-gray-5'"
            >
              <LucideAlarmClock
                v-if="person.overdue"
                class="size-3.5"
                aria-hidden="true"
              />
              {{ person.overdue }}
            </span>
            <span
              class="hidden text-right font-mono tabular-nums text-ink-gray-7 lg:block"
            >
              {{ person.slips }}
            </span>
            <span
              v-if="showPosts"
              class="hidden text-right font-mono tabular-nums lg:block"
              :title="
                __(
                  '{0} on time, {1} late, {2} missed',
                  String(person.posts_on_time),
                  String(person.posts_late),
                  String(person.posts_missed)
                )
              "
            >
              {{ postsOf(person) }}
            </span>
            <span
              class="hidden text-right font-mono tabular-nums text-ink-gray-6 lg:block"
            >
              {{ hoursText(person.hours) }}
            </span>
          </NativeButton>

          <div
            v-if="open === person.user"
            :id="`breakdown-${person.user}`"
            class="border-t border-outline-gray-1 bg-surface-gray-1 px-4 py-3 lg:pl-[4.75rem]"
          >
            <ScoreBreakdown
              v-if="person.breakdown.length"
              class="max-w-lg"
              :parts="person.breakdown"
              :score="person.score"
            />
            <p v-else class="text-p-sm text-ink-gray-6">
              {{ __("Nothing finished or overdue in this period yet.") }}
            </p>
            <p
              v-if="person.score > 0 && !person.eligible"
              class="mt-2 text-p-sm text-ink-gray-6"
            >
              {{
                __(
                  "Not enough finished yet this period to be champion; the minimum keeps one lucky task from winning."
                )
              }}
            </p>
          </div>
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
import { Avatar, FormControl } from "frappe-ui";
import { computed, ref } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideUsers from "~icons/lucide/users";
import {
  departmentLabel,
  hoursText,
  type PersonRow,
} from "../teamDashboardMeta";
import ScoreBreakdown from "./ScoreBreakdown.vue";

const props = defineProps<{
  people: PersonRow[];
  /** the person whose breakdown is open */
  open?: string;
}>();
const emit = defineEmits<{ toggle: [user: string] }>();

const SORTS = [
  { label: __("Best score"), value: "score" },
  { label: __("Most done"), value: "tasks" },
  { label: __("Best on time"), value: "on_time" },
  { label: __("Most overdue"), value: "overdue" },
  { label: __("Most hours"), value: "hours" },
  { label: __("Name"), value: "name" },
];
const sort = ref("score");

const postsOf = (p: PersonRow) => p.posts_on_time + p.posts_late;
const showPosts = computed(() =>
  props.people.some((p) => postsOf(p) || p.posts_missed)
);
const grid = computed(() =>
  showPosts.value
    ? "lg:grid-cols-[minmax(0,2.4fr)_repeat(8,minmax(0,0.7fr))]"
    : "lg:grid-cols-[minmax(0,2.4fr)_repeat(7,minmax(0,0.7fr))]"
);

const sorted = computed(() => {
  const rows = [...props.people];
  const by: Record<string, (a: PersonRow, b: PersonRow) => number> = {
    // the server's order: score, then on-time rate, tasks and overdue
    score: () => 0,
    tasks: (a, b) => b.tasks - a.tasks,
    on_time: (a, b) => (b.on_time_pct ?? -1) - (a.on_time_pct ?? -1),
    overdue: (a, b) => b.overdue - a.overdue,
    hours: (a, b) => b.hours - a.hours,
    name: (a, b) => a.name.localeCompare(b.name),
  };
  return rows.sort(by[sort.value]);
});
</script>
