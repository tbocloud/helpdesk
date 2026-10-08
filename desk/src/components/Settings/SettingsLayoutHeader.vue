<template>
  <header class="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
    <div class="flex min-w-0 flex-1 items-start gap-1">
      <Button
        v-if="backLabel"
        variant="ghost"
        class="-ms-2 shrink-0"
        :label="backLabel"
        :tooltip="backLabel"
        @click="emit('back')"
      >
        <template #icon>
          <LucideChevronLeft class="size-4 rtl:rotate-180" aria-hidden="true" />
        </template>
      </Button>
      <div class="flex min-w-0 flex-col gap-1">
        <div class="flex min-h-7 min-w-0 items-center gap-2">
          <slot name="title">
            <h1
              class="truncate text-lg-semibold text-ink-gray-9"
              :title="title"
            >
              {{ title }}
            </h1>
          </slot>
          <slot name="badge" />
          <UnsavedBadge :show="dirty" />
        </div>
        <slot name="description">
          <p v-if="description" class="max-w-prose text-p-sm text-ink-gray-6">
            {{ description }}
          </p>
        </slot>
      </div>
    </div>
    <div
      v-if="$slots.actions"
      class="flex shrink-0 flex-wrap items-center gap-2"
    >
      <slot name="actions" />
    </div>
  </header>
  <div v-if="$slots.bottom" class="mt-5">
    <slot name="bottom" />
  </div>
</template>

<script setup lang="ts">
import UnsavedBadge from "@/components/UnsavedBadge.vue";
import { Button } from "frappe-ui";
import LucideChevronLeft from "~icons/lucide/chevron-left";

defineProps<{
  title?: string;
  /** One line under the title: what this page changes. */
  description?: string;
  /** Shows the "Unsaved" badge. */
  dirty?: boolean;
  /** Shows a back button with this accessible name, e.g. "Back to SLA policies". */
  backLabel?: string;
}>();

const emit = defineEmits<{ (e: "back"): void }>();
</script>
