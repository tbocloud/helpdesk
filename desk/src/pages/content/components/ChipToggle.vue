<template>
  <button
    type="button"
    :role="role"
    :aria-pressed="role ? undefined : pressed"
    :aria-checked="role ? pressed : undefined"
    class="inline-flex h-7 items-center gap-1.5 rounded-full border px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
    :class="
      pressed
        ? 'border-brand bg-brand-soft text-brand-ink'
        : 'border-outline-gray-2 bg-surface-base text-ink-gray-7 hover:bg-surface-gray-2'
    "
    @click="emit('toggle')"
  >
    <LucideCheck v-if="pressed" class="size-3.5" aria-hidden="true" />
    <slot name="icon" />
    {{ label }}
  </button>
</template>

<script setup lang="ts">
import LucideCheck from "~icons/lucide/check";

defineProps<{ label: string; pressed: boolean; role?: string }>();
const emit = defineEmits<{ (e: "toggle"): void }>();
</script>
