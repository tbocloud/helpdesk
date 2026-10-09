<template>
  <div class="h-48" role="img" :aria-label="summary">
    <ECharts :options="options" class="h-full w-full" />
  </div>
</template>

<script setup lang="ts">
import {
  baseOptions,
  categoryAxis,
  tooltipRow,
  useChartColors,
  valueAxis,
} from "@/pages/performance/chartTheme";
import { __ } from "@/translation";
import { dayjs, ECharts } from "frappe-ui";
import { computed } from "vue";
import type { Dashboard } from "../teamDashboardMeta";

const props = defineProps<{ trend: NonNullable<Dashboard["trend"]> }>();
const colors = useChartColors();

function label(date: string, long = false) {
  const d = dayjs(date);
  if (props.trend.bucket === "month") return d.format(long ? "MMMM" : "MMM");
  if (props.trend.bucket === "week")
    return long ? __("Week of {0}", d.format("D MMM")) : d.format("D MMM");
  return d.format(long ? "ddd D MMM" : "D MMM");
}

const summary = computed(() =>
  __(
    "Tasks completed: {0} in total",
    String(props.trend.values.reduce((a, b) => a + b, 0))
  )
);

const options = computed(() => {
  const c = colors.value;
  const { dates, values } = props.trend;
  return {
    ...baseOptions(c),
    grid: { left: 8, right: 8, top: 8, bottom: 4, containLabel: true },
    tooltip: {
      ...baseOptions(c).tooltip,
      trigger: "axis",
      axisPointer: {
        type: "shadow",
        shadowStyle: { color: c.brandSoft, opacity: 0.4 },
      },
      formatter: (items: { dataIndex: number }[]) => {
        const i = items[0].dataIndex;
        return `<div style="font-weight:600;margin-bottom:4px">${label(
          dates[i],
          true
        )}</div>${tooltipRow(
          c.series[0],
          __("tasks completed"),
          String(values[i])
        )}`;
      },
    },
    xAxis: categoryAxis(c, {
      data: dates,
      axisLabel: {
        color: c.textSecondary,
        fontSize: 11,
        formatter: (d: string) => label(d),
        hideOverlap: true,
      },
    }),
    yAxis: valueAxis(c, { minInterval: 1 }),
    series: [
      {
        type: "bar",
        barMaxWidth: 24,
        itemStyle: { color: c.series[0], borderRadius: [3, 3, 0, 0] },
        data: values,
      },
    ],
  };
});
</script>
