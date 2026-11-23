<template>
  <div
    class="flex flex-wrap items-end gap-3"
    role="group"
    :aria-label="__('Division and period')"
  >
    <FormControl
      v-if="options.length > 1"
      variant="outline"
      size="md"
      type="select"
      class="w-full sm:w-52"
      :label="__('Division')"
      :model-value="division"
      :options="divisionOptions"
      @update:model-value="emit('update:division', $event)"
    />
    <FormControl
      variant="outline"
      size="md"
      type="select"
      class="w-full sm:w-44"
      :label="__('Period')"
      :model-value="period"
      :options="PERIODS"
      @update:model-value="emit('update:period', $event)"
    />
    <template v-if="period === 'custom'">
      <FormControl
        variant="outline"
        size="md"
        type="date"
        class="w-full sm:w-40"
        :label="__('From')"
        :model-value="custom.from"
        @update:model-value="emit('update:custom', { ...custom, from: $event })"
      />
      <FormControl
        variant="outline"
        size="md"
        type="date"
        class="w-full sm:w-40"
        :label="__('To')"
        :model-value="custom.to"
        @update:model-value="emit('update:custom', { ...custom, to: $event })"
      />
    </template>
    <slot />
    <LucideLoaderCircle
      v-if="loading"
      class="mb-2.5 ml-auto size-4 animate-spin text-ink-gray-6 motion-reduce:animate-none"
      :aria-label="__('Loading')"
    />
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { FormControl } from "frappe-ui";
import { computed } from "vue";
import LucideLoaderCircle from "~icons/lucide/loader-circle";
import { PERIODS } from "./divisions";

const props = defineProps<{
  division: string;
  period: string;
  custom: { from: string; to: string };
  /** the divisions the person may look at (from the server) */
  options: { name: string; division_name: string }[];
  loading?: boolean;
}>();

const emit = defineEmits<{
  "update:division": [value: string];
  "update:period": [value: string];
  "update:custom": [value: { from: string; to: string }];
}>();

const divisionOptions = computed(() => [
  { label: __("All divisions"), value: "" },
  ...props.options.map((d) => ({ label: d.division_name, value: d.name })),
]);
</script>
