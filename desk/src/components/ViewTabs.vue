<template>
  <!-- a page's views: pills in one white strip, the current one filled dark, each with its count -->
  <div
    role="tablist"
    :aria-label="ariaLabel"
    class="inline-flex max-w-full flex-wrap gap-1 rounded-full border border-outline-gray-2 bg-surface-base p-1"
    @keydown="onKeydown"
  >
    <button
      v-for="(option, index) in options"
      :key="option.value"
      ref="tabs"
      type="button"
      role="tab"
      :aria-selected="option.value === modelValue"
      :tabindex="
        option.value === modelValue ||
        (index === 0 && !options.some((o) => o.value === modelValue))
          ? 0
          : -1
      "
      class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full px-3 text-[12px] font-medium transition-colors"
      :class="
        option.value === modelValue
          ? 'bg-surface-gray-10 text-ink-base'
          : 'text-ink-gray-7 hover:bg-surface-gray-3'
      "
      @click="emit('update:modelValue', option.value)"
    >
      <component
        :is="option.icon"
        v-if="option.icon"
        class="size-4 shrink-0"
        aria-hidden="true"
      />
      {{ option.label }}
      <span
        v-if="option.count != null"
        class="min-w-[22px] rounded-full px-[7px] py-px text-center text-xs font-semibold tabular-nums"
        :class="
          option.value === modelValue
            ? 'bg-white/20 text-ink-base'
            : 'bg-surface-gray-4 text-ink-gray-7'
        "
        >{{ option.count }}</span
      >
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, type Component } from "vue";

export interface ViewTab {
  value: string;
  label: string;
  count?: number | string | null;
  icon?: Component;
}

const props = defineProps<{
  modelValue: string;
  options: ViewTab[];
  ariaLabel: string;
}>();

const emit = defineEmits<{ (e: "update:modelValue", value: string): void }>();

const tabs = ref<HTMLButtonElement[]>([]);

// arrow keys move between the views, as a tab list does
function onKeydown(event: KeyboardEvent) {
  const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
  const edge = { Home: 0, End: props.options.length - 1 }[event.key];
  if (step === undefined && edge === undefined) return;
  event.preventDefault();
  const current = props.options.findIndex((o) => o.value === props.modelValue);
  const next =
    edge ?? (current + step! + props.options.length) % props.options.length;
  emit("update:modelValue", props.options[next].value);
  tabs.value[next]?.focus();
}
</script>
