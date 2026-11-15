<template>
  <!-- stays until the work moves: own overdue, escalated and breached work, and what
       waits on this person as a reviewer, lead or head (docs/follow-ups.md) -->
  <!-- the collapsed sidebar column: the bell tile with how many items are waiting -->
  <Tooltip
    v-if="parts.length && rail"
    :text="railLabel"
    placement="right"
    :hover-delay="0"
  >
    <RouterLink
      :to="{ name: 'MyWork' }"
      class="relative mx-auto grid size-10 place-items-center rounded-[10px] transition-colors hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
      :aria-label="railLabel"
    >
      <span
        class="grid size-[26px] place-items-center rounded-[7px] bg-surface-gray-2"
        :class="urgent ? 'text-danger' : 'text-warning'"
        aria-hidden="true"
      >
        <LucideBellRing class="size-3.5" />
      </span>
      <span
        class="absolute -end-1 -top-1 min-w-4 rounded-full bg-surface-base px-1 text-center font-mono text-2xs leading-4 tabular-nums ring-1 ring-outline-gray-2"
        :class="urgent ? 'text-danger' : 'text-ink-gray-7'"
        aria-hidden="true"
      >
        {{ count > 99 ? "99+" : count }}
      </span>
    </RouterLink>
  </Tooltip>
  <!-- the menu panel's card: how much waits on this person, and the way to it -->
  <RouterLink
    v-else-if="parts.length && compact"
    :to="{ name: 'MyWork' }"
    class="flex flex-col gap-2.5 rounded-[14px] border p-4 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
    :class="
      urgent
        ? 'border-danger/25 bg-danger-soft hover:border-danger/50'
        : 'border-warning-border bg-warning-panel hover:border-warning/40'
    "
  >
    <span
      class="flex items-center gap-2 text-[12px] font-semibold"
      :class="urgent ? 'text-danger' : 'text-warning'"
    >
      <LucideBellRing class="size-4 shrink-0" aria-hidden="true" />
      {{ __("Needs your attention") }}
    </span>
    <span class="text-[13px] text-ink-gray-8">
      <strong class="text-[22px] tabular-nums text-ink-gray-9">{{
        count
      }}</strong>
      {{
        count === 1
          ? __("item is waiting on you")
          : __("items are waiting on you")
      }}
    </span>
    <span class="text-p-sm text-ink-gray-7">
      <template v-for="(part, index) in parts" :key="part.key">
        <span v-if="index" aria-hidden="true"> · </span>
        <span
          class="tabular-nums"
          :class="part.danger && 'font-medium text-danger'"
          >{{ part.label }}</span
        >
      </template>
    </span>
    <span
      class="text-[12px] font-semibold"
      :class="urgent ? 'text-danger' : 'text-warning'"
    >
      {{ __("Review now") }} <span aria-hidden="true">→</span>
    </span>
  </RouterLink>
  <RouterLink
    v-else-if="parts.length"
    :to="{ name: 'MyWork' }"
    class="flex min-w-0 items-start gap-2 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-3 text-base text-ink-gray-8 transition-colors hover:border-outline-gray-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
  >
    <LucideBellRing
      class="mt-0.5 size-4 shrink-0"
      :class="urgent ? 'text-danger' : 'text-warning'"
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
      <span class="ms-2 font-semibold text-brand-ink">
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
import { Tooltip } from "frappe-ui";
import { computed } from "vue";
import { RouterLink } from "vue-router";
import LucideBellRing from "~icons/lucide/bell-ring";
import LucideChevronRight from "~icons/lucide/chevron-right";

const props = defineProps<{
  summary?: FollowUpSummary | null;
  /** the sidebar's smaller strip */
  compact?: boolean;
  /** the collapsed sidebar rail: an icon with a count */
  rail?: boolean;
}>();

const parts = computed(() => summaryParts(props.summary));
const urgent = computed(() => parts.value.some((p) => p.danger));
const count = computed(() => props.summary?.total ?? 0);
const railLabel = computed(
  () => `${__("Follow-ups:")} ${parts.value.map((p) => p.label).join(", ")}`
);
</script>
