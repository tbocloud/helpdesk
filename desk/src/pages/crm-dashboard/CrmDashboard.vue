<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="flex min-w-0 items-center gap-2">
          <h1 class="truncate text-lg-medium text-ink-gray-9">{{ title }}</h1>
          <TaskyBadge
            v-if="page.data && !page.data.is_active"
            :label="__('Inactive')"
          />
          <Dropdown v-if="switchOptions.length > 1" :options="switchOptions">
            <Button
              variant="ghost"
              :label="__('Switch dashboard')"
              :aria-label="__('Switch dashboard')"
            >
              <template #icon>
                <LucideChevronsUpDown class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </Dropdown>
        </div>
      </template>
      <template #right-header>
        <Button
          v-if="canConfigure"
          :label="__('Configure')"
          @click="openSettings"
        >
          <template #prefix>
            <LucideSettings2 class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="relative min-h-0 flex-1 overflow-y-auto bg-surface-gray-1">
      <div class="mx-auto flex max-w-screen-2xl flex-col gap-5 p-4 md:p-5">
        <!-- nobody may open a dashboard yet -->
        <TaskyState
          v-if="dashboards.data && !dashboards.data.dashboards.length"
          :icon="LucideLayoutDashboard"
          :title="
            canConfigure
              ? __('No CRM dashboards yet')
              : __('There\'s no dashboard for you yet')
          "
          :message="
            canConfigure
              ? __(
                  'Connect a data source, then make a dashboard from a template in Settings → CRM dashboards.'
                )
              : __('Ask an admin to give your role a CRM dashboard.')
          "
        >
          <Button
            v-if="canConfigure"
            variant="solid"
            :label="__('Set up dashboards')"
            @click="openSettings"
          />
        </TaskyState>

        <TaskyState
          v-else-if="page.error && !page.data"
          error
          :icon="noAccess ? LucideLock : LucideCircleAlert"
          :title="
            noAccess
              ? __('You can\'t open this dashboard')
              : __('Couldn\'t load the dashboard')
          "
          :message="
            noAccess
              ? __('Ask an admin to give your role this dashboard.')
              : errorText(
                  page.error,
                  __('Check your connection and try again.')
                )
          "
        >
          <Button
            v-if="!noAccess"
            :label="__('Try again')"
            @click="page.reload()"
          />
          <Button
            v-else-if="dashboardId"
            :label="__('Open my dashboard')"
            @click="openDashboard('')"
          />
        </TaskyState>

        <!-- loading: the tiles' and panels' shape is known -->
        <div
          v-else-if="!page.data"
          class="flex flex-col gap-5"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div class="h-16 animate-pulse rounded-xl bg-surface-gray-2" />
          <div
            class="grid grid-cols-[repeat(auto-fill,minmax(11rem,1fr))] gap-3"
          >
            <div
              v-for="i in 6"
              :key="i"
              class="h-[104px] animate-pulse rounded-xl bg-surface-gray-2"
            />
          </div>
          <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div
              v-for="i in 2"
              :key="i"
              class="h-80 animate-pulse rounded-xl bg-surface-gray-2"
            />
          </div>
        </div>

        <TaskyState
          v-else-if="page.data.setup_needed"
          :icon="LucideDatabase"
          :title="
            canConfigure
              ? __('Connect a data source first')
              : __('This dashboard isn\'t ready yet')
          "
          :message="
            canConfigure
              ? __(
                  'The dashboard counts the leads of the companies you connect. Add one under Data sources.'
                )
              : __(
                  'No company\'s leads are connected yet. An admin is setting it up.'
                )
          "
        >
          <Button
            v-if="canConfigure"
            variant="solid"
            :label="__('Add a data source')"
            @click="openSettings"
          />
        </TaskyState>

        <TaskyState
          v-else-if="page.data.not_placed"
          :icon="LucideNetwork"
          :title="__('You aren\'t placed in the organisation yet')"
          :message="
            __(
              'This dashboard shows each person their own part of the leads. Ask an admin to link your user to an employee or a team under Settings → CRM dashboards → Organisation.'
            )
          "
        />

        <template v-else>
          <!-- the period and filters: kept in the URL, so a view can be shared -->
          <div
            class="flex flex-col gap-2"
            role="group"
            :aria-label="__('Period and filters')"
          >
            <div class="flex flex-wrap items-end gap-3">
              <FormControl
                variant="outline"
                :model-value="selectedPeriod"
                type="select"
                class="w-full sm:w-44"
                :label="__('Period')"
                :options="periodOptions"
                @update:model-value="setPeriod"
              />
              <template v-if="isCustom">
                <FormControl
                  variant="outline"
                  :model-value="custom.from"
                  type="date"
                  class="w-full sm:w-40"
                  :label="__('From')"
                  @update:model-value="setCustom('from', $event)"
                />
                <FormControl
                  variant="outline"
                  :model-value="custom.to"
                  type="date"
                  class="w-full sm:w-40"
                  :label="__('To')"
                  @update:model-value="setCustom('to', $event)"
                />
              </template>
              <FormControl
                variant="outline"
                v-for="filter in shownFilters"
                :key="filter.key"
                :model-value="filter.value"
                type="select"
                class="w-full sm:w-44"
                :label="filter.label"
                :disabled="!filter.options.length && !filter.value"
                :options="[{ label: __('All'), value: '' }, ...filter.options]"
                @update:model-value="setFilter(filter.key, $event)"
              />
              <Button
                v-if="moreFilters"
                variant="outline"
                :aria-expanded="allFilters"
                :label="
                  allFilters
                    ? __('Fewer filters')
                    : __('More filters ({0})', String(moreFilters))
                "
                @click="filtersOpen = !filtersOpen"
              >
                <template #prefix>
                  <LucideSlidersHorizontal class="size-4" aria-hidden="true" />
                </template>
              </Button>
              <Button
                v-if="anyFilter"
                variant="ghost"
                :label="__('Clear filters')"
                @click="clearFilters"
              />
              <p
                class="ml-auto flex items-center gap-1.5 self-end pb-2 text-p-xs text-ink-gray-6"
              >
                <LucideLoaderCircle
                  v-if="page.loading"
                  class="size-3.5 animate-spin motion-reduce:animate-none"
                  aria-hidden="true"
                />
                <span aria-live="polite">{{ freshness }}</span>
              </p>
            </div>
          </div>

          <div
            v-for="notice in page.data.notices"
            :key="notice.kind + notice.text"
            role="status"
            class="flex flex-wrap items-start gap-2 rounded-md px-3 py-2 text-p-sm"
            :class="
              notice.tone === 'danger'
                ? 'bg-danger-soft text-danger'
                : 'bg-warning-soft text-warning'
            "
          >
            <component
              :is="
                notice.tone === 'danger'
                  ? LucideCircleAlert
                  : LucideTriangleAlert
              "
              class="mt-0.5 size-4 shrink-0"
              aria-hidden="true"
            />
            <span class="min-w-0 flex-1">{{ notice.text }}</span>
            <Button
              v-if="canConfigure"
              :label="
                notice.kind === 'unmapped_statuses'
                  ? __('Map statuses')
                  : __('Check the source')
              "
              @click="openSettings"
            />
          </div>

          <TaskyState
            v-if="isCustom && !customReady"
            :icon="LucideCalendarRange"
            :title="__('Pick both dates')"
            :message="__('Choose a from and a to date to see that period.')"
          />

          <template v-else>
            <!-- the first three cards are the headline; the rest a balanced strip -->
            <section
              v-if="page.data.kpis.length"
              :aria-label="__('Key figures')"
              class="flex flex-col gap-3"
              :class="page.loading ? 'opacity-60' : ''"
            >
              <div
                class="grid grid-cols-1 gap-3"
                :class="HEADLINE_COLS[headline.length]"
              >
                <StatTile
                  v-for="(card, i) in headline"
                  :key="i"
                  v-bind="tile(card)"
                  :tint="
                    card.missing ? undefined : METRIC_LOOK[card.metric]?.tone
                  "
                >
                  <Sparkline
                    v-if="card.trend.some((v) => v)"
                    :values="card.trend"
                    :tone="METRIC_LOOK[card.metric]?.tone || 'brand'"
                    :label="trendLabel(card)"
                  />
                </StatTile>
              </div>
              <div
                v-if="strip.length"
                class="grid grid-cols-2 gap-3"
                :class="STRIP_COLS[stripCols]"
              >
                <StatTile
                  v-for="(card, i) in strip"
                  :key="i"
                  compact
                  class="border-l-4"
                  :class="
                    TONE_SECTION[METRIC_LOOK[card.metric]?.tone || 'info']
                      .border
                  "
                  v-bind="tile(card)"
                />
              </div>
            </section>

            <div
              v-if="page.data.charts.length"
              class="grid grid-cols-1 gap-4 lg:grid-cols-2"
              :class="page.loading ? 'opacity-60' : ''"
            >
              <DashboardChart
                v-for="(chart, i) in page.data.charts"
                :key="i + chart.title"
                :chart="chart"
                :wide="chartWidths[i] === 'full'"
                :currency="page.data.currency"
                :value-format="page.data.value_format"
              />
            </div>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import {
  setActiveSettingsTab,
  showSettingsModal,
} from "@/components/Settings/settingsModal";
import StatTile from "@/components/StatTile.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  dayjs,
  Dropdown,
  FormControl,
  usePageMeta,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideChevronsUpDown from "~icons/lucide/chevrons-up-down";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideDatabase from "~icons/lucide/database";
