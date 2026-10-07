<template>
  <section
    class="min-w-0 rounded-lg border border-outline-gray-2 bg-surface-base"
    :aria-labelledby="headingId"
  >
    <header class="flex items-center justify-between gap-2 px-4 py-3">
      <h2
        :id="headingId"
        class="flex min-w-0 items-center gap-2 text-base-medium text-ink-gray-9"
      >
        <span class="truncate">{{ title }}</span>
        <span
          v-if="count !== undefined"
          class="font-mono text-sm tabular-nums text-ink-gray-5"
        >
          {{ count }}
        </span>
      </h2>
      <RouterLink
        v-if="to"
        :to="to"
        class="shrink-0 rounded text-p-sm text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
      >
        {{ linkLabel || __("See all") }}
      </RouterLink>
    </header>
    <div class="border-t border-outline-gray-2">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { useId } from "vue";
import { RouterLink, type RouteLocationRaw } from "vue-router";

defineProps<{
  title: string;
  count?: number;
  to?: RouteLocationRaw;
  linkLabel?: string;
}>();

const headingId = `home-card-${useId()}`;
</script>
