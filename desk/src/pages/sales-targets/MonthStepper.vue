<template>
  <!-- the month (or week), with a step either side: targets are read and set month after
       month, the weekly lead report week after week -->
  <div class="flex items-center gap-1" role="group" :aria-label="words.unit">
    <Button
      size="md"
      :aria-label="words.earlier"
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
      :class="unit === 'week' ? 'w-48' : 'w-40'"
      :aria-label="words.unit"
      :options="options"
      @update:model-value="emit('update:modelValue', String($event))"
    />
    <Button
      size="md"
      :aria-label="words.later"
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

const props = withDefaults(
  defineProps<{
    modelValue: string;
    /** newest first, as the pickers list them */
    options: { label: string; value: string }[];
    unit?: "month" | "week";
  }>(),
  { unit: "month" }
);
const emit = defineEmits<{ "update:modelValue": [value: string] }>();

const index = computed(() =>
  props.options.findIndex((o) => o.value === props.modelValue)
);

const words = computed(() =>
  props.unit === "week"
    ? { unit: __("Week"), earlier: __("Earlier week"), later: __("Later week") }
    : {
        unit: __("Month"),
        earlier: __("Earlier month"),
        later: __("Later month"),
      }
);

/** +1 steps to the one before (further down the list), -1 to the one after. */
function step(by: number) {
  const next = props.options[index.value + by];
  if (next) emit("update:modelValue", next.value);
}
</script>
