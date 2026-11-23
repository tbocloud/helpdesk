<template>
  <!-- payment milestones, each a label and its share, adding up to 100%: a proposal's own
       (ProposalPaymentTermsField) or a payment terms template's (Settings) -->
  <fieldset
    class="flex flex-col gap-2"
    :disabled="disabled"
    :aria-label="__('Payment milestones')"
  >
    <div v-for="(m, i) in modelValue" :key="i" class="flex items-center gap-2">
      <FormControl
        class="min-w-0 flex-1"
        :model-value="m.label"
        type="text"
        :placeholder="__('Milestone, e.g. Advance')"
        :aria-label="__('Milestone {0}', String(i + 1))"
        maxlength="140"
        @update:model-value="set(i, { label: $event })"
      />
      <FormControl
        class="w-24"
        :model-value="m.share"
        type="number"
        min="0"
        max="100"
        step="any"
        :aria-label="__('Share of milestone {0} (%)', String(i + 1))"
        @update:model-value="set(i, { share: Number($event) || 0 })"
      />
      <span class="text-sm text-ink-gray-6" aria-hidden="true">%</span>
      <Button
        variant="ghost"
        :label="__('Remove milestone {0}', String(i + 1))"
        :disabled="modelValue.length < 2"
        @click="remove(i)"
      >
        <template #icon>
          <LucideTrash2 class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>
    <div class="flex flex-wrap items-center gap-3">
      <Button
        :label="__('Add milestone')"
        :disabled="modelValue.length >= MAX_MILESTONES"
        @click="add"
      >
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
      <span
        class="text-p-sm tabular-nums"
        :class="addsUp(modelValue) ? 'text-ink-gray-6' : 'text-danger'"
        role="status"
      >
        {{
          addsUp(modelValue)
            ? __("Adds up to 100%")
            : __(
                "Adds up to {0}%; make it 100%",
                String(milestoneTotal(modelValue))
              )
        }}
      </span>
    </div>
  </fieldset>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, FormControl } from "frappe-ui";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";
import {
  addsUp,
  MAX_MILESTONES,
  milestoneTotal,
  type PaymentMilestone,
} from "./proposals";

const props = defineProps<{
  modelValue: PaymentMilestone[];
  disabled?: boolean;
}>();
const emit = defineEmits<{
  (e: "update:modelValue", value: PaymentMilestone[]): void;
}>();

function set(i: number, patch: Partial<PaymentMilestone>) {
  emit(
    "update:modelValue",
    props.modelValue.map((m, j) => (j === i ? { ...m, ...patch } : m))
  );
}

function add() {
  emit("update:modelValue", [
    ...props.modelValue,
    { label: "", share: Math.max(100 - milestoneTotal(props.modelValue), 0) },
  ]);
}

function remove(i: number) {
  emit(
    "update:modelValue",
    props.modelValue.filter((_, j) => j !== i)
  );
}
</script>
