<template>
  <!-- stays until the work moves: own overdue, escalated and breached work, and what
       waits on this person as a reviewer, lead or head (docs/follow-ups.md) -->
  <RouterLink
    v-if="parts.length"
    :to="{ name: 'MyWork' }"
    class="flex min-w-0 items-start gap-2 rounded-lg border border-outline-gray-2 bg-surface-base text-ink-gray-8 transition-colors hover:border-outline-gray-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
    :class="compact ? 'px-2.5 py-2 text-sm' : 'px-3 py-2.5 text-base'"
  >
    <LucideBellRing
      class="mt-0.5 size-4 shrink-0"
      :class="urgent ? 'text-danger' : 'text-ink-gray-5'"
      aria-hidden="true"
    />
    <span class="min-w-0 flex-1">
      <span class="sr-only">{{ __("Follow-ups:") }}</span>
      <template v-for="(part, index) in parts" :key="part.key">
        <span v-if="index" class="text-ink-gray-4" aria-hidden="true"> · </span>
        <span
          class="tabular-nums"
          :class="part.danger ? 'text-danger' : 'text-ink-gray-7'"
          >{{ part.label }}</span
        >
      </template>
      <span v-if="!compact" class="ms-2 text-ink-gray-5">
        {{ __("Open My Work") }}
      </span>
    </span>
    <LucideChevronRight
      class="mt-0.5 size-4 shrink-0 text-ink-gray-4"
      aria-hidden="true"
    />
  </RouterLink>
</template>

<script setup lang="ts">
import { summaryParts, type FollowUpSummary } from "@/components/followUps";
import { __ } from "@/translation";
import { computed } from "vue";
import { RouterLink } from "vue-router";
import LucideBellRing from "~icons/lucide/bell-ring";
import LucideChevronRight from "~icons/lucide/chevron-right";

const props = defineProps<{
  summary?: FollowUpSummary | null;
  /** the sidebar's smaller strip */
  compact?: boolean;
}>();

const parts = computed(() => summaryParts(props.summary));
const urgent = computed(() => parts.value.some((p) => p.danger));
</script>
