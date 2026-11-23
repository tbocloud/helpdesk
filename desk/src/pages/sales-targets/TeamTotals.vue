<template>
  <!-- each counted target added up across the team: what was achieved of the team's total,
       with today's pace ticked -->
  <section
    class="flex min-w-0 flex-col gap-4 rounded-xl border border-outline-gray-2 bg-surface-base p-4 md:p-5"
    :aria-labelledby="heading"
  >
    <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
      <h2 :id="heading" class="text-base font-semibold text-ink-gray-9">
        {{ __("Team totals by target") }}
      </h2>
      <p v-if="totals.length" class="text-xs text-ink-gray-6 tabular-nums">
        {{
          from === 1
            ? __("Counted so far from 1 person")
            : __("Counted so far from {0} people", String(from))
        }}<template v-if="pace.state === 'running'">
          · {{ __("tick = today's pace") }}</template
        >
      </p>
    </div>

    <p v-if="!totals.length" class="py-6 text-center text-sm text-ink-gray-6">
      {{ __("Nothing counted yet. Totals add up once progress is counted.") }}
    </p>
    <ul v-else class="flex flex-col gap-3.5">
      <li
        v-for="total in totals"
        :key="total.name"
        class="grid grid-cols-[minmax(0,8.5rem)_minmax(0,1fr)_auto] items-center gap-4"
      >
        <span
          class="truncate text-sm font-medium text-ink-gray-8"
          :title="total.name"
          >{{ total.name }}</span
        >
        <span
          class="relative h-2.5 rounded-full bg-surface-gray-2"
          role="meter"
          :aria-valuenow="Math.round(total.percent)"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-label="__('{0}: {1}', total.name, total.standingText)"
        >
          <span
            class="block h-full rounded-full"
            :class="STANDING_LOOK[total.standing].fill"
            :style="{ width: `${Math.min(total.percent, 100)}%` }"
          />
          <span
            v-if="pace.state === 'running'"
            class="absolute -top-1 h-[18px] w-0.5 rounded-full bg-surface-gray-9"
            :style="{ left: `calc(${pace.percent}% - 1px)` }"
            aria-hidden="true"
          />
        </span>
        <span class="text-right text-sm text-ink-gray-6 tabular-nums">
          <strong class="font-semibold text-ink-gray-9">{{
            total.achieved
          }}</strong>
          / {{ total.target }}
        </span>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed, useId } from "vue";
import {
  figureText,
  STANDING_LOOK,
  type Criterion,
  type monthPace,
  type Standing,
  type TeamRow,
} from "./salesTargets";

const props = defineProps<{
  rows: TeamRow[];
  columns: Criterion[];
  currency: string;
  pace: ReturnType<typeof monthPace>;
}>();
const heading = useId();

/** Sums and counts add up; a rate (Percent) doesn't, so it is left out. */
const summed = computed(() => {
  const counters = new Set<string>();
  const list = props.columns
    .filter((c) => c.measure && ["Amount", "Number"].includes(c.value_type))
    .flatMap((column) => {
      const name = column.criterion.toLowerCase();
      let achieved = 0;
      let target = 0;
      let counted = false;
      for (const row of props.rows) {
        if (row.progress?.state !== "counted") continue;
        const criterion = row.person.target?.criteria.find(
          (c) => c.criterion.toLowerCase() === name
        );
        const measured =
          criterion && row.progress.criteria?.[criterion.criterion];
        if (!criterion || measured?.achieved == null) continue;
        achieved += measured.achieved;
        target += Number(criterion.target) || 0;
        counted = true;
        counters.add(row.person.user);
      }
      if (!counted) return [];
      const percent = target > 0 ? (achieved / target) * 100 : 100;
      const standing: Standing =
        percent >= 100
          ? "done"
          : props.pace.state === "over"
          ? "short"
          : percent >= props.pace.percent
          ? "on_pace"
          : "behind";
      return [
        {
          name: column.criterion,
          achieved: figureText(column, achieved, props.currency),
          target: figureText(column, target, props.currency),
          percent,
          standing,
          standingText:
            standing === "done"
              ? __("reached")
              : standing === "on_pace"
              ? __("on pace")
              : __("behind pace"),
        },
      ];
    });
  return { list, from: counters.size };
});
const totals = computed(() => summed.value.list);
const from = computed(() => summed.value.from);
</script>
