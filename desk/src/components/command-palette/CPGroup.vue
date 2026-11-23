<template>
  <div
    class="flex w-full min-w-0 items-center rounded p-2 text-base-medium text-ink-gray-8"
    :class="{ 'bg-surface-gray-3': active }"
  >
    <component
      :is="item.icon"
      v-if="item.icon"
      class="mr-3 h-4 w-4 shrink-0 text-ink-gray-6"
    />
    <span class="min-w-0 truncate">{{ item.title }}</span>
    <span
      v-if="item.description"
      class="ml-auto max-w-[45%] shrink-0 truncate pl-3 text-sm text-ink-gray-5"
    >
      {{ item.description }}
    </span>
  </div>
</template>
<script setup lang="ts">
defineProps<{
  item: { title: string; description?: string; icon?: unknown };
  active: boolean;
}>();
</script>
