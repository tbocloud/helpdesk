<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <h1 class="text-lg-medium text-ink-gray-9">
          {{ __("Customer report") }}
        </h1>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="report.loading && !!report.data"
          :aria-label="__('Refresh')"
          @click="report.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          variant="solid"
          :label="__('Download CSV')"
          :tooltip="
            __('The report below as a spreadsheet, with the totals row')
          "
          @click="download"
        >
          <template #prefix>
            <LucideFileSpreadsheet class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <p class="max-w-2xl text-p-sm text-ink-gray-6">
          {{
            __(
              "One month of work per customer: tickets, response times, SLA, ratings, hours logged on their projects and tasks completed. Use it for billing and customer reviews."
            )
          }}
        </p>

        <div
          class="mt-4 flex flex-wrap items-end gap-3"
          role="group"
          :aria-label="__('Report filters')"
        >
          <div class="w-full sm:w-52">
            <FormControl
              v-model="month"
              type="select"
              :label="__('Month')"
              :options="monthOptions"
            />
          </div>
          <div class="w-full sm:w-60">
            <Link
              v-model="customer"
              doctype="HD Customer"
              :label="__('Customer')"
              :placeholder="__('All customers')"
            />
          </div>
          <Button
            v-if="customer"
            variant="ghost"
            :label="__('All customers')"
            @click="customer = ''"
          >
            <template #prefix>
              <LucideX class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>

        <TaskyState
          v-if="report.error && !report.data"
          class="mt-5"
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the report')"
          :message="
            errorText(report.error, __('Check your connection and try again.'))
          "
          error
        >
          <Button :label="__('Retry')" @click="report.reload()" />
        </TaskyState>

        <template v-else>
          <section
            :aria-label="__('Totals for {0}', scopeLabel)"
            class="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
          >
            <StatTile
              :label="__('Tickets opened')"
              :value="totals ? totals.tickets_opened : '–'"
              :icon="LucideInbox"
              :loading="loading"
            />
            <StatTile
              :label="__('Tickets resolved')"
              :value="totals ? totals.tickets_resolved : '–'"
              :sub="resolveSub"
              :icon="LucideCircleCheckBig"
              icon-tone="success"
              :loading="loading"
            />
            <StatTile
              :label="__('SLA met')"
              :value="totals ? cell(totals, 'sla_kept_percent') : '–'"
              :sub="slaSub"
              :icon="slaLow ? LucideTriangleAlert : LucideTimer"
              :icon-tone="slaLow ? 'danger' : 'neutral'"
              :value-tone="slaLow ? 'danger' : 'neutral'"
              :loading="loading"
            />
            <StatTile
              :label="__('Tasks done')"
              :value="totals ? totals.tasks_completed : '–'"
              :icon="LucideListChecks"
              icon-tone="success"
              :loading="loading"
            />
            <StatTile
              :label="__('Hours logged')"
              :value="totals ? cell(totals, 'hours_logged') : '–'"
              :icon="LucideClock"
              icon-tone="info"
              :loading="loading"
            />
          </section>

          <SectionCard
            class="mt-6 overflow-hidden"
            :title="__('By customer')"
            :count="loading ? undefined : rows.length"
            :description="
              __(
                'Most hours first. A customer shows up when it had tickets, time or finished tasks in the month.'
              )
            "
            :aria-busy="report.loading"
          >
            <div v-if="loading" :aria-label="__('Loading')">
              <div
                v-for="i in 5"
                :key="i"
                class="flex items-center gap-4 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0"
              >
                <span
                  class="h-3.5 w-1/4 animate-pulse rounded bg-surface-gray-2"
                />
                <span
                  class="ml-auto h-3.5 w-1/3 animate-pulse rounded bg-surface-gray-2"
                />
              </div>
            </div>

            <TaskyState
              v-else-if="!rows.length && customer"
              :icon="LucideSearchX"
              :title="__('Nothing for {0} in {1}', customer, monthLabel)"
              :message="
                __(
                  'No tickets, timesheets or completed tasks for this customer in the month.'
                )
              "
            >
              <Button
                :label="__('Show all customers')"
                @click="customer = ''"
              />
            </TaskyState>
            <TaskyState
              v-else-if="!rows.length"
              :icon="LucideFileSpreadsheet"
              :title="__('Nothing in {0}', monthLabel)"
              :message="
                __(
                  'No tickets, timesheets or completed tasks in this month. Pick another month.'
                )
              "
            />

            <template v-else>
              <!-- md and up: the full table -->
              <div class="hidden md:block">
                <table
                  class="w-full text-sm"
                  :class="report.loading ? 'opacity-60' : ''"
                >
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
                        class="max-w-[14rem] truncate px-4 py-2.5 text-left font-normal text-ink-gray-8"
                      >
                        <CustomerName :customer="row.customer" />
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
                  <tfoot v-if="rows.length > 1">
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
                        {{ cell(totals!, col.key) }}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>

              <!-- small screens: one block per customer with labelled figures -->
              <ul role="list" class="md:hidden">
                <li
                  v-for="row in rows"
                  :key="row.customer"
                  class="border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
                >
                  <div class="truncate text-sm text-ink-gray-9">
                    <CustomerName :customer="row.customer" />
                  </div>
                  <dl class="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    <div
                      v-for="col in COLUMNS"
                      :key="col.key"
                      class="flex items-baseline justify-between gap-2"
                    >
                      <dt class="text-ink-gray-5">{{ col.label }}</dt>
                      <dd
                        class="font-mono tabular-nums"
                        :class="cellClass(row, col.key)"
                      >
                        {{ cell(row, col.key) }}
                      </dd>
                    </div>
                  </dl>
                </li>
              </ul>
            </template>
          </SectionCard>

          <p class="mt-2 text-p-xs text-ink-gray-5">
            {{
              __(
                "Tickets count by the day they were opened or resolved; hours by the day they were logged. First reply and resolution are average hours. Ratings are out of 5."
              )
            }}
          </p>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Link from "@/components/frappe-ui/Link.vue";
