<template>
  <span
    class="inline-flex max-w-full items-center gap-1 rounded-md bg-warning-soft px-1.5 py-0.5 text-xs font-medium text-warning"
    :title="__('Special day: {0}', name)"
  >
    <LucideStar class="size-3 shrink-0 fill-current" aria-hidden="true" />
    <span class="sr-only">{{ __("Special day:") }}</span>
    <span class="truncate">{{ name }}</span>
  </span>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import LucideStar from "~icons/lucide/star";

defineProps<{ name: string }>();
</script>
