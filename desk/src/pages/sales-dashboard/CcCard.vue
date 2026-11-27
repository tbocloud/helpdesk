<template>
  <!-- one card of the team dashboard: its colour on the top edge and the heading icon; with
       `to`, the heading's link covers the card, so a click anywhere opens what is behind it
       (links and buttons inside sit above it with `relative z-[1]`) -->
  <section
    class="cc-card flex min-w-0 flex-col gap-3 p-4"
    :class="to && 'cc-card-link relative'"
    :style="accentStyle(accent)"
    :aria-labelledby="headingId"
  >
    <header class="flex items-start justify-between gap-3">
      <div class="flex min-w-0 flex-col gap-0.5">
        <h2
          :id="headingId"
          class="flex items-center gap-1.5 text-xs font-bold uppercase tracking-[0.06em] text-ink-gray-9"
        >
          <component
            :is="icon"
            v-if="icon"
            class="cc-ink size-4 shrink-0"
            aria-hidden="true"
          />
          <RouterLink
            v-if="to"
            :to="to"
            class="rounded after:absolute after:inset-0 after:rounded-[14px] focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-highlight"
            >{{ title }}</RouterLink
          >
          <template v-else>{{ title }}</template>
        </h2>
        <p v-if="sub" class="text-xs text-ink-gray-6">{{ sub }}</p>
      </div>
      <slot name="actions" />
      <LucideChevronRight
        v-if="to && !$slots.actions"
        class="size-4 shrink-0 text-ink-gray-5"
        aria-hidden="true"
      />
    </header>
    <slot />
  </section>
</template>

<script setup lang="ts">
import { type Component, useId } from "vue";
import type { RouteLocationRaw } from "vue-router";
import LucideChevronRight from "~icons/lucide/chevron-right";
import { accentStyle, type Accent } from "./salesDashboard";

defineProps<{
  title: string;
  accent?: Accent;
  icon?: Component;
  sub?: string;
  /** where a click on the card goes: the list behind its figure */
  to?: RouteLocationRaw;
}>();

const headingId = useId();
</script>
