<template>
  <!-- the top three on a podium: first in the middle and tallest, second left, third right -->
  <section
    class="flex min-w-0 flex-col gap-6 rounded-xl bg-hero p-5 text-hero-ink md:p-7"
    :aria-labelledby="headingId"
  >
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="flex min-w-0 flex-col gap-1">
        <p class="flex items-center gap-1.5 text-sm text-hero-muted">
          <LucideTrophy class="size-3.5 text-hero-pace" aria-hidden="true" />
          {{ __("Scoreboard") }} · {{ monthTitle(month) }}
        </p>
        <h2
          :id="headingId"
          class="text-xl font-bold tracking-[-0.01em] sm:text-2xl"
        >
          {{ __("Top of the team") }}
        </h2>
      </div>
      <div class="flex flex-wrap gap-2">
        <span
          v-if="pace.state === 'running'"
          class="rounded-full bg-hero-track px-3 py-1 text-xs text-hero-muted"
        >
          {{ __("Today's pace") }}
          <span class="ms-1 font-semibold text-hero-ink tabular-nums"
            >{{ pace.percent }}%</span
          >
        </span>
        <span
          v-if="average != null"
          class="rounded-full bg-hero-track px-3 py-1 text-xs text-hero-muted"
        >
          {{ __("Board average") }}
          <span class="ms-1 font-semibold text-hero-ink tabular-nums"
            >{{ average }}%</span
          >
        </span>
      </div>
    </div>

    <ol class="grid grid-cols-3 items-end gap-2 sm:gap-3">
      <li
        v-for="spot in spots"
        :key="spot.place"
        class="min-w-0"
        :style="{ order: spot.order }"
      >
        <button
          v-if="spot.entry"
          type="button"
          class="group flex w-full min-w-0 flex-col items-center gap-2 rounded-t-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          :aria-label="
            __(
              '{0}: {1}, {2}% reached',
              ordinal(spot.entry.rank),
              spot.entry.row.person.full_name,
              String(spot.entry.overall.percent)
            )
          "
          @click="emit('open', spot.entry.row.person.user)"
        >
          <span class="flex flex-col items-center" aria-hidden="true">
            <LucideCrown
              v-if="spot.place === 1"
              class="mb-1 size-6 fill-hero-pace text-hero-pace"
            />
            <PersonAvatar
              :name="spot.entry.row.person.full_name"
              size="xl"
              class="ring-4"
              :class="spot.place === 1 ? 'ring-hero-pace' : 'ring-hero-track'"
            />
          </span>
          <span
            class="w-full truncate px-1 text-center text-sm font-semibold"
            aria-hidden="true"
            >{{ spot.entry.row.person.full_name }}</span
          >
          <span
            class="flex w-full flex-col items-center justify-start rounded-t-xl px-2 pt-4 transition-opacity group-hover:opacity-90"
            :class="[
              spot.height,
              spot.place === 1 ? 'bg-hero-fill text-hero' : 'bg-hero-track',
            ]"
            aria-hidden="true"
          >
            <span
              class="text-2xl font-bold leading-none tabular-nums sm:text-[32px]"
              >{{ spot.entry.overall.percent }}%</span
            >
            <span
              class="mt-1.5 text-xs tabular-nums"
              :class="spot.place === 1 ? 'text-hero' : 'text-hero-muted'"
              >{{ ordinal(spot.entry.rank) }} ·
              {{
                __(
                  "{0} of {1}",
                  String(spot.entry.overall.reached),
                  String(spot.entry.overall.counted)
                )
              }}</span
            >
          </span>
        </button>
        <span
          v-else
          class="block rounded-t-xl border border-dashed border-hero-track"
          :class="spot.height"
          aria-hidden="true"
        />
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import PersonAvatar from "@/components/PersonAvatar.vue";
import { __ } from "@/translation";
import { computed, useId } from "vue";
import LucideCrown from "~icons/lucide/crown";
import LucideTrophy from "~icons/lucide/trophy";
import { monthPace, monthTitle, ordinal, type RankedRow } from "./salesTargets";

const props = defineProps<{
  /** everyone ranked, first first; the podium takes the top three */
  ranked: RankedRow[];
  month: string;
  pace: ReturnType<typeof monthPace>;
  /** the board's average overall */
  average: number | null;
}>();
const emit = defineEmits<{ open: [user: string] }>();

const headingId = useId();

// in reading order first is in the middle; an empty place stays as an outline
const spots = computed(() =>
  [
    { place: 1, order: 2, height: "h-36 sm:h-40" },
    { place: 2, order: 1, height: "h-28 sm:h-32" },
    { place: 3, order: 3, height: "h-24 sm:h-24" },
  ].map((spot) => ({ ...spot, entry: props.ranked[spot.place - 1] ?? null }))
);
</script>