import LucideLayoutDashboard from "~icons/lucide/layout-dashboard";
import LucideLoaderCircle from "~icons/lucide/loader-circle";
import LucideLock from "~icons/lucide/lock";
import LucideNetwork from "~icons/lucide/network";
import LucideSettings2 from "~icons/lucide/settings-2";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import { monthLabel } from "@/pages/leads/business/businessFormat";
import LucideSlidersHorizontal from "~icons/lucide/sliders-horizontal";
import DashboardChart from "./DashboardChart.vue";
import Sparkline from "./Sparkline.vue";
import {
  formatValue,
  kpiChange,
  METRIC_LOOK,
  TONE_SECTION,
  type DashboardPage,
  type KpiCard,
  type DashboardSummary,
  type MetricKind,
} from "./crmDashboard";

const CUSTOM = "custom";

const route = useRoute();
const router = useRouter();

const dashboardId = computed(() => String(route.params.dashboardId || ""));

const dashboards = createResource<{
  dashboards: DashboardSummary[];
  can_configure: boolean;
}>({
  url: "helpdesk.api.crm_dashboard.get_dashboards",
  auto: true,
});

/** The URL's picks: `period`, `from`, `to` and one value per filter. With none, the
 * dashboard opens on its own defaults. */
const urlPicks = computed<Record<string, string>>(() => {
  const picks: Record<string, string> = {};
  for (const [key, value] of Object.entries(route.query)) {
    if (typeof value === "string" && value) picks[key] = value;
  }
  return picks;
});

