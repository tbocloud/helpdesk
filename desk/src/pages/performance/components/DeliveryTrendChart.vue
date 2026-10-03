<template>
  <div class="h-56">
    <ECharts :options="options" class="h-full w-full" />
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { dayjs, ECharts } from "frappe-ui";
import { computed } from "vue";
import {
  baseOptions,
  categoryAxis,
  tooltipRow,
  useChartColors,
  valueAxis,
} from "../chartTheme";
import { TIMINGS, timingColor } from "../performanceMeta";

const props = defineProps<{
  trend: {
    bucket: "day" | "week";
    dates: string[];
    series: Record<string, number[]>;
  };
}>();
const colors = useChartColors();

const options = computed(() => {
  const c = colors.value;
  const { dates, series, bucket } = props.trend;
  const fmt = (d: string) =>
    bucket === "week"
      ? __("Week of {0}", dayjs(d).format("D MMM"))
      : dayjs(d).format("ddd D MMM");
  return {
    ...baseOptions(c),
    grid: { left: 8, right: 8, top: 8, bottom: 4, containLabel: true },
    legend: { show: false },
    tooltip: {
      ...baseOptions(c).tooltip,
      trigger: "axis",
      axisPointer: {
        type: "shadow",
        shadowStyle: { color: c.brandSoft, opacity: 0.4 },
      },
      formatter: (items: any[]) => {
        const i = items[0].dataIndex;
        const lines = TIMINGS.filter((t) => series[t][i]).map((t) =>
          tooltipRow(timingColor(c, t), __(t), String(series[t][i]))
        );
        return `<div style="font-weight:600;margin-bottom:4px">${fmt(
          dates[i]
        )}</div>${lines.join("") || __("No posts due")}`;
      },
    },
    xAxis: categoryAxis(c, {
      data: dates,
      axisLabel: {
        color: c.textSecondary,
        fontSize: 11,
        formatter: (d: string) => dayjs(d).format("D MMM"),
        hideOverlap: true,
      },
    }),
    yAxis: valueAxis(c, { minInterval: 1 }),
    series: TIMINGS.map((t) => ({
      name: t,
      type: "bar",
      stack: "posts",
      barMaxWidth: 28,
      itemStyle: {
        color: timingColor(c, t),
        borderColor: c.surface,
        borderWidth: 1,
      },
      emphasis: { focus: "none" },
      data: series[t],
    })),
  };
});
</script>
