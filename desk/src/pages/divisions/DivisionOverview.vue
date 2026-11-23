<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Business overview')"
      :subtitle="
        __('Leads, sales, quotations and projects across your divisions.')
      "
    >
      <template #right-header>
        <Button
          size="md"
          :aria-label="__('Refresh')"
          :loading="overview.loading"
          @click="overview.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          size="md"
          :label="__('Reports')"
          :route="{ name: 'DivisionReports', query: route.query }"
        >
          <template #prefix>
            <LucideFileSpreadsheet class="size-[18px]" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <DivisionFilters
          v-model:division="division"
          v-model:period="period"
          v-model:custom="custom"
          :options="overview.data?.options || []"
          :loading="overview.loading"
        />

        <TaskyState
          v-if="overview.error && !overview.data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          error
          :icon="noAccess ? LucideLock : LucideCircleAlert"
          :title="
            noAccess
              ? __('This overview isn\'t for you')
              : __('Couldn\'t load the overview')
          "
          :message="
            noAccess
              ? __(
                  'It is for Super Admins and the managers of a division. Ask a Super Admin if you need it.'
                )
              : errorText(overview.error, __('Try again in a minute.'))
          "
        >
          <Button
            v-if="!noAccess"
            :label="__('Try again')"
            @click="overview.reload()"
          />
        </TaskyState>

        <TaskyState
          v-else-if="!range"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :icon="LucideCalendarRange"
          :title="__('Pick both dates')"
          :message="__('Choose a from and a to date to see that period.')"
        />

        <div
          v-else-if="!overview.data"
          class="flex flex-col gap-4"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div
            class="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4"
          >
            <div
              v-for="i in 10"
              :key="i"
              class="h-[104px] animate-pulse rounded-xl bg-surface-gray-3"
            />
          </div>
          <div class="h-80 animate-pulse rounded-xl bg-surface-gray-3" />
        </div>

        <template v-else>
          <!-- consolidated or one division: always said in words -->
          <p
            class="flex items-center gap-2 text-p-sm text-ink-gray-7"
            role="status"
          >
            <component
              :is="data.rows.length > 1 ? LucideLayers : LucideMapPin"
              class="size-4 shrink-0 text-ink-gray-6"
              aria-hidden="true"
            />
            <span>{{ scopeText }}</span>
          </p>

          <div
            v-for="problem in data.errors"
            :key="problem.division"
            role="status"
            class="flex items-start gap-2 rounded-xl bg-warning-soft px-4 py-3.5 text-p-sm text-warning"
          >
            <LucideTriangleAlert
              class="mt-0.5 size-4 shrink-0"
              aria-hidden="true"
            />
            <span>
              {{
                __(
                  "{0}: customers and quotations are left out ({1})",
                  problem.division,
                  problem.error
                )
              }}
            </span>
          </div>

          <section
            :aria-label="__('Key figures')"
            class="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4"
            :class="overview.loading ? 'opacity-60' : ''"
          >
            <StatTile
              v-for="kpi in kpis"
              :key="kpi.key"
              :label="kpi.label"
              :value="kpi.value"
              :sub="kpi.sub"
              :icon="kpi.icon"
              :icon-tone="kpi.tone"
            />
          </section>

          <div
            class="grid grid-cols-1 gap-4 lg:grid-cols-2"
            :class="overview.loading ? 'opacity-60' : ''"
          >
            <DashboardChart
              v-for="chart in charts"
              :key="chart.title"
              :chart="chart"
              :wide="chart.width === 'full'"
              :currency="data.currency"
              value-format="short"
              :empty-text="__('Nothing in this period.')"
            />
          </div>

          <!-- the divisions side by side -->
          <section
            v-if="data.rows.length > 1"
            class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            aria-labelledby="division-compare"
          >
            <h2
              id="division-compare"
              class="border-b border-outline-gray-2 px-4 py-4 text-base font-semibold text-ink-gray-9"
            >
              {{ __("Divisions compared") }}
            </h2>
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr
                    class="h-11 bg-surface-gray-1 text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6"
                  >
                    <th scope="col" class="pl-4 pr-3 text-left">
                      {{ __("Division") }}
                    </th>
                    <th
                      v-for="column in COMPARE"
                      :key="column.key"
                      scope="col"
                      class="whitespace-nowrap px-3 text-right"
                    >
                      {{ column.label }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in data.rows"
                    :key="row.name"
                    class="h-14 border-b border-outline-gray-1 last:border-0 hover:bg-surface-gray-1"
                  >
                    <th
                      scope="row"
                      class="pl-4 pr-3 text-left font-medium text-ink-gray-9"
                    >
                      {{ row.division_name }}
                      <span class="block text-p-xs font-normal text-ink-gray-6">
                        {{ row.country }}
                      </span>
                    </th>
                    <td
                      v-for="column in COMPARE"
                      :key="column.key"
                      class="whitespace-nowrap px-3 text-right font-mono tabular-nums text-ink-gray-8"
                    >
                      {{
                        reportCell(column.kind, row[column.key], data.currency)
                      }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import DashboardChart from "./DashboardChart.vue";
import { formatValue } from "./chartLook";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, usePageMeta } from "frappe-ui";
import { computed, watch, type Component } from "vue";
import { useRoute } from "vue-router";
import LucideActivity from "~icons/lucide/activity";
import LucideBanknote from "~icons/lucide/banknote";
import LucideBuilding2 from "~icons/lucide/building-2";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideFileSpreadsheet from "~icons/lucide/file-spreadsheet";
import LucideFileText from "~icons/lucide/file-text";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucideFolderOpen from "~icons/lucide/folder-open";
import LucideLayers from "~icons/lucide/layers";
import LucideLock from "~icons/lucide/lock";
import LucideMapPin from "~icons/lucide/map-pin";
import LucidePercent from "~icons/lucide/percent";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUsers from "~icons/lucide/users";
import LucideUserRound from "~icons/lucide/user-round";
import DivisionFilters from "./DivisionFilters.vue";
import { useDivisionFilters } from "./useDivisionFilters";
import {
  OVERVIEW_API,
  overviewCharts,
  reportCell,
  type Overview,
  type ReportColumn,
} from "./divisions";

usePageMeta(() => ({ title: __("Business overview") }));

const route = useRoute();
const { division, period, custom, range, params } = useDivisionFilters();

const overview = createResource<Overview>({
  url: `${OVERVIEW_API}.get_overview`,
  makeParams: () => params.value,
});

watch(
  params,
  () => {
    if (range.value) overview.reload();
  },
  { immediate: true }
);

const data = computed(() => overview.data as Overview);
const noAccess = computed(() => overview.error?.exc_type === "PermissionError");

const scopeText = computed(() => {
  const names = data.value.rows.map((r) => r.division_name);
  return names.length > 1
    ? __("Consolidated: {0}", names.join(", "))
    : __("{0} division only", names[0] || "");
});

const COMPARE: ReportColumn[] = [
  { key: "employees", label: __("People"), kind: "int" },
  { key: "leads", label: __("Leads"), kind: "int" },
  { key: "conversion_rate", label: __("Conversion"), kind: "percent" },
  { key: "customers", label: __("Customers"), kind: "int" },
  { key: "quotations", label: __("Quotations"), kind: "int" },
  { key: "sales_value", label: __("Sales value"), kind: "money" },
  { key: "active_projects", label: __("Open projects"), kind: "int" },
  { key: "pending_tasks", label: __("Pending activities"), kind: "int" },
];

const kpis = computed(() => {
  const k = data.value.kpis;
  const count = (v: number | null) => formatValue("count", v, null);
  const tiles: {
    key: string;
    label: string;
    value: string;
    sub?: string;
    icon: Component;
    tone?: "brand" | "success" | "danger" | "info";
  }[] = [
    {
      key: "divisions",
      label: __("Divisions"),
      value: count(k.divisions),
      icon: LucideBuilding2,
    },
    {
      key: "employees",
      label: __("Employees"),
      value: count(k.employees),
      sub: __("Members of these divisions"),
      icon: LucideUserRound,
    },
    {
      key: "leads",
      label: __("Leads"),
      value: count(k.leads),
      sub: __("Created in the period"),
      icon: LucideUsers,
      tone: "brand",
    },
    {
      key: "conversion_rate",
      label: __("Lead conversion"),
      value: formatValue("percent", k.conversion_rate, null),
      sub: __("Won or converted"),
      icon: LucidePercent,
      tone: "info",
    },
    {
      key: "customers",
      label: __("Customers"),
      value: count(k.customers),
      sub: __("Enabled, on the ERP sites"),
      icon: LucideBuilding2,
    },
    {
      key: "quotations",
      label: __("Quotations"),
      value: count(k.quotations),
      sub: __("Dated in the period"),
      icon: LucideFileText,
    },
    {
      key: "sales_value",
      label: __("Sales value"),
      value: formatValue("money", k.sales_value, data.value.currency, "short"),
      sub: __("Ordered quotations"),
      icon: LucideBanknote,
      tone: "success",
    },
    {
      key: "projects",
      label: __("Projects"),
      value: count(k.projects),
      icon: LucideFolderKanban,
    },
    {
      key: "active_projects",
      label: __("Active projects"),
      value: count(k.active_projects),
      sub: __("Open now"),
      icon: LucideFolderOpen,
    },
    {
      key: "pending_activities",
      label: __("Pending activities"),
      value: count(k.pending_activities),
      sub: __("Open tasks on these divisions' projects"),
      icon: LucideActivity,
    },
  ];
  return tiles;
});

const charts = computed(() => overviewCharts(data.value));
</script>
