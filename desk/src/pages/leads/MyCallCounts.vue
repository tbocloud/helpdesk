<template>
  <!-- hidden quietly while the ERP site's TBO Smart can't count them, and on a failed read -->
  <section
    v-if="counts.data?.available"
    class="flex flex-col gap-3"
    :aria-label="__('Leads you contacted')"
  >
    <div class="flex items-center justify-between gap-2">
      <h2 class="text-base font-semibold text-ink-gray-9">
        {{ __("Leads you contacted") }}
      </h2>
      <Button
        :label="__('By day')"
        :disabled="!counts.data.days?.length"
        @click="showDays = true"
      >
        <template #prefix>
          <LucideCalendarDays class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>
    <div class="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4">
      <StatTile
        v-for="period in PERIODS"
        :key="period.key"
        :label="period.label"
        :value="contactedIn(counts.data[period.key]).toLocaleString()"
        :sub="
          __(
            '{0} calls · {1} answered',
            (counts.data[period.key]?.calls ?? 0).toLocaleString(),
            (counts.data[period.key]?.connected ?? 0).toLocaleString()
          )
        "
      />
    </div>
  </section>

  <Dialog
    :open="showDays"
    size="md"
    :title="__('Leads you contacted by day')"
    @update:open="(value: boolean) => (showDays = value)"
  >
    <div>
      <p class="mb-3 text-p-sm text-ink-gray-6">
        {{
          __(
            "As the Daily report counts them: a lead counts once a day you call it, move its stage or complete its follow-up, so a lead moved to Contacted without a logged call counts. Calls are every call you made or took; answered are the ones picked up. Days with neither are left out."
          )
        }}
      </p>
      <div class="max-h-[60vh] overflow-y-auto">
        <table class="w-full text-sm">
          <thead class="sticky top-0 bg-surface-base">
            <tr
              class="h-11 border-b border-outline-gray-2 text-left text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6"
            >
              <th scope="col" class="px-3 first:pl-0">{{ __("Day") }}</th>
              <th scope="col" class="px-3 text-right last:pl-3 last:pr-0">
                {{ __("Contacted") }}
              </th>
              <th scope="col" class="px-3 text-right last:pl-3 last:pr-0">
                {{ __("Calls") }}
              </th>
              <th scope="col" class="px-3 text-right last:pl-3 last:pr-0">
                {{ __("Answered") }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="day in counts.data?.days ?? []"
              :key="day.date"
              class="border-t border-outline-gray-1"
            >
              <td class="py-3 pr-3 text-ink-gray-8">
                {{ dayLabel(day.date) }}
              </td>
              <td
                class="px-3 py-3 text-right font-mono tabular-nums text-ink-gray-9"
              >
                {{ contactedIn(day) }}
              </td>
              <td
                class="px-3 py-3 text-right font-mono tabular-nums text-ink-gray-7"
              >
                {{ day.calls }}
              </td>
              <td
                class="py-3 pl-3 text-right font-mono tabular-nums text-ink-gray-7"
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
import StatTile from "@/components/StatTile.vue";
import { __ } from "@/translation";
import { Button, createResource, dayjs, Dialog } from "frappe-ui";
import { ref } from "vue";
import LucideCalendarDays from "~icons/lucide/calendar-days";

/** `contacted`: distinct leads reached by a call, a stage move or a completed follow-up */
type Tally = { calls: number; connected: number; contacted?: number };
type MyCallCounts = {
  available: boolean;
  today?: Tally;
  week?: Tally;
  month?: Tally;
  all_time?: Tally;
  /** newest first; only days with calls */
  days?: ({ date: string } & Tally)[];
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

// a TBO Smart older than v1.35 sends no `contacted`; its answered calls are the closest figure
function contactedIn(tally?: Tally) {
  return tally?.contacted ?? tally?.connected ?? 0;
}

function dayLabel(date: string) {
  const day = dayjs(date);
  if (day.isSame(dayjs(), "day")) return __("Today");
  if (day.isSame(dayjs().subtract(1, "day"), "day")) return __("Yesterday");
  return day.format("ddd, D MMM YYYY");
}

// Refresh reads past the server's 60-second cache
defineExpose({ reload: () => counts.submit({ days: 366, fresh: 1 }) });
</script>
