<template>
  <div
    class="flex flex-col gap-1 rounded-xl p-4"
    :class="[
      hero ? 'sm:col-span-2' : '',
      color ? TRACK[color] : 'border border-outline-gray-2 bg-surface-base',
    ]"
  >
    <div class="flex items-center gap-1.5 text-sm text-ink-gray-7">
      <component
        :is="icon"
        v-if="icon"
        class="size-4"
        :class="color ? INK[color] : 'text-ink-gray-5'"
        aria-hidden="true"
      />
      {{ label }}
    </div>
    <div
      class="font-semibold tabular-nums"
      :class="[
        hero ? 'text-5xl leading-tight' : 'text-2xl',
        color ? INK[color] : 'text-ink-gray-9',
      ]"
    >
      {{ value }}
    </div>
    <div v-if="meter != null" class="mt-1 flex flex-col gap-1">
      <div
        class="h-2 overflow-hidden rounded-full"
        :class="color ? 'bg-surface-base' : TRACK[tone]"
        role="meter"
        :aria-valuenow="Math.round(meter)"
        aria-valuemin="0"
        aria-valuemax="100"
        :aria-label="label"
      >
        <div
          class="h-full rounded-full transition-[width]"
          :class="FILL[tone]"
          :style="{ width: `${Math.min(meter, 100)}%` }"
        />
      </div>
    </div>
    <div v-if="sub" class="text-p-sm text-ink-gray-6">{{ sub }}</div>
  </div>
</template>

<script setup lang="ts">
import type { Component } from "vue";
import { FILL, INK, TRACK, type Tone } from "../performanceMeta";

withDefaults(
  defineProps<{
    label: string;
    value: string;
    sub?: string;
    icon?: Component;
    hero?: boolean;
    /** 0-100; draws a meter under the value */
    meter?: number | null;
    tone?: Tone;
    /** gives the whole tile a soft background in this tone */
    color?: Tone;
  }>(),
  { tone: "brand", meter: null, color: undefined }
);
</script>
