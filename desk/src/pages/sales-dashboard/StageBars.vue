<template>
  <!-- open leads per stage as upright bars, each with its count above and name below; a bar
       opens that stage's leads -->
  <ul
    class="flex h-56 items-end gap-1.5 overflow-x-auto pb-1"
    :aria-label="label"
  >
    <li
      v-for="(row, index) in rows"
      :key="row.stage"
      class="flex h-full min-w-[2.75rem] flex-1 flex-col"
      :style="accentStyle(ACCENTS[index % ACCENTS.length])"
    >
      <RouterLink
        :to="link(row.stage)"
        class="group flex h-full flex-col items-center gap-1 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        :title="`${row.stage}: ${row.count.toLocaleString()} · ${fullAmount(
          row.value ?? 0,
          currency
        )}`"
      >
        <span class="cc-ink font-mono text-[11px] font-bold tabular-nums">{{
          row.count.toLocaleString()
        }}</span>
        <span class="flex w-full flex-1 items-end justify-center">
          <span
            class="cc-fill cc-arc block w-full max-w-[2.25rem] rounded-t-md opacity-90 transition-opacity group-hover:opacity-100"
            :style="{ height: `${Math.max(percent(row.count, max), 2)}%` }"
            aria-hidden="true"
          />
        </span>
        <span class="w-full truncate text-center text-[10px] text-ink-gray-6">{{
          row.stage
        }}</span>
      </RouterLink>
    </li>
  </ul>
</template>

<script setup lang="ts">
import { fullAmount } from "@/pages/leads/business/businessFormat";
import { computed } from "vue";
import { RouterLink, type RouteLocationRaw } from "vue-router";
import {
  accentStyle,
  ACCENTS,
  percent,
  type PipelineStage,
} from "./salesDashboard";

const props = defineProps<{
  rows: PipelineStage[];
  currency: string;
  /** what the chart shows, for screen readers */
  label: string;
  link: (stage: string) => RouteLocationRaw;
}>();

const max = computed(() => Math.max(0, ...props.rows.map((r) => r.count)));
</script>
