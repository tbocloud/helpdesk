<template>
  <!-- a part of the dashboard the ERP site couldn't answer; the rest still shows -->
  <p
    v-if="message"
    role="alert"
    class="flex items-start gap-2 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-3 text-sm text-danger"
  >
    <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
    {{ message }}
  </p>
</template>

<script setup lang="ts">
import LucideCircleAlert from "~icons/lucide/circle-alert";

defineProps<{ message?: string }>();
</script>
