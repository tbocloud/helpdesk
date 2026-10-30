<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <h1 class="text-lg-medium text-ink-gray-9">{{ __("Leads") }}</h1>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="isList && leads.loading && !!data"
          :aria-label="__('Refresh')"
          @click="refresh"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button variant="solid" :label="__('New lead')" @click="showNew = true">
          <template #prefix>
            <LucidePlus class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <div class="flex flex-col gap-3">
          <div class="overflow-x-auto">
            <TabButtons
              :model-value="view"
              size="md"
              :aria-label="__('Which leads')"
              :options="tabs"
              @update:model-value="
                view = $event as LeadTab;
                picked = true;
              "
            />
          </div>
          <!-- the Daily report has the day's new leads itself, and loads in one request -->
          <template
            v-if="view !== 'daily' && view !== 'today' && view !== 'business'"
          >
            <!-- hidden quietly until the ERP site's TBO Smart counts it, and on a failed read -->
            <div
              v-if="!intakeData && intakeLoading"
              class="h-[118px] animate-pulse rounded-xl bg-surface-gray-2 md:h-[94px]"
              aria-hidden="true"
            />
            <LeadIntakeStrip v-else-if="intakeOn" :intake="intakeData!" />
          </template>
        </div>

        <!-- the batch of calls for this slot; it replaces Call today for those who have it -->
        <TodaysCalls v-if="view === 'today'" ref="todayPanel" class="mt-4" />

        <LeadsOverview
          v-else-if="view === 'overview'"
          ref="overviewPanel"
          class="mt-4"
          @intake="takeOverviewIntake"
        />

        <!-- the Daily Sales Performance Report; only when the ERP site has it -->
        <LeadsDailyReport
          v-else-if="view === 'daily'"
          ref="dailyPanel"
          class="mt-4"
        />

        <!-- management only: the ERP site decides who (System Manager or TBO Management) -->
        <template v-else-if="view === 'business'">
          <LeadsBusiness
            v-if="canViewBusiness"
            ref="businessPanel"
            class="mt-4"
            :options="options"
          />
        </template>

        <div v-else class="mt-3 flex flex-col gap-3">
          <div
            class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(14rem,2fr)_repeat(4,minmax(9rem,1fr))]"
            role="group"
            :aria-label="__('Filter the leads')"
          >
            <FormControl
              v-model="search"
              type="search"
              :label="__('Search')"
              :placeholder="__('Name, company, email or mobile')"
              autocomplete="off"
            >
              <template #prefix>
                <LucideSearch
                  class="size-4 text-ink-gray-5"
                  aria-hidden="true"
                />
              </template>
            </FormControl>
            <FormControl
              v-model="filters.stage"
              type="select"
              :label="__('Stage')"
              :options="stageOptions"
            />
            <FormControl
              v-model="filters.owner"
              type="select"
              :label="__('Owner')"
              :options="ownerOptions"
            />
            <FormControl
              v-model="filters.segment"
              type="select"
              :label="__('Segment')"
              :options="choices(options?.segments, __('Any segment'))"
            />
            <FormControl
              v-if="departmentFilter.length"
              v-model="filters.department"
              type="select"
              :label="__('Department')"
              :options="departmentFilter"
            />
            <FormControl
              v-if="intakeOn"
              v-model="created"
              type="select"
              :label="__('Created')"
              :options="CREATED"
            />
          </div>
          <LeadCategoryFilters
            ref="categoryPanel"
            v-model="categories"
            :options="options"
          />
          <div
            v-if="created === 'custom'"
            class="flex flex-wrap items-end gap-3"
            role="group"
            :aria-label="__('Created between')"
          >
            <FormControl
              v-model="extra.from"
              type="date"
              class="w-40"
              :label="__('From')"
            />
            <FormControl
              v-model="extra.to"
              type="date"
              class="w-40"
              :label="__('To')"
            />
          </div>
          <div
            v-if="hasFilters || canCategorise"
            class="flex flex-wrap items-center justify-end gap-2"
          >
            <template v-if="canCategorise">
              <span
                v-if="selecting"
                class="mr-auto font-mono text-p-sm tabular-nums text-ink-gray-7"
                aria-live="polite"
                >{{ __("{0} selected", String(selected.size)) }}</span
              >
              <Button
                v-if="selecting"
                :label="__('Select this page')"
                @click="selectPage"
              />
              <Button
                v-if="selecting"
                variant="solid"
                :label="__('Set category')"
                :disabled="!selected.size"
                @click="showSet = true"
              />
              <Button
                :label="selecting ? __('Done') : __('Select leads')"
                @click="toggleSelecting"
              >
                <template #prefix>
                  <LucideListChecks class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </template>
            <!-- what the Overview opened this list with -->
            <span
              v-for="chip in extraChips"
              :key="chip"
              class="rounded-full bg-surface-gray-2 px-2.5 py-1 text-xs text-ink-gray-8"
              >{{ chip }}</span
            >
            <Button
              v-if="hasFilters"
              variant="ghost"
              :label="__('Clear filters')"
              @click="clearFilters"
            >
              <template #prefix>
                <LucideX class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
        </div>

        <template v-if="isList">
          <TaskyState
            v-if="waitingForDates"
            class="mt-6"
            :icon="LucideCalendarRange"
            :title="__('Pick both dates')"
            :message="
              __('Choose a from and a to date to see the leads created then.')
            "
          />
          <TaskyState
            v-else-if="leads.error && !data"
            class="mt-6"
            error
            :icon="LucideCircleAlert"
            :title="__('Couldn\'t load the leads')"
            :message="
              errorText(leads.error, __('Check your connection and try again.'))
            "
          >
            <Button :label="__('Try again')" @click="leads.reload()" />
          </TaskyState>

          <!-- loading: the rows' shape is known -->
          <div
            v-else-if="!data"
            class="mt-4 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            aria-busy="true"
            :aria-label="__('Loading')"
          >
            <div
              v-for="i in 6"
              :key="i"
              class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-4 last:border-b-0"
            >
              <div class="flex flex-1 flex-col gap-2">
                <div
                  class="h-3.5 w-1/3 animate-pulse rounded bg-surface-gray-2"
                />
                <div
                  class="h-3 w-1/2 animate-pulse rounded bg-surface-gray-2"
                />
              </div>
              <div class="h-5 w-20 animate-pulse rounded bg-surface-gray-2" />
            </div>
          </div>

          <TaskyState
            v-else-if="!data.total && (hasFilters || view !== 'all')"
            class="mt-6"
            :icon="LucideSearchX"
            :title="__('No leads match')"
            :message="
              __(
                'Nothing in this view with these filters. Try All, or clear the filters.'
              )
            "
          >
            <Button :label="__('Show all leads')" @click="showAll" />
          </TaskyState>

          <TaskyState
            v-else-if="!data.total"
            class="mt-6"
            :icon="LucideUserPlus"
            :title="__('No leads yet')"
            :message="
              __(
                'Leads you can see on the ERP site show up here. Add the first one when someone shows interest.'
              )
            "
          >
            <Button
              variant="solid"
              :label="__('New lead')"
              @click="showNew = true"
            />
          </TaskyState>

          <template v-else>
            <ul
              class="mt-4 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
              role="list"
              :aria-label="__('Leads')"
              :aria-busy="leads.loading"
            >
              <li
                v-for="row in data.rows"
                :key="row.name"
                class="flex items-center border-b border-outline-gray-1 last:border-b-0"
              >
                <Checkbox
                  v-if="selecting"
                  class="ml-4 shrink-0"
                  :model-value="selected.has(row.name)"
                  :label="__('Select {0}', row.lead_name || row.name)"
                  @update:model-value="toggleRow(row.name)"
                />
                <router-link
                  :to="{ name: 'Lead', params: { leadId: row.name } }"
                  class="flex min-w-0 flex-1 flex-col gap-2 px-4 py-3 transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4 md:flex-row md:items-center md:gap-4"
                >
                  <div class="flex min-w-0 flex-1 flex-col gap-0.5">
                    <div class="flex min-w-0 flex-wrap items-center gap-2">
                      <span
                        class="truncate text-base-medium text-ink-gray-9"
                        :title="row.lead_name || row.name"
                        >{{ row.lead_name || row.name }}</span
                      >
                      <TaskyBadge
                        v-if="row.tbo_stage"
                        :label="stageLabel(options, row.tbo_stage)"
                        :tone="stageTone(options, row.tbo_stage)"
                      />
                      <!-- gone quiet: no activity for longer than its department allows -->
                      <TaskyBadge
                        v-if="quiet.get(row.name)"
                        tone="warning"
                        :icon="LucideClock"
                        :label="
                          __(
                            'No activity {0} days',
                            String(quiet.get(row.name))
                          )
                        "
                        class="font-normal tabular-nums"
                      />
                      <!-- where it stands with the client: the proposal or quotation -->
                      <TaskyBadge
                        v-if="statuses.get(row.name)"
                        :label="statuses.get(row.name)!.label"
                        :tone="statuses.get(row.name)!.tone"
                        :title="statuses.get(row.name)!.title"
                        class="font-normal tabular-nums"
                      />
                    </div>
                    <div
                      class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-gray-6"
                    >
                      <span v-if="row.company_name" class="truncate">{{
                        row.company_name
                      }}</span>
                      <template v-if="departmentLabel(row)">
                        <span aria-hidden="true">·</span>
                        <span class="inline-flex items-center gap-1">
                          <LucideBuilding2
                            class="size-3.5 shrink-0 text-ink-gray-5"
                            aria-hidden="true"
                          />
                          <span class="sr-only">{{ __("Department") }}</span>
                          {{ departmentLabel(row) }}
                        </span>
                      </template>
                      <template v-if="row.segment">
                        <span aria-hidden="true">·</span>
                        <span>{{ row.segment }}</span>
                      </template>
                      <template v-if="categoryLabel(row)">
                        <span aria-hidden="true">·</span>
                        <span class="inline-flex items-center gap-1">
                          <LucideTag
                            class="size-3.5 shrink-0 text-ink-gray-5"
                            aria-hidden="true"
                          />
                          <span class="sr-only">{{ __("Category") }}</span>
                          {{ categoryLabel(row) }}
                        </span>
                      </template>
                      <template v-if="row.mobile_no || row.email_id">
                        <span aria-hidden="true">·</span>
                        <span class="truncate font-mono">{{
                          row.mobile_no || row.email_id
                        }}</span>
                      </template>
                    </div>
                  </div>
                  <div
                    class="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-gray-7 md:w-80 md:justify-end"
                  >
                    <span
                      v-if="row.next_follow_up"
                      class="inline-flex items-center gap-1 tabular-nums"
                      :class="
                        followUpLate(row) ? 'font-medium text-danger' : ''
                      "
                    >
                      <component
                        :is="
                          followUpLate(row) ? LucideCalendarX : LucideCalendar
                        "
                        class="size-3.5"
                        aria-hidden="true"
                      />
                      {{ followUpText(row) }}
                    </span>
                    <span class="inline-flex min-w-0 items-center gap-1">
                      <LucideUser
                        class="size-3.5 shrink-0 text-ink-gray-5"
                        aria-hidden="true"
                      />
                      <span class="truncate">{{
                        row.owner_name ||
                        ownerName(options, row.lead_owner) ||
                        __("No owner")
                      }}</span>
                    </span>
                    <span
                      v-if="row.score !== null && row.score !== undefined"
                      class="font-mono tabular-nums text-ink-gray-8"
                      :title="__('Lead score')"
                    >
                      <span class="sr-only">{{ __("Score") }}</span>
                      {{ row.score }}
                    </span>
                  </div>
                </router-link>
                <Button
                  v-if="options?.can_call && row.mobile_no"
                  class="mr-3 shrink-0"
                  variant="ghost"
                  :label="__('Call {0}', row.lead_name || row.name)"
                  :tooltip="__('MyOperator rings your phone, then the lead')"
                  :loading="
                    clickToCall.loading && clickToCall.params?.name === row.name
                  "
                  :disabled="clickToCall.loading"
                  @click="clickToCall.submit({ name: row.name })"
                >
                  <template #icon>
                    <LucidePhone class="size-4" aria-hidden="true" />
                  </template>
                </Button>
              </li>
            </ul>

            <nav
              class="mt-3 flex flex-wrap items-center justify-between gap-2"
              :aria-label="__('Pages')"
            >
              <span
                class="font-mono text-p-sm tabular-nums text-ink-gray-6"
                aria-live="polite"
              >
                {{ rangeText }}
              </span>
              <div class="flex gap-2">
                <Button
                  :label="__('Previous')"
                  :disabled="page === 1 || leads.loading"
                  @click="page--"
                >
                  <template #prefix>
                    <LucideChevronLeft class="size-4" aria-hidden="true" />
                  </template>
                </Button>
                <Button
                  :label="__('Next')"
                  :disabled="page >= pageCount || leads.loading"
                  @click="page++"
                >
                  <template #suffix>
                    <LucideChevronRight class="size-4" aria-hidden="true" />
                  </template>
                </Button>
              </div>
            </nav>
          </template>
        </template>
      </div>
    </div>

    <LeadFormDialog v-model:open="showNew" @saved="openLead" />
    <LeadSetCategoryDialog
      v-model:open="showSet"
      :leads="[...selected]"
      @saved="categorised"
    />
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { watchDebounced } from "@vueuse/core";
import {
  Button,
  Checkbox,
  createResource,
  dayjs,
  FormControl,
  TabButtons,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideBuilding2 from "~icons/lucide/building-2";
import LucideCalendar from "~icons/lucide/calendar";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideCalendarX from "~icons/lucide/calendar-x";
import LucideChevronLeft from "~icons/lucide/chevron-left";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideClock from "~icons/lucide/clock";
import LucidePhone from "~icons/lucide/phone";
import LucidePlus from "~icons/lucide/plus";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideListChecks from "~icons/lucide/list-checks";
import LucideSearch from "~icons/lucide/search";
import LucideSearchX from "~icons/lucide/search-x";
import LucideTag from "~icons/lucide/tag";
import LucideUser from "~icons/lucide/user";
import LucideUserPlus from "~icons/lucide/user-plus";
import LucideX from "~icons/lucide/x";
import LeadCategoryFilters from "./LeadCategoryFilters.vue";
import LeadFormDialog from "./LeadFormDialog.vue";
import LeadSetCategoryDialog from "./LeadSetCategoryDialog.vue";
import LeadIntakeStrip from "./LeadIntakeStrip.vue";
import LeadsBusiness from "./LeadsBusiness.vue";
import LeadsDailyReport from "./LeadsDailyReport.vue";
import LeadsOverview from "./LeadsOverview.vue";
import TodaysCalls from "./TodaysCalls.vue";
import { batchesOn } from "./callBatches";
import {
  categoryLabel,
  choices,
  clientStatus,
  departmentLabel,
  LEAD_VIEWS,
  loadLeadOptions,
  useClickToCall,
  leadOptions,
  METRIC_LABELS,
  ownerName,
  stageLabel,
  stageTone,
  staleLeads,
  usableDepartments,
  type LeadIntake,
  type StaleLead,
  type LeadCategories,
  type LeadOptions,
  type LeadRow,
  type LeadMetric,
  type LeadView,
} from "./leads";

const PAGE_LENGTH = 20;
// the Overview comes first and is where the page opens (docs/leads.md)
// and the Daily report sits next to it, once the ERP site has it
type LeadTab = LeadView | "overview" | "daily" | "business" | "today";
const TABS: { value: LeadTab; label: string }[] = [
  { value: "today", label: __("Today's calls") },
  { value: "overview", label: __("Overview") },
  { value: "daily", label: __("Daily report") },
  { value: "business", label: __("Business") },
  ...LEAD_VIEWS,
];
const PERIOD_LABELS: Record<string, string> = {
  today: __("today"),
  yesterday: __("yesterday"),
  week: __("this week"),
  month: __("this month"),
  quarter: __("this quarter"),
};
// the Created filter: leads taken in a period (the ERP site's "intake" metric)
const CREATED = [
  { label: __("Any time"), value: "" },
  { label: __("Today"), value: "today" },
  { label: __("Yesterday"), value: "yesterday" },
  { label: __("This week"), value: "week" },
  { label: __("This month"), value: "month" },
  { label: __("Custom"), value: "custom" },
];
const overviewPanel = ref<InstanceType<typeof LeadsOverview> | null>(null);
const dailyPanel = ref<InstanceType<typeof LeadsDailyReport> | null>(null);
const todayPanel = ref<InstanceType<typeof TodaysCalls> | null>(null);
const businessPanel = ref<InstanceType<typeof LeadsBusiness> | null>(null);

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();
const showNew = ref(false);

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}

