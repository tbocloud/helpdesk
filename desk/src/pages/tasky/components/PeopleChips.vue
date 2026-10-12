<template>
  <div v-if="people.length" class="flex flex-wrap items-center gap-1 pt-0.5">
    <span class="text-xs text-ink-gray-5">{{ __("For:") }}</span>
    <span
      v-for="person in people"
      :key="person.user"
      class="rounded bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-7"
    >
      {{ person.full_name }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import type { Person } from "../projectFiles";

/** The "For:" list of a project file or folder. */
defineProps<{ people: Person[] }>();
</script>
