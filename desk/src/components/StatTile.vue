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
    class="flex min-w-0 items-start rounded-xl border text-left"
    :class="[
      compact ? 'px-3 py-2.5' : 'flex-col gap-2 p-4 sm:flex-row sm:gap-3',
      hero ? 'sm:col-span-2' : '',
      pressed
        ? 'border-brand bg-brand-soft'
        : tint
        ? TINTS[tint].tile
        : 'border-outline-gray-2 bg-surface-base',
      interactive
        ? 'transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4'
        : '',
      interactive && !pressed ? 'hover:border-outline-gray-4' : '',
    ]"
  >
    <!-- the icon sits in a circle; soft colour only when iconTone carries meaning -->
    <span
      v-if="icon && !compact"
      class="grid size-9 shrink-0 place-items-center rounded-full"
      :class="tint ? TINTS[tint].circle : circleClass"
    >
      <component :is="icon" class="size-[18px]" aria-hidden="true" />
    </span>

    <span class="flex min-w-0 flex-1 flex-col gap-1">
      <span class="flex items-center gap-1.5 text-sm text-ink-gray-7">
        <component
          :is="icon"
          v-if="icon && compact"
          class="size-4 shrink-0"
          :class="iconInk"
          aria-hidden="true"
        />
        <span class="min-w-0 flex-1" :class="compact ? 'truncate' : ''">{{
          label
        }}</span>
        <LucideChevronRight
          v-if="to"
          class="size-4 shrink-0 text-ink-gray-4"
          aria-hidden="true"
        />
      </span>
      <span
        class="font-semibold tabular-nums"
        :class="[
          hero ? 'text-5xl leading-tight' : compact ? 'text-xl' : 'text-3xl',
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
      <!-- the change against the last period: an arrow and words, never colour alone -->
      <span
        v-if="deltaText && !loading"
        class="flex items-start gap-1 text-p-sm tabular-nums"
        :class="deltaTone === 'neutral' ? 'text-ink-gray-6' : INK[deltaTone]"
      >
        <LucideArrowUp
          v-if="delta != null && delta > 0"
          class="mt-[3px] size-3.5 shrink-0"
          aria-hidden="true"
        />
        <LucideArrowDown
          v-else-if="delta != null && delta < 0"
          class="mt-[3px] size-3.5 shrink-0"
          aria-hidden="true"
        />
        <span v-if="delta" class="sr-only">
          {{ delta > 0 ? __("Up") : __("Down") }}
        </span>
        <span class="min-w-0">{{ deltaText }}</span>
      </span>
      <span
        v-if="sub && !loading"
        class="text-p-sm tabular-nums text-ink-gray-6"
      >
        {{ sub }}
      </span>
      <!-- extra content under the figures, e.g. a mini trend -->
      <slot v-if="!loading" />
    </span>
  </component>
</template>

<script setup lang="ts">
import NativeButton from "@/components/NativeButton";
import { FILL, INK, TONE_CLASSES, TRACK, type Tone } from "@/components/tone";
import { __ } from "@/translation";
import { computed, type Component } from "vue";
import { RouterLink, type RouteLocationRaw } from "vue-router";
import LucideArrowDown from "~icons/lucide/arrow-down";
import LucideArrowUp from "~icons/lucide/arrow-up";
import LucideChevronRight from "~icons/lucide/chevron-right";

const props = withDefaults(
  defineProps<{
    label: string;
    value: string | number;
    sub?: string;
    icon?: Component;
    /**
     * Colours the icon's circle, only when that carries meaning: success for
     * done, danger for overdue or risk, info for time and hours.
     */
    iconTone?: Tone | "brand";
    /**
     * Fills the tile with its tone's soft colour and sets the icon on the solid tone,
     * for headline figures on a screen that is colourful by exception (ui-guidelines §8).
     */
    tint?: Tone | "brand";
    hero?: boolean;
    /** tighter padding and a smaller number, for a strip above a list */
    compact?: boolean;
    /** 0-100; draws a meter under the value */
    meter?: number | null;
    /** the meter's colour */
    tone?: Tone;
    /** colours the value, only when that says how it went */
    valueTone?: Tone;
    /** signed change against the last period; its sign picks the arrow */
    delta?: number | null;
    /** the change in words, e.g. "101 vs last week" */
    deltaText?: string;
    /** colours the change line, only when that says it got better or worse */
    deltaTone?: Tone;
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
    delta: null,
    deltaTone: "neutral",
    // undefined keeps the tile a plain block; Vue would default a boolean to false
    pressed: undefined,
  }
);

const interactive = computed(() => !!props.to || props.pressed !== undefined);

// brand is not a status tone, so it is handled here, as TaskyBadge does
const circleClass = computed(() =>
  props.iconTone === "brand"
    ? "bg-brand-soft text-brand-ink"
    : TONE_CLASSES[props.iconTone]
);
const iconInk = computed(() =>
  props.iconTone === "neutral"
    ? "text-ink-gray-5"
    : props.iconTone === "brand"
    ? "text-brand-ink"
    : INK[props.iconTone]
);

// full class strings, so Tailwind finds them
const TINTS: Record<Tone | "brand", { tile: string; circle: string }> = {
  neutral: {
    tile: "border-transparent bg-surface-gray-2",
    circle: "bg-surface-gray-7 text-ink-base",
  },
  info: {
    tile: "border-transparent bg-info-soft",
    circle: "bg-info text-ink-base",
  },
  warning: {
    tile: "border-transparent bg-warning-soft",
    circle: "bg-warning text-ink-base",
  },
  success: {
    tile: "border-transparent bg-success-soft",
    circle: "bg-success text-ink-base",
  },
  danger: {
    tile: "border-transparent bg-danger-soft",
    circle: "bg-danger text-ink-base",
  },
  brand: {
    tile: "border-transparent bg-brand-soft",
    circle: "bg-brand text-brand-on",
  },
};
</script>
