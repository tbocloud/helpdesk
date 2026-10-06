<template>
  <!-- one row per customer, so the chart grows with the list -->
  <div :style="{ height: `${Math.max(rows.length * 34 + 24, 140)}px` }">
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
  categoryAxis,
  escapeHtml,
  tooltipRow,
  useChartColors,
  valueAxis,
} from "../chartTheme";
import { TIMINGS, timingColor } from "../performanceMeta";

interface Row {
  customer: string;
  posts: number;
  on_time: number;
  published: number;
  missed: number;
  upcoming: number;
}

const props = defineProps<{ rows: Row[]; selected?: string | null }>();
const emit = defineEmits<{ (e: "select", customer: string): void }>();
const colors = useChartColors();

const counts = (r: Row) => ({
  "On time": r.on_time,
  Late: r.published - r.on_time,
  Missed: r.missed,
  Upcoming: r.upcoming,
});
const label = (r: Row) => r.customer || __("No customer");

// biggest at the top
const ordered = computed(() => [...props.rows].reverse());

function onClick(params: {
  dataIndex?: number;
  value?: string;
  componentType?: string;
}) {
  const row =
    params.componentType === "yAxis"
      ? ordered.value.find((r) => label(r) === params.value)
      : ordered.value[params.dataIndex ?? -1];
  if (row) emit("select", row.customer);
}

const options = computed(() => {
  const c = colors.value;
  const rows = ordered.value;
  const lastKey = rows.map((r) =>
    [...TIMINGS].reverse().find((t) => counts(r)[t])
  );
  return {
    ...baseOptions(c),
    grid: { left: 8, right: 40, top: 4, bottom: 4, containLabel: true },
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
        const n = counts(row);
        const lines = TIMINGS.filter((t) => n[t]).map((t) =>
          tooltipRow(timingColor(c, t), __(t), String(n[t]))
        );
        return `<div style="font-weight:600;margin-bottom:4px">${escapeHtml(
          label(row)
        )} · ${escapeHtml(
          __("{0} posts", String(row.posts))
        )}</div>${lines.join("")}`;
      },
    },
    xAxis: valueAxis(c, { minInterval: 1 }),
    yAxis: categoryAxis(c, {
      data: rows.map(label),
      axisLabel: {
        color: c.textPrimary,
        fontSize: 12,
        width: 140,
        overflow: "truncate",
        // the customer open below reads in brand
        formatter: (name: string) =>
          props.selected != null &&
          name === label({ customer: props.selected } as Row)
            ? `{sel|${name}}`
            : name,
        rich: { sel: { color: c.brand, fontWeight: 600, fontSize: 12 } },
      },
      triggerEvent: true,
    }),
    series: TIMINGS.map((t, i) => ({
      name: t,
      type: "bar",
      stack: "posts",
      barMaxWidth: 18,
      cursor: "pointer",
      itemStyle: {
        color: timingColor(c, t),
        borderColor: c.surface,
        borderWidth: 1,
      },
      emphasis: { focus: "none" },
      data: rows.map((r, ri) => ({
        value: counts(r)[t] || 0,
        itemStyle: {
          ...(lastKey[ri] === t ? { borderRadius: [0, 4, 4, 0] } : {}),
          // the customer open below stays at full strength
          opacity:
            props.selected == null || r.customer === props.selected ? 1 : 0.45,
        },
      })),
      label:
        i === TIMINGS.length - 1
          ? {
              show: true,
              position: "right",
              color: c.textSecondary,
              fontSize: 11,
              formatter: (p: any) => String(rows[p.dataIndex].posts),
            }
          : undefined,
    })),
  };
});
</script>
