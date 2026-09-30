<template>
  <section v-if="rows.length" :aria-labelledby="headingId">
    <h3 :id="headingId" class="mb-1.5 text-xs text-ink-gray-5">
      {{ __("Pull requests") }}
    </h3>
    <ul
      class="divide-y divide-outline-gray-1 rounded-md border border-outline-gray-2"
    >
      <li
        v-for="row in rows"
        :key="row.key"
        class="flex flex-col gap-1.5 px-3 py-2 sm:flex-row sm:items-center sm:gap-3"
      >
        <a
          :href="row.pr.url"
          target="_blank"
          rel="noopener noreferrer"
          class="flex min-w-0 flex-1 items-center gap-2 rounded text-sm text-ink-gray-8 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          :title="row.pr.title"
        >
          <component
            :is="row.state.icon"
            class="size-4 shrink-0 text-ink-gray-6"
            aria-hidden="true"
          />
          <span class="shrink-0 font-mono text-xs tabular-nums text-ink-gray-6">
            {{ row.ref }}
          </span>
          <span class="truncate">{{ row.pr.title }}</span>
          <LucideExternalLink
            class="size-3.5 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
          <span class="sr-only">{{ __("(opens GitHub in a new tab)") }}</span>
        </a>
        <div class="flex shrink-0 flex-wrap items-center gap-1.5">
          <TaskyBadge :tone="row.state.tone" :label="__(row.state.label)" />
          <TaskyBadge
            v-for="chip in row.chips"
            :key="chip.label"
            :tone="chip.tone"
            :icon="chip.icon"
            :label="__(chip.label)"
          />
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed, useId } from "vue";
import LucideExternalLink from "~icons/lucide/external-link";
import {
  prCiMeta,
  prRef,
  prReviewMeta,
  prStateMeta,
  type TaskPullRequest,
} from "../pullRequestMeta";
import type { StatusMeta } from "../taskMeta";
import TaskyBadge from "./TaskyBadge.vue";

const props = withDefaults(
  defineProps<{
    /** Linked GitHub PRs, newest activity first; nothing renders when empty. */
    pullRequests?: TaskPullRequest[];
  }>(),
  { pullRequests: () => [] }
);

const headingId = `task-prs-${useId()}`;

// review and CI chips only when GitHub has said something about them
const rows = computed(() =>
  props.pullRequests.map((pr) => ({
    key: `${pr.repo}#${pr.number}`,
    pr,
    ref: prRef(pr),
    state: prStateMeta(pr.state),
    chips: [prReviewMeta(pr.review_state), prCiMeta(pr.ci_state)].filter(
      (meta): meta is StatusMeta => !!meta
    ),
  }))
);
</script>
