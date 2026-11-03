<template>
  <div
    v-if="query.trim().length >= 2"
    class="rounded-lg border border-outline-gray-2"
    aria-live="polite"
  >
    <p v-if="loading" class="px-3 py-2 text-p-sm text-ink-gray-6">
      {{ __("Searching…") }}
    </p>
    <p v-else-if="!items.length" class="px-3 py-2 text-p-sm text-ink-gray-6">
      {{ __("Nothing found. Try another word.") }}
    </p>
    <ul v-else class="flex flex-col" role="list">
      <li v-for="item in items" :key="id(item)">
        <button
          type="button"
          class="flex min-h-11 w-full items-center px-3 py-2 text-start text-base text-ink-gray-8 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight"
          @click="emit('pick', item)"
        >
          {{ label(item) }}
        </button>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts" generic="T">
import { __ } from "@/translation";

defineProps<{
  items: T[];
  loading: boolean;
  query: string;
  label: (item: T) => string;
  id: (item: T) => string;
}>();
const emit = defineEmits<{ (e: "pick", item: T): void }>();
</script>
