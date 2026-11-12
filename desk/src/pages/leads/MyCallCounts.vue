<template>
  <!-- hidden quietly while the ERP site's TBO Smart can't count them, and on a failed read -->
  <section
    v-if="counts.data?.available"
    class="rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-label="__('Your calls')"
  >
    <div class="flex items-center justify-between gap-2 px-4 pt-3">
      <h2 class="text-sm font-medium text-ink-gray-8">
        {{ __("Your calls") }}
      </h2>
      <Button
        variant="ghost"
        :label="__('By day')"
        :disabled="!counts.data.days?.length"
        @click="showDays = true"
      >
        <template #prefix>
          <LucideCalendarDays class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>
    <dl class="grid grid-cols-2 sm:grid-cols-4">
      <div
        v-for="period in PERIODS"
        :key="period.key"
        class="flex flex-col gap-0.5 px-4 pb-3 pt-2"
      >
        <dt class="text-xs text-ink-gray-5">{{ period.label }}</dt>
        <dd class="font-mono text-xl tabular-nums text-ink-gray-9">
          {{ (counts.data[period.key]?.calls ?? 0).toLocaleString() }}
        </dd>
        <dd class="text-xs text-ink-gray-6">
          {{
            __(
              "{0} contacted",
              (counts.data[period.key]?.connected ?? 0).toLocaleString()
            )
          }}
        </dd>
      </div>
    </dl>
  </section>

  <Dialog
    :open="showDays"
    size="lg"
    :title="__('Your calls by day')"
    @update:open="(value: boolean) => (showDays = value)"
  >
    <div>
      <p class="mb-3 text-p-sm text-ink-gray-6">
        {{
          __(
            "Every call you made or took, as the Daily report counts them; contacted are the answered ones. Days without calls are left out."
          )
        }}
      </p>
      <div class="max-h-[60vh] overflow-y-auto">
        <table class="w-full text-sm">
          <thead class="sticky top-0 bg-surface-base">
            <tr class="text-left text-xs text-ink-gray-5">
              <th scope="col" class="py-2 font-normal">{{ __("Day") }}</th>
              <th scope="col" class="py-2 text-right font-normal">
                {{ __("Calls") }}
              </th>
              <th scope="col" class="py-2 text-right font-normal">
                {{ __("Contacted") }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="day in counts.data?.days ?? []"
              :key="day.date"
              class="border-t border-outline-gray-1"
            >
              <td class="py-2 text-ink-gray-8">{{ dayLabel(day.date) }}</td>
              <td
                class="py-2 text-right font-mono tabular-nums text-ink-gray-9"
              >
                {{ day.calls }}
              </td>
              <td
                class="py-2 text-right font-mono tabular-nums text-ink-gray-7"
              >
                {{ day.connected }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, createResource, dayjs, Dialog } from "frappe-ui";
import { ref } from "vue";
import LucideCalendarDays from "~icons/lucide/calendar-days";

type Tally = { calls: number; connected: number };
type MyCallCounts = {
  available: boolean;
  today?: Tally;
  week?: Tally;
  month?: Tally;
  all_time?: Tally;
  /** newest first; only days with calls */
  days?: { date: string; calls: number; connected: number }[];
};

const PERIODS: {
  key: "today" | "week" | "month" | "all_time";
  label: string;
}[] = [
  { key: "today", label: __("Today") },
  { key: "week", label: __("This week") },
  { key: "month", label: __("This month") },
  { key: "all_time", label: __("All time") },
];

const showDays = ref(false);
const counts = createResource<MyCallCounts>({
  url: "helpdesk.api.leads.get_my_call_counts",
  params: { days: 366 },
  auto: true,
  onError() {},
});

function dayLabel(date: string) {
  const day = dayjs(date);
  if (day.isSame(dayjs(), "day")) return __("Today");
  if (day.isSame(dayjs().subtract(1, "day"), "day")) return __("Yesterday");
  return day.format("ddd, D MMM YYYY");
}

defineExpose({ reload: () => counts.reload() });
</script>