import LayoutHeader from "@/components/LayoutHeader.vue";
import SectionCard from "@/components/SectionCard.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { watchDebounced } from "@vueuse/core";
import { Button, createResource, dayjs, FormControl } from "frappe-ui";
import { computed, defineComponent, h, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheckBig from "~icons/lucide/circle-check-big";
import LucideClock from "~icons/lucide/clock";
import LucideFileSpreadsheet from "~icons/lucide/file-spreadsheet";
import LucideInbox from "~icons/lucide/inbox";
import LucideListChecks from "~icons/lucide/list-checks";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSearchX from "~icons/lucide/search-x";
import LucideTimer from "~icons/lucide/timer";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideX from "~icons/lucide/x";

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
  "customer" | "sla_kept" | "sla_failed" | "ratings"
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
  { key: "sla_kept_percent", label: __("SLA met") },
  { key: "avg_rating", label: __("Rating") },
  { key: "hours_logged", label: __("Hours") },
  { key: "tasks_completed", label: __("Tasks done") },
];
const MONTHS_BACK = 12;
const LOW_SLA_PERCENT = 80;
const LOW_RATING = 3;
const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

/** A customer's name linking to its page, or "No customer" for unlinked work. */
const CustomerName = defineComponent({
  props: { customer: { type: String, default: "" } },
  setup(props) {
    return () =>
      props.customer
        ? h(
            RouterLink,
            {
              to: { name: "Customer", params: { id: props.customer } },
              class:
                "rounded hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4",
            },
            () => props.customer
          )
        : h("span", { class: "text-ink-gray-5" }, __("No customer"));
  },
});

// --- filters, kept in the URL so a report can be shared ---

const route = useRoute();
const router = useRouter();

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}

const lastMonth = dayjs().subtract(1, "month").format("YYYY-MM");
const month = ref(
  MONTH_PATTERN.test(queryValue("month")) ? queryValue("month") : lastMonth
);
const customer = ref(queryValue("customer"));

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
  makeParams: () => ({
    month: month.value,
    customer: customer.value || undefined,
  }),
  auto: true,
});

watchDebounced(
  [month, customer],
  () => {
    router.replace({
      query: {
        ...route.query,
        month: month.value === lastMonth ? undefined : month.value,
        customer: customer.value || undefined,
      },
    });
    report.reload();
  },
  { debounce: 100 }
);

const data = computed<Report | null>(() => report.data ?? null);
const rows = computed(() => data.value?.customers ?? []);
const totals = computed(() => data.value?.totals ?? null);
const loading = computed(() => report.loading && !report.data);
const monthLabel = computed(() =>
  dayjs(`${month.value}-01`).format("MMMM YYYY")
);
const scopeLabel = computed(() =>
  customer.value ? `${customer.value}, ${monthLabel.value}` : monthLabel.value
);

const slaLow = computed(
  () =>
    totals.value?.sla_kept_percent != null &&
    totals.value.sla_kept_percent < LOW_SLA_PERCENT
);

const slaSub = computed(() => {
  const t = totals.value;
  if (!t) return undefined;
  const judged = t.sla_kept + t.sla_failed;
  if (!judged) return __("No resolved tickets with an SLA");
  return __("{0} of {1} resolved in time", String(t.sla_kept), String(judged));
});

const resolveSub = computed(() => {
  const t = totals.value;
  if (!t?.avg_rating) return undefined;
  return __("Rated {0}/5 on average", String(t.avg_rating));
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
  const params = new URLSearchParams({ month: month.value });
  if (customer.value) params.set("customer", customer.value);
  window.open(
    `/api/method/helpdesk.api.customer_report.download_customer_report?${params}`,
    "_blank"
  );
}
</script>
