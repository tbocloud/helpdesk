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
    <fieldset
      v-if="custom"
      class="flex flex-col gap-2"
      :disabled="disabled"
      :aria-label="__('Payment milestones')"
    >
      <div
        v-for="(m, i) in milestones"
        :key="i"
        class="flex items-center gap-2"
      >
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
          :disabled="milestones.length < 2"
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
          :disabled="milestones.length >= MAX"
          @click="add"
        >
          <template #prefix>
            <LucidePlus class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <span
          class="text-p-sm tabular-nums"
          :class="adds ? 'text-ink-gray-6' : 'text-danger'"
          role="status"
        >
          {{
            adds
              ? __("Adds up to 100%")
              : __("Adds up to {0}%; make it 100%", String(total))
          }}
        </span>
      </div>
    </fieldset>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, FormControl } from "frappe-ui";
import { computed } from "vue";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";
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
// as many as the ERP site keeps
const MAX = 12;
const custom = computed(() => props.milestones.length > 0);
const options = computed(() => [
  ...props.templates.map((t) => ({ label: t, value: t })),
  { label: __("Custom milestones…"), value: CUSTOM },
]);
const total = computed(
  () =>
    Math.round(
      props.milestones.reduce((sum, m) => sum + (Number(m.share) || 0), 0) * 100
    ) / 100
);
const adds = computed(() => total.value === 100);

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

function set(i: number, patch: Partial<PaymentMilestone>) {
  emit("update", {
    payment_milestones: props.milestones.map((m, j) =>
      j === i ? { ...m, ...patch } : m
    ),
  });
}

function add() {
  emit("update", {
    payment_milestones: [
      ...props.milestones,
      { label: "", share: Math.max(100 - total.value, 0) },
    ],
  });
}

function remove(i: number) {
  emit("update", {
    payment_milestones: props.milestones.filter((_, j) => j !== i),
  });
}
</script>
