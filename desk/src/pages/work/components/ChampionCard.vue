<template>
  <section
    class="flex min-w-0 flex-col gap-3 rounded-lg border border-outline-gray-2 bg-surface-base p-4"
    :aria-labelledby="headingId"
  >
    <h2
      :id="headingId"
      class="flex items-center gap-1.5 text-sm text-ink-gray-6"
    >
      <LucideAward class="size-4 shrink-0 text-brand" aria-hidden="true" />
      <span class="truncate">{{ title }}</span>
    </h2>

    <div v-if="loading" class="flex items-center gap-3" aria-busy="true">
      <div class="size-10 animate-pulse rounded-full bg-surface-gray-2" />
      <div class="flex flex-1 flex-col gap-2">
        <div class="h-4 w-1/3 animate-pulse rounded bg-surface-gray-2" />
        <div class="h-3 w-2/3 animate-pulse rounded bg-surface-gray-2" />
      </div>
    </div>

    <p v-else-if="!champion" class="text-p-sm text-ink-gray-6">
      {{
        __(
          "No champion yet. Someone becomes champion once they've finished enough work in the period."
        )
      }}
    </p>

    <template v-else>
      <div class="flex items-center gap-3">
        <Avatar
          :label="champion.name"
          :image="champion.image || undefined"
          size="xl"
        />
        <div class="min-w-0 flex-1">
          <div class="truncate text-lg-medium text-ink-gray-9">
            {{ champion.name }}
          </div>
          <div class="text-p-sm text-ink-gray-6">
            {{ __("Score") }}
            <span class="font-mono tabular-nums text-ink-gray-8">{{
              champion.score
            }}</span>
          </div>
        </div>
      </div>

      <ul class="flex flex-col gap-1.5" :aria-label="__('Why')">
        <li
          v-for="reason in champion.reasons"
          :key="reason"
          class="flex items-start gap-2 text-p-sm text-ink-gray-8"
        >
          <LucideCheck
            class="mt-0.5 size-3.5 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
          <span class="min-w-0">{{ reason }}</span>
        </li>
      </ul>

      <details v-if="champion.breakdown.length" class="group">
        <summary
          class="inline-flex cursor-pointer list-none items-center [&::-webkit-details-marker]:hidden gap-1 rounded text-p-sm text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          <LucideChevronRight
            class="size-3.5 transition-transform group-open:rotate-90 motion-reduce:transition-none"
            aria-hidden="true"
          />
          {{ __("How the score adds up") }}
        </summary>
        <ScoreBreakdown
          class="mt-2"
          :parts="champion.breakdown"
          :score="champion.score"
        />
      </details>
    </template>
  </section>
</template>

<script setup lang="ts">
import { Avatar } from "frappe-ui";
import { useId } from "vue";
import LucideAward from "~icons/lucide/award";
import LucideCheck from "~icons/lucide/check";
import LucideChevronRight from "~icons/lucide/chevron-right";
import type { Champion } from "../teamDashboardMeta";
import ScoreBreakdown from "./ScoreBreakdown.vue";

defineProps<{
  title: string;
  champion: Champion | null;
  loading?: boolean;
}>();

const headingId = `champion-${useId()}`;
</script>
