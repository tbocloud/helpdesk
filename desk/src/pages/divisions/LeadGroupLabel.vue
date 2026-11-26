<template>
  <!-- a status group's colour, always beside its name -->
  <span class="inline-flex items-center gap-1.5">
    <span
      class="size-2 shrink-0 rounded-full"
      :class="GROUP_LOOK[group].dot"
      aria-hidden="true"
    />
    {{ GROUP_LOOK[group].label }}
  </span>
</template>

<script setup lang="ts">
import { GROUP_LOOK, type LeadGroup } from "./leadStatus";

defineProps<{ group: LeadGroup }>();
</script>
