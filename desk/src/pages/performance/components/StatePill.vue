<template>
  <span
    class="inline-flex h-6 items-center gap-1 rounded-full px-2 text-xs font-medium"
    :class="tone.classes"
  >
    <component :is="tone.icon" class="size-3.5" aria-hidden="true" />
    {{ __(state) }}
  </span>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideClock from "~icons/lucide/clock";

const props = defineProps<{ state: string }>();

// status colours carry meaning only, always with an icon and the word
const tone = computed(() => {
  if (["Completed", "Published on time"].includes(props.state))
    return { classes: "bg-success-soft text-success", icon: LucideCircleCheck };
  if (["Completed late", "Published late"].includes(props.state))
    return { classes: "bg-warning-soft text-warning", icon: LucideClock };
  if (["Overdue", "Missed"].includes(props.state))
    return { classes: "bg-danger-soft text-danger", icon: LucideCircleAlert };
  return {
    classes: "bg-surface-gray-2 text-ink-gray-7",
    icon: LucideCircleDot,
  };
});
</script>