// a salesperson whose department hands out call batches opens on them, anyone else on
// the Overview
function defaultTab(): LeadTab {
  return authStore.isSalesEmployee &&
    batchesOn(leadOptions.data as LeadOptions | undefined)
    ? "today"
    : "overview";
}

function queryView(): LeadTab {
  const value = queryValue("view");
  return TABS.some((v) => v.value === value)
    ? (value as LeadTab)
    : defaultTab();
}

function queryPage() {
  return Math.max(Math.floor(Number(queryValue("page"))) || 1, 1);
}

// the view, search, filters and page live in the URL, so a view can be shared
const view = ref<LeadTab>(queryView());
// a list of leads, not one of the two report tabs
const isList = computed(
  () =>
    view.value !== "overview" &&
    view.value !== "daily" &&
    view.value !== "today" &&
    view.value !== "business"
);
const search = ref(queryValue("q"));
// what the list is searched for: the box, once typing pauses
const appliedSearch = ref(search.value);
watchDebounced(search, (q) => (appliedSearch.value = q), { debounce: 300 });
const filters = reactive({
  stage: queryValue("stage"),
  owner: queryValue("owner"),
  segment: queryValue("segment"),
  department: queryValue("department"),
});
// Industry, State, District and Organisation size: each any of its values, kept in the
// URL as repeated keys (?industry=Resorts&industry=Hotels…)
const CATEGORY_KEYS = ["industry", "state", "district", "org_size"] as const;
function queryList(key: string) {
  const value = route.query[key];
  return (Array.isArray(value) ? value : [value]).filter(
    (v): v is string => typeof v === "string" && !!v
  );
}
function queryCategories(): LeadCategories {
  return Object.fromEntries(
    CATEGORY_KEYS.map((key) => [key, queryList(key)])
  ) as unknown as LeadCategories;
}
const categories = ref<LeadCategories>(queryCategories());
const categoryPanel = ref<InstanceType<typeof LeadCategoryFilters> | null>(
  null
);
const hasCategories = computed(() =>
  CATEGORY_KEYS.some((key) => categories.value[key].length)
);
const emptyCategories = (): LeadCategories => ({
  industry: [],
  state: [],
  district: [],
  org_size: [],
});

