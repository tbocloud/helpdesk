<template>
  <span
    class="inline-flex h-5 shrink-0 items-center gap-1 whitespace-nowrap rounded-md px-1.5 text-xs font-medium"
    :class="TONE_CLASSES[tone]"
  >
    <component :is="icon" v-if="icon" class="size-3.5" aria-hidden="true" />
    <slot>{{ label }}</slot>
  </span>
</template>

<script setup lang="ts">
import { TONE_CLASSES, type Tone } from "@/components/tone";
import type { Component } from "vue";

withDefaults(
  defineProps<{
    label?: string;
    tone?: Tone;
    icon?: Component;
  }>(),
  { tone: "neutral" }
);
</script>
