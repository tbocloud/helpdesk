<template>
  <ul v-if="rows.length" class="flex flex-col gap-2" role="list">
    <li
      v-for="row in rows"
      :key="row.label"
      class="grid grid-cols-[minmax(6rem,12rem)_minmax(0,1fr)_4.5rem] items-center gap-3 text-p-sm"
    >
      <span class="min-w-0 break-words text-ink-gray-8">{{ row.label }}</span>
      <span
        class="h-2 overflow-hidden rounded-full bg-surface-gray-2"
        aria-hidden="true"
      >
        <span
          class="block h-2 rounded-full"
          :class="row.tone === 'danger' ? 'bg-danger' : 'bg-surface-gray-7'"
          :style="{ width: `${Math.max(2, row.share)}%` }"
        />
      </span>
      <span class="text-right tabular-nums text-ink-gray-8">{{
        row.text
      }}</span>
    </li>
  </ul>
  <p v-else class="text-p-sm text-ink-gray-6">
    {{ empty || __("Nothing to show in this period.") }}
  </p>
</template>

<script setup lang="ts">
// A short list of labelled bars: each value beside its bar, so it never rests on colour alone.
// A long label wraps rather than being cut, so the whole name shows without hovering.
import { __ } from "@/translation";

defineProps<{
  rows: { label: string; share: number; text: string; tone?: string }[];
  empty?: string;
}>();
</script>
