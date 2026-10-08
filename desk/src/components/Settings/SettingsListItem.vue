<template>
  <div
    class="flex min-h-14 items-center gap-3 px-3 py-2"
    :class="onOpen ? 'hover:bg-surface-gray-1' : ''"
  >
    <component
      :is="onOpen ? NativeButton : 'div'"
      v-bind="onOpen ? { type: 'button' } : {}"
      class="flex min-w-0 flex-1 items-center gap-3 rounded text-left"
      @click="onOpen?.()"
    >
      <slot name="prefix" />
      <span class="flex min-w-0 flex-col gap-0.5">
        <span class="flex min-w-0 items-center gap-2">
          <span
            class="truncate text-base-medium"
            :class="muted ? 'text-ink-gray-5' : 'text-ink-gray-9'"
            :title="title"
          >
            {{ title }}
          </span>
          <slot name="badges" />
        </span>
        <span
          v-if="subtitle"
          class="truncate text-p-sm text-ink-gray-6"
          :title="subtitle"
        >
          {{ subtitle }}
        </span>
      </span>
    </component>
    <slot name="meta" />
    <div v-if="$slots.actions" class="flex shrink-0 items-center gap-1">
      <slot name="actions" />
    </div>
    <LucideChevronRight
      v-else-if="onOpen"
      class="size-4 shrink-0 text-ink-gray-5 rtl:rotate-180"
      aria-hidden="true"
    />
  </div>
</template>

<script setup lang="ts">
import NativeButton from "@/components/NativeButton";
import LucideChevronRight from "~icons/lucide/chevron-right";

defineProps<{
  title: string;
  subtitle?: string;
  /** Greys the title, e.g. a disabled or inactive record. */
  muted?: boolean;
  /** Makes the title area a button that opens the record. */
  onOpen?: () => void;
}>();
</script>
