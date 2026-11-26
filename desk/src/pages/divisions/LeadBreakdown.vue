<template>
  <section
    class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-labelledby="headingId"
  >
    <h2
      :id="headingId"
      class="border-b border-outline-gray-2 px-4 py-4 text-base font-semibold text-ink-gray-9"
    >
      {{ title }}
    </h2>
    <p
      v-if="!rows.length"
      class="px-4 py-10 text-center text-p-sm text-ink-gray-6"
    >
      {{ __("No leads in this period for these filters.") }}
    </p>
    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr
            class="h-11 bg-surface-gray-1 text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6"
          >
            <th scope="col" class="pl-4 pr-3 text-left">{{ firstLabel }}</th>
            <th v-if="showDivision" scope="col" class="px-3 text-left">
              {{ __("Division") }}
            </th>
            <th
              v-for="c in COLUMNS"
              :key="c.key"
              scope="col"
              class="whitespace-nowrap px-3 text-right last:pr-4"
            >
              {{ c.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in shown"
            :key="row.id"
            class="h-12 border-b border-outline-gray-1 last:border-0 hover:bg-surface-gray-1"
          >
            <th scope="row" class="max-w-[14rem] pl-4 pr-3 text-left font-medium">
              <button
                v-if="row.key"
                type="button"
                class="max-w-full truncate rounded text-ink-gray-9 underline-offset-2 hover:text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                :title="row.label"
                :aria-label="__('Show only the leads of {0}', row.label)"
                @click="emit('pick', row.key)"
              >
                {{ row.label }}
              </button>
              <span v-else class="text-ink-gray-6">{{ row.label }}</span>
            </th>
            <td
              v-if="showDivision"
              class="whitespace-nowrap px-3 text-ink-gray-7"
            >
              {{ row.division }}
            </td>
            <td
              v-for="c in COLUMNS"
              :key="c.key"
              class="whitespace-nowrap px-3 text-right font-mono tabular-nums text-ink-gray-8 last:pr-4"
            >
              {{ c.value(row) }}
            </td>
          </tr>
        </tbody>
      </table>
      <div
        v-if="rows.length > LIMIT"
        class="border-t border-outline-gray-1 px-4 py-2.5"
      >
        <Button
          variant="ghost"
          :label="
            expanded ? __('Show fewer') : __('Show all {0}', rows.length)
          "
          :aria-expanded="expanded"
          @click="expanded = !expanded"
        />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button } from "frappe-ui";
import { computed, ref, useId } from "vue";
import { formatValue } from "./chartLook";
import type { BreakdownRow } from "./leadStatus";

const props = defineProps<{
  title: string;
  firstLabel: string;
  rows: BreakdownRow[];
  showDivision?: boolean;
}>();
const emit = defineEmits<{ pick: [key: string] }>();

const LIMIT = 10;
const headingId = `lead-breakdown-${useId()}`;
const expanded = ref(false);
const shown = computed(() =>
  expanded.value ? props.rows : props.rows.slice(0, LIMIT)
);

const count = (v: number) => formatValue("count", v, null);
const COLUMNS: { key: string; label: string; value: (r: BreakdownRow) => string }[] = [
  { key: "total", label: __("Leads"), value: (r) => count(r.total) },
  { key: "open", label: __("Open"), value: (r) => count(r.open) },
  { key: "won", label: __("Won"), value: (r) => count(r.won + r.converted) },
  { key: "lost", label: __("Lost"), value: (r) => count(r.lost) },
  {
    key: "conversion",
    label: __("Conversion"),
    value: (r) => formatValue("percent", r.conversion_rate, null),
  },
];
</script>
