<template>
  <div class="flex flex-col items-center gap-4">
    <!-- screen readers can't read the chart, so its numbers are in the label and the legend -->
    <div class="relative size-44 shrink-0" role="img" :aria-label="summary">
      <ECharts
        :options="options"
        :events="{ click: onClick }"
        class="h-full w-full"
      />
      <div
        class="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"
        aria-hidden="true"
      >
        <span class="text-xs text-ink-gray-5">{{ __("Total active") }}</span>
        <span class="text-3xl font-semibold tabular-nums text-ink-gray-9">
          {{ split.total }}
        </span>
      </div>
    </div>

    <ul class="grid w-full grid-cols-2 gap-1" :aria-label="__('Legend')">
      <li v-for="part in parts" :key="part.key">
        <button
          v-if="part.key !== 'other'"
          type="button"
          class="flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          :class="
            selected === part.key
              ? 'bg-brand-soft text-ink-gray-9'
              : 'text-ink-gray-7 hover:bg-surface-gray-2'
          "
          :aria-pressed="selected === part.key"
          @click="emit('select', part.key)"
        >
          <span
            class="size-2.5 shrink-0 rounded-full"
            :style="{ background: part.color }"
            aria-hidden="true"
          />
          <span class="min-w-0 flex-1 truncate">{{ part.label }}</span>
          <span class="font-mono text-xs tabular-nums text-ink-gray-9">
            {{ part.value }}
          </span>
        </button>
        <div
          v-else
          class="flex items-center gap-2 px-2 py-1 text-sm text-ink-gray-6"
        >
          <span
            class="size-2.5 shrink-0 rounded-full"
            :style="{ background: part.color }"
            aria-hidden="true"
          />
          <span class="min-w-0 flex-1 truncate">{{ part.label }}</span>
          <span class="font-mono text-xs tabular-nums">{{ part.value }}</span>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import {
  baseOptions,
  tooltipRow,
  useChartColors,
  type ChartColors,
} from "@/pages/performance/chartTheme";
import { __ } from "@/translation";
import { ECharts } from "frappe-ui";
import { computed } from "vue";
import {
  URGENCY_ORDER,
  type ActiveSplit,
  type Bucket,
  type Urgency,
} from "../overviewMeta";

type Part = Urgency | "other";

const props = defineProps<{
  split: ActiveSplit;
  selected: Bucket;
  labels: Record<Urgency, string>;
}>();
const emit = defineEmits<{ (e: "select", bucket: Urgency): void }>();
const colors = useChartColors();

// status colours only for the parts that mean trouble; key and the rest stay gray
function colorOf(c: ChartColors, key: Part) {
  return {
    overdue: c.danger,
    at_risk: c.warning,
    due_soon: c.info,
    key: c.textSecondary,
    other: c.axis,
  }[key];
}

const parts = computed(() =>
  [...URGENCY_ORDER, "other" as const].map((key) => ({
    key,
    label: key === "other" ? __("Other") : props.labels[key],
    value: props.split[key] ?? 0,
    color: colorOf(colors.value, key),
  }))
);

const summary = computed(() =>
  [
    __("Active work: {0} in total.", String(props.split.total ?? 0)),
    parts.value.map((p) => `${p.label} ${p.value}`).join(", "),
  ].join(" ")
);

function onClick(params: { data?: { key?: Part } }) {
  const key = params.data?.key;
  if (key && key !== "other") emit("select", key);
}

const options = computed(() => {
  const c = colors.value;
  const total = props.split.total ?? 0;
  const focused = URGENCY_ORDER.includes(props.selected as Urgency);
  return {
    ...baseOptions(c),
    tooltip: {
      ...baseOptions(c).tooltip,
      trigger: "item",
      formatter: (p: any) =>
        tooltipRow(
          p.color,
          p.name,
          `${p.value} · ${total ? Math.round((p.value / total) * 100) : 0}%`
        ),
    },
    series: [
      {
        type: "pie",
        radius: ["68%", "92%"],
        avoidLabelOverlap: false,
        label: { show: false },
        labelLine: { show: false },
        itemStyle: { borderColor: c.surface, borderWidth: 2, borderRadius: 4 },
        emphasis: { scale: true, scaleSize: 4 },
        data: total
          ? parts.value
              .filter((p) => p.value)
              .map((p) => ({
                key: p.key,
                name: p.label,
                value: p.value,
                cursor: p.key === "other" ? "default" : "pointer",
                itemStyle: {
                  color: p.color,
                  // the part whose list is open below stays at full strength
                  opacity: !focused || p.key === props.selected ? 1 : 0.45,
                },
              }))
          : [
              {
                key: "other",
                name: __("Nothing active"),
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
