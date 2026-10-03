<template>
  <div class="relative size-44 shrink-0">
    <ECharts :options="options" class="h-full w-full" />
    <!-- the headline sits in the hole -->
    <div
      class="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"
    >
      <span class="text-3xl font-semibold tabular-nums text-ink-gray-9">{{
        center
      }}</span>
      <span class="text-xs text-ink-gray-5">{{ caption }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { ECharts } from "frappe-ui";
import { computed } from "vue";
import {
  baseOptions,
  tooltipRow,
  useChartColors,
} from "@/pages/performance/chartTheme";
import { TIMINGS, timingColor, type Timing } from "@/pages/performance/performanceMeta";

const props = defineProps<{
  counts: Record<Timing, number>;
  center: string;
  caption: string;
}>();
const colors = useChartColors();

const LABEL: Record<Timing, string> = {
  "On time": __("On time"),
  Late: __("Late"),
  Missed: __("Overdue"),
  Upcoming: __("Not due yet"),
};

const options = computed(() => {
  const c = colors.value;
  const total = TIMINGS.reduce((n, t) => n + props.counts[t], 0);
  return {
    ...baseOptions(c),
    tooltip: {
      ...baseOptions(c).tooltip,
      trigger: "item",
      formatter: (p: any) =>
        tooltipRow(
          p.color,
          LABEL[p.data.key as Timing],
          `${p.value} · ${total ? Math.round((p.value / total) * 100) : 0}%`
        ),
    },
    series: [
      {
        type: "pie",
        radius: ["68%", "92%"],
        avoidLabelOverlap: false,
        label: { show: false },
        labelLine: { show: false },
        itemStyle: { borderColor: c.surface, borderWidth: 2, borderRadius: 4 },
        emphasis: { scale: true, scaleSize: 4 },
        data: total
          ? TIMINGS.filter((t) => props.counts[t]).map((t) => ({
              key: t,
              value: props.counts[t],
              itemStyle: { color: timingColor(c, t) },
            }))
          : [{ key: "Upcoming", value: 1, itemStyle: { color: c.grid } }],
      },
    ],
  };
});
</script>
