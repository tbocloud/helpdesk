<template>
  <!-- the one gold card: whoever leads the board, an award rather than a status -->
  <section
    class="flex min-w-0 flex-col gap-5 rounded-xl border border-champion-border bg-champion-soft p-5"
    :aria-labelledby="headingId"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h2
        :id="headingId"
        class="flex items-center gap-1.5 text-sm font-semibold text-champion"
      >
        <LucideTrophy class="size-4 shrink-0" aria-hidden="true" />
        {{
          pace.state === "over"
            ? __("Champion of {0}", monthTitle(month))
            : __("Leading this month")
        }}
      </h2>
      <span
        v-if="status === 'ahead'"
        class="rounded-full bg-success-soft px-2.5 py-0.5 text-xs font-medium text-success"
        >{{ __("Ahead of pace") }}</span
      >
    </div>

    <div class="flex min-w-0 items-center gap-4">
      <div
        class="relative size-[5.5rem] shrink-0"
        role="img"
        :aria-label="__('{0}% reached', String(leader.overall.percent))"
      >
        <svg
          viewBox="0 0 88 88"
          class="size-full -rotate-90"
          aria-hidden="true"
        >
          <circle
            cx="44"
            cy="44"
            r="38"
            fill="none"
            stroke-width="8"
            class="stroke-champion-border"
          />
          <circle
            cx="44"
            cy="44"
            r="38"
            fill="none"
            stroke-width="8"
            stroke-linecap="round"
            pathLength="100"
            :stroke-dasharray="`${leader.overall.percent} 100`"
            class="stroke-success"
          />
        </svg>
        <span
          class="absolute inset-0 flex flex-col items-center justify-center"
          aria-hidden="true"
        >
          <span
            class="text-xl font-bold leading-none text-ink-gray-9 tabular-nums"
            >{{ leader.overall.percent }}%</span
          >
          <span class="text-[10px] text-ink-gray-6">{{ __("reached") }}</span>
        </span>
      </div>
      <div class="flex min-w-0 flex-col gap-1">
        <p class="truncate text-xl font-semibold text-ink-gray-9">
          {{ leader.row.person.full_name }}
        </p>
        <p class="text-p-sm text-ink-gray-7 tabular-nums">{{ paceLine }}</p>
      </div>
    </div>

    <ul class="flex flex-col gap-2.5" :aria-label="__('Why')">
      <li
        v-for="reason in reasons"
        :key="reason"
        class="flex items-center gap-2.5 text-p-sm text-ink-gray-8"
      >
        <span
          class="grid size-5 shrink-0 place-items-center rounded-full bg-success-soft text-success"
          aria-hidden="true"
        >
          <LucideCheck class="size-3" />
        </span>
        {{ reason }}
      </li>
    </ul>

    <button
      type="button"
      class="mt-auto flex items-center gap-1 self-start rounded text-sm font-semibold text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
      @click="emit('open', leader.row.person.user)"
    >
      {{ __("See {0}'s targets", firstName(leader.row.person.full_name)) }}
      <LucideArrowRight class="size-4" aria-hidden="true" />
    </button>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed, useId } from "vue";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideCheck from "~icons/lucide/check";
import LucideTrophy from "~icons/lucide/trophy";
import {
  monthPace,
  monthTitle,
  paceStatus,
  type RankedRow,
} from "./salesTargets";

const props = defineProps<{
  leader: RankedRow;
  /** others level with the leader on both counts */
  tied: string[];
  month: string;
  pace: ReturnType<typeof monthPace>;
}>();
const emit = defineEmits<{ open: [user: string] }>();

const headingId = useId();
const firstName = (name: string) => name.split(" ")[0];
const status = computed(() => paceStatus(props.leader.overall, props.pace));

const paceLine = computed(() => {
  const { percent } = props.leader.overall;
  if (props.pace.state !== "running")
    return __("Ended {0} at {1}%", monthTitle(props.month), String(percent));
  const gap = percent - props.pace.percent;
  const today = String(props.pace.percent);
  if (gap > 0)
    return __("{0} points ahead of today's {1}% pace", String(gap), today);
  if (gap < 0)
    return __("{0} points behind today's {1}% pace", String(-gap), today);
  return __("Right on today's {0}% pace", today);
});

const reasons = computed(() => {
  const { overall } = props.leader;
  const out = [
    __(
      "{0} of {1} targets reached",
      String(overall.reached),
      String(overall.counted)
    ),
  ];
  if (status.value === "ahead")
    out.push(__("Ahead of today's pace of {0}%", String(props.pace.percent)));
  if (!overall.behind) out.push(__("No target behind pace"));
  if (props.tied.length) out.push(__("Level with {0}", props.tied.join(", ")));
  return out;
});
</script>
