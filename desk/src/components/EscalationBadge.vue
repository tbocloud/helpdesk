<template>
  <!-- how far up the follow-up ladder overdue work has gone (docs/follow-ups.md) -->
  <TaskyBadge
    v-if="label"
    :tone="level >= 2 ? 'danger' : 'warning'"
    :icon="LucideChevronsUp"
    :title="label"
  >
    {{ label }}
  </TaskyBadge>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { escalationLabel } from "@/components/followUps";
import { computed } from "vue";
import LucideChevronsUp from "~icons/lucide/chevrons-up";

const props = defineProps<{
  /** 1 the lead, 2 the department head, 3 the managers; nothing below 1 */
  level?: number | null;
}>();

const level = computed(() => props.level || 0);
const label = computed(() => escalationLabel(level.value));
</script>