// managers pick many leads and set their category at once
const auth = useAuthStore();
const canCategorise = computed(
  () => auth.isManager && !!options.value?.org_sizes
);
const selecting = ref(false);
const selected = ref(new Set<string>());
const showSet = ref(false);
function toggleSelecting() {
  selecting.value = !selecting.value;
  selected.value = new Set();
}
function toggleRow(name: string) {
  const next = new Set(selected.value);
  if (!next.delete(name)) next.add(name);
  selected.value = next;
}
function selectPage() {
  selected.value = new Set([
    ...selected.value,
    ...(data.value?.rows ?? []).map((r) => r.name),
  ]);
}
function categorised() {
  leads.reload();
  categoryPanel.value?.reload();
  leadOptions.reload();
  toggleSelecting();
}

// set by a number on the Overview: the leads it counts, and its period
function queryExtra() {
  return {
    source: queryValue("source"),
    temperature: queryValue("temperature"),
    metric: queryValue("metric"),
    period: queryValue("period"),
    from: queryValue("from"),
    to: queryValue("to"),
  };
}
const extra = reactive(queryExtra());
const extraChips = computed(() => {
  const chips: string[] = [];
  if (extra.metric && extra.metric !== "intake") {
    const label = METRIC_LABELS[extra.metric as LeadMetric] || extra.metric;
    const when =
      extra.period === "custom" && extra.from && extra.to
        ? `${dayjs(extra.from).format("D MMM")} – ${dayjs(extra.to).format(
            "D MMM"
          )}`
        : PERIOD_LABELS[extra.period || "month"];
    chips.push(
      [
        "stale",
        "overdue",
        "hot",
        "open",
        "high_intent",
        "unhappy",
        "stage_suggested",
      ].includes(extra.metric)
        ? label
        : `${label}, ${when}`
    );
  }
  if (extra.source) chips.push(__("Source: {0}", extra.source));
  if (extra.temperature) chips.push(extra.temperature);
  return chips;
});
const page = ref(queryPage());

