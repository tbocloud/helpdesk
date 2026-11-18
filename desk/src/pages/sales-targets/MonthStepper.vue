<template>
  <!-- the month, with a step either side: targets are read and set month after month -->
  <div class="flex items-center gap-1" role="group" :aria-label="__('Month')">
    <Button
      size="md"
      :aria-label="__('Earlier month')"
      :disabled="index >= options.length - 1"
      @click="step(1)"
    >
      <template #icon>
        <LucideChevronLeft class="size-4" />
      </template>
    </Button>
    <FormControl
      :model-value="modelValue"
      type="select"
      size="md"
      class="w-40"
      :aria-label="__('Month')"
      :options="options"
      @update:model-value="emit('update:modelValue', String($event))"
    />
    <Button
      size="md"
      :aria-label="__('Later month')"
      :disabled="index <= 0"
      @click="step(-1)"
    >
      <template #icon>
        <LucideChevronRight class="size-4" />
      </template>
    </Button>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, FormControl } from "frappe-ui";
import { computed } from "vue";
import LucideChevronLeft from "~icons/lucide/chevron-left";
import LucideChevronRight from "~icons/lucide/chevron-right";

const props = defineProps<{
  modelValue: string;
  /** newest first, as the pickers list them */
  options: { label: string; value: string }[];
}>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();

const index = computed(() =>
  props.options.findIndex((o) => o.value === props.modelValue)
);

/** +1 steps to the month before (further down the list), -1 to the month after. */
function step(by: number) {
  const next = props.options[index.value + by];
  if (next) emit("update:modelValue", next.value);
}
</script>