const custom = computed(() => ({
  from: urlPicks.value.from || "",
  to: urlPicks.value.to || "",
}));
// the URL's pick shows at once, before the page has loaded it
const selectedPeriod = computed(
  () => urlPicks.value.period || page.data?.period.key || ""
);
const isCustom = computed(() => selectedPeriod.value === CUSTOM);
const customReady = computed(() => !!(custom.value.from && custom.value.to));

const page = createResource<DashboardPage>({
  url: "helpdesk.api.crm_dashboard.get_dashboard",
  makeParams: () => {
    const { from, to, ...filters } = urlPicks.value;
    return {
      name: dashboardId.value || undefined,
      filters: Object.keys(urlPicks.value).length
        ? { ...filters, from_date: from, to_date: to }
        : null,
    };
  },
  auto: true,
});

watch([dashboardId, urlPicks], () => {
  // a custom period waits for both of its dates
  if (urlPicks.value.period === CUSTOM && !customReady.value) return;
  page.reload();
});

const title = computed(() => page.data?.dashboard_name || __("CRM dashboard"));
usePageMeta(() => ({ title: title.value }));
const canConfigure = computed(
  () => !!(page.data?.can_configure || dashboards.data?.can_configure)
);
const noAccess = computed(() => {
  const e = page.error as { exc_type?: string } | null;
  return e?.exc_type === "PermissionError";
});

const switchOptions = computed(() =>
  (dashboards.data?.dashboards || []).map((d) => ({
    label: d.is_active
      ? d.dashboard_name
      : __("{0} (inactive)", d.dashboard_name),
    onClick: () => openDashboard(d.name),
  }))
);

const periodOptions = computed(() => [
  ...Object.entries(page.data?.periods || {}).map(([value, label]) => ({
    label,
    value,
  })),
  { label: __("Custom dates"), value: CUSTOM },
]);

const anyFilter = computed(
  () => !!page.data?.filters.some((filter) => filter.value)
);

const freshness = computed(() => {
  if (page.loading) return __("Updating…");
  const synced = page.data?.synced_on;
  return synced
    ? __("Figures as of {0}.", dayjs(synced).fromNow())
    : __("A data source hasn't been read yet; its leads aren't counted.");
});

