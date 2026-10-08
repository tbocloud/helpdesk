<template>
  <div
    class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-6"
  >
    <div class="flex min-w-0 flex-col gap-1">
      <label :id="labelId" :for="id" class="text-base-medium text-ink-gray-8">
        {{ label }}
      </label>
      <p v-if="description" class="max-w-prose text-p-sm text-ink-gray-6">
        {{ description }}
      </p>
    </div>
    <div class="shrink-0">
      <!--
        Every control must be named by the label: bind `id` on controls that
        take one (Switch, FormControl, Select); pass `id` and `labelledby` to
        popover triggers (SelectDropdown, Link, Autocomplete) so their name is
        the label plus the current value. A control with its own visible text
        (a Button) needs neither.
      -->
      <slot :id="id" :labelledby="labelId" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useId } from "vue";

defineProps<{ label: string; description?: string }>();

const id = `setting-${useId()}`;
const labelId = `${id}-label`;
</script>
