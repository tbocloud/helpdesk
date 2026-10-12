<template>
  <section
    class="flex min-w-0 flex-col rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-labelledby="headingId"
  >
    <header class="flex items-start justify-between gap-3 px-4 py-3">
      <div class="min-w-0">
        <h2
          :id="headingId"
          class="flex min-w-0 items-center gap-2 text-base-semibold text-ink-gray-9"
        >
          <component
            :is="icon"
            v-if="icon"
            class="size-4 shrink-0"
            :class="iconClass || 'text-ink-gray-5'"
            aria-hidden="true"
          />
          <span class="truncate">{{ title }}</span>
          <span
            v-if="count !== undefined"
            class="font-mono text-sm tabular-nums text-ink-gray-5"
          >
            {{ count }}
          </span>
        </h2>
        <p v-if="description" class="mt-0.5 text-p-sm text-ink-gray-5">
          {{ description }}
        </p>
      </div>
      <div v-if="$slots.actions || to" class="flex shrink-0 items-center gap-2">
        <slot name="actions" />
        <RouterLink
          v-if="to"
          :to="to"
          class="rounded text-p-sm text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          {{ linkLabel || __("See all") }}
        </RouterLink>
      </div>
    </header>
    <div class="flex-1 border-t border-outline-gray-2">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { useId, type Component } from "vue";
import { RouterLink, type RouteLocationRaw } from "vue-router";

defineProps<{
  title: string;
  /** One line under the title: what the section shows or how to use it. */
  description?: string;
  count?: number;
  /** Only for meaning, e.g. a red icon on overdue work. */
  icon?: Component;
  iconClass?: string;
  to?: RouteLocationRaw;
  linkLabel?: string;
}>();

const headingId = `section-card-${useId()}`;
</script>
