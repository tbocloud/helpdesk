<template>
  <!-- screen readers can't read the chart, so its numbers are in the label and the legend -->
  <div
    class="relative shrink-0"
    :class="small ? 'size-32' : 'size-40'"
    role="img"
    :aria-label="summary"
  >
    <ECharts :options="options" class="h-full w-full" />
    <div
      class="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"
      aria-hidden="true"
    >
      <span
        class="font-bold tabular-nums leading-none tracking-[-0.02em] text-ink-gray-9"
        :class="small ? 'text-2xl' : 'text-3xl'"
        >{{ value }}</span
      >
      <span v-if="caption" class="mt-1 text-xs text-ink-gray-6">{{
        caption
      }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  baseOptions,
  tooltipRow,
  useChartColors,
} from "@/pages/performance/chartTheme";
import { __ } from "@/translation";
import { ECharts } from "frappe-ui";
import { drawColor } from "./salesDashboard";
import { computed } from "vue";

/** One part of the ring; `color` is a theme variable such as "--success", or a colour. */
export interface DonutPart {
  label: string;
  value: number;
  color: string;
}

const props = defineProps<{
  parts: DonutPart[];
  /** the figure in the middle */
  value: string | number;
  caption?: string;
  /** what the chart shows, for screen readers */
  label: string;
  small?: boolean;
}>();
const colors = useChartColors();

const whole = computed(() =>
  props.parts.reduce((sum, part) => sum + part.value, 0)
);

const summary = computed(() =>
  [
    props.label,
    props.parts.map((p) => `${p.label} ${p.value}`).join(", "),
  ].join(": ")
);

const options = computed(() => {
  const c = colors.value;
  const sum = whole.value;
  return {
    ...baseOptions(c),
    tooltip: {
      ...baseOptions(c).tooltip,
      trigger: "item",
      formatter: (p: any) =>
        tooltipRow(
          p.color,
          p.name,
          `${p.value} · ${sum ? Math.round((p.value / sum) * 100) : 0}%`
        ),
    },
    series: [
      {
        type: "pie",
        radius: ["70%", "94%"],
        avoidLabelOverlap: false,
        label: { show: false },
        labelLine: { show: false },
        // a 2px surface gap between the parts
        itemStyle: { borderColor: c.surface, borderWidth: 2, borderRadius: 4 },
        emphasis: { scale: true, scaleSize: 3 },
        data: sum
          ? props.parts
              .filter((p) => p.value > 0)
              .map((p) => ({
                name: p.label,
                value: p.value,
                itemStyle: { color: drawColor(p.color) },
              }))
          : [
              {
                name: __("Nothing yet"),
                value: 1,
                itemStyle: { color: c.grid },
                tooltip: { show: false },
              },
            ],
      },
    ],
  };
});
</script>
