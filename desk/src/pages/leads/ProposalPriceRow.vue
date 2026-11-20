<template>
  <!-- one price on the Price card: the list price until one is typed (docs/proposals.md) -->
  <li class="flex flex-wrap items-center gap-x-3 gap-y-1 py-1.5">
    <span class="flex min-w-0 flex-1 flex-col">
      <span class="truncate text-sm text-ink-gray-8">{{ label }}</span>
      <span v-if="detail" class="truncate text-xs text-ink-gray-5">
        {{ detail }}
      </span>
    </span>
    <button
      v-if="set"
      type="button"
      class="rounded text-xs text-ink-gray-6 underline decoration-outline-gray-4 underline-offset-2 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
      @click="emit('price', null)"
    >
      {{ several ? __("Use the list prices") : __("Use the list price") }}
    </button>
    <span v-else class="text-xs text-ink-gray-5">
      {{ several ? __("List prices") : __("List price") }}
    </span>
    <FormControl
      class="w-36"
      :model-value="price"
      type="number"
      min="0"
      step="any"
      :aria-label="__('Price of {0}', label)"
      @update:model-value="typed"
    />
  </li>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { FormControl } from "frappe-ui";

defineProps<{
  label: string;
  /** what the price covers, under the label */
  detail?: string;
  price: number;
  /** a price was typed; otherwise it shows the list price */
  set: boolean;
  /** it stands for several modules, so its list price is theirs added up */
  several?: boolean;
}>();
const emit = defineEmits<{
  /** null: back to the list price */
  (e: "price", value: number | null): void;
}>();

function typed(value: string | number | null) {
  // an emptied box is the list price again, not a price of 0
  if (value === "" || value === null) return emit("price", null);
  emit("price", Math.max(Number(value) || 0, 0));
}
</script>