const hasFilters = computed(
  () =>
    !!(
      search.value.trim() ||
      filters.stage ||
      filters.owner ||
      filters.segment ||
      filters.department ||
      hasCategories.value ||
      extra.metric ||
      extraChips.value.length
    )
);

const created = computed({
  get: () => (extra.metric === "intake" ? extra.period || "month" : ""),
  set: (value: string) => {
    if (!value) {
      if (extra.metric === "intake")
        Object.assign(extra, { metric: "", period: "", from: "", to: "" });
      return;
    }
    const custom = value === "custom";
    Object.assign(extra, {
      metric: "intake",
      period: value,
      from: custom ? extra.from : "",
      to: custom ? extra.to : "",
    });
  },
});
// a custom period waits for both dates before the list asks for it
const waitingForDates = computed(
  () =>
    !!extra.metric &&
    extra.period === "custom" &&
    !(extra.from && extra.to && extra.from <= extra.to)
);

function clearFilters() {
  search.value = "";
  Object.assign(filters, {
    stage: "",
    owner: "",
    segment: "",
    department: "",
  });
  categories.value = emptyCategories();
  Object.assign(extra, {
    source: "",
    temperature: "",
    metric: "",
    period: "",
    from: "",
    to: "",
  });
}

function showAll() {
  clearFilters();
  view.value = "all";
}

