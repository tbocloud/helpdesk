<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Lead status')"
      :subtitle="__('Every lead status, division by division.')"
    >
      <template #right-header>
        <Button
          size="md"
          :aria-label="__('Refresh')"
          :loading="leads.loading"
          @click="leads.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
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
          :options="leads.data?.options || []"
          :loading="leads.loading"
        >
          <FormControl
            v-for="filter in extraFilters"
            :key="filter.key"
            variant="outline"
            size="md"
            type="select"
            class="w-full sm:w-44"
            :label="filter.label"
            :model-value="query(filter.key)"
            :options="filter.options"
            @update:model-value="setFilter(filter.key, $event)"
          />
          <Button
            v-if="filtered"
            size="md"
            variant="ghost"
            class="mb-0.5"
            :label="__('Clear filters')"
            @click="clearFilters"
          />
        </DivisionFilters>

        <TaskyState
          v-if="leads.error && !leads.data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          error
          :icon="noAccess ? LucideLock : LucideCircleAlert"
          :title="
            noAccess
              ? __('Lead status isn\'t for you')
              : __('Couldn\'t load lead status')
          "
          :message="
            noAccess
              ? __(
                  'It is for Super Admins and the managers of a division. Ask a Super Admin if you need it.'
                )
              : errorText(leads.error, __('Try again in a minute.'))
          "
        >
          <Button
            v-if="!noAccess"
            :label="__('Try again')"
            @click="leads.reload()"
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
          v-else-if="!leads.data"
          class="flex flex-col gap-4"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div
            class="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-4"
          >
            <div
              v-for="i in 6"
              :key="i"
              class="h-[104px] animate-pulse rounded-xl bg-surface-gray-3"
            />
          </div>
          <div class="h-80 animate-pulse rounded-xl bg-surface-gray-3" />
        </div>

        <template v-else>
          <p
            class="flex flex-wrap items-center gap-x-2 gap-y-1 text-p-sm text-ink-gray-7"
            role="status"
          >
            <component
              :is="data.divisions.length > 1 ? LucideLayers : LucideMapPin"
              class="size-4 shrink-0 text-ink-gray-6"
              aria-hidden="true"
            />
            <span>{{ scopeText }}</span>
            <span v-if="syncText" class="text-ink-gray-6">· {{ syncText }}</span>
          </p>

          <div
            v-if="noSite.length"
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
                  "{0}: no ERP site yet, so no leads. A Super Admin sets it in Settings → Divisions.",
                  noSite.join(", ")
                )
              }}
            </span>
          </div>

          <section
            :aria-label="__('Key figures')"
            class="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-4"
            :class="leads.loading ? 'opacity-60' : ''"
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
            :class="leads.loading ? 'opacity-60' : ''"
          >
            <DashboardChart
              v-for="chart in charts"
              :key="chart.title"
              :chart="chart"
              :wide="chart.width === 'full'"
              :currency="data.currency"
              value-format="short"
            />
          </div>

          <!-- every status, a column per division -->
          <section
            class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            aria-labelledby="lead-status-table"
          >
            <header
              class="flex flex-wrap items-baseline justify-between gap-2 border-b border-outline-gray-2 px-4 py-4"
            >
              <h2
                id="lead-status-table"
                class="text-base font-semibold text-ink-gray-9"
              >
                {{ __("Status by division") }}
              </h2>
              <p class="text-p-xs text-ink-gray-6">
                {{ __("Pick a status to see only its leads.") }}
              </p>
            </header>
            <p
              v-if="!data.statuses.length"
              class="px-4 py-10 text-center text-p-sm text-ink-gray-6"
            >
              {{ __("No leads in this period for these filters.") }}
            </p>
            <div v-else class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr :class="HEAD_ROW">
                    <th scope="col" class="pl-4 pr-3 text-left">
                      {{ __("Status") }}
                    </th>
                    <th scope="col" class="px-3 text-left">
                      {{ __("Group") }}
                    </th>
                    <th
                      v-for="d in data.divisions"
                      :key="d.name"
                      scope="col"
                      class="whitespace-nowrap px-3 text-right"
                    >
                      {{ d.division_name }}
                    </th>
                    <th
                      v-if="data.divisions.length > 1"
                      scope="col"
                      class="px-3 text-right"
                    >
                      {{ __("Total") }}
                    </th>
                    <th scope="col" class="pl-3 pr-4 text-right">
                      {{ __("Share") }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in data.statuses"
                    :key="row.status"
                    :class="BODY_ROW"
                  >
                    <th scope="row" class="pl-4 pr-3 text-left font-medium">
                      <button
                        type="button"
                        class="rounded text-ink-gray-9 underline-offset-2 hover:text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                        :aria-label="__('Show only {0} leads', row.status)"
                        @click="setFilter('status', row.status)"
                      >
                        {{ row.status }}
                      </button>
                    </th>
                    <td class="whitespace-nowrap px-3 text-ink-gray-7">
                      <GroupLabel :group="row.group" />
                    </td>
                    <td
                      v-for="d in data.divisions"
                      :key="d.name"
                      :class="NUM_CELL"
                    >
                      {{ count(row.divisions[d.name] || 0) }}
                    </td>
                    <td
                      v-if="data.divisions.length > 1"
                      :class="[NUM_CELL, 'font-semibold text-ink-gray-9']"
                    >
                      {{ count(row.total) }}
                    </td>
                    <td class="pl-3 pr-4">
                      <div class="flex items-center justify-end gap-2">
                        <div
                          class="hidden h-1.5 w-20 overflow-hidden rounded-full bg-surface-gray-3 sm:block"
                          aria-hidden="true"
                        >
                          <div
                            class="h-full rounded-full bg-brand"
                            :style="{ width: `${share(row.total)}%` }"
                          />
                        </div>
                        <span
                          class="w-12 text-right font-mono tabular-nums text-ink-gray-7"
                        >
                          {{ share(row.total) }}%
                        </span>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <LeadBreakdown
              :title="__('By salesperson')"
              :first-label="__('Salesperson')"
              :rows="peopleRows"
              :show-division="data.divisions.length > 1"
              @pick="(key) => setFilter('employee', key)"
            />
            <LeadBreakdown
              :title="__('By lead source')"
              :first-label="__('Lead source')"
              :rows="sourceRows"
              @pick="(key) => setFilter('source', key)"
            />
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  dayjs,
  FormControl,
  usePageMeta,
} from "frappe-ui";
import { computed, watch, type Component } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideBanknote from "~icons/lucide/banknote";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideLayers from "~icons/lucide/layers";
import LucideLock from "~icons/lucide/lock";
import LucideMapPin from "~icons/lucide/map-pin";
import LucidePercent from "~icons/lucide/percent";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideTrophy from "~icons/lucide/trophy";
import LucideUsers from "~icons/lucide/users";
import DashboardChart from "./DashboardChart.vue";
import DivisionFilters from "./DivisionFilters.vue";
import GroupLabel from "./LeadGroupLabel.vue";
import LeadBreakdown from "./LeadBreakdown.vue";
import { formatValue } from "./chartLook";
import { OVERVIEW_API } from "./divisions";
import {
  GROUP_LOOK,
  leadStatusCharts,
  type BreakdownRow,
  type LeadStatusData,
} from "./leadStatus";
import { useDivisionFilters } from "./useDivisionFilters";

