<template>
  <!-- one card of the team dashboard: its colour on the top edge and the heading icon -->
  <section
    class="cc-card flex min-w-0 flex-col gap-3 p-4"
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
          {{ title }}
        </h2>
        <p v-if="sub" class="text-xs text-ink-gray-6">{{ sub }}</p>
      </div>
      <slot name="actions" />
    </header>
    <slot />
  </section>
</template>

<script setup lang="ts">
import { type Component, useId } from "vue";
import { accentStyle, type Accent } from "./salesDashboard";

defineProps<{
  title: string;
  accent?: Accent;
  icon?: Component;
  sub?: string;
}>();

const headingId = useId();
</script>
