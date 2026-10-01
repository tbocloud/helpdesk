<template>
  <div class="flex flex-col items-center gap-4 sm:flex-row">
    <div class="h-52 w-52 shrink-0">
      <ECharts :options="options" class="h-full w-full" />
    </div>
    <ul
      class="flex w-full flex-col gap-1.5 text-sm"
      :aria-label="__('Hours by activity')"
    >
      <li v-for="s in slices" :key="s.name" class="flex items-center gap-2">
        <span
          class="size-2.5 shrink-0 rounded-sm"
          :style="{ background: s.color }"
          aria-hidden="true"
        />
        <span class="min-w-0 flex-1 truncate text-ink-gray-8">{{
          s.name
        }}</span>
        <span class="font-mono text-xs tabular-nums text-ink-gray-6">{{
          formatHours(s.value)
        }}</span>
        <span
          class="w-10 text-right font-mono text-xs tabular-nums text-ink-gray-5"
          >{{ s.pct }}%</span
        >
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { ECharts } from "frappe-ui";
import { computed } from "vue";
import {
  MAX_CATEGORIES,
  baseOptions,
  formatHours,
  tooltipRow,
  useChartColors,
} from "../chartTheme";

const props = defineProps<{ items: { activity: string; hours: number }[] }>();
const colors = useChartColors();

const total = computed(() => props.items.reduce((s, i) => s + i.hours, 0));

// top activities in fixed palette order, the rest folded into Other
const slices = computed(() => {
  const c = colors.value;
  const top = props.items.slice(0, MAX_CATEGORIES);
  const rest = props.items
    .slice(MAX_CATEGORIES)
    .reduce((s, i) => s + i.hours, 0);
  const out = top.map((i, n) => ({
    name: i.activity,
    value: i.hours,
    color: c.series[n],
  }));
  if (rest)
    out.push({
      name: __("Other"),
      value: Math.round(rest * 10) / 10,
      color: c.other,
    });
  return out.map((s) => ({
    ...s,
    pct: total.value ? Math.round((s.value / total.value) * 100) : 0,
  }));
});

const options = computed(() => {
  const c = colors.value;
  return {
    ...baseOptions(c),
    tooltip: {
      ...baseOptions(c).tooltip,
      trigger: "item",
      formatter: (p: any) =>
        tooltipRow(p.color, p.name, `${formatHours(p.value)} · ${p.percent}%`),
    },
    title: {
      text: formatHours(total.value),
      subtext: __("logged"),
      left: "center",
      top: "40%",
      textStyle: { color: c.textPrimary, fontSize: 18, fontWeight: 600 },
      subtextStyle: { color: c.textSecondary, fontSize: 11 },
    },
    series: [
      {
        type: "pie",
        radius: ["62%", "88%"],
        avoidLabelOverlap: true,
        label: { show: false },
        itemStyle: { borderColor: c.surface, borderWidth: 2, borderRadius: 4 },
        emphasis: { scale: true, scaleSize: 4 },
        data: slices.value.map((s) => ({
          name: s.name,
          value: s.value,
          itemStyle: { color: s.color },
        })),
      },
    ],
  };
});
</script>
