<template>
  <!-- a whole number with its unit after it, e.g. "3 working days" -->
  <span class="inline-flex items-center gap-2">
    <FormControl
      :id="id"
      :model-value="modelValue"
      type="number"
      min="1"
      class="w-20"
      :disabled="disabled"
      :aria-label="ariaLabel"
      @update:model-value="(v: string) => emit('update:modelValue', Number(v))"
    />
    <span
      v-if="suffix"
      class="whitespace-nowrap text-sm text-ink-gray-6"
      :class="disabled ? 'opacity-60' : ''"
      >{{ suffix }}</span
    >
  </span>
</template>

<script setup lang="ts">
import { FormControl } from "frappe-ui";

defineProps<{
  modelValue?: number | null;
  suffix?: string;
  id?: string;
  disabled?: boolean;
  ariaLabel?: string;
}>();

const emit = defineEmits<{ "update:modelValue": [value: number] }>();
</script>
