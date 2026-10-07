<template>
  <div
    class="flex flex-col items-center gap-2 px-6 py-16 text-center"
    :role="error ? 'alert' : undefined"
  >
    <div
      class="mb-1 flex size-12 items-center justify-center rounded-full bg-surface-gray-2"
    >
      <component :is="icon" class="size-5 text-ink-gray-6" aria-hidden="true" />
    </div>
    <div class="text-base-medium text-ink-gray-8">{{ title }}</div>
    <p v-if="message" class="max-w-sm text-p-sm text-ink-gray-6">
      {{ message }}
    </p>
    <div
      v-if="$slots.default"
      class="mt-2 flex flex-wrap items-center justify-center gap-2"
    >
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Component } from "vue";

defineProps<{
  icon: Component;
  title: string;
  message?: string;
  error?: boolean;
}>();
</script>
