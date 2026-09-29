<template>
  <TaskyBadge
    :icon="ai ? LucideSparkles : LucideFileText"
    :label="kindLabel(ai)"
    :title="
      ai
        ? __('Written by AI from the week\'s figures')
        : __('Plain summary built from the week\'s figures')
    "
  />
</template>

<script setup lang="ts">
import TaskyBadge from "@/pages/tasky/components/TaskyBadge.vue";
import { __ } from "@/translation";
import LucideFileText from "~icons/lucide/file-text";
import LucideSparkles from "~icons/lucide/sparkles";
import { kindLabel } from "../summaryMeta";

defineProps<{ ai: boolean }>();
</script>
