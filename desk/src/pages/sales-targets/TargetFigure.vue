<template>
  <!-- one numeric target of a person's month: a cell in the hairline grid, its name, how
       far they are against it and how that is counted -->
  <div
    class="flex min-w-0 flex-col gap-3 border-b border-r border-outline-gray-1 p-4 md:p-5"
  >
    <div class="flex min-w-0 items-center gap-2">
      <span
        class="grid size-7 shrink-0 place-items-center rounded-lg bg-surface-gray-2 text-ink-gray-7"
      >
        <component :is="look.icon" class="size-3.5" aria-hidden="true" />
        <span class="sr-only">{{ look.label }}</span>
      </span>
      <h3
        class="min-w-0 truncate text-sm font-medium text-ink-gray-7"
        :title="criterion.criterion"
      >
        {{ criterion.criterion }}
      </h3>
    </div>

    <template v-if="result">
      <p class="flex flex-wrap items-baseline gap-x-1.5 tabular-nums">
        <span
          class="break-words text-[28px] font-bold leading-none tracking-[-0.02em] text-ink-gray-9"
          >{{
            result.achieved === null
              ? "—"
              : figureText(criterion, result.achieved, currency)
          }}</span
        >
        <span class="text-sm text-ink-gray-6">
          {{ __("of {0}", targetText(criterion, currency)) }}
        </span>
      </p>
      <TargetProgress
        :criterion="criterion"
        :result="result"
        :progress="progress!"
        :owner="owner"
        :link="link"
      />
    </template>
    <template v-else>
      <p
        class="break-words text-[28px] font-bold leading-none tracking-[-0.02em] text-ink-gray-9 tabular-nums"
      >
        {{ targetText(criterion, currency) }}
      </p>
      <span
        v-if="criterion.measure && !progress"
        class="h-1.5 w-full animate-pulse rounded-full bg-surface-gray-3"
        :aria-label="__('Counting')"
      />
      <p v-else class="text-xs text-ink-gray-6">{{ note }}</p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed } from "vue";
import type { RouteLocationRaw } from "vue-router";
import TargetProgress from "./TargetProgress.vue";
import {
  figureText,
  MEASURE_LOOK,
  progressOf,
  targetText,
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

const look = computed(() => VALUE_TYPE_LOOK[props.criterion.value_type]);

const result = computed(() => {
  const measured = props.progress?.criteria?.[props.criterion.criterion];
  return props.criterion.measure && measured
    ? progressOf(props.criterion, measured, props.progress!, props.currency)
    : null;
});

/** Why there is no progress to show, in words. */
const note = computed(() => {
  const { measure } = props.criterion;
  if (!measure) return __("Target only: not counted from the leads.");
  const label = MEASURE_LOOK[measure].label;
  if (props.progress?.state === "not_started")
    return __("Counts {0} once the month begins.", label.toLowerCase());
  if (props.progress?.state === "unavailable")
    return __("Couldn't count it: {0}", props.progress.reason || "");
  return __("Counts {0}.", label.toLowerCase());
});
</script>
