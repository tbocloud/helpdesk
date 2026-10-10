<template>
  <!-- missed is a state on top of the stage, so both show side by side -->
  <span
    class="inline-flex h-6 shrink-0 items-stretch overflow-hidden rounded-full text-xs font-medium"
  >
    <template v-if="missed">
      <span
        class="inline-flex items-center gap-1.5 bg-danger-soft pl-2 pr-1.5 text-danger"
      >
        <LucideCircleAlert class="size-3.5" aria-hidden="true" />
        {{ __("Missed") }}<span class="sr-only">,</span>
      </span>
      <span class="w-px bg-surface-base" aria-hidden="true" />
    </template>
    <span
      class="inline-flex items-center gap-1 pr-2"
      :class="[stage.classes, missed ? 'pl-1.5' : 'pl-2']"
    >
      <component :is="stage.icon" class="size-3.5" aria-hidden="true" />
      {{ __(post.status) }}
    </span>
  </span>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed } from "vue";
import LucideBan from "~icons/lucide/ban";
import LucideCalendar from "~icons/lucide/calendar";
import LucideCheck from "~icons/lucide/check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideClock from "~icons/lucide/clock";
import LucideEye from "~icons/lucide/eye";
import LucidePencil from "~icons/lucide/pencil";
import LucideSend from "~icons/lucide/send";
import { isMissed, stageColor, type ContentPost } from "../constants";

const props = defineProps<{ post: ContentPost }>();

const missed = computed(() => isMissed(props.post));

const stage = computed(() => {
  const status = props.post.status;
  if (status === "Cancelled")
    return {
      classes: "bg-surface-gray-2 text-ink-gray-6",
      icon: LucideBan,
    };
  if (status === "Published")
    return {
      classes: "bg-success-soft text-success",
      icon: LucideSend,
    };
  // ready but not out yet, so not styled like Published
  if (status === "Scheduled")
    return {
      classes: "bg-surface-gray-2 text-ink-gray-7",
      icon: LucideCalendar,
    };
  if (status === "Changes Requested")
    return {
      classes: "bg-warning-soft text-warning",
      icon: LucidePencil,
    };
  switch (stageColor(status)) {
    case "violet":
      return {
        classes: "bg-success-soft text-success",
        icon: LucideCheck,
      };
    case "amber":
      return {
        classes: "bg-warning-soft text-warning",
        icon: LucideEye,
      };
    default:
      return {
        classes: "bg-surface-gray-2 text-ink-gray-7",
        icon: status === "Idea" ? LucideClock : LucidePencil,
      };
  }
});
</script>
