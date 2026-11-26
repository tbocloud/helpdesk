<template>
  <!-- the month's ranking by the month overall: the top three on a podium, the leader,
       everyone in order, and who isn't on the board yet with why -->
  <TaskyState
    v-if="pace.state === 'ahead'"
    class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
    :icon="LucideCalendarClock"
    :title="__('{0} hasn\'t begun', monthTitle(month))"
    :message="
      __(
        'The scoreboard ranks people once their targets start counting on the 1st.'
      )
    "
  />

  <TaskyState
    v-else-if="!withTargets.length"
    class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
    :icon="LucideTrophy"
    :title="__('No one has targets for {0}', monthTitle(month))"
    :message="__('Assign targets and the scoreboard ranks people by them.')"
  />

  <template v-else-if="counting">
    <div :class="SPLIT" aria-busy="true" :aria-label="__('Counting')">
      <div class="h-80 animate-pulse rounded-xl bg-surface-gray-3" />
      <div class="h-80 animate-pulse rounded-xl bg-surface-gray-3" />
    </div>
    <div class="h-72 animate-pulse rounded-xl bg-surface-gray-3" />
  </template>

  <template v-else>
    <div v-if="ranked.length" :class="SPLIT">
      <ScoreboardPodium
        :ranked="ranked"
        :month="month"
        :pace="pace"
        :average="average"
        @open="emit('open', $event)"
      />
      <ScoreboardLeader
        v-if="leader"
        :leader="leader"
        :tied="tied"
        :month="month"
        :pace="pace"
        @open="emit('open', $event)"
      />
    </div>

    <div :class="SPLIT">
      <section
        class="min-w-0 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
        :aria-labelledby="boardHeading"
      >
        <div
          class="flex flex-wrap items-start justify-between gap-3 border-b border-outline-gray-2 px-5 py-4"
        >
          <div class="flex min-w-0 flex-col gap-0.5">
            <h2
              :id="boardHeading"
              class="text-base font-semibold text-ink-gray-9"
            >
              {{ __("Full ranking") }}
            </h2>
            <p class="text-p-sm text-ink-gray-6">
              {{
                pace.state === "running"
                  ? __(
                      "By share of targets reached · the black tick is today's pace ({0}%)",
                      String(pace.percent)
                    )
                  : __("By share of targets reached in {0}", monthTitle(month))
              }}
            </p>
          </div>
          <div v-if="ranked.length" class="flex flex-wrap gap-1.5">
            <span
              v-if="statusCounts.ahead"
              class="rounded-full bg-success-soft px-2.5 py-0.5 text-xs font-medium text-success tabular-nums"
              >{{ __("{0} ahead", String(statusCounts.ahead)) }}</span
            >
            <span
              v-if="statusCounts.behind"
              class="rounded-full bg-warning-soft px-2.5 py-0.5 text-xs font-medium text-warning tabular-nums"
              >{{ __("{0} behind pace", String(statusCounts.behind)) }}</span
            >
          </div>
        </div>

        <TaskyState
          v-if="!ranked.length"
          class="py-10"
          :icon="LucideCircleDashed"
          :title="__('Nothing counted yet')"
          :message="
            __(
              'People join the board once something is counted against their targets.'
            )
          "
        />

        <ol v-else class="divide-y divide-outline-gray-1">
          <li v-for="entry in ranked" :key="entry.row.person.user">
            <button
              type="button"
              class="grid w-full grid-cols-[2.25rem_auto_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2 px-5 py-4 text-left transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight sm:grid-cols-[2.25rem_auto_minmax(0,1fr)_minmax(8rem,14rem)_4.5rem]"
              :aria-label="rowLabel(entry)"
              @click="emit('open', entry.row.person.user)"
            >
              <span
                class="grid size-9 place-items-center rounded-lg font-mono text-sm font-semibold tabular-nums"
                :class="
                  entry.rank === 1
                    ? 'border border-champion-border bg-champion-soft text-champion'
                    : 'bg-surface-gray-2 text-ink-gray-7'
                "
                aria-hidden="true"
                >{{ entry.rank }}</span
              >
              <PersonAvatar
                :name="entry.row.person.full_name"
                size="lg"
                class="!size-10"
              />
              <span class="flex min-w-0 flex-col gap-1.5" aria-hidden="true">
                <span class="truncate text-sm font-semibold text-ink-gray-9">{{
                  entry.row.person.full_name
                }}</span>
                <span class="flex flex-wrap gap-1.5">
                  <span
                    class="rounded-md bg-surface-gray-2 px-2 py-0.5 text-xs text-ink-gray-7 tabular-nums"
                    >{{ reachedText(entry) }}</span
                  >
                  <span
                    class="flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium tabular-nums"
                    :class="STATUS_LOOK[status(entry)].chip"
                  >
                    <component
                      :is="STATUS_LOOK[status(entry)].icon"
                      class="size-3"
                    />
                    {{ statusText(entry) }}</span
                  >
                </span>
              </span>
              <span
                class="text-right font-mono text-xl font-semibold text-ink-gray-9 tabular-nums sm:order-last"
                aria-hidden="true"
                >{{ entry.overall.percent }}%</span
              >
              <span
                class="relative col-span-full block h-2 rounded-full bg-surface-gray-2 sm:col-span-1"
                aria-hidden="true"
              >
                <span
                  class="block h-full rounded-full"
                  :class="entry.overall.behind ? 'bg-warning' : 'bg-success'"
                  :style="{ width: `${entry.overall.percent}%` }"
                />
                <span
                  v-if="pace.state === 'running'"
                  class="absolute -top-1 h-4 w-0.5 -translate-x-1/2 rounded-full bg-ink-gray-9"
                  :style="{ left: `${pace.percent}%` }"
                />
              </span>
            </button>
          </li>
        </ol>
      </section>

      <section
        v-if="unranked.length"
        class="min-w-0 self-start overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
        :aria-labelledby="offHeading"
      >
        <div
          class="flex flex-col gap-0.5 border-b border-outline-gray-2 px-5 py-4"
        >
          <h2 :id="offHeading" class="text-base font-semibold text-ink-gray-9">
            {{ __("Not on the board") }}
            <span class="font-normal text-ink-gray-5 tabular-nums">{{
              unranked.length
            }}</span>
          </h2>
          <p class="text-p-sm text-ink-gray-6">
            {{
              unranked.every((r) => r.person.target)
                ? __("Has targets, but nothing counted yet this month.")
                : __("Nothing counted yet, or no targets this month.")
            }}
          </p>
        </div>
        <ul class="divide-y divide-outline-gray-1">
          <li v-for="row in unranked" :key="row.person.user">
            <component
              :is="single ? 'div' : 'button'"
              :type="single ? undefined : 'button'"
              class="flex w-full items-center justify-between gap-3 px-5 py-3 text-left"
              :class="
                single
                  ? ''
                  : 'transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight'
              "
              @click="!single && emit('open', row.person.user)"
            >
              <span class="flex min-w-0 items-center gap-3">
                <PersonAvatar
                  :name="row.person.full_name"
                  size="lg"
                  class="!size-10"
                />
                <span class="truncate text-sm font-semibold text-ink-gray-9">{{
                  row.person.full_name
                }}</span>
              </span>
              <span
                v-if="row.person.target && !row.progress"
                class="h-1 w-16 animate-pulse rounded-full bg-surface-gray-3"
                :aria-label="__('Counting')"
              />
              <span
                v-else
                class="flex shrink-0 items-center gap-1.5 rounded-full border border-outline-gray-2 bg-surface-gray-1 px-2.5 py-0.5 text-xs text-ink-gray-6"
                :title="row.progress?.reason || undefined"
              >
                <LucideCircleDashed class="size-3" aria-hidden="true" />
                {{
                  row.person.target
                    ? uncountedText(row.progress!)
                    : __("No targets")
                }}
              </span>
            </component>
          </li>
        </ul>
        <!-- one person: a plain row and a link, as the mockup; more: each row opens them -->
        <div v-if="single" class="px-5 pb-4 pt-1">
          <button
            type="button"
            class="flex items-center gap-1 rounded text-sm font-semibold text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            @click="emit('open', unranked[0].person.user)"
          >
            {{
              __(
                "Check {0}'s targets",
                unranked[0].person.full_name.split(" ")[0]
              )
            }}
            <LucideArrowRight class="size-4" aria-hidden="true" />
          </button>
        </div>
      </section>
    </div>
  </template>
