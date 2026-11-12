<template>
  <span
    class="inline-flex h-5 shrink-0 items-center rounded px-1.5 text-2xs font-semibold uppercase tracking-wide"
    :class="TONE_CLASSES.warning"
  >
    {{ __("Key") }}
  </span>
</template>

<script setup lang="ts">
import { TONE_CLASSES } from "@/components/tone";
import { __ } from "@/translation";
</script>
