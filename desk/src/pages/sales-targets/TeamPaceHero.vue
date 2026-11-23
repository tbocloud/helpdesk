<template>
  <!-- the team's month at a glance: the average reached on a gauge with today's pace ticked,
       what the pace means in words, and where each person stands -->
  <section
    class="flex flex-col gap-6 rounded-xl bg-hero p-5 text-hero-ink sm:flex-row sm:items-center md:p-7"
    :aria-labelledby="headingId"
  >
    <div
      class="relative mx-auto size-40 shrink-0 sm:mx-0"
      role="img"
      :aria-label="gaugeLabel"
    >
      <svg viewBox="0 0 120 120" class="size-full" aria-hidden="true">
        <path
          :d="ARC"
          fill="none"
          stroke-width="11"
          stroke-linecap="round"
          class="stroke-hero-track"
        />
        <path
          v-if="average"
          :d="ARC"
          fill="none"
          stroke-width="11"
          stroke-linecap="round"
          pathLength="100"
          :stroke-dasharray="`${Math.min(average, 100)} 100`"
          class="stroke-hero-fill"
        />
        <line
          v-if="pace.state === 'running'"
          v-bind="tick"
          stroke-width="3.5"
          stroke-linecap="round"
          class="stroke-hero-pace"
        />
      </svg>
      <span
        class="absolute inset-0 flex flex-col items-center justify-center pt-1"
      >
        <span class="text-[34px] font-bold leading-none tabular-nums">{{
          average == null ? "—" : `${average}%`
        }}</span>
        <span class="mt-1 text-xs text-hero-muted">{{
          __("team average")
        }}</span>
      </span>
    </div>

    <div class="flex min-w-0 flex-1 flex-col gap-3">
      <p class="text-sm text-hero-muted tabular-nums">{{ period }}</p>
      <h2
        :id="headingId"
        class="text-xl font-bold leading-snug tracking-[-0.01em] sm:text-2xl"
      >
        {{ headline }}
      </h2>
      <p class="text-p-sm text-hero-muted">{{ explain }}</p>

      <!-- everyone, in one bar: behind, on track, nothing counted; the rest are not set -->
      <div
        class="mt-1 flex h-2.5 overflow-hidden rounded-full bg-hero-track"
        role="img"
        :aria-label="standingLabel"
      >
        <span
          v-for="part in parts"
          :key="part.key"
          class="h-full"
          :class="part.fill"
          :style="{ width: `${(part.count / total) * 100}%` }"
        />
      </div>
      <ul class="flex flex-wrap gap-x-5 gap-y-1.5 text-sm tabular-nums">
        <li
          v-for="part in [...parts, unsetPart]"
          :key="part.key"
          class="flex items-center gap-1.5"
        >
          <span
            class="size-2.5 shrink-0"
            :class="[
              part.fill,
              part.key === 'unset' ? 'rounded-sm' : 'rounded-full',
            ]"
            aria-hidden="true"
          />
          {{ part.label }}
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import { computed } from "vue";
import { monthTitle, type monthPace, type TeamStanding } from "./salesTargets";

const props = defineProps<{
  month: string;
  pace: ReturnType<typeof monthPace>;
  /** the team's average share reached; null with nothing counted */
  average: number | null;
  counts: Record<TeamStanding, number>;
  total: number;
  headingId: string;
}>();

// a 240° arc open at the bottom, centred on (60, 60) with a radius of 48
const ARC = "M18.43 84 A48 48 0 1 1 101.57 84";
const tick = computed(() => {
  const angle = ((150 + (240 * props.pace.percent) / 100) * Math.PI) / 180;
  const at = (r: number) => ({
    x: 60 + r * Math.cos(angle),
    y: 60 + r * Math.sin(angle),
  });
  const inner = at(39);
  const outer = at(57);
  return { x1: inner.x, y1: inner.y, x2: outer.x, y2: outer.y };
});

const period = computed(() => {
  const start = dayjs(`${props.month}-01`);
  const title = monthTitle(props.month);
  if (props.pace.state === "ahead") return title;
  return `${title} · 1 – ${props.pace.day} ${start.format("MMM")}`;
});
const headline = computed(() =>
  props.pace.state === "running"
    ? __("The team should be at {0}% by today", String(props.pace.percent))
    : props.pace.state === "over"
    ? __("{0} is over", monthTitle(props.month))
    : __("{0} hasn't begun", monthTitle(props.month))
);
const explain = computed(() =>
  props.pace.state === "running"
    ? __(
        "The yellow tick on the gauge is today's pace: {0} of {1} days gone.",
        String(props.pace.day),
        String(props.pace.days)
      )
    : props.pace.state === "over"
    ? props.average == null
      ? __("Nothing was counted for the month.")
      : __("The team ended at {0}% of its targets.", String(props.average))
    : __("Progress counts from the 1st, from everyone's leads.")
);
const gaugeLabel = computed(() =>
  props.average == null
    ? __("Team average: nothing counted yet")
    : props.pace.state === "running"
    ? __(
        "Team average {0}% against a pace of {1}%",
        String(props.average),
        String(props.pace.percent)
      )
    : __("Team average {0}%", String(props.average))
);

const parts = computed(() => [
  {
    key: "behind",
    count: props.counts.behind,
    fill: "bg-warm-fill",
    label: __("{0} behind", String(props.counts.behind)),
  },
  {
    key: "on_track",
    count: props.counts.on_track,
    fill: "bg-hero-fill",
    label: __("{0} on track", String(props.counts.on_track)),
  },
  {
    key: "uncounted",
    count: props.counts.uncounted,
    fill: "bg-hero-muted",
    label: __("{0} nothing counted", String(props.counts.uncounted)),
  },
]);
const unsetPart = computed(() => ({
  key: "unset",
  count: props.counts.unset,
  fill: "bg-hero-track ring-1 ring-inset ring-hero-muted",
  label: __("{0} not set", String(props.counts.unset)),
}));
const standingLabel = computed(() =>
  [...parts.value, unsetPart.value].map((p) => p.label).join(", ")
);
</script>