</template>

<script setup lang="ts">
import PersonAvatar from "@/components/PersonAvatar.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { computed, useId, type Component } from "vue";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideTrendingDown from "~icons/lucide/trending-down";
import LucideTrendingUp from "~icons/lucide/trending-up";
import LucideTrophy from "~icons/lucide/trophy";
import ScoreboardLeader from "./ScoreboardLeader.vue";
import ScoreboardPodium from "./ScoreboardPodium.vue";
import {
  monthPace,
  monthTitle,
  paceStatus,
  rankRows,
  uncountedText,
  type RankedRow,
  type TeamRow,
} from "./salesTargets";

const props = defineProps<{
  rows: TeamRow[];
  month: string;
  pace: ReturnType<typeof monthPace>;
}>();
const emit = defineEmits<{ open: [user: string] }>();

const SPLIT =
  "grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] lg:items-stretch";
// each person's standing against today's pace, always with its words and an icon
const STATUS_LOOK: Record<
  ReturnType<typeof paceStatus>,
  { chip: string; icon: Component }
> = {
  ahead: { chip: "bg-success-soft text-success", icon: LucideTrendingUp },
  on_pace: { chip: "bg-info-soft text-info", icon: LucideCircleCheck },
  behind: { chip: "bg-warning-soft text-warning", icon: LucideTrendingDown },
};
const boardHeading = useId();
const offHeading = useId();

