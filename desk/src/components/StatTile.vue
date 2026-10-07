<template>
  <!-- one tile for every count: static, a link (`to`) or a toggle (`pressed`) -->
  <component
    :is="to ? RouterLink : pressed !== undefined ? NativeButton : 'div'"
    v-bind="
      to
        ? { to }
        : pressed !== undefined
        ? { type: 'button', 'aria-pressed': pressed }
        : {}
    "
    class="flex min-w-0 flex-col gap-1 rounded-xl border p-4 text-left"
    :class="[
      hero ? 'sm:col-span-2' : '',
      pressed
        ? 'border-brand bg-brand-soft'
        : 'border-outline-gray-2 bg-surface-base',
      interactive
        ? 'transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4'
        : '',
      interactive && !pressed ? 'hover:border-outline-gray-4' : '',
    ]"
  >
    <span class="flex items-center gap-1.5 text-sm text-ink-gray-7">
      <component
        :is="icon"
        v-if="icon"
        class="size-4 shrink-0"
        :class="iconTone === 'neutral' ? 'text-ink-gray-5' : INK[iconTone]"
        aria-hidden="true"
      />
      <span class="min-w-0 flex-1 truncate">{{ label }}</span>
      <LucideChevronRight
        v-if="to"
        class="size-4 shrink-0 text-ink-gray-4"
        aria-hidden="true"
      />
    </span>
    <span
      class="font-semibold tabular-nums"
      :class="[
        hero ? 'text-5xl leading-tight' : 'text-2xl',
        valueTone === 'neutral' ? 'text-ink-gray-9' : INK[valueTone],
      ]"
    >
      <span
        v-if="loading"
        class="inline-block h-7 w-10 animate-pulse rounded bg-surface-gray-2"
      />
      <template v-else>{{ value }}</template>
    </span>
    <span v-if="meter != null" class="mt-1 flex flex-col gap-1">
      <span
        class="block h-2 overflow-hidden rounded-full"
        :class="TRACK[tone]"
        role="meter"
        :aria-valuenow="Math.round(meter)"
        aria-valuemin="0"
        aria-valuemax="100"
        :aria-label="label"
      >
        <span
          class="block h-full rounded-full transition-[width]"
          :class="FILL[tone]"
          :style="{ width: `${Math.min(meter, 100)}%` }"
        />
      </span>
    </span>
    <span v-if="sub && !loading" class="text-p-sm tabular-nums text-ink-gray-6">
      {{ sub }}
    </span>
  </component>
</template>

<script setup lang="ts">
import { FILL, INK, TRACK, type Tone } from "@/components/tone";
import { computed, h, type Component, type FunctionalComponent } from "vue";
import { RouterLink, type RouteLocationRaw } from "vue-router";
import LucideChevronRight from "~icons/lucide/chevron-right";

const props = withDefaults(
  defineProps<{
    label: string;
    value: string | number;
    sub?: string;
    icon?: Component;
    /** colours the icon, only when that carries meaning (e.g. overdue) */
    iconTone?: Tone;
    hero?: boolean;
    /** 0-100; draws a meter under the value */
    meter?: number | null;
    /** the meter's colour */
    tone?: Tone;
    /** colours the value, only when that says how it went */
    valueTone?: Tone;
    loading?: boolean;
    /** makes the tile a link to another page */
    to?: RouteLocationRaw;
    /** makes the tile a toggle button (e.g. a filter); emits click */
    pressed?: boolean;
  }>(),
  {
    tone: "neutral",
    iconTone: "neutral",
    meter: null,
    valueTone: "neutral",
    // undefined keeps the tile a plain block; Vue would default a boolean to false
    pressed: undefined,
  }
);

// `:is="'button'"` would resolve to frappe-ui's globally registered Button (Vue
// prefers a registered component over the native tag), which renders its own
// label and drops this tile's content; this always renders a real <button>
const NativeButton: FunctionalComponent = (_, { attrs, slots }) =>
  h("button", attrs, slots.default?.());
NativeButton.inheritAttrs = false;

const interactive = computed(() => !!props.to || props.pressed !== undefined);
</script>
