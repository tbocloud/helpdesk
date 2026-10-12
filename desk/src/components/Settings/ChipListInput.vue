<template>
  <div class="flex flex-wrap items-center gap-2">
    <span
      v-for="value in values"
      :key="value"
      class="inline-flex min-h-7 items-center gap-1 rounded-full bg-surface-gray-2 pe-1 ps-2.5 text-sm text-ink-gray-8"
    >
      <span :class="mono ? 'font-mono text-xs' : ''">{{ value }}</span>
      <button
        type="button"
        class="grid size-5 place-items-center rounded-full text-ink-gray-5 hover:bg-surface-gray-4 hover:text-ink-gray-8"
        :aria-label="__('Remove {0}', value)"
        @click="values = values.filter((v) => v !== value)"
      >
        <LucideX class="size-3.5" aria-hidden="true" />
      </button>
    </span>
    <Link
      v-model="adding"
      class="w-56"
      :doctype="doctype"
      :filters="filters"
      :placeholder="placeholder"
    />
  </div>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import { __ } from "@/translation";
import { ref, watch } from "vue";
import LucideX from "~icons/lucide/x";

defineProps<{
  doctype: string;
  filters?: Record<string, unknown>;
  /** Also the accessible name of the picker, e.g. "Add a person". */
  placeholder: string;
  /** Shows values in Geist Mono, e.g. emails. */
  mono?: boolean;
}>();

/** The picked records' names, each shown as a removable chip. */
const values = defineModel<string[]>({ required: true });
const adding = ref("");

watch(adding, (value) => {
  if (!value) return;
  if (!values.value.includes(value)) values.value = [...values.value, value];
  adding.value = "";
});
</script>
