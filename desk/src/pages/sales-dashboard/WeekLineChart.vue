<template>
  <div class="flex flex-col gap-2">
    <!-- the legend: always there for two or more lines, so a line is never told by colour alone -->
    <ul
      v-if="series.length > 1"
      class="flex flex-wrap gap-x-4 gap-y-1"
      :aria-label="__('Legend')"
    >
      <li
        v-for="line in series"
        :key="line.name"
        class="inline-flex items-center gap-1.5 text-xs text-ink-gray-7"
      >
        <span
          class="h-0.5 w-3 rounded-full"
          :style="{ background: cssColor(line.color) }"
          aria-hidden="true"
        />
        {{ line.name }}
      </li>
    </ul>
    <div :class="height" role="img" :aria-label="summary">
      <ECharts :options="options" class="h-full w-full" />
    </div>
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
import { cssColor, drawColor, total } from "./salesDashboard";

/** One line; `color` is a theme variable such as "--brand", or a colour. */
export interface WeekLine {
  name: string;
  values: number[];
  color: string;
}

const props = withDefaults(
  defineProps<{
    days: string[];
    series: WeekLine[];
    /** what the chart shows, for screen readers */
    label: string;
    /** shade under the first line */
    area?: boolean;
    height?: string;
  }>(),
  { height: "h-56" }
);
const colors = useChartColors();

const summary = computed(
  () =>
    `${props.label}: ` +
    props.series.map((line) => `${line.name} ${total(line.values)}`).join(", ")
);

const options = computed(() => {
  const c = colors.value;
  return {
    ...baseOptions(c),
    grid: { left: 8, right: 12, top: 12, bottom: 4, containLabel: true },
    tooltip: {
      ...baseOptions(c).tooltip,
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: c.axis } },
      formatter: (items: { dataIndex: number }[]) => {
        const i = items[0].dataIndex;
        return `<div style="font-weight:600;margin-bottom:4px">${dayjs(
          props.days[i]
        ).format("ddd D MMM")}</div>${props.series
          .map((line) =>
            tooltipRow(drawColor(line.color), line.name, String(line.values[i]))
          )
          .join("")}`;
      },
    },
    xAxis: categoryAxis(c, {
      data: props.days.map((day) => dayjs(day).format("ddd")),
      boundaryGap: false,
    }),
    yAxis: valueAxis(c, { minInterval: 1 }),
    series: props.series.map((line, index) => ({
      type: "line",
      name: line.name,
      data: line.values,
      symbol: "circle",
      symbolSize: 8,
      lineStyle: { width: 2, color: drawColor(line.color) },
      itemStyle: {
        color: c.surface,
        borderColor: drawColor(line.color),
        borderWidth: 2,
      },
      areaStyle:
        props.area && index === 0
          ? { color: drawColor(line.color), opacity: 0.08 }
          : undefined,
    })),
  };
});
</script>