loadLeadOptions();
const options = computed(() => leadOptions.data as LeadOptions | undefined);
const hasDaily = computed(() => !!options.value?.has_daily_report);
const canViewBusiness = computed(() => !!options.value?.can_view_business);
const hasBatches = computed(() => batchesOn(options.value));
// Today's calls is the Call today list for people who get call batches: one place
const tabs = computed(() =>
  TABS.filter((tab) => {
    if (tab.value === "daily") return hasDaily.value;
    if (tab.value === "business") return canViewBusiness.value;
    if (tab.value === "today") return hasBatches.value;
    if (tab.value === "call_today") return !hasBatches.value;
    return true;
  })
);
const homeTab = computed<LeadTab>(defaultTab);
// the tab was picked by hand: the options arriving later don't move it
const picked = ref(false);
// an old link to a tab this person or the ERP site doesn't have
watch(options, (value) => {
  if (!value) return;
  if (!picked.value && !queryValue("view") && view.value === "overview")
    view.value = homeTab.value;
  if (!value.has_daily_report && view.value === "daily")
    view.value = "overview";
  if (!hasBatches.value && view.value === "today") view.value = "overview";
  if (hasBatches.value && view.value === "call_today") view.value = "today";
  // a link to a tab the person may not open
  if (value && !value.can_view_business && view.value === "business")
    view.value = "overview";
});
const clickToCall = useClickToCall();

