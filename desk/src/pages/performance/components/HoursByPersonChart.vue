<template>
  <!-- the chart fills this box; one row per person -->
  <div :style="{ height: `${Math.max(rows.length * 34 + 48, 160)}px` }">
    <ECharts
      :options="options"
      :events="{ click: onClick }"
      class="h-full w-full"
    />
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { ECharts } from "frappe-ui";
import { computed } from "vue";
import {
  baseOptions,
  escapeHtml,
  categoryAxis,
  formatHours,
  tooltipRow,
  useChartColors,
  valueAxis,
} from "../chartTheme";

interface Row {
  employee: string;
  employee_name: string;
  hours: number;
  activities: Record<string, number>;
}

const props = defineProps<{ rows: Row[]; activities: string[] }>();
const emit = defineEmits<{ (e: "select", employee: string): void }>();
const colors = useChartColors();

const OTHER = "Other";

function onClick(params: {
  dataIndex?: number;
  value?: string;
  componentType?: string;
}) {
  // bars report their row; axis labels report the name
  const rows = [...props.rows].reverse();
  const row =
    params.componentType === "yAxis"
      ? rows.find((r) => r.employee_name === params.value)
      : rows[params.dataIndex ?? -1];
  if (row) emit("select", row.employee);
}

const options = computed(() => {
  const c = colors.value;
  // biggest at the top
  const rows = [...props.rows].reverse();
  const keys = [...props.activities, OTHER];
  const colorOf = (i: number) =>
    i < props.activities.length ? c.series[i] : c.other;
  // the rounded end belongs to each bar's last non-empty segment
  const lastKey = rows.map((r) =>
    [...keys].reverse().find((k) => r.activities[k])
  );

  return {
    ...baseOptions(c),
    grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
    legend: { show: false },
    tooltip: {
      ...baseOptions(c).tooltip,
      trigger: "axis",
      axisPointer: {
        type: "shadow",
        shadowStyle: { color: c.brandSoft, opacity: 0.4 },
      },
      formatter: (items: any[]) => {
        const row = rows[items[0].dataIndex];
        const lines = keys
          .map((k, i) => ({ k, i, v: row.activities[k] || 0 }))
          .filter((x) => x.v)
          .sort((a, b) => b.v - a.v)
          .map((x) =>
            tooltipRow(
              colorOf(x.i),
              x.k === OTHER ? __("Other") : x.k,
              formatHours(x.v)
            )
          );
        return `<div style="font-weight:600;margin-bottom:4px">${escapeHtml(
          row.employee_name
        )} · ${formatHours(row.hours)}</div>${lines.join("")}`;
      },
    },
    xAxis: valueAxis(c, {
      axisLabel: {
        color: c.textSecondary,
        fontSize: 11,
        formatter: "{value} h",
      },
    }),
    yAxis: categoryAxis(c, {
      data: rows.map((r) => r.employee_name),
      axisLabel: {
        color: c.textPrimary,
        fontSize: 12,
        width: 150,
        overflow: "truncate",
      },
      triggerEvent: true,
    }),
    series: keys.map((k, i) => ({
      name: k,
      type: "bar",
      stack: "hours",
      barMaxWidth: 20,
      cursor: "pointer",
      itemStyle: { color: colorOf(i), borderColor: c.surface, borderWidth: 1 },
      emphasis: { focus: "none" },
      data: rows.map((r, ri) => ({
        value: r.activities[k] || 0,
        itemStyle:
          lastKey[ri] === k ? { borderRadius: [0, 4, 4, 0] } : undefined,
      })),
      // total at the tip of each bar, on the last series only
      label:
        i === keys.length - 1
          ? {
              show: true,
              position: "right",
              color: c.textSecondary,
              fontSize: 11,
              formatter: (p: any) => formatHours(rows[p.dataIndex].hours),
            }
          : undefined,
    })),
  };
});
</script>