usePageMeta(() => ({ title: __("Lead status") }));

const HEAD_ROW =
  "h-11 bg-surface-gray-1 text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6";
const BODY_ROW =
  "h-12 border-b border-outline-gray-1 last:border-0 hover:bg-surface-gray-1";
const NUM_CELL =
  "whitespace-nowrap px-3 text-right font-mono tabular-nums text-ink-gray-8";

const route = useRoute();
const router = useRouter();
const { division, period, custom, range, params } = useDivisionFilters();

// the lead filters, kept in the URL beside the division and period
type FilterKey = "group" | "status" | "employee" | "source";
const FILTER_KEYS: FilterKey[] = ["group", "status", "employee", "source"];
const query = (key: FilterKey) => String(route.query[key] || "");
function setFilter(key: FilterKey, value: string) {
  router.replace({ query: { ...route.query, [key]: value || undefined } });
}
function clearFilters() {
  const next = { ...route.query };
  FILTER_KEYS.forEach((k) => delete next[k]);
  router.replace({ query: next });
}
const filtered = computed(() => FILTER_KEYS.some((k) => query(k)));

const leads = createResource<LeadStatusData>({
  url: `${OVERVIEW_API}.get_lead_status`,
  makeParams: () => ({
    ...params.value,
    group: query("group") || null,
    status: query("status") || null,
    employee: query("employee") || null,
    lead_source: query("source") || null,
  }),
});