const stageOptions = computed(() => [
  { label: __("Any stage"), value: "" },
  ...(options.value?.stages ?? []).map((s) => ({
    label: s.label || s.name,
    value: s.name,
  })),
]);
// only once the ERP site has departments; an older TBO Smart leaves the filter out
const departmentFilter = computed(() => {
  const list = usableDepartments(options.value, filters.department);
  return list.length
    ? [
        { label: __("Any department"), value: "" },
        ...list.map((d) => ({ label: d.name, value: d.name })),
      ]
    : [];
});
const ownerOptions = computed(() => [
  { label: __("Anyone"), value: "" },
  ...(options.value?.owners ?? []).map((o) => ({
    label: o.full_name || o.email,
    value: o.email,
  })),
]);

const leads = createResource({
  url: "helpdesk.api.leads.list_leads",
  makeParams: () => ({
    search: appliedSearch.value.trim() || null,
    stage: filters.stage || null,
    owner: filters.owner || null,
    segment: filters.segment || null,
    department: filters.department || null,
    ...categories.value,
    source: extra.source || null,
    temperature: extra.temperature || null,
    metric: extra.metric || null,
    period: extra.metric ? extra.period || "month" : null,
    from_date: extra.metric ? extra.from || null : null,
    to_date: extra.metric ? extra.to || null : null,
    view: isList.value ? view.value : "all",
    start: (page.value - 1) * PAGE_LENGTH,
    page_length: PAGE_LENGTH,
  }),
  auto: isList.value && !waitingForDates.value,
});

