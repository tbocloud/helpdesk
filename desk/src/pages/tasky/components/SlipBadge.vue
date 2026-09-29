<template>
  <TaskyBadge
    tone="warning"
    :icon="LucideCalendarClock"
    class="font-mono tabular-nums"
    :title="slipTitle(count)"
  >
    <span aria-hidden="true">{{ slipLabel(count) }}</span>
    <span class="sr-only">{{ slipTitle(count) }}</span>
  </TaskyBadge>
</template>

<script setup lang="ts">
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import { slipLabel, slipTitle } from "../taskMeta";
import TaskyBadge from "./TaskyBadge.vue";

defineProps<{
  /** How many times the due date was moved later; render only when ≥ 1. */
  count: number;
}>();
</script>
