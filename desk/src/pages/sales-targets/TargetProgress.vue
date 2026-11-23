<template>
  <!-- how far one counted target is: a bar with the pace marked, the standing in words,
       and the sums behind it -->
  <div class="flex min-w-0 flex-col gap-2">
    <div
      class="relative h-1.5 rounded-full bg-surface-gray-2"
      role="meter"
      :aria-valuenow="Math.round(result.percent ?? 0)"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-label="__('{0}: share of the target reached', criterion.criterion)"
    >
      <div
        class="h-full rounded-full transition-[width] motion-reduce:transition-none"
        :class="STANDING_LOOK[result.standing].fill"
        :style="{ width: `${Math.min(result.percent ?? 0, 100)}%` }"
      />
      <!-- where an even pace would be today -->
      <span
        v-if="result.pacePercent !== null && result.standing !== 'done'"
        class="absolute -top-1 h-3.5 w-0.5 rounded-full bg-surface-gray-8"
        :style="{ left: `calc(${result.pacePercent}% - 1px)` }"
        aria-hidden="true"
      />
    </div>

    <p
      class="flex flex-wrap items-center gap-x-1.5 text-xs tabular-nums"
      :class="STANDING_LOOK[result.standing].ink"
    >
      <component
        :is="STANDING_LOOK[result.standing].icon"
        class="size-3.5 shrink-0"
        aria-hidden="true"
      />
      <span class="font-medium">{{ result.standingText }}</span>
      <span v-if="result.percent !== null" class="text-ink-gray-6">
        · {{ Math.round(result.percent) }}%
      </span>
    </p>

    <details class="group text-xs">
      <summary
        class="inline-flex cursor-pointer list-none items-center gap-1 rounded font-medium text-ink-gray-7 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight [&::-webkit-details-marker]:hidden"
      >
        <LucideChevronRight
          class="size-3.5 transition-transform group-open:rotate-90 motion-reduce:transition-none"
          aria-hidden="true"
        />
        {{ __("How it's counted") }}
      </summary>
      <HowCounted
        class="mt-2"
        :result="result"
        :progress="progress"
        :owner="owner"
        :link="link"
      />
    </details>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import type { RouteLocationRaw } from "vue-router";
import LucideChevronRight from "~icons/lucide/chevron-right";
import HowCounted from "./HowCounted.vue";
import {
  STANDING_LOOK,
  type Criterion,
  type CriterionProgress,
  type Progress,
} from "./salesTargets";

defineProps<{
  criterion: Criterion;
  result: CriterionProgress;
  progress: Progress;
  /** whose leads were counted, by name */
  owner: string;
  /** the Leads list of the leads behind the figure; null when the viewer can't open it */
  link: RouteLocationRaw | null;
}>();
</script>