// new leads taken today and yesterday; quiet on failure (the strip just stays out). The
// Overview brings it with its own request, so only the list asks for it here.
const intake = createResource({
  url: "helpdesk.api.leads.get_lead_intake",
  auto: isList.value,
  onSuccess(data: LeadIntake) {
    intakeData.value = data;
  },
  onError() {},
});
const intakeData = ref<LeadIntake>();
const overviewSettled = ref(false);
const intakeLoading = computed(
  () => intake.loading || (view.value === "overview" && !overviewSettled.value)
);
const intakeOn = computed(() => !!intakeData.value?.available);

function takeOverviewIntake(value: LeadIntake | undefined) {
  overviewSettled.value = true;
  if (value) intakeData.value = value;
}

// the cached answer shows at once, and is asked again each time the page opens
if (isList.value) staleLeads.fetch();

watch(view, (tab) => {
  if (isList.value && !intakeData.value) intake.fetch();
  if (isList.value && !staleLeads.data && !staleLeads.loading)
    staleLeads.fetch();
});

function refresh() {
  if (view.value === "today") todayPanel.value?.reload();
  else if (view.value === "overview") overviewPanel.value?.reload();
  else if (view.value === "daily") dailyPanel.value?.reload();
  else if (view.value === "business") businessPanel.value?.reload();
  else {
    intake.submit({ fresh: 1 });
    staleLeads.submit({ fresh: 1 });
    if (!waitingForDates.value) leads.reload();
  }
}

const data = computed(
  () => leads.data as { rows: LeadRow[]; total: number } | undefined
);
// idle days by lead name; empty while the ERP site's TBO Smart is older than this
const quiet = computed(
  () =>
    new Map(
      ((staleLeads.data?.leads ?? []) as StaleLead[]).map((l) => [
        l.name,
        l.idle_days,
      ])
    )
);
const statuses = computed(
  () => new Map((data.value?.rows ?? []).map((r) => [r.name, clientStatus(r)]))
);
const pageCount = computed(() =>
  Math.max(Math.ceil((data.value?.total ?? 0) / PAGE_LENGTH), 1)
);
const rangeText = computed(() => {
  const total = data.value?.total ?? 0;
  const first = (page.value - 1) * PAGE_LENGTH + 1;
  const last = Math.min(page.value * PAGE_LENGTH, total);
  return __("{0}–{1} of {2}", String(first), String(last), String(total));
});

