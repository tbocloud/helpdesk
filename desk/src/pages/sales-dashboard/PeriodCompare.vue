<template>
  <!-- the period against the same days of the one before, figure by figure -->
  <CcCard
    accent="violet"
    :icon="LucideChartLine"
    :title="__('Period performance')"
    :sub="__('{0} against the same days of {1}', periodLabel, range)"
  >
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-xs text-ink-gray-6">
          <th scope="col" class="py-1.5 font-medium">
            <span class="sr-only">{{ __("Figure") }}</span>
          </th>
          <th scope="col" class="py-1.5 text-right font-medium">
            {{ __("Now") }}
          </th>
          <th scope="col" class="py-1.5 text-right font-medium">
            {{ __("Before") }}
          </th>
          <th scope="col" class="py-1.5 pl-3 text-right font-medium">
            {{ __("Change") }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.label"
          class="border-t border-outline-gray-1"
        >
          <th scope="row" class="py-2.5 text-left font-normal text-ink-gray-7">
            {{ row.label }}
          </th>
          <td
            class="py-2.5 text-right font-mono font-semibold tabular-nums text-ink-gray-9"
            :title="row.title"
          >
            {{ row.now }}
          </td>
          <td class="py-2.5 text-right font-mono tabular-nums text-ink-gray-6">
            {{ row.before }}
          </td>
          <td class="py-2.5 pl-3 text-right">
            <span
              class="cc-pill inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-xs font-semibold tabular-nums"
              :style="accentStyle(CHANGE_LOOK[row.change.look].accent)"
            >
              <component
                :is="CHANGE_LOOK[row.change.look].icon"
                class="size-3"
                aria-hidden="true"
              />
              {{ row.change.text }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </CcCard>
</template>

<script setup lang="ts">
import { fullAmount, shortAmount } from "@/pages/leads/business/businessFormat";
import { __ } from "@/translation";
import { computed } from "vue";
import LucideArrowDownRight from "~icons/lucide/arrow-down-right";
import LucideArrowUpRight from "~icons/lucide/arrow-up-right";
import LucideChartLine from "~icons/lucide/chart-line";
import LucideMinus from "~icons/lucide/minus";
import CcCard from "./CcCard.vue";
import { accentStyle, type Accent } from "./salesDashboard";

type Figures = {
  new: number;
  contacted: number;
  meetings: number;
  quotations_sent: number;
  won: number;
  won_value: number;
};

const props = defineProps<{
  now: Partial<Figures>;
  before: Partial<Figures>;
  /** "This month" */
  periodLabel: string;
  /** the days before, in words */
  range: string;
  currency: string;
}>();

// more is better for every figure here: up green, down red, each with its arrow
const CHANGE_LOOK: Record<string, { accent?: Accent; icon: unknown }> = {
  up: { accent: "green", icon: LucideArrowUpRight },
  down: { accent: "red", icon: LucideArrowDownRight },
  same: { icon: LucideMinus },
};

const FIGURES: { key: keyof Figures; label: string; money?: boolean }[] = [
  { key: "new", label: __("New leads") },
  { key: "contacted", label: __("Contacted") },
  { key: "meetings", label: __("Meetings held") },
  { key: "quotations_sent", label: __("Proposals sent") },
  { key: "won", label: __("Won") },
  { key: "won_value", label: __("Won value"), money: true },
];

function changeOf(now: number, before: number) {
  if (now === before) return { look: "same" as const, text: __("Same") };
  const look = now > before ? ("up" as const) : ("down" as const);
  if (!before) return { look, text: __("New") };
  const delta = Math.round(((now - before) / before) * 100);
  return { look, text: `${delta > 0 ? "+" : ""}${delta}%` };
}

const rows = computed(() =>
  FIGURES.map((figure) => {
    const now = props.now[figure.key] ?? 0;
    const before = props.before[figure.key] ?? 0;
    const show = (value: number) =>
      figure.money
        ? shortAmount(value, props.currency)
        : value.toLocaleString();
    return {
      label: figure.label,
      now: show(now),
      before: show(before),
      title: figure.money ? fullAmount(now, props.currency) : undefined,
      change: changeOf(now, before),
    };
  })
);
</script>
