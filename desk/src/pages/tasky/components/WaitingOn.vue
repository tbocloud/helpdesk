<template>
  <span
    class="inline-flex min-w-0 items-center gap-1 text-xs text-ink-gray-6"
    :title="label"
  >
    <LucideLock class="size-3 shrink-0 text-warning" aria-hidden="true" />
    <span class="truncate">{{ label }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import LucideLock from "~icons/lucide/lock";
import { waitingOnLabel } from "../taskMeta";

const props = defineProps<{ subject?: string | null }>();

const label = computed(() => waitingOnLabel(props.subject));
</script>
