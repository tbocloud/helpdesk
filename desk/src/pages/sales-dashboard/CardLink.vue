<template>
  <!-- a card's "Details →" link to the page behind it -->
  <RouterLink
    :to="to"
    class="relative z-[1] inline-flex shrink-0 items-center gap-1 rounded text-sm font-medium text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
  >
    <slot />
    <LucideArrowRight class="size-3.5" aria-hidden="true" />
  </RouterLink>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from "vue-router";
import LucideArrowRight from "~icons/lucide/arrow-right";

defineProps<{ to: RouteLocationRaw }>();
</script>
