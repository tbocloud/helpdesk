<template>
  <!-- the year is its months compared: each month's figures and its champion -->
  <SectionCard
    :title="__('Month by month')"
    :description="
      __(
        'Each month starts fresh on the 1st. A closed month shows the champion kept when it ended.'
      )
    "
    class="overflow-hidden"
  >
    <div
      class="hidden gap-3 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2 text-xs text-ink-gray-5 lg:grid"
      :class="GRID"
      aria-hidden="true"
    >
      <span>{{ __("Month") }}</span>
      <span class="text-right">{{ __("Done") }}</span>
      <span class="text-right">{{ __("Weighted") }}</span>
      <span class="text-right">{{ __("On time") }}</span>
      <span class="text-right">{{ __("Quality") }}</span>
      <span>{{ __("Champion") }}</span>
    </div>
    <ul role="list">
      <li
        v-for="row in months"
        :key="row.month"
        class="border-b border-outline-gray-1 last:border-b-0"
      >
        <NativeButton
          v-if="!row.future"
          type="button"
          class="flex w-full flex-col gap-1 px-4 py-2.5 text-left transition-colors hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4 lg:grid lg:items-center lg:gap-3"
          :class="GRID"
          :aria-label="__('Show {0}', monthName(row))"
          @click="emit('open', row.month)"
        >
          <span class="flex items-center justify-between gap-2">
            <span class="text-base text-ink-gray-9">{{ monthName(row) }}</span>
            <LucideChevronRight
              class="size-4 shrink-0 text-ink-gray-4 lg:hidden"
              aria-hidden="true"
            />
          </span>
          <!-- small screens: one labelled line -->
          <span
            class="flex flex-wrap gap-x-3 gap-y-0.5 text-p-sm tabular-nums text-ink-gray-6 lg:hidden"
          >
            <span>{{
              __(
                "{0} done · {1} weighted",
                String(row.tasks ?? 0),
                weightText(row.weight)
              )
            }}</span>
            <span>{{ __("{0} on time", pctText(row.on_time_pct)) }}</span>
            <span>{{ __("quality {0}", qualityText(row.quality)) }}</span>
          </span>
          <span class="hidden text-right font-mono tabular-nums lg:block">
            {{ row.tasks }}
          </span>
          <span
            class="hidden text-right font-mono tabular-nums text-ink-gray-9 lg:block"
          >
            {{ weightText(row.weight) }}
          </span>
          <span
            class="hidden text-right font-mono tabular-nums lg:block"
            :class="onTimeClass(row.on_time_pct)"
          >
            {{ pctText(row.on_time_pct) }}
          </span>
          <span
            class="hidden text-right font-mono tabular-nums text-ink-gray-7 lg:block"
          >
            {{ qualityText(row.quality) }}
          </span>
          <span class="flex min-w-0 items-center gap-2 text-sm">
            <LucideUser
              class="size-4 shrink-0 text-ink-gray-5"
              aria-hidden="true"
            />
            <template v-if="row.champion">
              <span class="sr-only">{{ __("Champion") }}</span>
              <span class="truncate text-ink-gray-8">{{
                row.champion.name
              }}</span>
              <span class="font-mono text-xs tabular-nums text-ink-gray-5">
                {{ row.champion.score }}
              </span>
            </template>
            <span v-else class="text-ink-gray-5">{{ __("No champion") }}</span>
          </span>
        </NativeButton>
        <div
          v-else
          class="flex items-center justify-between gap-3 px-4 py-2.5 text-p-sm text-ink-gray-5"
        >
          <span>{{ monthName(row) }}</span>
          <span>{{ __("Not started") }}</span>
        </div>
      </li>
    </ul>
  </SectionCard>
</template>

<script setup lang="ts">
import NativeButton from "@/components/NativeButton";
import SectionCard from "@/components/SectionCard.vue";
import { onTimeClass, pctText } from "@/pages/performance/performanceMeta";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideUser from "~icons/lucide/user";
import { qualityText, weightText, type MonthRow } from "../teamDashboardMeta";

defineProps<{ months: MonthRow[] }>();
/** Opens that month on the page (its first day, "YYYY-MM-DD"). */
const emit = defineEmits<{ open: [month: string] }>();

const GRID =
  "lg:grid-cols-[minmax(0,1.2fr)_repeat(4,minmax(0,0.6fr))_minmax(0,1.6fr)]";

function monthName(row: MonthRow) {
  return dayjs(row.month).format("MMMM");
}
</script>
