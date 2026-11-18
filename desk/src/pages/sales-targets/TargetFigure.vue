<template>
  <!-- one numeric target of a person's month: a cell in the hairline grid, its name and figure -->
  <div
    class="flex min-w-0 flex-col gap-3 border-b border-r border-outline-gray-1 p-4 md:p-5"
  >
    <div class="flex min-w-0 items-center gap-2">
      <span
        class="grid size-7 shrink-0 place-items-center rounded-lg bg-surface-gray-2 text-ink-gray-7"
      >
        <component :is="look.icon" class="size-3.5" aria-hidden="true" />
        <span class="sr-only">{{ look.label }}</span>
      </span>
      <h3
        class="min-w-0 truncate text-sm font-medium text-ink-gray-7"
        :title="criterion.criterion"
      >
        {{ criterion.criterion }}
      </h3>
    </div>
    <p
      class="break-words text-[28px] font-bold leading-none tracking-[-0.02em] text-ink-gray-9 tabular-nums"
    >
      {{ targetText(criterion, currency) }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { targetText, VALUE_TYPE_LOOK, type Criterion } from "./salesTargets";

const props = defineProps<{
  criterion: Criterion;
  currency: string;
}>();

const look = computed(() => VALUE_TYPE_LOOK[props.criterion.value_type]);
</script>
