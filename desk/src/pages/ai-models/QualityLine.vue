<template>
  <div class="flex items-baseline justify-between gap-3">
    <dt class="min-w-0 text-ink-gray-7">
      {{ label }}
      <span v-if="note" class="block text-p-xs text-ink-gray-5">{{
        note
      }}</span>
    </dt>
    <dd class="shrink-0 text-base-medium tabular-nums text-ink-gray-9">
      {{ value }}
    </dd>
  </div>
</template>

<script setup lang="ts">
defineProps<{ label: string; value: string; note?: string }>();
</script>
