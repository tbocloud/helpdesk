<template>
  <section
    class="border-t border-outline-gray-2 py-6 first:border-t-0 first:pt-0 last:pb-0"
    :aria-labelledby="headingId"
  >
    <div class="mb-4 flex items-start justify-between gap-3">
      <div class="min-w-0">
        <h2 :id="headingId" class="text-base-semibold text-ink-gray-9">
          {{ title }}
        </h2>
        <p
          v-if="description"
          class="mt-1 max-w-prose text-p-sm text-ink-gray-6"
        >
          {{ description }}
        </p>
      </div>
      <div v-if="$slots.actions" class="flex shrink-0 items-center gap-2">
        <slot name="actions" />
      </div>
    </div>
    <div class="flex flex-col gap-5">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
import { useId } from "vue";

defineProps<{
  title: string;
  /** One line under the title: what the section controls. */
  description?: string;
}>();

const headingId = `settings-section-${useId()}`;
</script>
