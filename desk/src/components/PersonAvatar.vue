<template>
  <!-- a person's initials on their own colour; the same name always gets the same colour -->
  <span
    class="inline-flex shrink-0 items-center justify-center rounded-full font-semibold"
    :class="[SIZES[size], neutral ? 'bg-surface-gray-2 text-ink-gray-7' : tone]"
    aria-hidden="true"
    >{{ initials }}</span
  >
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    name?: string | null;
    size?: "xs" | "sm" | "md" | "lg";
    /** gray, for things rather than people (a lead, a company) */
    neutral?: boolean;
  }>(),
  { size: "sm" }
);

// full class strings, so Tailwind finds them
const SIZES = {
  xs: "size-[22px] text-[10px]",
  sm: "size-[26px] text-[11px]",
  md: "size-7 text-[11px]",
  lg: "size-[30px] text-[11px]",
};
const TONES = [
  "bg-person-1-soft text-person-1",
  "bg-person-2-soft text-person-2",
  "bg-person-3-soft text-person-3",
  "bg-person-4-soft text-person-4",
  "bg-person-5-soft text-person-5",
  "bg-person-6-soft text-person-6",
];

const initials = computed(() =>
  (props.name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase()
);

const tone = computed(() => {
  let hash = 0;
  for (const ch of props.name || "") hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  return TONES[Math.abs(hash) % TONES.length];
});
</script>
