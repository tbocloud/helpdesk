<template>
  <!-- a timeline template, or a custom period in days whose phases the ERP site scales from
       the nearest template (docs/proposals.md) -->
  <div class="flex flex-col gap-2">
    <FormControl
      :model-value="days ? CUSTOM : template || suggested || ''"
      type="select"
      :label="__('Timeline')"
      :options="options"
      :disabled="disabled"
      @update:model-value="pick"
    />
    <FormControl
      v-if="days"
      :model-value="days"
      type="number"
      min="1"
      max="1000"
      step="1"
      :label="__('Custom period (days)')"
      :disabled="disabled"
      @update:model-value="setDays"
    />
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { FormControl } from "frappe-ui";
import { computed } from "vue";

const props = defineProps<{
  /** the template picked (its title) */
  template?: string | null;
  /** a custom period in days; 0 is none, so the template */
  days: number;
  timelines: { title: string; days: number }[];
  /** the template the effort suggests, marked and shown when none is picked */
  suggested?: string | null;
  disabled?: boolean;
}>();
const emit = defineEmits<{
  (
    e: "update",
    value: { timeline_template?: string | null; timeline_days: number }
  ): void;
}>();

const CUSTOM = "__custom";
const options = computed(() => [
  ...props.timelines.map((t) => ({
    label:
      t.title === props.suggested ? __("{0} (suggested)", t.title) : t.title,
    value: t.title,
  })),
  { label: __("Custom period…"), value: CUSTOM },
]);

function pick(value: string) {
  if (value !== CUSTOM)
    return emit("update", {
      timeline_template: value || null,
      timeline_days: 0,
    });
  // starts from the template it was on, so presales only nudges the number
  const from = props.timelines.find(
    (t) => t.title === (props.template || props.suggested)
  );
  emit("update", { timeline_days: Math.round(from?.days || 30) });
}

function setDays(value: string | number) {
  // an emptied box stays a custom period of 1 day rather than dropping back to a template
  emit("update", {
    timeline_days: Math.min(Math.max(Math.round(Number(value) || 1), 1), 1000),
  });
}
</script>
