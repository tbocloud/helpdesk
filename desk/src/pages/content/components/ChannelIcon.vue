<template>
  <!-- Lucide dropped its brand marks, so the social ones are drawn here in its 24px stroke style -->
  <svg
    v-if="mark"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    :style="{ color: channelColor(channel) }"
    aria-hidden="true"
  >
    <path v-for="d in mark" :key="d" :d="d" />
  </svg>
  <component
    :is="fallback"
    v-else
    :style="{ color: channelColor(channel) }"
    aria-hidden="true"
  />
</template>

<script setup lang="ts">
import { channelColor } from "@/pages/performance/performanceMeta";
import { computed } from "vue";
import LucideGlobe from "~icons/lucide/globe";
import LucideMail from "~icons/lucide/mail";
import LucideMessageCircle from "~icons/lucide/message-circle";
import LucideNewspaper from "~icons/lucide/newspaper";

const props = defineProps<{ channel: string }>();

const MARKS: Record<string, string[]> = {
  Instagram: [
    "M7 2h10a5 5 0 0 1 5 5v10a5 5 0 0 1-5 5H7a5 5 0 0 1-5-5V7a5 5 0 0 1 5-5z",
    "M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z",
    "M17.5 6.5h.01",
  ],
  Facebook: [
    "M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z",
  ],
  LinkedIn: [
    "M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-4 0v7h-4v-7a6 6 0 0 1 6-6z",
    "M2 9h4v12H2z",
    "M6 4a2 2 0 1 1-4 0 2 2 0 0 1 4 0z",
  ],
  X: ["M4 4l11.733 16H20L8.267 4z", "M4 20l6.768-6.768", "M13.232 10.768 20 4"],
  YouTube: [
    "M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17",
    "m10 15 5-3-5-3z",
  ],
};

const FALLBACKS = {
  Blog: LucideNewspaper,
  Email: LucideMail,
  WhatsApp: LucideMessageCircle,
};

const mark = computed(() => MARKS[props.channel]);
const fallback = computed(
  () => FALLBACKS[props.channel as keyof typeof FALLBACKS] ?? LucideGlobe
);
</script>
