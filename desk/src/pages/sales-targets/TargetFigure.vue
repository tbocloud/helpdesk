<template>
  <!-- one target of a person's month as the mockup's card: its kind on a coloured top edge,
       icon and pill, the figure (what they achieved of it, once counted), and how far they are -->
  <article
    class="relative flex min-w-0 flex-col gap-3 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base p-5"
  >
    <span
      class="absolute inset-x-0 top-0 h-1"
      :class="look.bar"
      aria-hidden="true"
    />
    <div class="flex items-start justify-between gap-3">
      <span
        class="grid size-10 shrink-0 place-items-center rounded-lg"
        :class="look.tile"
        aria-hidden="true"
      >
        <component :is="look.icon" class="size-5" />
      </span>
      <span class="text-sm font-medium text-ink-gray-6 tabular-nums">
        {{ __("Target {0}", String(index)) }}
      </span>
    </div>

    <h3
      class="break-words text-base font-semibold text-ink-gray-9"
      :title="criterion.criterion"
    >
      {{ criterion.criterion }}
    </h3>

    <p
      v-if="isText"
      class="whitespace-pre-line break-words text-p-base font-medium text-ink-gray-8"
    >
      {{ criterion.unassigned || !criterion.target ? "—" : criterion.target }}
    </p>
    <p v-else class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
      <span
        class="break-all text-[32px] font-bold leading-none tracking-[-0.02em] text-ink-gray-9 tabular-nums"
        >{{ value }}</span
      >
      <span v-if="result" class="text-sm text-ink-gray-6 tabular-nums">{{
        __("of {0}", targetText(criterion, currency))
      }}</span>
    </p>

    <span
      class="inline-flex h-6 items-center self-start rounded-md px-2 text-xs font-medium"
      :class="look.tile"
    >
      {{ criterion.info_only ? __("Info only") : look.label }}
    </span>

    <TargetProgress
      v-if="result"
      :criterion="criterion"
      :result="result"
      :progress="progress!"
      :owner="owner"
      :link="link"
    />
    <span
      v-else-if="counting"
      class="h-1.5 w-full animate-pulse rounded-full bg-surface-gray-3"
      :aria-label="__('Counting')"
    />
    <p v-else-if="note" class="text-xs text-ink-gray-6">{{ note }}</p>
    <!-- a KPI's tick-off -->
    <slot />
  </article>
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
  /** its place in the month's list, from 1 */
  index: number;
  currency: string;
  /** the month's progress; null while it loads */
  progress: Progress | null;
  /** whose leads are counted, by name */
  owner: string;
  link: RouteLocationRaw | null;
  /** a standard criterion not assigned for the month: shown as 0, nothing counted */
  unassigned?: boolean;
}>();

const look = computed(() => VALUE_TYPE_LOOK[props.criterion.value_type]);
const isText = computed(() => props.criterion.value_type === "Text");

const result = computed(() => {
  const measured = props.progress?.criteria?.[props.criterion.criterion];
  return !props.unassigned && props.criterion.measure && measured
    ? progressOf(props.criterion, measured, props.progress!, props.currency)
    : null;
});

const counting = computed(
  () => !!props.criterion.measure && !props.progress && !props.unassigned
);
/** What they achieved once it is counted, else the target itself. */
const value = computed(() => {
  if (!result.value) return targetText(props.criterion, props.currency);
  return result.value.achieved === null
    ? "—"
    : figureText(props.criterion, result.value.achieved, props.currency);
});

/** Why there is no progress to show, in words. */
const note = computed(() => {
  const { measure, value_type, info_only } = props.criterion;
  if (props.unassigned) return __("Not assigned yet");
  if (value_type === "Text") return info_only ? __("Information only") : "";
  if (!measure) return __("Target only: not counted from the leads.");
  const label = MEASURE_LOOK[measure].label;
  if (props.progress?.state === "not_started")
    return __("Counts {0} once the month begins.", label.toLowerCase());
  if (props.progress?.state === "unavailable")
    return __("Couldn't count it: {0}", props.progress.reason || "");
  return __("Counts {0}.", label.toLowerCase());
});
</script>