watch(
  () => [params.value, ...FILTER_KEYS.map(query)],
  () => {
    if (range.value) leads.reload();
  },
  { immediate: true, deep: true }
);

const data = computed(() => leads.data as LeadStatusData);
const noAccess = computed(() => leads.error?.exc_type === "PermissionError");

const all = (label: string) => ({ label, value: "" });
const extraFilters = computed(() => {
  const f = leads.data?.filters;
  return [
    {
      key: "group" as const,
      label: __("Status group"),
      options: [
        all(__("All groups")),
        ...(leads.data?.groups || []).map((g) => ({
          label: GROUP_LOOK[g].label,
          value: g,
        })),
      ],
    },
    {
      key: "status" as const,
      label: __("Status"),
      options: [
        all(__("All statuses")),
        ...(f?.statuses || []).map((s) => ({ label: s, value: s })),
      ],
    },
    {
      key: "employee" as const,
      label: __("Salesperson"),
      options: [all(__("Everyone")), ...(f?.employees || [])],
    },
    {
      key: "source" as const,
      label: __("Lead source"),
      options: [
        all(__("All sources")),
        ...(f?.lead_sources || []).map((s) => ({ label: s, value: s })),
      ],
    },
  ];
});

const count = (v: number | null) => formatValue("count", v, null);
const share = (n: number) =>
  data.value.kpis.total ? Math.round((100 * n) / data.value.kpis.total) : 0;

const scopeText = computed(() => {
  const names = data.value.divisions.map((d) => d.division_name);
  return names.length > 1
    ? __("Consolidated: {0}", names.join(", "))
    : __("{0} division only", names[0] || "");
});

// the lead copy is as fresh as the divisions' last sync with their ERP sites
const syncText = computed(() => {
  const times = data.value.divisions
    .map((d) => d.last_synced_on)
    .filter(Boolean) as string[];
  if (!times.length) return "";
  const oldest = times.reduce((a, b) => (a < b ? a : b));
  return __("Leads synced from the ERP sites {0}", dayjs(oldest).fromNow());
});

const noSite = computed(() =>
  data.value.divisions.filter((d) => !d.has_site).map((d) => d.division_name)
);

const kpis = computed(() => {
  const k = data.value.kpis;
  const tiles: {
    key: string;
    label: string;
    value: string;
    sub?: string;
    icon: Component;
    tone?: "brand" | "success" | "danger" | "info";
  }[] = [
    {
      key: "total",
      label: __("Leads"),
      value: count(k.total),
      sub: __("Created in the period"),
      icon: LucideUsers,
      tone: "brand",
    },
    {
      key: "open",
      label: __("Open"),
      value: count(k.open),
      sub: __("Still being worked"),
      icon: LucideHourglass,
    },
    {
      key: "won",
      label: __("Won or converted"),
      value: count(k.won + k.converted),
      icon: LucideTrophy,
      tone: "success",
    },
    {
      key: "lost",
      label: __("Lost"),
      value: count(k.lost),
      icon: LucideCircleX,
      tone: "danger",
    },
    {
      key: "conversion",
      label: __("Conversion"),
      value: formatValue("percent", k.conversion_rate, null),
      sub: __("Won or converted of all leads"),
      icon: LucidePercent,
      tone: "info",
    },
    {
      key: "open_value",
      label: __("Open pipeline"),
      value: formatValue("money", k.open_value, data.value.currency, "short"),
      sub: __("Expected revenue of open leads"),
      icon: LucideBanknote,
    },
  ];
  if (k.other) {
    tiles.push({
      key: "other",
      label: __("Not grouped"),
      value: count(k.other),
      sub: __("Statuses not mapped on the ERP site"),
      icon: LucideTriangleAlert,
    });
  }
  return tiles;
});

const charts = computed(() => leadStatusCharts(data.value));

const peopleRows = computed<BreakdownRow[]>(() =>
  data.value.people.map((p) => ({
    key: p.employee,
    id: `${p.division}:${p.employee}`,
    label: p.name || __("No salesperson"),
    division: p.division_name,
    ...p,
  }))
);
const sourceRows = computed<BreakdownRow[]>(() =>
  data.value.lead_sources.map((s) => ({
    key: s.lead_source,
    id: s.lead_source,
    label: s.lead_source || __("No source"),
    ...s,
  }))
);
</script>
