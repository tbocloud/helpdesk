<template>
  <!-- one criterion of a person's month: its number in the list, name, type and target -->
  <article
    class="flex min-w-0 flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
    :class="long && 'sm:col-span-2'"
    :aria-labelledby="nameId"
  >
    <div class="flex items-start justify-between gap-3">
      <div class="flex min-w-0 flex-col gap-1">
        <span class="text-xs font-medium tabular-nums text-ink-gray-5">
          {{ __("Target {0}", String(position)) }}
        </span>
        <h3
          :id="nameId"
          class="text-sm font-semibold leading-snug text-ink-gray-8"
        >
          {{ criterion.criterion }}
        </h3>
      </div>
      <span
        class="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-gray-2 text-ink-gray-7 ring-1 ring-inset ring-black/[0.04]"
      >
        <component :is="look.icon" class="size-4" aria-hidden="true" />
      </span>
    </div>

    <p
      v-if="isText"
      class="min-w-0 whitespace-pre-line break-words text-p-base text-ink-gray-9"
    >
      {{ value }}
    </p>
    <p
      v-else
      class="text-[26px] font-bold leading-none tracking-[-0.02em] tabular-nums text-ink-gray-9"
    >
      {{ value }}
    </p>

    <p class="mt-auto text-xs text-ink-gray-6">{{ look.label }}</p>
  </article>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed, useId } from "vue";
import { targetText, VALUE_TYPE_LOOK, type Criterion } from "./salesTargets";

const props = defineProps<{
  criterion: Criterion;
  /** 1 for the first criterion, as the Sales Head ordered them */
  position: number;
  currency: string;
}>();

const nameId = useId();
const look = computed(() => VALUE_TYPE_LOOK[props.criterion.value_type]);
const isText = computed(() => props.criterion.value_type === "Text");
const value = computed(() => targetText(props.criterion, props.currency));
// a long text target takes two columns, so it doesn't stretch one card down the page
const long = computed(() => isText.value && value.value.length > 80);
</script>
