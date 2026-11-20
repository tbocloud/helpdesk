<template>
  <!-- a small trend beside a stat; the tile's own figure says the number -->
  <div class="h-9 w-24 shrink-0" aria-hidden="true">
    <ECharts :options="options" class="h-full w-full" />
  </div>
</template>

<script setup lang="ts">
import { useChartColors } from "@/pages/performance/chartTheme";
import { ECharts } from "frappe-ui";
import { drawColor } from "./salesDashboard";
import { computed } from "vue";

const props = defineProps<{
  values: number[];
  /** a theme variable such as "--brand" */
  color: string;
}>();
const colors = useChartColors();

const options = computed(() => {
  // read again when the theme changes
  void colors.value;
  const color = drawColor(props.color);
  return {
    animation: false,
    grid: { left: 2, right: 4, top: 4, bottom: 4 },
    xAxis: { type: "category", show: false, boundaryGap: false },
    yAxis: { type: "value", show: false, min: 0 },
    series: [
      {
        type: "line",
        data: props.values,
        symbol: "none",
        lineStyle: { width: 2, color },
        areaStyle: { color, opacity: 0.1 },
      },
    ],
  };
});
</script>
