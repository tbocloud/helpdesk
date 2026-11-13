<template>
  <!-- a card's last months as a thin line: the shape, not exact figures -->
  <svg
    class="mt-2 block h-9 w-full"
    viewBox="0 0 120 36"
    preserveAspectRatio="none"
    role="img"
    :aria-label="label"
  >
    <path :d="shape.area" :style="{ fill: color, opacity: 0.22 }" />
    <path
      :d="shape.line"
      fill="none"
      :stroke="color"
      stroke-width="2.5"
      stroke-linecap="round"
      stroke-linejoin="round"
      vector-effect="non-scaling-stroke"
    />
  </svg>
</template>

<script setup lang="ts">
import { useChartColors } from "@/pages/performance/chartTheme";
import { computed } from "vue";

const props = defineProps<{
  values: (number | null)[];
  /** the tone of the card it sits in */
  tone: "brand" | "info" | "success" | "warning" | "danger";
  /** what a screen reader hears: each month and its figure */
  label: string;
}>();

const W = 120;
const H = 36;
const PAD = 3;

const colors = useChartColors();
const color = computed(() => colors.value[props.tone] || colors.value.brand);

/** The line and its wash; a month with no figure breaks the line there. */
const shape = computed(() => {
  const values = props.values;
  const known = values.filter((v): v is number => v !== null);
  if (!known.length) return { line: "", area: "" };
  const low = Math.min(0, ...known);
  const span = Math.max(...known) - low || 1;
  const step = values.length > 1 ? W / (values.length - 1) : 0;
  const y = (v: number) => H - PAD - ((v - low) / span) * (H - 2 * PAD);
  const runs: [number, number][][] = [[]];
  values.forEach((v, i) => {
    if (v === null) runs.push([]);
    else runs[runs.length - 1].push([i * step, y(v)]);
  });
  let line = "";
  let area = "";
  for (const run of runs.filter((r) => r.length > 1)) {
    const points = run.map(([x, py]) => `${x.toFixed(1)} ${py.toFixed(1)}`);
    line += `M${points.join(" L")} `;
    area += `M${run[0][0].toFixed(1)} ${H} L${points.join(" L")} L${run[
      run.length - 1
    ][0].toFixed(1)} ${H} Z `;
  }
  return { line, area };
});
</script>
