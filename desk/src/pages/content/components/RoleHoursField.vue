<template>
  <div class="flex flex-col gap-1.5">
    <!-- both labels on one row, in the same style, so the boxes below line up -->
    <div
      class="flex items-end gap-2 text-xs text-ink-gray-5"
      aria-hidden="true"
    >
      <span class="min-w-0 flex-1 truncate">{{ label }}</span>
      <span class="w-20 shrink-0">{{ __("Est. hours") }}</span>
    </div>
    <div class="flex items-start gap-2">
      <PeoplePicker
        v-model="people"
        class="min-w-0 flex-1"
        :label="label"
        hide-label
        :placeholder="placeholder || __('Assign')"
      />
      <FormControl
        v-model="hours"
        class="w-20 shrink-0"
        type="number"
        min="0"
        step="0.5"
        placeholder="—"
        :aria-label="__('Estimated hours for {0}', label)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { FormControl } from "frappe-ui";
import PeoplePicker from "./PeoplePicker.vue";

defineProps<{ label: string; placeholder?: string }>();
const people = defineModel<string[]>("people", { required: true });
const hours = defineModel<number | string | null>("hours");
</script>
