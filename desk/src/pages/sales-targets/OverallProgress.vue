<template>
  <!-- a person's month overall (overallOf): a small bar and "62% reached", or "62% · 2 behind" -->
  <span
    class="flex items-center gap-2 text-xs tabular-nums"
    :class="behind ? 'text-warning' : 'text-ink-gray-6'"
  >
    <span
      class="block h-1 w-16 overflow-hidden rounded-full bg-surface-gray-2"
      aria-hidden="true"
    >
      <span
        class="block h-full rounded-full"
        :class="behind ? 'bg-warning' : 'bg-success'"
        :style="{ width: `${percent}%` }"
      />
    </span>
    {{
      behind
        ? __("{0}% · {1} behind", String(percent), String(behind))
        : __("{0}% reached", String(percent))
    }}
  </span>
</template>

<script setup lang="ts">
import { __ } from "@/translation";

defineProps<{ percent: number; behind: number }>();
</script>
