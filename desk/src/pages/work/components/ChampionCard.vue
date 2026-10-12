<template>
  <!-- the one gold card: an award, so it gets the champion tone (theme.css) -->
  <section
    class="relative flex min-w-0 flex-col gap-4 rounded-xl border border-champion-border bg-champion-soft p-5"
    :aria-labelledby="headingId"
  >
    <h2
      :id="headingId"
      class="flex min-w-0 items-center gap-1.5 pe-14 text-sm text-ink-gray-7"
    >
      <LucideTrophy class="size-4 shrink-0 text-champion" aria-hidden="true" />
      <span class="truncate">
        <span class="font-semibold text-champion">{{ title }}</span>
        <template v-if="period"> · {{ period }}</template>
      </span>
    </h2>

    <!-- the badge: a rosette, shown once someone has earned it -->
    <span
      v-if="champion && !loading"
      class="absolute end-4 top-4 grid size-12 place-items-center rounded-full border border-champion-border bg-surface-base text-champion"
      aria-hidden="true"
    >
      <LucideAward class="size-6" />
    </span>

    <div v-if="loading" class="flex items-center gap-3" aria-busy="true">
      <div class="size-14 animate-pulse rounded-full bg-surface-gray-2" />
      <div class="flex flex-1 flex-col gap-2">
        <div class="h-4 w-1/3 animate-pulse rounded bg-surface-gray-2" />
        <div class="h-3 w-2/3 animate-pulse rounded bg-surface-gray-2" />
      </div>
    </div>

    <p v-else-if="!champion" class="text-p-sm text-ink-gray-7">
      {{
        __(
          "No champion yet. Someone becomes champion once they've finished enough work in the period."
        )
      }}
    </p>

    <template v-else>
      <div class="flex min-w-0 items-center gap-4 pe-14">
        <Avatar
          :label="champion.name"
          :image="champion.image || undefined"
          size="3xl"
          class="size-14"
        />
        <div class="min-w-0 flex-1">
          <div class="truncate text-2xl font-semibold text-ink-gray-9">
            {{ champion.name }}
          </div>
          <div class="text-base text-ink-gray-7">
            {{ __("Score") }}
            <span class="font-mono font-semibold tabular-nums text-ink-gray-9">
              {{ champion.score }}
            </span>
          </div>
        </div>
      </div>

      <ul class="flex flex-col gap-2" :aria-label="__('Why')">
        <li
          v-for="reason in champion.reasons"
          :key="reason"
          class="flex items-start gap-2 text-p-base text-ink-gray-8"
        >
          <LucideCheck
            class="mt-0.5 size-4 shrink-0 text-success"
            aria-hidden="true"
          />
          <span class="min-w-0">{{ reason }}</span>
        </li>
      </ul>

      <details v-if="champion.breakdown.length" class="group">
        <summary
          class="inline-flex cursor-pointer list-none items-center [&::-webkit-details-marker]:hidden gap-1.5 rounded text-p-sm text-ink-gray-7 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          <LucideChevronRight
            class="size-4 transition-transform group-open:rotate-90 motion-reduce:transition-none"
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
import LucideTrophy from "~icons/lucide/trophy";
import type { Champion } from "../teamDashboardMeta";
import ScoreBreakdown from "./ScoreBreakdown.vue";

defineProps<{
  /** "Champion" or "ERP champion" */
  title: string;
  /** "This week" */
  period?: string;
  champion: Champion | null;
  loading?: boolean;
}>();

const headingId = `champion-${useId()}`;
</script>
