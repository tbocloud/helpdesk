<template>
  <!-- a row's share of its support hours; the text beside it says the same in words -->
  <span
    class="block h-1.5 overflow-hidden rounded-full"
    :class="TRACK[tone]"
    role="meter"
    :aria-valuenow="Math.round(period.percent)"
    aria-valuemin="0"
    aria-valuemax="100"
    :aria-valuetext="usageText(period)"
    :aria-label="label"
  >
    <span
      class="block h-full rounded-full"
      :class="FILL[tone]"
      :style="{ width: `${Math.min(period.percent, 100)}%` }"
    />
  </span>
</template>

<script setup lang="ts">
import { FILL, TRACK } from "@/components/tone";
import {
  STAGE_TONE,
  usageText,
  type UsagePeriod,
} from "@/composables/supportHours";
import { computed } from "vue";

const props = defineProps<{
  period: UsagePeriod;
  /** what the meter measures, e.g. the customer's name */
  label: string;
}>();

const tone = computed(() => STAGE_TONE[props.period.stage]);
</script>
