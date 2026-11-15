<template>
  <span
    class="flex shrink-0 items-center justify-center rounded-full bg-surface-gray-3 text-lg-medium text-ink-gray-8"
    :class="small ? 'size-9' : 'size-12'"
    aria-hidden="true"
    >{{ initial }}</span
  >
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ name?: string | null; small?: boolean }>();
const initial = computed(() =>
  (props.name || "?").trim().charAt(0).toUpperCase()
);
</script>
