<template>
  <!-- one numeric target on the person's page: achieved of goal, a bar with today's pace,
       where they stand, and the sums behind it on request -->
  <article
    class="flex min-w-0 flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
  >
    <div class="flex min-w-0 items-center gap-2.5">
      <span
        class="grid size-7 shrink-0 place-items-center rounded-md"
        :class="look.tile"
        aria-hidden="true"
      >
        <component :is="look.icon" class="size-4" />
      </span>
      <h3
        class="min-w-0 flex-1 truncate text-base font-semibold text-ink-gray-9"
        :title="criterion.criterion"
      >
        {{ criterion.criterion }}
      </h3>
      <button
        v-if="result"
        type="button"
        class="grid size-7 shrink-0 place-items-center rounded-full text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        :class="open && 'bg-surface-gray-2 text-ink-gray-8'"
        :aria-expanded="open"
        :aria-controls="detailsId"
        :aria-label="__('How {0} is counted', criterion.criterion)"
        @click="open = !open"
      >
        <LucideInfo class="size-4" aria-hidden="true" />
      </button>
    </div>

    <p class="text-sm text-ink-gray-6 tabular-nums">
      <strong class="font-semibold text-ink-gray-9">{{ achieved }}</strong>
      {{ __("of {0}", targetText(criterion, currency)) }}
    </p>

    <template v-if="result">
      <div
        class="relative h-1.5 rounded-full bg-surface-gray-2"
        role="meter"
        :aria-valuenow="Math.round(result.percent ?? 0)"
        aria-valuemin="0"
        aria-valuemax="100"
        :aria-label="
          __('{0}: share of the target reached', criterion.criterion)
        "
      >
        <div
          class="h-full rounded-full transition-[width] motion-reduce:transition-none"
          :class="STANDING_LOOK[result.standing].fill"
          :style="{ width: `${Math.min(result.percent ?? 0, 100)}%` }"
        />
        <!-- where an even pace would be today -->
        <span
          v-if="result.pacePercent !== null"
          class="absolute -top-1 h-3.5 w-0.5 rounded-full bg-surface-gray-9"
          :style="{ left: `calc(${result.pacePercent}% - 1px)` }"
          aria-hidden="true"
        />
      </div>
      <p
        class="flex items-center justify-between gap-2 text-xs font-semibold tabular-nums"
        :class="STANDING_LOOK[result.standing].ink"
      >
        <span class="flex min-w-0 items-center gap-1.5">
          <component
            :is="STANDING_LOOK[result.standing].icon"
            class="size-3.5 shrink-0"
            aria-hidden="true"
          />
          <span class="truncate">{{ result.standingText }}</span>
        </span>
        <span v-if="result.percent !== null" class="text-ink-gray-7">
          {{ Math.round(result.percent) }}%
        </span>
      </p>
      <HowCounted
        v-if="open"
        :id="detailsId"
        :result="result"
        :progress="progress!"
        :owner="owner"
        :link="link"
      />
    </template>
    <template v-else-if="counting">
      <span
        class="h-1.5 w-full animate-pulse rounded-full bg-surface-gray-3"
        :aria-label="__('Counting')"
      />
      <span class="h-3 w-24 animate-pulse rounded bg-surface-gray-2" />
    </template>
    <template v-else>
      <span class="h-1.5 rounded-full bg-surface-gray-2" aria-hidden="true" />
      <p class="text-xs text-ink-gray-6">
        {{ uncountedNote(criterion, progress) }}
      </p>
    </template>
  </article>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed, ref, useId } from "vue";
import type { RouteLocationRaw } from "vue-router";
import LucideInfo from "~icons/lucide/info";
import HowCounted from "./HowCounted.vue";
import {
  figureText,
  progressOf,
  STANDING_LOOK,
  targetText,
  uncountedNote,
  VALUE_TYPE_LOOK,
  type Criterion,
  type Progress,
} from "./salesTargets";

const props = defineProps<{
  criterion: Criterion;
  currency: string;
  /** the month's progress; null while it loads */
  progress: Progress | null;
  /** whose leads are counted, by name */
  owner: string;
  link: RouteLocationRaw | null;
}>();

const open = ref(false);
const detailsId = useId();
const look = computed(() => VALUE_TYPE_LOOK[props.criterion.value_type]);

const result = computed(() => {
  const measured = props.progress?.criteria?.[props.criterion.criterion];
  return props.criterion.measure && measured
    ? progressOf(props.criterion, measured, props.progress!, props.currency)
    : null;
});
const counting = computed(() => !!props.criterion.measure && !props.progress);
const achieved = computed(() =>
  result.value?.achieved == null
    ? "—"
    : figureText(props.criterion, result.value.achieved, props.currency)
);
</script>
