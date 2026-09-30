<template>
  <span
    class="inline-flex h-6 shrink-0 items-center gap-1 rounded-full px-2 text-xs font-medium"
    :class="tone.classes"
  >
    <component :is="tone.icon" class="size-3.5" aria-hidden="true" />
    <template v-if="missed">{{ __("Missed") }} ·</template>
    {{ __(post.status) }}
  </span>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed } from "vue";
import LucideBan from "~icons/lucide/ban";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideEye from "~icons/lucide/eye";
import LucidePencil from "~icons/lucide/pencil";
import LucideSend from "~icons/lucide/send";
import { isMissed, stageColor, type ContentPost } from "../constants";

const props = defineProps<{ post: ContentPost }>();

const missed = computed(() => isMissed(props.post));

const tone = computed(() => {
  if (missed.value)
    return { classes: "bg-danger-soft text-danger", icon: LucideCircleAlert };
  if (props.post.status === "Cancelled")
    return { classes: "bg-surface-gray-2 text-ink-gray-6", icon: LucideBan };
  if (props.post.status === "Published")
    return { classes: "bg-success-soft text-success", icon: LucideSend };
  switch (stageColor(props.post.status)) {
    case "violet":
      return {
        classes: "bg-brand-soft text-brand-ink",
        icon: LucideCircleCheck,
      };
    case "amber":
      return { classes: "bg-warning-soft text-warning", icon: LucideEye };
    default:
      return {
        classes: "bg-info-soft text-info",
        icon: props.post.status === "Idea" ? LucideClock : LucidePencil,
      };
  }
});
</script>
