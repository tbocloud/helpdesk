<template>
  <!-- one numeric target of a person's month as the app's stat card: its name, the figure
       (what they achieved of it, once counted), how far they are and how that is counted -->
  <StatTile
    :label="criterion.criterion"
    :value="value"
    :sub="sub"
    :icon="look.icon"
    :icon-tone="look.tone"
  >
    <TargetProgress
      v-if="result"
      class="mt-1"
      :criterion="criterion"
      :result="result"
      :progress="progress!"
      :owner="owner"
      :link="link"
    />
    <span
      v-else-if="counting"
      class="mt-1 h-1.5 w-full animate-pulse rounded-full bg-surface-gray-3"
      :aria-label="__('Counting')"
    />
  </StatTile>
</template>

<script setup lang="ts">
import StatTile from "@/components/StatTile.vue";
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
  /** a standard criterion not assigned for the month: shown as 0, nothing counted */
  unassigned?: boolean;
}>();

const look = computed(() => VALUE_TYPE_LOOK[props.criterion.value_type]);

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
/** "of ₹5,00,000" under what they achieved, else why nothing is counted. */
const sub = computed(() => {
  if (result.value)
    return __("of {0}", targetText(props.criterion, props.currency));
  return counting.value ? "" : note.value;
});

/** Why there is no progress to show, in words. */
const note = computed(() => {
  const { measure } = props.criterion;
  if (props.unassigned) return __("Not assigned yet");
  if (!measure) return __("Target only: not counted from the leads.");
  const label = MEASURE_LOOK[measure].label;
  if (props.progress?.state === "not_started")
    return __("Counts {0} once the month begins.", label.toLowerCase());
  if (props.progress?.state === "unavailable")
    return __("Couldn't count it: {0}", props.progress.reason || "");
  return __("Counts {0}.", label.toLowerCase());
});
</script>