// an old link, or leads removed on the ERP site: go to the last page there is
watch(data, (d) => {
  if (d && page.value > pageCount.value) page.value = pageCount.value;
});

// the URL changed from outside (the sidebar, back and forward): take its state,
// page included, without the reset to page 1 below
let fromRoute = false;
watch(
  () => route.query,
  () => {
    if (route.name !== "Leads") return;
    const wanted = {
      view: queryView(),
      q: queryValue("q"),
      stage: queryValue("stage"),
      owner: queryValue("owner"),
      segment: queryValue("segment"),
      department: queryValue("department"),
      page: queryPage(),
      extra: queryExtra(),
      categories: queryCategories(),
    };
    if (
      JSON.stringify({ ...extra }) === JSON.stringify(wanted.extra) &&
      JSON.stringify(categories.value) === JSON.stringify(wanted.categories) &&
      view.value === wanted.view &&
      appliedSearch.value.trim() === wanted.q.trim() &&
      filters.stage === wanted.stage &&
      filters.owner === wanted.owner &&
      filters.segment === wanted.segment &&
      filters.department === wanted.department &&
      page.value === wanted.page
    )
      return;
    fromRoute = true;
    view.value = wanted.view;
    search.value = appliedSearch.value = wanted.q;
    Object.assign(filters, {
      stage: wanted.stage,
      owner: wanted.owner,
      segment: wanted.segment,
      department: wanted.department,
    });
    Object.assign(extra, wanted.extra);
    categories.value = wanted.categories;
    page.value = wanted.page;
  }
);

// a new view, search or filter starts again at page 1
watch(
  [
    view,
    appliedSearch,
    () => ({ ...filters }),
    () => ({ ...extra }),
    categories,
  ],
  () => {
    if (!fromRoute) page.value = 1;
  }
);

watch(
  [
    view,
    appliedSearch,
    () => ({ ...filters }),
    () => ({ ...extra }),
    page,
    categories,
  ],
  ([v, q, f, x, p, c]) => {
    fromRoute = false;
    router.replace({
      query: {
        ...route.query,
        view: v === homeTab.value ? undefined : v,
        q: q.trim() || undefined,
        stage: f.stage || undefined,
        owner: f.owner || undefined,
        segment: f.segment || undefined,
        department: f.department || undefined,
        industry: c.industry.length ? c.industry : undefined,
        state: c.state.length ? c.state : undefined,
        district: c.district.length ? c.district : undefined,
        org_size: c.org_size.length ? c.org_size : undefined,
        source: x.source || undefined,
        temperature: x.temperature || undefined,
        metric: x.metric || undefined,
        // the Overview keeps its own period in the URL too
        period: x.period || undefined,
        from: x.from || undefined,
        to: x.to || undefined,
        page: p > 1 ? String(p) : undefined,
      },
    });
    if (isList.value && !waitingForDates.value) leads.reload();
  }
);

function followUpLate(row: LeadRow) {
  return (
    !!row.next_follow_up &&
    dayjs(row.next_follow_up).isBefore(dayjs().startOf("day"))
  );
}

function followUpText(row: LeadRow) {
  const day = dayjs(row.next_follow_up);
  if (day.isSame(dayjs(), "day")) return __("Follow up today");
  if (followUpLate(row))
    return __("Follow-up was due {0}", day.format("D MMM"));
  return __("Follow up {0}", day.format("D MMM"));
}

function openLead(name: string) {
  if (name) router.push({ name: "Lead", params: { leadId: name } });
  else leads.reload();
}
</script>
