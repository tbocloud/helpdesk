<template>
  <!-- one row per project, so the chart grows with the list; screen readers
       get the numbers from the label, keyboards use the Project filter -->
  <div
    role="img"
    :aria-label="summary"
    :style="{ height: `${Math.max(rows.length * 34 + 24, 140)}px` }"
  >
    <ECharts
      :options="options"
      :events="{ click: onClick }"
      class="h-full w-full"
    />
  </div>
</template>

<script setup lang="ts">
import {
  baseOptions,
  categoryAxis,
  escapeHtml,
  tooltipRow,
  useChartColors,
  valueAxis,
} from "@/pages/performance/chartTheme";
import { __ } from "@/translation";
import { ECharts } from "frappe-ui";
import { computed } from "vue";
import type { ProjectCount } from "../overviewMeta";

const props = defineProps<{ rows: ProjectCount[]; selected?: string | null }>();
const emit = defineEmits<{ (e: "select", project: string): void }>();
const colors = useChartColors();

// busiest at the top
const ordered = computed(() => [...props.rows].reverse());
// the axis holds project IDs, since two projects can share a name
const nameOf = computed(
  () => new Map(props.rows.map((r) => [r.project, r.project_name]))
);

const summary = computed(() =>
  [
    __("Open tasks by project:"),
    props.rows.map((r) => `${r.project_name} ${r.count}`).join(", "),
  ].join(" ")
);

function onClick(params: {
  dataIndex?: number;
  value?: string;
  componentType?: string;
}) {
  const row =
    params.componentType === "yAxis"
      ? ordered.value.find((r) => r.project === params.value)
      : ordered.value[params.dataIndex ?? -1];
  if (row) emit("select", row.project);
}

const options = computed(() => {
  const c = colors.value;
  const rows = ordered.value;
  const names = nameOf.value;
  return {
    ...baseOptions(c),
    grid: { left: 8, right: 32, top: 4, bottom: 4, containLabel: true },
    tooltip: {
      ...baseOptions(c).tooltip,
      trigger: "axis",
      axisPointer: {
        type: "shadow",
        shadowStyle: { color: c.brandSoft, opacity: 0.4 },
      },
      formatter: (items: any[]) => {
        const row = rows[items[0].dataIndex];
        return `<div style="font-weight:600;margin-bottom:4px">${escapeHtml(
          row.project_name
        )}</div>${tooltipRow(
          items[0].color,
          __("open tasks"),
          String(row.count)
        )}`;
      },
    },
    xAxis: valueAxis(c, { minInterval: 1 }),
    yAxis: categoryAxis(c, {
      data: rows.map((r) => r.project),
      axisLabel: {
        color: c.textPrimary,
        fontSize: 12,
        width: 140,
        overflow: "truncate",
        // the project the page is filtered to reads in brand
        formatter: (project: string) => {
          const name = names.get(project) ?? project;
          return project === props.selected ? `{sel|${name}}` : name;
        },
        rich: { sel: { color: c.brand, fontWeight: 600, fontSize: 12 } },
      },
      triggerEvent: true,
    }),
    series: [
      {
        type: "bar",
        barMaxWidth: 18,
        cursor: "pointer",
        emphasis: { focus: "none" },
        data: rows.map((r) => ({
          value: r.count,
          itemStyle: {
            color: r.project === props.selected ? c.brand : c.other,
            borderRadius: [0, 4, 4, 0],
          },
        })),
        label: {
          show: true,
          position: "right",
          color: c.textSecondary,
          fontSize: 11,
        },
      },
    ],
  };
});
</script>
