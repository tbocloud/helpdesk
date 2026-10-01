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
  formatHours,
  tooltipRow,
  useChartColors,
  valueAxis,
} from "../chartTheme";

const props = defineProps<{
  days: { day: string; hours: number }[];
  /** draws a reference line, e.g. a working day for one person */
  target?: number;
}>();
const colors = useChartColors();

const options = computed(() => {
  const c = colors.value;
  const many = props.days.length > 31;
  return {
    ...baseOptions(c),
    grid: { left: 8, right: 16, top: 16, bottom: 4, containLabel: true },
    tooltip: {
      ...baseOptions(c).tooltip,
      trigger: "axis",
      axisPointer: {
        type: "shadow",
        shadowStyle: { color: c.brandSoft, opacity: 0.4 },
      },
      formatter: (items: any[]) => {
        const d = props.days[items[0].dataIndex];
        return `<div style="font-weight:600;margin-bottom:4px">${dayjs(
          d.day
        ).format("ddd, D MMM")}</div>${tooltipRow(
          c.brand,
          __("logged"),
          formatHours(d.hours)
        )}`;
      },
    },
    xAxis: categoryAxis(c, {
      data: props.days.map((d) =>
        dayjs(d.day).format(many ? "D MMM" : "ddd D")
      ),
    }),
    yAxis: valueAxis(c, {
      axisLabel: {
        color: c.textSecondary,
        fontSize: 11,
        formatter: "{value} h",
      },
    }),
    series: [
      {
        name: __("Hours"),
        type: "bar",
        barMaxWidth: 24,
        itemStyle: { color: c.brand, borderRadius: [4, 4, 0, 0] },
        data: props.days.map((d) => d.hours),
        markLine: props.target
          ? {
              silent: true,
              symbol: "none",
              lineStyle: { color: c.textSecondary, type: "solid", width: 1 },
              label: {
                color: c.textSecondary,
                fontSize: 11,
                formatter: __("{0} working day", formatHours(props.target)),
                position: "insideEndTop",
              },
              data: [{ yAxis: props.target }],
            }
          : undefined,
      },
    ],
  };
});
</script>
