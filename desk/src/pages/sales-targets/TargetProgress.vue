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
        :class="FILL[result.standing]"
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
      :class="INK[result.standing]"
    >
      <component
        :is="ICONS[result.standing]"
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
      <dl
        class="mt-2 flex flex-col gap-2 rounded-lg bg-surface-gray-1 px-3 py-2.5"
      >
        <div v-for="line in result.lines" :key="line.label">
          <dt class="font-medium text-ink-gray-8">{{ line.label }}</dt>
          <dd
            class="text-ink-gray-7"
            :class="/[÷×=]/.test(line.text) && 'font-mono tabular-nums'"
          >
            {{ line.text }}
          </dd>
        </div>
        <div>
          <dt class="font-medium text-ink-gray-8">{{ __("Counted over") }}</dt>
          <dd class="text-ink-gray-7 tabular-nums">
            {{ __("{0}, leads owned by {1}", countedOver(progress), owner) }}
          </dd>
        </div>
        <RouterLink
          v-if="link"
          :to="link"
          class="inline-flex items-center gap-1 self-start rounded font-medium text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        >
          {{ __("See these leads") }}
          <LucideArrowRight class="size-3.5" aria-hidden="true" />
        </RouterLink>
      </dl>
    </details>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import type { RouteLocationRaw } from "vue-router";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideTrendingDown from "~icons/lucide/trending-down";
import LucideTrendingUp from "~icons/lucide/trending-up";
import {
  countedOver,
  type Criterion,
  type CriterionProgress,
  type Progress,
  type Standing,
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

// behind is warning, never danger: a target not yet reached isn't a failure (ui-guidelines §8)
const FILL: Record<Standing, string> = {
  done: "bg-success",
  on_pace: "bg-success",
  behind: "bg-warning",
  short: "bg-warning",
  below: "bg-warning",
  none: "bg-surface-gray-4",
};
const INK: Record<Standing, string> = {
  done: "text-success",
  on_pace: "text-success",
  behind: "text-warning",
  short: "text-warning",
  below: "text-warning",
  none: "text-ink-gray-6",
};
const ICONS: Record<Standing, unknown> = {
  done: LucideCircleCheck,
  on_pace: LucideTrendingUp,
  behind: LucideTrendingDown,
  short: LucideTrendingDown,
  below: LucideTrendingDown,
  none: LucideCircleDashed,
};
</script>
