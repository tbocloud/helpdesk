<template>
  <section
    class="flex min-w-0 flex-col overflow-hidden rounded-xl border border-l-4 border-outline-gray-2 bg-surface-base"
    :class="[section.border, wide ? 'lg:col-span-2' : '']"
    :aria-labelledby="headingId"
  >
    <!-- the heading takes its metric's tone, beside the icon and the words -->
    <header class="flex items-center gap-2 px-5 py-3" :class="section.head">
      <component
        :is="look.icon"
        class="size-4 shrink-0"
        :class="section.ink"
        aria-hidden="true"
      />
      <h2 :id="headingId" class="text-base font-semibold text-ink-gray-9">
        {{ chart.title }}
      </h2>
    </header>
    <p class="px-5 pt-4 text-p-sm text-ink-gray-6">{{ subtitle }}</p>

    <div class="min-w-0 flex-1 p-5">
      <p
        v-if="chart.missing"
        class="flex items-start gap-2 rounded-xl bg-surface-gray-2 px-3 py-2 text-p-sm text-ink-gray-7"
      >
        <LucideInfo class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ chart.missing }}</span>
      </p>
      <p
        v-else-if="!hasData"
        class="py-10 text-center text-p-sm text-ink-gray-6"
      >
        {{ __("No leads in this period for these filters.") }}
      </p>

      <!-- a table: rows on wide screens, two-line items on a phone -->
      <template v-else-if="chart.chart_type === 'table'">
        <div class="hidden overflow-x-auto sm:block">
          <table class="w-full text-sm">
            <caption class="sr-only">
              {{
                chart.title
              }}
            </caption>
            <thead>
              <tr class="border-b border-outline-gray-2 text-ink-gray-6">
                <th scope="col" class="py-2 pr-3 text-left font-medium">
                  {{ chart.dimension_label }}
                </th>
                <th
                  v-for="column in chart.columns"
                  :key="column.metric"
                  scope="col"
                  class="whitespace-nowrap px-3 py-2 text-right font-medium"
                >
                  <span class="inline-flex items-center gap-1.5">
                    <span
                      class="inline-block size-2 shrink-0 rounded-full"
                      :style="{ background: columnColor(column.metric) }"
                      aria-hidden="true"
                    />
                    {{ column.label }}
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in chart.items"
                :key="item.key"
                class="border-b border-outline-gray-1 last:border-0"
              >
                <th
                  scope="row"
                  class="max-w-[14rem] py-2 pr-3 text-left font-normal text-ink-gray-8"
                  :title="item.label"
                >
                  <span class="block truncate">{{ item.label }}</span>
                  <!-- its share of the largest, in the sorting metric's colour -->
                  <span
                    class="mt-1 block h-1 rounded-full"
                    :style="{
                      width: `${share(item)}%`,
                      background: columnColor(chart.metric),
                    }"
                    aria-hidden="true"
                  />
                </th>
                <td
                  v-for="column in chart.columns"
                  :key="column.metric"
                  class="whitespace-nowrap px-3 py-2 text-right font-mono tabular-nums text-ink-gray-8"
                >
                  {{ cell(column.kind, item.columns?.[column.metric]) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <ul class="flex flex-col divide-y divide-outline-gray-1 sm:hidden">
          <li
            v-for="item in chart.items"
            :key="item.key"
            class="flex flex-col gap-1 py-2"
          >
            <div class="flex items-baseline justify-between gap-3">
              <span class="min-w-0 truncate text-sm text-ink-gray-8">{{
                item.label
              }}</span>
              <span class="font-mono text-sm tabular-nums text-ink-gray-9">
                {{ cell(chart.kind, item.value) }}
              </span>
            </div>
            <p class="text-p-xs tabular-nums text-ink-gray-6">
              {{ rowSummary(item) }}
            </p>
          </li>
        </ul>
      </template>

      <template v-else>
        <div
          :class="wide ? 'h-72' : 'h-64'"
          role="img"
          :aria-label="__('{0}: chart', chart.title)"
        >
          <ECharts :options="options" class="h-full w-full" />
        </div>
        <!-- the chart's figures for screen readers -->
        <table class="sr-only">
          <caption>
            {{
              chart.title
            }}
          </caption>
          <thead>
            <tr>
              <th scope="col">{{ chart.dimension_label }}</th>
              <th scope="col">{{ chart.metric_label }}</th>
              <th v-if="chart.compare_label" scope="col">
                {{ chart.compare_label }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in chart.items" :key="item.key">
              <th scope="row">{{ itemLabel(item) }}</th>
              <td>{{ cell(chart.kind, item.value) }}</td>
              <td v-if="chart.compare_label">
                {{ cell(chart.kind, item.compare) }}
              </td>
            </tr>
          </tbody>
        </table>
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import {
  baseOptions,
  categoryAxis,
  escapeHtml,
  MAX_CATEGORIES,
  tooltipRow,
  useChartColors,
  valueAxis,
} from "@/pages/performance/chartTheme";
import { monthLabel } from "@/pages/leads/business/businessFormat";
import { __ } from "@/translation";
import { ECharts } from "frappe-ui";
import { computed, useId } from "vue";
import LucideInfo from "~icons/lucide/info";
import {
  formatValue,
  METRIC_LOOK,
  seriesSlots,
  TONE_SECTION,
  type ChartItem,
  type DashboardChart,
  type MetricKind,
  type ValueFormat,
} from "./crmDashboard";

const props = defineProps<{
  chart: DashboardChart;
  /** takes the whole row: asked for, or a half chart with no partner on its row */
  wide?: boolean;
  currency: string | null;
  valueFormat: ValueFormat;
}>();

const headingId = `crm-chart-${useId()}`;
const colors = useChartColors();
const look = computed(
  () => METRIC_LOOK[props.chart.metric] || METRIC_LOOK.total_leads
);
const section = computed(() => TONE_SECTION[look.value.tone]);
const isMonth = computed(() => props.chart.dimension === "month");

const hasData = computed(() =>
  props.chart.items.some((i) => i.value || i.compare)
);

const subtitle = computed(() => {
  const c = props.chart;
  const parts = [
    c.chart_type === "table"
      ? __("By {0}", c.dimension_label.toLowerCase())
      : c.compare_label
      ? __(
          "{0} and {1} by {2}",
          c.metric_label,
          c.compare_label.toLowerCase(),
          c.dimension_label.toLowerCase()
        )
      : __("{0} by {1}", c.metric_label, c.dimension_label.toLowerCase()),
  ];
  if (c.period_label) parts.push(c.period_label);
  if (!isMonth.value && c.total_groups > c.items.length)
    parts.push(
      __("top {0} of {1}", String(c.items.length), String(c.total_groups))
    );
  return parts.join(" · ");
});

function cell(kind: MetricKind, value: number | null | undefined) {
  return formatValue(kind, value, props.currency, props.valueFormat);
}

function itemLabel(item: ChartItem) {
  return isMonth.value ? monthLabel(item.key, true) : item.label;
}

function rowSummary(item: ChartItem) {
  return props.chart.columns
    .filter((c) => c.metric !== props.chart.metric)
    .map((c) => `${c.label} ${cell(c.kind, item.columns?.[c.metric])}`)
    .join(" · ");
}

/** A row's value as a share of the largest, for the bar under its name. */
function share(item: ChartItem) {
  const most = Math.max(...props.chart.items.map((i) => i.value || 0));
  return most > 0
    ? Math.max(2, Math.round(((item.value || 0) / most) * 100))
    : 0;
}

/** A table column's dot: its metric's own series colour, beside its name. */
function columnColor(metric: string) {
  return colors.value.series[METRIC_LOOK[metric]?.slot ?? 0];
}

function axisValue(value: number) {
  return formatValue(props.chart.kind, value, props.currency, "short");
}

const options = computed(() => {
  const c = colors.value;
  const chart = props.chart;
  const labels = chart.items.map(itemLabel);
  const series = [
    { metric: chart.metric, name: chart.metric_label, key: "value" as const },
    ...(chart.compare_metric
      ? [
          {
            metric: chart.compare_metric,
            name: chart.compare_label || "",
            key: "compare" as const,
          },
        ]
      : []),
  ];
  // each metric keeps its own colour, unless two that share a chart look alike
  const slots = seriesSlots(chart.metric, chart.compare_metric);
  const seriesColor = (n: number) => c.series[slots[n]];
  const tooltip = {
    ...baseOptions(c).tooltip,
    // the card clips what spills over its edge
    confine: true,
    trigger: chart.chart_type === "donut" ? "item" : "axis",
    axisPointer: { type: "shadow", shadowStyle: { color: c.brandSoft } },
    formatter: (points: any) => {
      const list = Array.isArray(points) ? points : [points];
      const i = list[0].dataIndex;
      const rows =
        chart.chart_type === "donut"
          ? [
              tooltipRow(
                list[0].color,
                chart.metric_label,
                cell(chart.kind, list[0].value)
              ),
            ]
          : series.map((s, n) =>
              tooltipRow(
                seriesColor(n),
                s.name,
                cell(chart.kind, chart.items[i]?.[s.key])
              )
            );
      const heading =
        chart.chart_type === "donut" ? list[0].name : labels[i] ?? "";
      return `<div style="font-weight:600;margin-bottom:4px">${escapeHtml(
        heading
      )}</div>${rows.join("")}`;
    },
  };

  if (chart.chart_type === "donut") {
    // a fixed palette slot per slice, never cycled: the smallest slices become "Other"
    const shown = chart.items.slice(0, MAX_CATEGORIES - 1);
    const rest = chart.items.slice(MAX_CATEGORIES - 1);
    const data = shown.map((item, slot) => ({
      name: itemLabel(item),
      value: item.value || 0,
      itemStyle: { color: c.series[slot] },
    }));
    if (rest.length)
      data.push({
        name: __("Other"),
        value: rest.reduce((sum, item) => sum + (item.value || 0), 0),
        itemStyle: { color: c.other },
      });
    return {
      ...baseOptions(c),
      tooltip,
      legend: {
        bottom: 0,
        icon: "circle",
        itemWidth: 8,
        itemHeight: 8,
        textStyle: { color: c.textSecondary, fontSize: 11 },
      },
      series: [
        {
          type: "pie",
          radius: ["52%", "76%"],
          center: ["50%", "44%"],
          label: { show: false },
          itemStyle: { borderColor: c.surface, borderWidth: 2 },
          data,
        },
      ],
    };
  }

  // months run left to right; anything else reads best as horizontal bars
  const horizontal = chart.chart_type === "bar" && !isMonth.value;
  const categories = categoryAxis(c, {
    data: labels,
    inverse: horizontal,
    axisLabel: {
      color: c.textSecondary,
      fontSize: 11,
      width: horizontal ? 120 : undefined,
      overflow: "truncate",
      hideOverlap: true,
    },
  });
  const values = valueAxis(c, {
    axisLabel: { color: c.textSecondary, fontSize: 11, formatter: axisValue },
    minInterval: chart.kind === "count" ? 1 : undefined,
  });
  return {
    ...baseOptions(c),
    tooltip,
    grid: {
      left: 8,
      right: horizontal || chart.chart_type === "line" ? 64 : 16,
      top: chart.compare_metric ? 32 : 12,
      bottom: 4,
      containLabel: true,
    },
    // two series need a key; colour alone never says which is which
    legend: {
      show: !!chart.compare_metric,
      top: 0,
      left: 0,
      icon: "roundRect",
      itemWidth: 10,
      itemHeight: 4,
      textStyle: { color: c.textSecondary, fontSize: 11 },
    },
    xAxis: horizontal ? values : categories,
    yAxis: horizontal ? categories : values,
    series: series.map((s, n) => ({
      name: s.name,
      type: chart.chart_type === "line" ? "line" : "bar",
      data: chart.items.map((item) => item[s.key] ?? null),
      barMaxWidth: 24,
      symbolSize: 6,
      connectNulls: false,
      itemStyle: {
        color: seriesColor(n),
        borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0],
      },
      lineStyle: { width: 2, color: seriesColor(n) },
      // a soft flat wash under a trend line; fainter when two lines overlap
      areaStyle:
        chart.chart_type === "line"
          ? { color: seriesColor(n), opacity: series.length > 1 ? 0.06 : 0.14 }
          : undefined,
      // a lighter series colour needs its figure beside it: at a bar's end, a line's last point
      label: {
        show: horizontal,
        position: "right",
        color: c.textSecondary,
        fontSize: 11,
        formatter: (p: { value: number }) => cell(chart.kind, p.value),
      },
      endLabel: {
        show: chart.chart_type === "line",
        color: c.textSecondary,
        fontSize: 11,
        formatter: (p: { value: number }) => cell(chart.kind, p.value),
      },
    })),
  };
});
</script>
