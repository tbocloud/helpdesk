<template>
  <!-- missed is a state on top of the stage, so both show side by side -->
  <span
    class="inline-flex shrink-0 items-stretch overflow-hidden rounded-full"
    :class="
      size === 'md'
        ? 'h-7 border border-outline-gray-2 bg-surface-base text-sm'
        : 'h-6 text-xs font-medium'
    "
  >
    <template v-if="missed">
      <span
        class="inline-flex items-center gap-1.5 bg-danger-soft font-medium text-danger"
        :class="size === 'md' ? 'px-3' : 'pl-2 pr-1.5'"
      >
        <LucideCircleAlert
          :class="size === 'md' ? 'size-[13px]' : 'size-3.5'"
          aria-hidden="true"
        />
        {{ __("Missed") }}<span class="sr-only">,</span>
      </span>
      <span
        class="w-px"
        :class="size === 'md' ? 'bg-outline-gray-2' : 'bg-surface-base'"
        aria-hidden="true"
      />
    </template>
    <span
      v-if="size === 'md'"
      class="inline-flex items-center gap-1.5 bg-surface-base px-3 text-ink-gray-8"
    >
      <component
        :is="stage.icon"
        class="size-[13px]"
        :class="stage.iconClass"
        aria-hidden="true"
      />
      {{ __(post.status) }}
    </span>
    <span
      v-else
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

// sm: tinted chip for tables; md: bordered split pill for entry cards
const props = withDefaults(
  defineProps<{ post: ContentPost; size?: "sm" | "md" }>(),
  { size: "sm" }
);

const missed = computed(() => isMissed(props.post));

const stage = computed(() => {
  const status = props.post.status;
  if (status === "Cancelled")
    return {
      classes: "bg-surface-gray-2 text-ink-gray-6",
      iconClass: "text-ink-gray-6",
      icon: LucideBan,
    };
  if (status === "Published")
    return {
      classes: "bg-success-soft text-success",
      iconClass: "text-success",
      icon: LucideSend,
    };
  // ready but not out yet, so not styled like Published
  if (status === "Scheduled")
    return {
      classes: "bg-surface-gray-2 text-ink-gray-7",
      iconClass: "text-ink-gray-7",
      icon: LucideCalendar,
    };
  if (status === "Changes Requested")
    return {
      classes: "bg-warning-soft text-warning",
      iconClass: "text-warning",
      icon: LucidePencil,
    };
  switch (stageColor(status)) {
    case "violet":
      return {
        classes: "bg-success-soft text-success",
        iconClass: "text-success",
        icon: LucideCheck,
      };
    case "amber":
      return {
        classes: "bg-warning-soft text-warning",
        iconClass: "text-warning",
        icon: LucideEye,
      };
    default:
      return {
        classes: "bg-surface-gray-2 text-ink-gray-7",
        iconClass: "text-ink-gray-7",
        icon: status === "Idea" ? LucideClock : LucidePencil,
      };
  }
});
</script>
