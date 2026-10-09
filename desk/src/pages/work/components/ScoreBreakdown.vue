<template>
  <!-- each part of a score, as the server worked it out (helpdesk.team_dashboard.score) -->
  <dl class="flex flex-col gap-1 text-p-sm">
    <div
      v-for="part in parts"
      :key="part.key"
      class="flex items-baseline justify-between gap-3"
    >
      <dt class="min-w-0 text-ink-gray-7">{{ part.detail }}</dt>
      <dd class="shrink-0 font-mono tabular-nums text-ink-gray-8">
        {{ part.points > 0 ? "+" : "−" }}{{ Math.abs(part.points) }}
      </dd>
    </div>
    <div
      class="mt-1 flex items-baseline justify-between gap-3 border-t border-outline-gray-2 pt-1.5"
    >
      <dt class="text-ink-gray-8">{{ __("Score") }}</dt>
      <dd class="font-mono font-medium tabular-nums text-ink-gray-9">
        {{ score }}
      </dd>
    </div>
  </dl>
</template>

<script setup lang="ts">
import type { BreakdownPart } from "../teamDashboardMeta";

defineProps<{ parts: BreakdownPart[]; score: number }>();
</script>