const withTargets = computed(() => props.rows.filter((r) => r.person.target));
// the progress is read after the team; until any of it is in, the board is counting
const counting = computed(() => withTargets.value.every((r) => !r.progress));

const ranked = computed(() => rankRows(props.rows));
const unranked = computed(() =>
  props.rows.filter((r) => r.overall?.percent == null)
);
const single = computed(() => unranked.value.length === 1);
const average = computed(() =>
  ranked.value.length
    ? Math.round(
        ranked.value.reduce((sum, e) => sum + e.overall.percent, 0) /
          ranked.value.length
      )
    : null
);
// the leader, once they have reached something; others level with them are named
const leader = computed(() => {
  const top = ranked.value[0];
  return top && top.overall.percent > 0 ? top : null;
});
const tied = computed(() =>
  ranked.value
    .slice(1)
    .filter((e) => e.rank === 1)
    .map((e) => e.row.person.full_name)
);

const status = (entry: RankedRow) => paceStatus(entry.overall, props.pace);
const statusCounts = computed(() => ({
  ahead: ranked.value.filter((e) => status(e) === "ahead").length,
  behind: ranked.value.filter((e) => status(e) === "behind").length,
}));

function reachedText(entry: RankedRow) {
  return __(
    "{0} of {1} reached",
    String(entry.overall.reached),
    String(entry.overall.counted)
  );
}
function statusText(entry: RankedRow) {
  const look = status(entry);
  if (look === "behind") return __("{0} behind", String(entry.overall.behind));
  return look === "ahead" ? __("Ahead of pace") : __("On pace");
}
function rowLabel(entry: RankedRow) {
  return [
    __("Rank {0}", String(entry.rank)),
    entry.row.person.full_name,
    __("{0}% reached", String(entry.overall.percent)),
    reachedText(entry),
    statusText(entry),
  ].join(", ");
}
</script>
