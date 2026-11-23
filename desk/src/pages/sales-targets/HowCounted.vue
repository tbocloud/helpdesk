<template>
  <!-- the sums behind one counted target, the period and whose leads, and a link to them -->
  <dl
    class="flex flex-col gap-2 rounded-lg bg-surface-gray-1 px-3 py-2.5 text-xs"
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
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import type { RouteLocationRaw } from "vue-router";
import LucideArrowRight from "~icons/lucide/arrow-right";
import {
  countedOver,
  type CriterionProgress,
  type Progress,
} from "./salesTargets";

defineProps<{
  result: CriterionProgress;
  progress: Progress;
  /** whose leads were counted, by name */
  owner: string;
  /** the Leads list of the leads behind the figure; null when the viewer can't open it */
  link: RouteLocationRaw | null;
}>();
</script>
