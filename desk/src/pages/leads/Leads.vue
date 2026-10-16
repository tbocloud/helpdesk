<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <h1 class="text-lg-medium text-ink-gray-9">{{ __("Leads") }}</h1>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="leads.loading && !!data"
          :aria-label="__('Refresh')"
          @click="leads.reload()"
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
              :options="LEAD_VIEWS"
              @update:model-value="view = $event as LeadView"
            />
          </div>
          <div
            class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(14rem,2fr)_repeat(3,minmax(10rem,1fr))]"
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
          </div>
          <div v-if="hasFilters" class="flex justify-end">
            <Button
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

        <TaskyState
          v-if="leads.error && !data"
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
              <div class="h-3 w-1/2 animate-pulse rounded bg-surface-gray-2" />
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
              class="border-b border-outline-gray-1 last:border-b-0"
            >
              <router-link
                :to="{ name: 'Lead', params: { leadId: row.name } }"
                class="flex flex-col gap-2 px-4 py-3 transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4 md:flex-row md:items-center md:gap-4"
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
                  </div>
                  <div
                    class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-gray-6"
                  >
                    <span v-if="row.company_name" class="truncate">{{
                      row.company_name
                    }}</span>
                    <template v-if="row.segment">
                      <span aria-hidden="true">·</span>
                      <span>{{ row.segment }}</span>
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
                    :class="followUpLate(row) ? 'font-medium text-danger' : ''"
                  >
                    <component
                      :is="followUpLate(row) ? LucideCalendarX : LucideCalendar"
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
      </div>
    </div>

    <LeadFormDialog v-model:open="showNew" @saved="openLead" />
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { refDebounced } from "@vueuse/core";
import {
  Button,
  createResource,
  dayjs,
  FormControl,
  TabButtons,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCalendar from "~icons/lucide/calendar";
import LucideCalendarX from "~icons/lucide/calendar-x";
import LucideChevronLeft from "~icons/lucide/chevron-left";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucidePlus from "~icons/lucide/plus";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSearch from "~icons/lucide/search";
import LucideSearchX from "~icons/lucide/search-x";
import LucideUser from "~icons/lucide/user";
import LucideUserPlus from "~icons/lucide/user-plus";
import LucideX from "~icons/lucide/x";
import LeadFormDialog from "./LeadFormDialog.vue";
import {
  choices,
  LEAD_VIEWS,
  leadOptions,
  ownerName,
  stageLabel,
  stageTone,
  type LeadOptions,
  type LeadRow,
  type LeadView,
} from "./leads";

const PAGE_LENGTH = 20;

const route = useRoute();
const router = useRouter();
const showNew = ref(false);

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}

// the view, search, filters and page live in the URL, so a view can be shared
const view = ref<LeadView>(
  LEAD_VIEWS.some((v) => v.value === route.query.view)
    ? (route.query.view as LeadView)
    : "all"
);
const search = ref(queryValue("q"));
const debouncedSearch = refDebounced(search, 300);
const filters = reactive({
  stage: queryValue("stage"),
  owner: queryValue("owner"),
  segment: queryValue("segment"),
});
const page = ref(Math.max(Number(queryValue("page")) || 1, 1));

const hasFilters = computed(
  () =>
    !!(search.value.trim() || filters.stage || filters.owner || filters.segment)
);

function clearFilters() {
  search.value = "";
  Object.assign(filters, { stage: "", owner: "", segment: "" });
}

function showAll() {
  clearFilters();
  view.value = "all";
}

if (!leadOptions.data && !leadOptions.loading) leadOptions.fetch();
const options = computed(() => leadOptions.data as LeadOptions | undefined);

const stageOptions = computed(() => [
  { label: __("Any stage"), value: "" },
  ...(options.value?.stages ?? []).map((s) => ({
    label: s.label || s.name,
    value: s.name,
  })),
]);
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
    search: debouncedSearch.value.trim() || null,
    stage: filters.stage || null,
    owner: filters.owner || null,
    segment: filters.segment || null,
    view: view.value,
    start: (page.value - 1) * PAGE_LENGTH,
    page_length: PAGE_LENGTH,
  }),
  auto: true,
});

const data = computed(
  () => leads.data as { rows: LeadRow[]; total: number } | undefined
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

// a new view, search or filter starts again at page 1
watch([view, debouncedSearch, () => ({ ...filters })], () => {
  page.value = 1;
});

watch([view, debouncedSearch, () => ({ ...filters }), page], ([v, q, f, p]) => {
  router.replace({
    query: {
      ...route.query,
      view: v === "all" ? undefined : v,
      q: q.trim() || undefined,
      stage: f.stage || undefined,
      owner: f.owner || undefined,
      segment: f.segment || undefined,
      page: p > 1 ? String(p) : undefined,
    },
  });
  leads.reload();
});

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
