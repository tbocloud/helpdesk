<template>
  <div
    class="relative size-16 shrink-0"
    role="img"
    :aria-label="
      __('{0} of {1}, {2}', String(actual), String(target), statusText)
    "
  >
    <svg viewBox="0 0 48 48" class="size-16 -rotate-90" aria-hidden="true">
      <circle
        cx="24"
        cy="24"
        :r="RADIUS"
        fill="none"
        stroke="currentColor"
        stroke-width="5"
        class="text-ink-gray-3"
      />
      <circle
        cx="24"
        cy="24"
        :r="RADIUS"
        fill="none"
        stroke="currentColor"
        stroke-width="5"
        stroke-linecap="round"
        :class="INK[tone]"
        :stroke-dasharray="CIRCUMFERENCE"
        :stroke-dashoffset="CIRCUMFERENCE * (1 - share)"
      />
    </svg>
    <span
      class="absolute inset-0 flex items-center justify-center font-mono text-sm font-semibold tabular-nums text-ink-gray-9"
      aria-hidden="true"
      >{{ actual }}</span
    >
  </div>
</template>

<script setup lang="ts">
import { INK, type Tone } from "@/components/tone";
import { __ } from "@/translation";
import { computed } from "vue";

const props = defineProps<{
  actual: number;
  target: number;
  tone: Tone;
  /** what a screen reader hears besides the numbers, e.g. "on track" */
  statusText: string;
}>();

const RADIUS = 20;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
const share = computed(() =>
  props.target > 0 ? Math.min(props.actual / props.target, 1) : 0
);
</script>