// full class strings, so Tailwind finds them
const HEADLINE_COLS: Record<number, string> = {
  1: "",
  2: "sm:grid-cols-2",
  3: "sm:grid-cols-3",
  4: "sm:grid-cols-2 lg:grid-cols-4",
};
const STRIP_COLS: Record<number, string> = {
  2: "lg:grid-cols-2",
  3: "sm:grid-cols-3",
  4: "sm:grid-cols-4",
  5: "sm:grid-cols-3 lg:grid-cols-5",
};
// four cards or fewer all lead; more: three lead and the rest follow in a strip
const headlineCount = computed(() => {
  const n = page.data?.kpis.length || 0;
  return n <= 4 ? n : 3;
});
const headline = computed(() =>
  (page.data?.kpis || []).slice(0, headlineCount.value)
);
const strip = computed(() =>
  (page.data?.kpis || []).slice(headlineCount.value)
);
/** As many columns as leave no card alone on its row: 8 cards are 4 and 4. */
const stripCols = computed(() => {
  const n = strip.value.length;
  if (n <= 5) return Math.max(n, 2);
  return [4, 5, 3].find((cols) => n % cols === 0) || 4;
});

function tile(card: KpiCard) {
  const look = METRIC_LOOK[card.metric];
  const change = kpiChange(
    card,
    page.data?.currency || null,
    page.data?.value_format || "short"
  );
  return {
    label: card.label,
    value: value(card.kind, card.value),
    sub: card.missing || card.period_label || undefined,
    icon: look?.icon,
    iconTone: card.missing ? "neutral" : look?.tone,
    delta: change?.delta ?? null,
    deltaText: change?.text,
    deltaTone: change?.tone,
  };
}

/** "Last 6 months: Jun 26 12, Jul 26 18, …", for a screen reader. */
function trendLabel(card: KpiCard) {
  const months = page.data?.trend_months || [];
  return __(
    "Last {0} months: {1}",
    String(months.length),
    months
      .map(
        (m, i) => `${monthLabel(m, true)} ${value(card.kind, card.trend[i])}`
      )
      .join(", ")
  );
}

// the first two filters show; the rest open with More filters, and stay open while
// one of them is picked
const SHOWN_FILTERS = 2;
const filtersOpen = ref(false);
const moreFilters = computed(() =>
  Math.max(0, (page.data?.filters.length || 0) - SHOWN_FILTERS)
);
const allFilters = computed(
  () =>
    filtersOpen.value ||
    !!page.data?.filters.slice(SHOWN_FILTERS).some((filter) => filter.value)
);
const shownFilters = computed(() =>
  (page.data?.filters || []).slice(
    0,
    allFilters.value ? undefined : SHOWN_FILTERS
  )
);

/** Each chart's width: a half chart alone on its row widens, so no row has a hole. */
const chartWidths = computed(() => {
  const widths = (page.data?.charts || []).map((chart) => chart.width);
  for (let i = 0; i < widths.length; ) {
    if (widths[i] === "half" && widths[i + 1] === "half") i += 2;
    else {
      widths[i] = "full";
      i += 1;
    }
  }
  return widths;
});

function value(kind: MetricKind, amount: number | null) {
  return formatValue(
    kind,
    amount,
    page.data?.currency || null,
    page.data?.value_format
  );
}

/** What is on screen now, as URL picks: the defaults count until something is picked. */
function currentPicks(): Record<string, string> {
  if (Object.keys(urlPicks.value).length || !page.data)
    return { ...urlPicks.value };
  const picks: Record<string, string> = { period: page.data.period.key };
  for (const filter of page.data.filters) {
    if (filter.value) picks[filter.key] = filter.value;
  }
  return picks;
}

function pick(changes: Record<string, string>) {
  const picks = { ...currentPicks(), ...changes };
  // a company's branches, a branch's teams...: a choice clears the ones below it
  for (const filter of page.data?.filters || []) {
    if (filter.parents.some((parent) => parent in changes))
      delete picks[filter.key];
  }
  const query = Object.fromEntries(Object.entries(picks).filter(([, v]) => v));
  router.replace({ query });
}

function setPeriod(period: string) {
  const changes: Record<string, string> = { period };
  if (period !== CUSTOM) Object.assign(changes, { from: "", to: "" });
  pick(changes);
}

function setCustom(edge: "from" | "to", date: string) {
  pick({ period: CUSTOM, [edge]: date });
}

function setFilter(key: string, value: string) {
  pick({ [key]: value });
}

function clearFilters() {
  const keys = (page.data?.filters || []).map((filter) => filter.key);
  pick(Object.fromEntries(keys.map((key) => [key, ""])));
}

function openDashboard(name: string) {
  router.push({
    name: "CrmDashboard",
    params: { dashboardId: name || undefined },
  });
}

function openSettings() {
  showSettingsModal.value = true;
  setActiveSettingsTab("CRM dashboards");
}
</script>
