<template>
  <div
    class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-6"
  >
    <div class="flex min-w-0 flex-col gap-1">
      <label :for="id" class="text-base-medium text-ink-gray-8">
        {{ label }}
      </label>
      <p v-if="description" class="max-w-prose text-p-sm text-ink-gray-6">
        {{ description }}
      </p>
    </div>
    <div class="shrink-0">
      <!-- bind `id` on the control so the label above names it -->
      <slot :id="id" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useId } from "vue";

defineProps<{ label: string; description?: string }>();

const id = `setting-${useId()}`;
</script>
