<template>
  <ul class="flex flex-col gap-2.5" :aria-label="__('Hours by project')">
    <li v-for="p in shown" :key="p.project" class="flex flex-col gap-1">
      <div class="flex items-baseline justify-between gap-3 text-sm">
        <span class="truncate text-ink-gray-8">{{ p.project }}</span>
        <span class="shrink-0 font-mono text-xs tabular-nums text-ink-gray-6">{{
          formatHours(p.hours)
        }}</span>
      </div>
      <div class="h-2 rounded-full bg-brand-soft">
        <div
          class="h-full rounded-full bg-brand"
          :style="{ width: `${(p.hours / max) * 100}%` }"
        />
      </div>
    </li>
    <li v-if="hidden" class="text-p-sm text-ink-gray-5">
      {{ __("+ {0} more projects", String(hidden)) }}
    </li>
  </ul>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed } from "vue";
import { formatHours } from "../chartTheme";

const LIMIT = 8;
const props = defineProps<{ items: { project: string; hours: number }[] }>();
const shown = computed(() => props.items.slice(0, LIMIT));
const hidden = computed(() => Math.max(props.items.length - LIMIT, 0));
const max = computed(() => Math.max(...props.items.map((p) => p.hours), 1));
</script>
