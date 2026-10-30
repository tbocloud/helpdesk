<template>
  <ul role="list" class="biz-rows m-0 flex list-none flex-col gap-2 p-0">
    <li
      v-for="row in rows"
      :key="row.key ?? row.label"
      class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 sm:grid-cols-[11rem_minmax(0,1fr)_auto]"
    >
      <span
        class="truncate text-sm text-[color:var(--biz-ink,var(--ink-gray-9))]"
        :title="row.label"
        >{{ row.label }}</span
      >
      <span
        class="track order-last col-span-2 block h-1.5 overflow-hidden rounded-full sm:order-none sm:col-span-1"
        aria-hidden="true"
      >
        <span
          class="fill block h-full rounded-full"
          :style="{ width: `${share(row.value)}%` }"
        />
      </span>
      <span
        class="text-right font-mono text-sm tabular-nums text-[color:var(--biz-ink,var(--ink-gray-9))]"
      >
        {{ row.text }}
        <span
          v-if="row.sub"
          class="block text-xs text-[color:var(--biz-muted,var(--ink-gray-6))] sm:ml-2 sm:inline"
          >{{ row.sub }}</span
        >
      </span>
    </li>
  </ul>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { BusinessRow } from "./businessFormat";

const props = defineProps<{ rows: BusinessRow[]; max?: number }>();

const top = computed(
  () => props.max ?? Math.max(1, ...props.rows.map((row) => row.value))
);
function share(value: number) {
  return Math.min(Math.max((value / top.value) * 100, value > 0 ? 2 : 0), 100);
}
</script>

<style scoped>
.track {
  background-color: var(--biz-track, var(--surface-gray-2));
}
.fill {
  background-color: var(--biz-a, var(--brand));
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}
</style>
