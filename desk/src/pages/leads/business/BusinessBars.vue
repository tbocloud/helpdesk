<template>
  <figure class="biz-chart m-0 flex flex-col gap-2">
    <figcaption class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
      <span
        v-for="(s, i) in series"
        :key="s.name"
        class="inline-flex items-center gap-1.5 text-[color:var(--biz-muted,var(--ink-gray-6))]"
      >
        <span
          class="inline-block size-2.5 rounded-sm"
          :class="i === 0 ? 'bar-a' : 'bar-b'"
          aria-hidden="true"
        />
        {{ s.name }}
      </span>
    </figcaption>
    <svg
      :viewBox="`0 0 ${W} ${H}`"
      class="h-auto w-full"
      role="img"
      :aria-label="ariaLabel"
    >
      <g v-for="tick in ticks" :key="tick.y">
        <line :x1="LEFT" :x2="W" :y1="tick.y" :y2="tick.y" class="grid-line" />
        <text
          :x="LEFT - 6"
          :y="tick.y + 3.5"
          text-anchor="end"
          class="axis-text"
        >
          {{ tick.text }}
        </text>
      </g>
      <g v-for="(label, g) in labels" :key="label">
        <rect
          v-for="(s, i) in series"
          :key="s.name"
          :x="barX(g, i)"
          :y="barY(s.values[g])"
          :width="barWidth"
          :height="Math.max(BASE - barY(s.values[g]), 0)"
          rx="2"
          :class="i === 0 ? 'bar-a' : 'bar-b'"
        />
        <!-- the value on top of each bar while there is room for it -->
        <template v-if="labels.length <= 7">
          <text
            v-for="(s, i) in series"
            :key="`v${s.name}`"
            :x="barX(g, i) + barWidth / 2"
            :y="barY(s.values[g]) - 4"
            text-anchor="middle"
            class="value-text"
          >
            {{ s.values[g] ? format(s.values[g]) : "" }}
          </text>
        </template>
        <text
          :x="LEFT + groupWidth * g + groupWidth / 2"
          :y="H - 6"
          text-anchor="middle"
          class="axis-text"
        >
          {{ label }}
        </text>
      </g>
    </svg>
    <!-- the same numbers for a screen reader -->
    <table class="sr-only">
      <caption>
        {{
          ariaLabel
        }}
      </caption>
      <thead>
        <tr>
          <th scope="col">{{ __("Month") }}</th>
          <th v-for="s in series" :key="s.name" scope="col">{{ s.name }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(label, g) in labels" :key="label">
          <th scope="row">{{ label }}</th>
          <td v-for="s in series" :key="s.name">{{ format(s.values[g]) }}</td>
        </tr>
      </tbody>
    </table>
  </figure>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed } from "vue";

const props = defineProps<{
  labels: string[];
  /** one or two series: the first is the brand colour, the second neutral grey */
  series: { name: string; values: number[] }[];
  /** a value as the chart shows it (axis ticks and bar tops) */
  format: (value: number) => string;
  ariaLabel: string;
}>();

const W = 640;
const H = 230;
const LEFT = 52;
const TOP = 22;
const BASE = H - 26;

const max = computed(() => {
  const top = Math.max(0, ...props.series.flatMap((s) => s.values));
  // a round top for the axis: 1, 2, 2.5 or 5 times a power of ten
  if (!top) return 1;
  const pow = 10 ** Math.floor(Math.log10(top));
  return ([1, 2, 2.5, 5, 10].find((m) => m * pow >= top) ?? 10) * pow;
});
const groupWidth = computed(
  () => (W - LEFT) / Math.max(props.labels.length, 1)
);
const barWidth = computed(() =>
  Math.min(36, (groupWidth.value * 0.7) / props.series.length)
);

function barX(group: number, index: number) {
  const used = barWidth.value * props.series.length;
  return (
    LEFT +
    groupWidth.value * group +
    (groupWidth.value - used) / 2 +
    barWidth.value * index
  );
}
function barY(value: number) {
  return BASE - (Math.max(value, 0) / max.value) * (BASE - TOP);
}
const ticks = computed(() =>
  [0, 0.5, 1].map((f) => ({
    y: barY(max.value * f),
    text: props.format(max.value * f),
  }))
);
</script>

<style scoped>
.bar-a {
  fill: var(--biz-a, var(--brand));
  background-color: var(--biz-a, var(--brand));
}
.bar-b {
  fill: var(--biz-b, var(--ink-gray-5));
  background-color: var(--biz-b, var(--ink-gray-5));
}
.grid-line {
  stroke: var(--biz-line, var(--outline-gray-2));
  stroke-width: 1;
}
.axis-text {
  fill: var(--biz-muted, var(--ink-gray-6));
  font-size: 11px;
  font-family: var(--font-mono, "Geist Mono", monospace);
  font-variant-numeric: tabular-nums;
}
.value-text {
  fill: var(--biz-ink, var(--ink-gray-9));
  font-size: 11px;
  font-family: var(--font-mono, "Geist Mono", monospace);
  font-variant-numeric: tabular-nums;
}
.biz-chart,
.bar-a,
.bar-b {
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}
</style>
