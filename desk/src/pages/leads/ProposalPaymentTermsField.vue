<template>
  <!-- a payment terms template, or this proposal's own milestones adding up to 100%
       (docs/proposals.md) -->
  <div class="flex flex-col gap-2" :class="custom ? 'sm:col-span-3' : ''">
    <FormControl
      :model-value="custom ? CUSTOM : terms || templates[0] || ''"
      type="select"
      :label="__('Payment terms')"
      :options="options"
      :disabled="disabled"
      @update:model-value="pick"
    />
    <PaymentMilestonesEditor
      v-if="custom"
      :model-value="milestones"
      :disabled="disabled"
      @update:model-value="emit('update', { payment_milestones: $event })"
    />
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { FormControl } from "frappe-ui";
import { computed } from "vue";
import PaymentMilestonesEditor from "./PaymentMilestonesEditor.vue";
import type { PaymentMilestone } from "./proposals";

const props = defineProps<{
  /** the template picked (its title) */
  terms?: string | null;
  /** this proposal's own milestones; none is the template */
  milestones: PaymentMilestone[];
  /** the payment terms templates' titles */
  templates: string[];
  disabled?: boolean;
}>();
const emit = defineEmits<{
  (
    e: "update",
    value: {
      payment_terms?: string | null;
      payment_milestones: PaymentMilestone[];
    }
  ): void;
}>();

const CUSTOM = "__custom";
const custom = computed(() => props.milestones.length > 0);
const options = computed(() => [
  ...props.templates.map((t) => ({ label: t, value: t })),
  { label: __("Custom milestones…"), value: CUSTOM },
]);
function pick(value: string) {
  if (value !== CUSTOM)
    return emit("update", {
      payment_terms: value || null,
      payment_milestones: [],
    });
  emit("update", {
    payment_milestones: [
      { label: __("Advance"), share: 50 },
      { label: __("On go-live"), share: 50 },
    ],
  });
}
</script>
