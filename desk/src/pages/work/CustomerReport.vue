<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">
          {{ __("Customer report") }}
        </div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="report.loading"
          :aria-label="__('Refresh')"
          @click="report.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button :label="__('Download CSV')" @click="download">
          <template #prefix>
            <LucideFileSpreadsheet class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <div class="flex flex-wrap items-end justify-between gap-3">
          <p class="max-w-xl text-p-sm text-ink-gray-6">
            {{
              __(
                "One month of work per customer: tickets, response times, SLA, ratings, hours logged on their projects and tasks completed. Use it for billing and customer reviews."
              )
            }}
          </p>
          <div class="w-full sm:w-52">
            <FormControl
              v-model="month"
              type="select"
              :label="__('Month')"
              :options="monthOptions"
            />
          </div>
        </div>

        <TaskyState
          v-if="report.error && !report.data"
          class="mt-3"
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the report')"
          :message="errorText(report.error, __('Try again.'))"
          error
        >
          <Button :label="__('Retry')" @click="report.reload()" />
        </TaskyState>

        <template v-else>
          <section
            :aria-label="__('Totals')"
            class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4"
          >
            <div
              v-for="tile in tiles"
              :key="tile.label"
              class="flex flex-col gap-2 rounded-lg border border-outline-gray-2 bg-surface-base p-4"
            >
              <span class="text-sm text-ink-gray-6">{{ tile.label }}</span>
              <span
                v-if="report.loading && !report.data"
                class="h-7 w-12 animate-pulse rounded bg-surface-gray-2"
              />
              <span
                v-else
                class="font-mono text-2xl-semibold tabular-nums text-ink-gray-9"
              >
                {{ tile.value }}
              </span>
            </div>
          </section>

          <div
            class="mt-3 overflow-x-auto rounded-lg border border-outline-gray-2 bg-surface-base"
          >
            <TaskyState
              v-if="!report.loading && !rows.length"
              :icon="LucideFileSpreadsheet"
              :title="__('Nothing in this month')"
              :message="
                __(
                  'No tickets, timesheets or completed tasks for {0}.',
                  monthLabel
                )
              "
            />
            <table v-else class="w-full min-w-[56rem] text-sm">
              <caption class="sr-only">
                {{
                  __("Customer report for {0}", monthLabel)
                }}
              </caption>
              <thead>
                <tr
                  class="border-b border-outline-gray-2 bg-surface-gray-1 text-left text-xs text-ink-gray-5"
                >
                  <th scope="col" class="px-4 py-2 font-normal">
                    {{ __("Customer") }}
                  </th>
                  <th
                    v-for="col in COLUMNS"
                    :key="col.key"
                    scope="col"
                    class="px-3 py-2 text-right font-normal"
                    :title="col.hint"
                  >
                    {{ col.label }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in rows"
                  :key="row.customer"
                  class="border-b border-outline-gray-1 last:border-b-0"
                >
                  <th
                    scope="row"
                    class="max-w-[16rem] truncate px-4 py-2.5 text-left font-normal text-ink-gray-8"
                  >
                    <RouterLink
                      v-if="row.customer"
                      :to="{ name: 'Customer', params: { id: row.customer } }"
                      class="rounded hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                    >
                      {{ row.customer }}
                    </RouterLink>
                    <span v-else class="text-ink-gray-5">
                      {{ __("No customer") }}
                    </span>
                  </th>
                  <td
                    v-for="col in COLUMNS"
                    :key="col.key"
                    class="px-3 py-2.5 text-right font-mono tabular-nums"
                    :class="cellClass(row, col.key)"
                  >
                    {{ cell(row, col.key) }}
                  </td>
                </tr>
              </tbody>
              <tfoot v-if="report.data">
                <tr
                  class="border-t border-outline-gray-2 bg-surface-gray-1 text-ink-gray-9"
                >
                  <th scope="row" class="px-4 py-2.5 text-left font-medium">
                    {{ __("Total") }}
                  </th>
                  <td
                    v-for="col in COLUMNS"
                    :key="col.key"
                    class="px-3 py-2.5 text-right font-mono font-medium tabular-nums"
                  >
                    {{ cell(report.data.totals, col.key) }}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
          <p class="mt-2 text-p-xs text-ink-gray-5">
            {{
              __(
                "Tickets count by the day they were opened or resolved; hours by the day they were logged. Ratings are out of 5."
              )
            }}
          </p>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { errorText } from "@/utils";
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { Button, createResource, dayjs, FormControl } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideFileSpreadsheet from "~icons/lucide/file-spreadsheet";
import LucideRefreshCw from "~icons/lucide/refresh-cw";

interface ReportRow {
  customer: string;
  tickets_opened: number;
  tickets_resolved: number;
  avg_first_reply_hours: number | null;
  avg_resolution_hours: number | null;
  sla_kept: number;
  sla_failed: number;
  sla_kept_percent: number | null;
  ratings: number;
  avg_rating: number | null;
  hours_logged: number;
  tasks_completed: number;
}

interface Report {
  month: string;
  customers: ReportRow[];
  totals: ReportRow;
}

type ColumnKey = Exclude<
  keyof ReportRow,
  "customer" | "sla_kept" | "sla_failed"
>;

const COLUMNS: { key: ColumnKey; label: string; hint?: string }[] = [
  { key: "tickets_opened", label: __("Opened") },
  { key: "tickets_resolved", label: __("Resolved") },
  {
    key: "avg_first_reply_hours",
    label: __("First reply"),
    hint: __("Average time to the first reply, in hours"),
  },
  {
    key: "avg_resolution_hours",
    label: __("Resolution"),
    hint: __("Average time to resolve, in hours"),
  },
  { key: "sla_kept_percent", label: __("SLA kept") },
  { key: "avg_rating", label: __("Rating") },
  { key: "hours_logged", label: __("Hours") },
  { key: "tasks_completed", label: __("Tasks done") },
];
const MONTHS_BACK = 12;
const LOW_SLA_PERCENT = 80;
const LOW_RATING = 3;

const lastMonth = dayjs().subtract(1, "month").format("YYYY-MM");
const month = ref(lastMonth);

const monthOptions = Array.from({ length: MONTHS_BACK + 1 }, (_v, i) => {
  const m = dayjs().subtract(i, "month");
  return {
    label:
      i === 0
        ? __("{0} (so far)", m.format("MMMM YYYY"))
        : m.format("MMMM YYYY"),
    value: m.format("YYYY-MM"),
  };
});

const report = createResource({
  url: "helpdesk.api.customer_report.get_customer_report",
  makeParams: () => ({ month: month.value }),
  auto: true,
});
watch(month, () => report.reload());

const data = computed<Report | null>(() => report.data ?? null);
const rows = computed(() => data.value?.customers ?? []);
const monthLabel = computed(() =>
  dayjs(`${month.value}-01`).format("MMMM YYYY")
);

const tiles = computed(() => {
  const t = data.value?.totals;
  return [
    { label: __("Tickets resolved"), value: t ? t.tickets_resolved : "–" },
    { label: __("SLA kept"), value: t ? cell(t, "sla_kept_percent") : "–" },
    { label: __("Customer rating"), value: t ? cell(t, "avg_rating") : "–" },
    { label: __("Hours logged"), value: t ? cell(t, "hours_logged") : "–" },
  ];
});

function cell(row: ReportRow, key: ColumnKey): string {
  const value = row[key];
  if (value === null || value === undefined) return "–";
  if (key === "sla_kept_percent") return `${value}%`;
  if (key === "avg_rating") return `${value}/5`;
  if (key === "hours_logged") return Number(value).toFixed(1);
  return String(value);
}

function cellClass(row: ReportRow, key: ColumnKey): string {
  // colour only where a number needs attention; the value itself says why
  if (key === "sla_kept_percent" && row.sla_kept_percent !== null)
    return row.sla_kept_percent < LOW_SLA_PERCENT
      ? "text-danger"
      : "text-ink-gray-8";
  if (key === "avg_rating" && row.avg_rating !== null)
    return row.avg_rating < LOW_RATING ? "text-warning" : "text-ink-gray-8";
  return row[key] ? "text-ink-gray-8" : "text-ink-gray-4";
}

function download() {
  window.open(
    `/api/method/helpdesk.api.customer_report.download_customer_report?month=${month.value}`,
    "_blank"
  );
}
</script>
