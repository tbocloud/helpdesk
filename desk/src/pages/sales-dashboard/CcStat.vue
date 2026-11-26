<template>
  <!-- a number card of the team dashboard: the label, its icon square, the figure and a
       coloured line under it; a link opens the leads behind it -->
  <component
    :is="to ? RouterLink : 'div'"
    v-bind="to ? { to } : {}"
    class="cc-card flex min-w-0 flex-col gap-1.5 p-3.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
    :style="accentStyle(accent)"
  >
    <span class="flex items-start justify-between gap-2">
      <span
        class="min-w-0 text-[11px] font-bold uppercase tracking-[0.06em] text-ink-gray-7"
        >{{ label }}</span
      >
      <span class="cc-soft grid size-7 shrink-0 place-items-center rounded-lg">
        <component :is="icon" class="size-3.5" aria-hidden="true" />
      </span>
    </span>
    <span
      class="cc-glow truncate font-mono text-[24px] font-bold leading-tight tabular-nums text-ink-gray-9"
      :title="title"
      >{{ value }}</span
    >
    <span class="flex items-end justify-between gap-2">
      <span class="cc-ink min-w-0 text-xs font-medium tabular-nums">{{
        sub
      }}</span>
      <LucideChevronRight
        v-if="to"
        class="size-4 shrink-0 text-ink-gray-5"
        aria-hidden="true"
      />
    </span>
  </component>
</template>

<script setup lang="ts">
import type { Component } from "vue";
import { RouterLink, type RouteLocationRaw } from "vue-router";
import LucideChevronRight from "~icons/lucide/chevron-right";
import { accentStyle, type Accent } from "./salesDashboard";

defineProps<{
  label: string;
  value: string | number;
  icon: Component;
  accent: Accent;
  sub?: string;
  /** the full figure, when `value` is shortened */
  title?: string;
  to?: RouteLocationRaw;
}>();
</script>
