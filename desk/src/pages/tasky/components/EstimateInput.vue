<template>
  <fieldset class="flex min-w-0 flex-col gap-1.5">
    <legend
      class="mb-1.5 text-xs text-ink-gray-5"
      :class="{ 'sr-only': hideLabel }"
    >
      {{ label || __("Estimate") }}
      <RequiredMark
        v-if="dueOrEstimate"
        :hint="__('(a due date or an estimate is required)')"
      />
    </legend>
    <div class="flex items-center gap-2">
      <TextInput
        :model-value="hours"
        type="number"
        inputmode="numeric"
        min="0"
        step="1"
        class="w-full min-w-0"
        placeholder="0"
        :aria-label="__('Hours')"
        @update:model-value="(v: string | number) => update(v, minutes)"
      >
        <template #suffix>
          <span class="text-xs text-ink-gray-5" aria-hidden="true">h</span>
        </template>
      </TextInput>
      <TextInput
        :model-value="minutes"
        type="number"
        inputmode="numeric"
        min="0"
        max="59"
        step="5"
        class="w-full min-w-0"
        placeholder="0"
        :aria-label="__('Minutes')"
        @update:model-value="(v: string | number) => update(hours, v)"
      >
        <template #suffix>
          <span class="text-xs text-ink-gray-5" aria-hidden="true">min</span>
        </template>
      </TextInput>
    </div>
  </fieldset>
</template>

<script setup lang="ts">
import RequiredMark from "@/components/RequiredMark.vue";
import { TextInput } from "frappe-ui";
import { computed } from "vue";
import { splitHours } from "../taskMeta";

/**
 * A task's estimate typed as hours and minutes. The model stays in hours (the
 * estimate fields are hours), so 1 h 30 min is 1.5 and 20 min is 0.33.
 */
const props = defineProps<{
  modelValue?: number | string | null;
  label?: string;
  /** the label is read by screen readers only, for a compact row (Templates) */
  hideLabel?: boolean;
  /** marked required: a new task needs this or a due date (taskMeta.hasDueOrEstimate) */
  dueOrEstimate?: boolean;
}>();
const emit = defineEmits<{ "update:modelValue": [hours: number] }>();

const parts = computed(() => splitHours(Number(props.modelValue) || 0));
// empty while 0, so the placeholder shows
const hours = computed(() => parts.value.hours || "");
const minutes = computed(() => parts.value.minutes || "");

function update(h: string | number, m: string | number) {
  const whole = Math.max(Math.floor(Number(h) || 0), 0);
  // 90 min typed in the minutes box is 1 h 30 min
  const mins = Math.max(Math.round(Number(m) || 0), 0);
  emit("update:modelValue", Math.round((whole + mins / 60) * 1000) / 1000);
}
</script>
