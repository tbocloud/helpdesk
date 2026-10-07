<template>
  <template v-if="item.kind === 'task'">
    <Button
      v-if="primary"
      size="sm"
      :label="primary.label"
      :icon-left="primary.icon"
      :loading="busy"
      :aria-label="`${primary.label}: ${item.title}`"
      @click="emit('step', primary.event, item)"
    />
    <Dropdown :options="menu" align="end">
      <Button
        size="sm"
        variant="ghost"
        :aria-label="__('More actions for {0}', item.title)"
      >
        <template #icon>
          <LucideEllipsis class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </Dropdown>
  </template>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, Dropdown } from "frappe-ui";
import { computed, type Component } from "vue";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCheck from "~icons/lucide/check";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucidePanelRight from "~icons/lucide/panel-right";
import LucidePause from "~icons/lucide/pause";
import LucidePlay from "~icons/lucide/play";
import type { WorkItem } from "../workMeta";

export type WorkStep =
  | "start"
  | "complete"
  | "hold"
  | "resume"
  | "plan"
  | "approve"
  | "details";

const props = defineProps<{
  item: WorkItem;
  /** The viewer is the assignee; otherwise only a lead's steps are offered. */
  mine: boolean;
  /** A step on this item is in flight. */
  busy?: boolean;
}>();

const emit = defineEmits<{
  step: [step: WorkStep, item: WorkItem];
}>();

interface Step {
  label: string;
  icon: Component;
  event: WorkStep;
}

const status = computed(() => props.item.status);
const blocked = computed(() => !!props.item.waiting_on);
// the server refuses to start or finish a task while its dependency is open
const canStart = computed(
  () => props.mine && status.value === "Open" && !blocked.value
);
const canComplete = computed(
  () =>
    props.mine &&
    ["Open", "Working", "Overdue"].includes(status.value) &&
    !blocked.value
);

/** The one next step: sign it off, start it, finish it, or pick it back up. */
const primary = computed<Step | null>(() => {
  if (status.value === "Pending Review")
    return props.item.can_approve
      ? { label: __("Approve"), icon: LucideCheck, event: "approve" }
      : null;
  if (canStart.value)
    return { label: __("Start"), icon: LucidePlay, event: "start" };
  if (canComplete.value)
    return {
      label: __("Complete"),
      icon: LucideCircleCheck,
      event: "complete",
    };
  if (props.mine && status.value === "On Hold")
    return { label: __("Resume"), icon: LucidePlay, event: "resume" };
  return null;
});

const menu = computed(() => {
  const steps: Step[] = [
    { label: __("Details"), icon: LucidePanelRight, event: "details" },
  ];
  // Complete stays reachable when Start is the button
  if (canComplete.value && primary.value?.event !== "complete")
    steps.push({
      label: __("Complete"),
      icon: LucideCircleCheck,
      event: "complete",
    });
  if (props.mine && ["Open", "Working", "Overdue"].includes(status.value))
    steps.push({ label: __("Put on hold"), icon: LucidePause, event: "hold" });
  if (props.item.can_plan)
    steps.push({ label: __("Plan"), icon: LucideCalendarClock, event: "plan" });
  return steps.map((s) => ({
    label: s.label,
    icon: s.icon,
    onClick: () => emit("step", s.event, props.item),
  }));
});
</script>
