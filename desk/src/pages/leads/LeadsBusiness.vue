<template>
  <div class="flex flex-col gap-5">
    <!-- the period and department: kept in the URL, so a view can be shared -->
    <div
      class="flex flex-wrap items-end gap-3"
      role="group"
      :aria-label="__('Period and department')"
    >
      <div class="overflow-x-auto">
        <TabButtons
          :model-value="period"
          size="md"
          :aria-label="__('Period')"
          :options="PERIODS"
          @update:model-value="setPeriod($event as BusinessPeriod)"
        />
      </div>
      <template v-if="period === 'custom'">
        <FormControl
          v-model="custom.from"
          type="date"
          class="w-40"
          :label="__('From')"
        />
        <FormControl
          v-model="custom.to"
          type="date"
          class="w-40"
          :label="__('To')"
        />
      </template>
      <FormControl
        v-if="departmentOptions.length > 1"
        v-model="department"
        type="select"
        class="w-full sm:w-56"
        :label="__('Department')"
        :options="departmentOptions"
      />
      <FormControl
        v-model="withProfit"
        type="checkbox"
        :label="__('Show profit')"
      />
      <div class="ml-auto flex flex-wrap gap-2">
        <Button
          variant="outline"
          :label="__('Download data (CSV)')"
          :disabled="!data"
          @click="data && downloadCsv(data)"
        >
          <template #prefix>
            <LucideTable class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          variant="solid"
          :label="__('Download as slides (PDF)')"
          :disabled="!data"
          @click="printSlides"
        >
          <template #prefix>
            <LucidePresentation class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>
    </div>

    <TaskyState
      v-if="period === 'custom' && !customReady"
      :icon="LucideCalendarRange"
      :title="__('Pick both dates')"
      :message="__('Choose a from and a to date to see that period.')"
    />

    <TaskyState
      v-else-if="page.error && !data"
      error
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the Business overview')"
      :message="
        errorText(page.error, __('Check your connection and try again.'))
      "
    >
      <Button :label="__('Try again')" @click="refresh()" />
    </TaskyState>

    <TaskyState
      v-else-if="page.data && !page.data.available"
      :icon="LucideCircleAlert"
      :title="__('The ERP site can\'t show this yet')"
      :message="
        __(
          'The Business overview needs the latest TBO Smart on the ERP site. Ask an admin to update it.'
        )
      "
    />

    <!-- loading: the tiles' and panels' shape is known -->
    <div
      v-else-if="!data"
      class="flex flex-col gap-5"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div class="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <div
          v-for="i in 7"
          :key="i"
          class="h-[88px] animate-pulse rounded-xl bg-surface-gray-2"
        />
      </div>
      <div class="grid gap-5 lg:grid-cols-2">
        <div class="h-72 animate-pulse rounded-xl bg-surface-gray-2" />
        <div class="h-72 animate-pulse rounded-xl bg-surface-gray-2" />
      </div>
    </div>

    <template v-else>
      <div
        v-if="page.error"
        role="alert"
        class="flex flex-wrap items-center gap-3 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-3"
      >
        <LucideCircleAlert
          class="size-4 shrink-0 text-danger"
          aria-hidden="true"
        />
        <p class="min-w-0 flex-1 text-p-sm text-ink-gray-8">
          {{
            __(
              "Couldn't update the Business overview: {0} These numbers may be out of date.",
              errorText(page.error, __("Check your connection."))
            )
          }}
        </p>
        <Button :label="__('Try again')" @click="refresh()" />
      </div>

      <p class="text-p-sm text-ink-gray-6">
        {{ periodText }}
        <span v-if="page.loading" class="sr-only" aria-live="polite">{{
          __("Updating")
        }}</span>
      </p>

      <section
        class="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7"
        :aria-label="__('Headline numbers')"
      >
        <StatTile
          v-for="kpi in kpis"
          :key="kpi.key"
          compact
          :label="kpi.label"
          :value="kpi.value"
          :sub="kpi.sub"
          :title="kpi.title"
        />
      </section>

      <div class="grid gap-5 lg:grid-cols-2">
        <section class="panel" :aria-labelledby="ids.revenue">
          <header class="panel-head">
            <h2 :id="ids.revenue" class="text-base-medium text-ink-gray-9">
              {{ __("Revenue by month") }}
            </h2>
            <span class="text-xs text-ink-gray-6">{{
              __("Invoiced and collected, {0}", rangeText(data))
            }}</span>
          </header>
          <div class="p-4">
            <BusinessBars
              :labels="revenue.labels"
              :series="revenue.series"
              :format="(v: number) => shortAmount(v, data!.currency)"
              :aria-label="__('Revenue invoiced and collected, by month')"
            />
          </div>
        </section>

        <section class="panel" :aria-labelledby="ids.funnel">
          <header class="panel-head">
            <h2 :id="ids.funnel" class="text-base-medium text-ink-gray-9">
              {{ __("Funnel") }}
            </h2>
            <span class="text-xs text-ink-gray-6">{{
              __("Of {0} new leads in the period", String(data.new_leads))
            }}</span>
          </header>
          <p v-if="!data.new_leads" class="px-4 py-4 text-p-sm text-ink-gray-6">
            {{ __("No new leads in this period.") }}
          </p>
          <div v-else class="p-4">
            <BusinessRows :rows="funnel" :max="data.new_leads" />
          </div>
        </section>

        <section class="panel" :aria-labelledby="ids.stages">
          <header class="panel-head">
            <h2 :id="ids.stages" class="text-base-medium text-ink-gray-9">
              {{ __("Pipeline by stage") }}
            </h2>
            <span class="text-xs text-ink-gray-6">{{
              __("Open clients now, with quoted value")
            }}</span>
          </header>
          <p v-if="!stages.length" class="px-4 py-4 text-p-sm text-ink-gray-6">
            {{ __("No open clients.") }}
          </p>
          <div v-else class="p-4"><BusinessRows :rows="stages" /></div>
        </section>

        <section class="panel" :aria-labelledby="ids.proposals">
          <header class="panel-head">
            <h2 :id="ids.proposals" class="text-base-medium text-ink-gray-9">
              {{ __("Proposals and onboarding") }}
            </h2>
            <span class="text-xs text-ink-gray-6">{{ rangeText(data) }}</span>
          </header>
          <dl class="grid grid-cols-2 gap-x-4 gap-y-3 p-4 sm:grid-cols-3">
            <div v-for="fact in facts" :key="fact.label" class="min-w-0">
              <dt class="text-xs text-ink-gray-6">{{ fact.label }}</dt>
              <dd
                class="font-mono text-lg tabular-nums text-ink-gray-9"
                :title="fact.title"
              >
                {{ fact.value }}
              </dd>
              <dd v-if="fact.sub" class="text-xs text-ink-gray-6">
                {{ fact.sub }}
              </dd>
            </div>
          </dl>
        </section>

        <section class="panel" :aria-labelledby="ids.trendLeads">
          <header class="panel-head">
            <h2 :id="ids.trendLeads" class="text-base-medium text-ink-gray-9">
              {{ __("Last 6 months: leads and wins") }}
            </h2>
          </header>
          <div class="p-4">
            <BusinessBars
              :labels="trend.labels"
              :series="trend.people"
              :format="(v: number) => String(Math.round(v))"
              :aria-label="__('New leads and clients won, last 6 months')"
            />
          </div>
        </section>

        <section class="panel" :aria-labelledby="ids.trendMoney">
          <header class="panel-head">
            <h2 :id="ids.trendMoney" class="text-base-medium text-ink-gray-9">
              {{ __("Last 6 months: invoiced and collected") }}
            </h2>
          </header>
          <div class="p-4">
            <BusinessBars
              :labels="trend.labels"
              :series="trend.money"
              :format="(v: number) => shortAmount(v, data!.currency)"
              :aria-label="__('Revenue invoiced and collected, last 6 months')"
            />
          </div>
        </section>

        <section class="panel" :aria-labelledby="ids.clients">
          <header class="panel-head">
            <h2 :id="ids.clients" class="text-base-medium text-ink-gray-9">
              {{ __("Top clients by invoiced value") }}
            </h2>
            <span class="text-xs text-ink-gray-6">{{ rangeText(data) }}</span>
          </header>
          <p v-if="!clients.length" class="px-4 py-4 text-p-sm text-ink-gray-6">
            {{ __("Nothing invoiced in this period.") }}
          </p>
          <div v-else class="p-4"><BusinessRows :rows="clients" /></div>
        </section>

        <section
          v-if="data.profit.available"
          class="panel"
          :aria-labelledby="ids.profit"
        >
          <header class="panel-head">
            <h2 :id="ids.profit" class="text-base-medium text-ink-gray-9">
              {{ __("Profit") }}
            </h2>
            <span class="text-xs text-ink-gray-6">{{
              __("Income minus expense, {0}", rangeText(data))
            }}</span>
          </header>
          <dl class="grid grid-cols-3 gap-4 p-4">
            <div v-for="item in profit" :key="item.label">
              <dt class="text-xs text-ink-gray-6">{{ item.label }}</dt>
              <dd
                class="font-mono text-lg tabular-nums text-ink-gray-9"
                :title="item.title"
              >
                {{ item.value }}
              </dd>
            </div>
          </dl>
        </section>
        <section
          v-else-if="withProfit && data.profit.reason"
          class="panel"
          :aria-labelledby="ids.profit"
        >
          <header class="panel-head">
            <h2 :id="ids.profit" class="text-base-medium text-ink-gray-9">
              {{ __("Profit") }}
            </h2>
          </header>
          <p class="px-4 py-4 text-p-sm text-ink-gray-6">
            {{ data.profit.reason }}
          </p>
        </section>
      </div>

      <section class="panel" :aria-labelledby="ids.departments">
        <header class="panel-head">
          <h2 :id="ids.departments" class="text-base-medium text-ink-gray-9">
            {{ __("By department") }}
          </h2>
          <span class="text-xs text-ink-gray-6">{{
            __(
              "Open and money in the period; money not linked to a lead is shown apart"
            )
          }}</span>
        </header>
        <p
          v-if="!data.by_department.length"
          class="px-4 py-4 text-p-sm text-ink-gray-6"
        >
          {{ __("Nothing to split by department yet.") }}
        </p>
        <div v-else class="overflow-x-auto">
          <table class="w-full min-w-[40rem] text-sm">
            <thead>
              <tr class="text-left text-xs text-ink-gray-6">
                <th scope="col" class="px-4 py-2 font-normal">
                  {{ __("Department") }}
                </th>
                <th
                  v-for="col in DEPARTMENT_COLUMNS"
                  :key="col.label"
                  scope="col"
                  class="px-3 py-2 text-right font-normal"
                >
                  {{ col.label }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in data.by_department"
                :key="row.label"
                class="border-t border-outline-gray-1"
              >
                <th
                  scope="row"
                  class="max-w-[14rem] truncate px-4 py-2 text-left font-normal text-ink-gray-9"
                >
                  {{ row.label }}
                </th>
                <td
                  v-for="col in DEPARTMENT_COLUMNS"
                  :key="col.label"
                  class="px-3 py-2 text-right font-mono tabular-nums text-ink-gray-9"
                >
                  {{ col.cell(row, data.currency) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <ul
        role="list"
        class="m-0 flex list-none flex-col gap-1 p-0 text-p-xs text-ink-gray-6"
      >
        <li v-for="note in notes" :key="note">{{ note }}</li>
      </ul>

      <BusinessSlides :data="data" />
    </template>
  </div>
</template>

<script setup lang="ts">
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  dayjs,
  FormControl,
  TabButtons,
} from "frappe-ui";
import { computed, reactive, useId, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucidePresentation from "~icons/lucide/presentation";
import LucideTable from "~icons/lucide/table";
import BusinessBars from "./business/BusinessBars.vue";
import { downloadCsv } from "./business/businessExport";
import {
  businessKpis,
  businessNotes,
  clientRows,
  funnelRows,
  revenueChart,
  stageRows,
  trendCharts,
} from "./business/businessFigures";
import { fullAmount, rangeText, shortAmount } from "./business/businessFormat";
import BusinessRows from "./business/BusinessRows.vue";
import BusinessSlides from "./business/BusinessSlides.vue";
import {
  type BusinessDepartment,
  type BusinessOverview,
  type BusinessPeriod,
  type LeadOptions,
  usableDepartments,
} from "./leads";

const props = defineProps<{ options?: LeadOptions }>();

const PERIODS: { value: BusinessPeriod; label: string }[] = [
  { value: "month", label: __("This month") },
  { value: "last_month", label: __("Last month") },
  { value: "quarter", label: __("This quarter") },
  { value: "fy", label: __("This FY") },
  { value: "custom", label: __("Custom") },
];
const DEPARTMENT_COLUMNS: {
  label: string;
  cell: (row: BusinessDepartment, currency: string) => string;
}[] = [
  { label: __("Open now"), cell: (r) => String(r.open) },
  {
    label: __("Open value"),
    cell: (r, c) => shortAmount(r.open_value, c),
  },
  { label: __("Won"), cell: (r) => String(r.won) },
  { label: __("Won value"), cell: (r, c) => shortAmount(r.won_value, c) },
  { label: __("Invoiced"), cell: (r, c) => shortAmount(r.invoiced, c) },
  { label: __("Collected"), cell: (r, c) => shortAmount(r.collected, c) },
];

const route = useRoute();
const router = useRouter();
const ids = {
  revenue: useId(),
  funnel: useId(),
  stages: useId(),
  proposals: useId(),
  trendLeads: useId(),
  trendMoney: useId(),
  clients: useId(),
  profit: useId(),
  departments: useId(),
};

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}
function setQuery(query: Record<string, string | undefined>) {
  router.replace({ query: { ...route.query, ...query } });
}

const period = computed<BusinessPeriod>(() => {
  const value = queryValue("bperiod");
  return PERIODS.some((p) => p.value === value)
    ? (value as BusinessPeriod)
    : "month";
});
const custom = reactive({ from: queryValue("bfrom"), to: queryValue("bto") });
const customReady = computed(
  () => !!custom.from && !!custom.to && custom.from <= custom.to
);
const department = computed({
  get: () => queryValue("bdept"),
  set: (value: string) => setQuery({ bdept: value || undefined }),
});
const withProfit = computed({
  get: () => queryValue("bprofit") === "1",
  set: (value: boolean) => setQuery({ bprofit: value ? "1" : undefined }),
});
function setPeriod(value: BusinessPeriod) {
  setQuery({ bperiod: value === "month" ? undefined : value });
}
watch(
  () => ({ ...custom }),
  (c) => setQuery({ bfrom: c.from || undefined, bto: c.to || undefined })
);

const departmentOptions = computed(() => {
  const list = usableDepartments(props.options, department.value);
  return list.length
    ? [
        { label: __("All departments"), value: "" },
        ...list.map((d) => ({ label: d.name, value: d.name })),
      ]
    : [];
});

function pageParams(fresh: boolean) {
  return {
    period: period.value,
    from_date: period.value === "custom" ? custom.from : null,
    to_date: period.value === "custom" ? custom.to : null,
    department: department.value || null,
    include_profit: withProfit.value ? 1 : 0,
    fresh: fresh ? 1 : 0,
  };
}

const page = createResource({
  url: "helpdesk.api.leads.get_business_overview",
  makeParams: () => pageParams(false),
});

// the refresh button and "Try again" ask the ERP site again instead of the 60-second copy
function refresh() {
  page.submit(pageParams(true));
}
watch(
  [
    period,
    department,
    withProfit,
    () => customReady.value && `${custom.from}:${custom.to}`,
  ],
  () => {
    if (period.value !== "custom" || customReady.value) page.reload();
  },
  { immediate: true }
);
defineExpose({ reload: refresh });

const data = computed(() =>
  page.data?.available ? (page.data as BusinessOverview) : undefined
);
const periodText = computed(() =>
  __(
    "{0}, {1}. Company-wide figures, for management only.",
    rangeText(data.value!),
    data.value!.department || __("all departments")
  )
);

const kpis = computed(() => businessKpis(data.value!));
const revenue = computed(() => revenueChart(data.value!));
const trend = computed(() => trendCharts(data.value!));
const funnel = computed(() => funnelRows(data.value!));
const stages = computed(() => stageRows(data.value!));
const clients = computed(() => clientRows(data.value!));
const notes = computed(() => businessNotes(data.value!));

const facts = computed(() => {
  const d = data.value!;
  const c = d.currency;
  return [
    {
      label: __("Proposals sent"),
      value: String(d.proposals.sent.count),
      title: fullAmount(d.proposals.sent.value, c),
      sub: shortAmount(d.proposals.sent.value, c),
    },
    {
      label: __("Accepted"),
      value: String(d.proposals.accepted.count),
      title: fullAmount(d.proposals.accepted.value, c),
      sub: shortAmount(d.proposals.accepted.value, c),
    },
    {
      label: __("Acceptance rate"),
      value: `${d.proposals.acceptance_rate}%`,
      title: "",
      sub: __("Accepted of sent, same period"),
    },
    {
      label: __("Declined"),
      value: String(d.proposals.declined),
      title: "",
      sub: "",
    },
    {
      label: __("Clients won"),
      value: String(d.onboarding.won.count),
      title: fullAmount(d.onboarding.won.value, c),
      sub: shortAmount(d.onboarding.won.value, c),
    },
    {
      label: __("Projects started"),
      value: String(d.onboarding.projects_started),
      title: "",
      sub: __("Linked to a hub project"),
    },
    {
      label: __("Meetings held"),
      value: String(d.meetings_held),
      title: "",
      sub: "",
    },
  ];
});
const profit = computed(() => {
  const p = data.value!.profit;
  const c = data.value!.currency;
  return [
    [__("Income"), p.income],
    [__("Expense"), p.expense],
    [__("Profit"), p.profit],
  ].map(([label, value]) => ({
    label: label as string,
    value: shortAmount(value as number, c),
    title: fullAmount(value as number, c),
  }));
});

// the PDF is the browser's print of the slides laid out by BusinessSlides; the file takes
// the report's name for the length of the dialog
function printSlides() {
  const title = document.title;
  document.title = `TBO Business overview ${dayjs(data.value!.from_date).format(
    "D MMM YYYY"
  )} to ${dayjs(data.value!.to_date).format("D MMM YYYY")}`;
  window.addEventListener("afterprint", () => (document.title = title), {
    once: true,
  });
  window.print();
}
</script>

<style scoped>
.panel {
  @apply min-w-0 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base;
}
.panel-head {
  @apply flex flex-wrap items-baseline justify-between gap-2 border-b border-outline-gray-1 px-4 py-3;
}
</style>
