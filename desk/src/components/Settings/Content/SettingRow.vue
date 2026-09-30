<template>
  <div class="mt-6 flex items-center justify-between gap-6">
    <div class="flex flex-col gap-1">
      <span class="text-base-medium text-ink-gray-8">{{ label }}</span>
      <span v-if="description" class="text-p-sm text-ink-gray-6">{{
        description
      }}</span>
    </div>
    <slot />
  </div>
</template>

<script setup lang="ts">
defineProps<{ label: string; description?: string }>();
</script>
