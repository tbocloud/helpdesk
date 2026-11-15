<template>
  <div v-if="people.length" class="flex flex-wrap items-center gap-1 pt-0.5">
    <span class="text-xs text-ink-gray-5">{{ __("For:") }}</span>
    <span
      v-for="person in people"
      :key="person.user"
      class="inline-flex items-center gap-1.5 rounded-full bg-surface-gray-2 py-0.5 pl-0.5 pr-2 text-xs text-ink-gray-7"
    >
      <PersonAvatar :name="person.full_name" size="xs" />
      {{ person.full_name }}
    </span>
  </div>
</template>

<script setup lang="ts">
import PersonAvatar from "@/components/PersonAvatar.vue";
import { __ } from "@/translation";
import type { Person } from "../projectFiles";

/** The "For:" list of a project file or folder. */
defineProps<{ people: Person[] }>();
</script>
