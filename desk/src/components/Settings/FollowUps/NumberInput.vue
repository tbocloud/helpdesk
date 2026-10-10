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
      @update:model-value="update"
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

// a cleared box keeps the last number instead of saving 0, which the server refuses
function update(value: string) {
  if (value === "" || value == null) return;
  emit("update:modelValue", Number(value));
}
</script>
