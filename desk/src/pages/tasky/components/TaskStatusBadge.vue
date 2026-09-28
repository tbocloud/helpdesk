<template>
  <TaskyBadge :tone="meta.tone" :icon="meta.icon" :label="__(meta.label)" />
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed } from "vue";
import { projectStatusMeta, taskStatusMeta } from "../taskMeta";
import TaskyBadge from "./TaskyBadge.vue";

const props = withDefaults(
  defineProps<{ status?: string; kind?: "task" | "project" }>(),
  { kind: "task" }
);

const meta = computed(() =>
  props.kind === "project"
    ? projectStatusMeta(props.status)
    : taskStatusMeta(props.status)
);
</script>
