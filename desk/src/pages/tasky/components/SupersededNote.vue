<template>
  <p
    v-if="
      item.status === 'Superseded' && (item.superseded_by || item.status_note)
    "
    class="flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-ink-gray-6"
    :title="changedBy"
  >
    <template v-if="item.superseded_by">
      <span>{{ __("Replaced by") }}</span>
      <RouterLink
        :to="to"
        class="min-w-0 max-w-full truncate rounded font-medium text-ink-gray-8 underline decoration-outline-gray-3 underline-offset-2 hover:decoration-ink-gray-6 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
      >
        {{ item.superseded_by.label }}
      </RouterLink>
    </template>
    <span v-if="item.superseded_by && item.status_note" aria-hidden="true"
      >·</span
    >
    <span v-if="item.status_note" class="min-w-0 max-w-full break-words">
      {{ item.status_note }}
    </span>
  </p>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { timeAgo } from "@/utils";
import { computed } from "vue";
import { RouterLink, type RouteLocationRaw } from "vue-router";
import type { ProjectFile, ProjectFolder } from "../projectFiles";

/** What replaced a superseded file or folder, and the note left with it. */
const props = defineProps<{
  item: ProjectFile | ProjectFolder;
  /** Where the replacement is. */
  to: RouteLocationRaw;
}>();

const changedBy = computed(() =>
  props.item.status_changed_by_name && props.item.status_changed_on
    ? __(
        "Marked superseded by {0}, {1}",
        props.item.status_changed_by_name,
        timeAgo(props.item.status_changed_on)
      )
    : undefined
);
</script>
