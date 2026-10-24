<template>
  <TaskyBadge
    tone="brand"
    :title="
      state === 'reassigned'
        ? __('Given back to you since you last opened it')
        : __('Assigned to you and not opened yet')
    "
  >
    {{ state === "reassigned" ? __("Reassigned") : __("New") }}
  </TaskyBadge>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import type { AssignmentState } from "../taskMeta";

defineProps<{
  /** Render only when set: the task was given to the viewer since they last opened it. */
  state: AssignmentState;
}>();
</script>
