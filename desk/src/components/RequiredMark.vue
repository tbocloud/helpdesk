<template>
  <!-- the mark frappe-ui puts on a required label, without making the browser require the
       field: a task needs a due date or an estimate, so either one is enough -->
  <span class="select-none text-danger" aria-hidden="true">*</span>
  <span class="sr-only">{{ hint || __("(required)") }}</span>
</template>

<script setup lang="ts">
import { __ } from "@/translation";

defineProps<{
  /** what screen readers hear instead of "(required)" */
  hint?: string;
}>();
</script>
