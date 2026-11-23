<template>
  <!-- who needs a word first: the person furthest behind, the targets they are behind on,
       and what they have already reached -->
  <section
    class="flex min-w-0 flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4 md:p-5"
    :aria-labelledby="heading"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h2 :id="heading" class="text-base font-semibold text-ink-gray-9">
        {{ __("Behind pace") }}
      </h2>
      <TaskyBadge
        v-if="focus"
        tone="warning"
        class="tabular-nums"
        :label="
          __(
            '{0} · {1} shown',
            focus.row.person.full_name,
            String(focus.behind.length)
          )
        "
      />
    </div>

    <TaskyState
      v-if="!focus"
      class="py-6"
      :icon="LucideCircleCheck"
      :title="__('No one is behind pace')"
      :message="
        counted
          ? __(
              'Everyone counted so far is on pace or has reached their targets.'
            )
          : __('Who is behind shows here once progress is counted.')
      "
    />
    <template v-else>
      <ul class="flex flex-col gap-2">
        <li
          v-for="item in focus.behind"
          :key="item.name"
          class="flex items-center gap-3 rounded-lg bg-warning-soft px-3 py-2.5"
        >
          <span
            class="grid size-8 shrink-0 place-items-center rounded-full bg-surface-base text-warning"
            aria-hidden="true"
          >
            <LucideTrendingDown class="size-4" />
          </span>
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-sm font-semibold text-ink-gray-9">{{
              item.name
            }}</span>
            <span class="text-xs text-ink-gray-7 tabular-nums">{{
              item.line
            }}</span>
          </span>
          <span
            class="shrink-0 text-right text-xs font-semibold text-warning tabular-nums"
            >{{ item.standingText }}</span
          >
        </li>
      </ul>
      <p
        v-if="focus.reached.length"
        class="flex items-start gap-2 rounded-lg bg-success-soft px-3 py-2.5 text-xs text-ink-gray-8"
      >
        <LucideCircleCheck
          class="mt-px size-3.5 shrink-0 text-success"
          aria-hidden="true"
        />
        <span>
          <strong class="font-semibold">{{ __("Already reached:") }}</strong>
          {{ focus.reached.join(", ") }}
        </span>
      </p>
      <button
        type="button"
        class="flex items-center gap-1 self-start rounded text-sm font-medium text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        @click="emit('open', focus.row.person.user)"
      >
        {{ __("Open {0}'s targets", focus.row.person.full_name) }}
        <LucideArrowRight class="size-4" aria-hidden="true" />
      </button>
    </template>
  </section>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { computed, useId } from "vue";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideTrendingDown from "~icons/lucide/trending-down";
import {
  figureText,
  progressOf,
  targetText,
  type TeamRow,
} from "./salesTargets";

const props = defineProps<{ rows: TeamRow[]; currency: string }>();
const emit = defineEmits<{ open: [user: string] }>();
const heading = useId();

const SHOWN = 3;
const counted = computed(() => props.rows.some((r) => r.overall));

/** The person behind on the most targets (then the lowest month overall). */
const focus = computed(() => {
  const row = props.rows
    .filter((r) => r.standing === "behind")
    .sort(
      (a, b) =>
        b.overall!.behind - a.overall!.behind ||
        (a.overall!.percent ?? 0) - (b.overall!.percent ?? 0)
    )[0];
  if (!row) return null;
  const behind = [];
  const reached = [];
  for (const criterion of row.person.target!.criteria) {
    const measured =
      criterion.measure && row.progress?.criteria?.[criterion.criterion];
    if (criterion.value_type === "Text" || !measured) continue;
    const result = progressOf(
      criterion,
      measured,
      row.progress!,
      props.currency
    );
    if (result.percent == null) continue;
    const percent = Math.round(result.percent);
    if (result.standing === "done")
      reached.push(`${criterion.criterion} (${percent}%)`);
    else if (["behind", "short", "below"].includes(result.standing))
      behind.push({
        name: criterion.criterion,
        // how far short of the pace, as a share of the target: the biggest gap first
        gap: (result.pacePercent ?? 100) - result.percent,
        line: __(
          "{0} of {1} · {2}%",
          figureText(criterion, result.achieved!, props.currency),
          targetText(criterion, props.currency),
          String(percent)
        ),
        standingText: result.standingText,
      });
  }
  behind.sort((a, b) => b.gap - a.gap);
  return { row, behind: behind.slice(0, SHOWN), reached };
});
</script>
