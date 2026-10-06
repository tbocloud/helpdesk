<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("Overview") }}</div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="overview.loading"
          :aria-label="__('Refresh')"
          @click="overview.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-7xl px-4 py-5 md:px-6">
        <!-- Filters: the grid fits one more filter without layout changes -->
        <div
          class="grid grid-cols-1 gap-3 sm:grid-cols-[repeat(auto-fit,minmax(12rem,1fr))]"
          role="group"
          :aria-label="__('Filter overview')"
        >
          <Link
            v-model="filters.project"
            doctype="Project"
            :label="__('Project')"
            :placeholder="__('All projects')"
          />
          <Link
            v-model="filters.customer"
            doctype="HD Customer"
            :label="__('Customer')"
            :placeholder="__('All customers')"
          />
          <Link
            v-model="filters.assignee"
            doctype="User"
            hide-me
            :label="__('Assignee')"
            :placeholder="__('Anyone')"
          />
          <Link
            v-model="filters.department"
            doctype="HD Department"
            :filters="{ is_active: 1 }"
            :label="__('Department')"
            :placeholder="__('All departments')"
          />
        </div>
        <div v-if="hasFilters" class="mt-2 flex justify-end">
          <Button variant="ghost" :label="__('Clear filters')" @click="clear">
            <template #prefix>
              <LucideX class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>

        <TaskyState
          v-if="overview.error && !overview.data"
          class="mt-6"
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the overview')"
          :message="__('Check your connection and try again.')"
          error
        >
          <Button :label="__('Retry')" @click="overview.reload()" />
        </TaskyState>

        <template v-else>
          <!-- Dashboard: charts on top, tiles around what needs attention.
               Dense flow lets the two-column tablet layout fill its gaps. -->
          <div
            class="mt-5 grid grid-cols-1 gap-4 md:grid-flow-row-dense md:grid-cols-2 lg:grid-cols-12"
            :aria-busy="overview.loading"
          >
            <!-- Active work by urgency -->
            <section
              class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4 lg:col-span-3"
              :aria-labelledby="`${uid}-active`"
            >
              <h2
                :id="`${uid}-active`"
                class="text-base-medium text-ink-gray-8"
              >
                {{ __("Active work") }}
              </h2>
              <div
                v-if="firstLoad"
                class="mx-auto size-44 animate-pulse rounded-full bg-surface-gray-2"
              />
              <OverviewDonut
                v-else
                :split="active"
                :selected="activeBucket"
                :labels="urgencyLabels"
                @select="activeBucket = $event"
              />
            </section>

            <!-- Open tasks by project -->
            <section
              class="flex min-w-0 flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4 md:col-span-2 lg:col-span-6"
              :aria-labelledby="`${uid}-projects`"
            >
              <header>
                <h2
                  :id="`${uid}-projects`"
                  class="text-base-medium text-ink-gray-8"
                >
                  {{ __("Tasks by project") }}
                </h2>
                <p class="text-p-sm text-ink-gray-5">
                  {{
                    filters.project
                      ? __("Click the bar again to see every project")
                      : __(
                          "Open tasks in the busiest projects; click one to filter"
                        )
                  }}
                </p>
              </header>
              <div v-if="firstLoad" class="flex flex-col gap-3 py-1">
                <div
                  v-for="i in 5"
                  :key="i"
                  class="h-4 animate-pulse rounded bg-surface-gray-2"
                  :style="{ width: `${90 - i * 12}%` }"
                />
              </div>
              <p
                v-else-if="!projects.length"
                class="flex flex-1 items-center justify-center py-10 text-p-sm text-ink-gray-5"
              >
                {{ __("No open tasks in any project.") }}
              </p>
              <OverviewProjectChart
                v-else
                :rows="projects"
                :selected="filters.project || null"
                @select="toggleProject"
              />
            </section>

            <!-- Overdue, on hold and waiting for review -->
            <section
              class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base lg:col-span-3"
              :aria-label="__('Work status')"
            >
              <ul role="list">
                <li
                  v-for="row in statusRows"
                  :key="row.key"
                  class="border-b border-outline-gray-1 last:border-b-0"
                >
                  <button
                    type="button"
                    class="flex w-full flex-col gap-2 px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
                    :class="
                      activeBucket === row.key
                        ? 'bg-brand-soft'
                        : 'hover:bg-surface-gray-1'
                    "
                    :aria-pressed="activeBucket === row.key"
                    :aria-controls="listId"
                    @click="activeBucket = row.key"
                  >
                    <span class="flex items-center justify-between gap-2">
                      <span
                        class="flex items-center gap-1.5 text-sm text-ink-gray-7"
                      >
                        <component
                          :is="row.icon"
                          class="size-4"
                          :class="row.iconClass"
                          aria-hidden="true"
                        />
                        {{ row.label }}
                      </span>
                      <span
                        class="text-2xl font-semibold tabular-nums text-ink-gray-9"
                      >
                        <span
                          v-if="firstLoad"
                          class="inline-block h-6 w-6 animate-pulse rounded bg-surface-gray-2"
                        />
                        <template v-else>{{ counts[row.key] ?? 0 }}</template>
                      </span>
                    </span>
                    <span
                      class="block h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
                      aria-hidden="true"
                    >
                      <span
                        class="block h-full rounded-full transition-[width]"
                        :class="
                          row.key === 'overdue'
                            ? 'bg-danger'
                            : 'bg-surface-gray-6'
                        "
                        :style="{ width: `${share(row.key)}%` }"
                      />
                    </span>
                    <span class="text-xs tabular-nums text-ink-gray-5">
                      {{ __("{0}% of active work", String(share(row.key))) }}
                    </span>
                  </button>
                </li>
              </ul>
            </section>

            <!-- At risk, waiting on task -->
            <div class="grid grid-cols-2 gap-4 lg:col-span-3 lg:grid-cols-1">
              <button
                v-for="tile in leftTiles"
                :key="tile.key"
                type="button"
                class="flex min-h-28 flex-col justify-between gap-3 rounded-xl border p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                :class="tileClass(tile.key)"
                :aria-pressed="activeBucket === tile.key"
                :aria-controls="listId"
                @click="activeBucket = tile.key"
              >
                <span class="flex items-center justify-between gap-2">
                  <span class="text-sm text-ink-gray-7">{{ tile.label }}</span>
                  <component
                    :is="tile.icon"
                    class="size-4 shrink-0"
                    :class="tile.iconClass"
                    aria-hidden="true"
                  />
                </span>
                <span
                  class="text-4xl font-semibold tabular-nums text-ink-gray-9"
                >
                  <span
                    v-if="firstLoad"
                    class="inline-block h-9 w-10 animate-pulse rounded bg-surface-gray-2"
                  />
                  <template v-else>{{ counts[tile.key] ?? 0 }}</template>
                </span>
              </button>
            </div>

            <!-- What needs action first -->
            <section
              class="order-last flex min-w-0 flex-col overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base md:col-span-2 lg:order-none lg:col-span-6"
              :aria-labelledby="`${uid}-attention`"
            >
              <header
                class="flex items-start justify-between gap-3 border-b border-outline-gray-2 px-4 py-3"
              >
                <div class="min-w-0">
                  <h2
                    :id="`${uid}-attention`"
                    class="flex items-center gap-1.5 text-base-medium text-ink-gray-8"
                  >
                    <LucideTriangleAlert
                      class="size-4 text-danger"
                      aria-hidden="true"
                    />
                    {{ __("Action required") }}
                  </h2>
                  <p class="text-p-sm tabular-nums text-ink-gray-5">
                    {{
                      __(
                        "{0} overdue · {1} at risk",
                        String(counts.overdue ?? 0),
                        String(counts.at_risk ?? 0)
                      )
                    }}
                  </p>
                </div>
              </header>
              <div v-if="firstLoad">
                <div
                  v-for="i in 3"
                  :key="i"
                  class="flex flex-col gap-2 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0"
                >
                  <div
                    class="h-3.5 w-3/5 animate-pulse rounded bg-surface-gray-2"
                  />
                  <div
                    class="h-3 w-2/5 animate-pulse rounded bg-surface-gray-2"
                  />
                </div>
              </div>
              <OverviewAttention v-else :items="attention" />
            </section>

            <!-- Due soon, key -->
            <div class="grid grid-cols-2 gap-4 lg:col-span-3 lg:grid-cols-1">
              <button
                v-for="tile in rightTiles"
                :key="tile.key"
                type="button"
                class="flex min-h-28 flex-col justify-between gap-3 rounded-xl border p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                :class="tileClass(tile.key)"
                :aria-pressed="activeBucket === tile.key"
                :aria-controls="listId"
                @click="activeBucket = tile.key"
              >
                <span class="flex items-center justify-between gap-2">
                  <span class="text-sm text-ink-gray-7">{{ tile.label }}</span>
                  <component
                    :is="tile.icon"
                    class="size-4 shrink-0"
                    :class="tile.iconClass"
                    aria-hidden="true"
                  />
                </span>
                <span
                  class="text-4xl font-semibold tabular-nums text-ink-gray-9"
                >
                  <span
                    v-if="firstLoad"
                    class="inline-block h-9 w-10 animate-pulse rounded bg-surface-gray-2"
                  />
                  <template v-else>{{ counts[tile.key] ?? 0 }}</template>
                </span>
              </button>
            </div>
          </div>

          <!-- List -->
          <div class="mt-6 flex items-center justify-between gap-2">
            <h2 class="text-base-medium text-ink-gray-8">
              {{ activeTile.label }}
            </h2>
            <span class="text-sm text-ink-gray-5">{{ activeTile.hint }}</span>
          </div>
          <div
            :id="listId"
            class="mt-2 overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-base"
            :aria-busy="overview.loading"
          >
            <div
              class="hidden grid-cols-[1fr_9rem_8rem_9rem] gap-4 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2 text-xs text-ink-gray-5 md:grid"
              aria-hidden="true"
            >
              <span>{{ __("Work") }}</span>
              <span>{{ __("Assignee") }}</span>
              <span>{{ __("Status") }}</span>
              <span class="text-right">{{ __("Deadline") }}</span>
            </div>

            <div v-if="firstLoad">
              <div
                v-for="i in 6"
                :key="i"
                class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0"
              >
                <div class="size-4 animate-pulse rounded bg-surface-gray-2" />
                <div class="flex flex-1 flex-col gap-2">
                  <div
                    class="h-3.5 w-2/5 animate-pulse rounded bg-surface-gray-2"
                  />
                  <div
                    class="h-3 w-1/4 animate-pulse rounded bg-surface-gray-2"
                  />
                </div>
                <div
                  class="hidden size-6 animate-pulse rounded-full bg-surface-gray-2 md:block"
                />
                <div
                  class="hidden h-3 w-20 animate-pulse rounded bg-surface-gray-2 md:block"
                />
              </div>
            </div>

            <TaskyState
              v-else-if="!visibleItems.length"
              :icon="LucideCircleCheck"
              :title="__('Nothing here')"
              :message="activeTile.empty"
            >
              <Button
                v-if="hasFilters"
                :label="__('Clear filters')"
                @click="clear"
              />
            </TaskyState>

            <ul v-else role="list">
              <li
                v-for="item in visibleItems"
                :key="itemKey(item)"
                class="border-b border-outline-gray-1 last:border-b-0"
              >
                <WorkItemRow :item="item" show-assignees />
              </li>
            </ul>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyState from "@/pages/tasky/components/TaskyState.vue";
import { __ } from "@/translation";
import { Button, createResource } from "frappe-ui";
import { computed, reactive, ref, useId, watch, type Component } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClipboardCheck from "~icons/lucide/clipboard-check";
import LucideHourglass from "~icons/lucide/hourglass";
import LucidePause from "~icons/lucide/pause";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideStar from "~icons/lucide/star";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideX from "~icons/lucide/x";
import OverviewAttention from "./components/OverviewAttention.vue";
import OverviewDonut from "./components/OverviewDonut.vue";
import OverviewProjectChart from "./components/OverviewProjectChart.vue";
import WorkItemRow from "./components/WorkItemRow.vue";
import {
  BUCKETS,
  type ActiveSplit,
  type Bucket,
  type OverviewData,
  type Urgency,
} from "./overviewMeta";
import { itemKey, type WorkItem } from "./workMeta";

// one place to add a filter: the key here, a Link above, and the API argument
type FilterKey = "project" | "customer" | "assignee" | "department";
const FILTER_KEYS: FilterKey[] = [
  "project",
  "customer",
  "assignee",
  "department",
];
const ATTENTION_SHOWN = 5;

interface Tile {
  key: Bucket;
  label: string;
  hint: string;
  empty: string;
  icon: Component;
  iconClass: string;
}

const route = useRoute();
const router = useRouter();
const uid = useId();
const listId = `work-overview-list-${uid}`;

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}

const activeBucket = ref<Bucket>(
  BUCKETS.includes(route.query.bucket as Bucket)
    ? (route.query.bucket as Bucket)
    : "overdue"
);

const filters = reactive(
  Object.fromEntries(FILTER_KEYS.map((k) => [k, queryValue(k)])) as Record<
    FilterKey,
    string
  >
);

const hasFilters = computed(() => FILTER_KEYS.some((k) => !!filters[k]));

function clear() {
  for (const key of FILTER_KEYS) filters[key] = "";
}

function toggleProject(project: string) {
  filters.project = filters.project === project ? "" : project;
}

const overview = createResource({
  url: "helpdesk.api.work.get_overview",
  makeParams: () =>
    Object.fromEntries(FILTER_KEYS.map((k) => [k, filters[k] || null])),
  auto: true,
});

// keep the bucket and filters in the URL so the view can be shared
watch(
  [activeBucket, () => ({ ...filters })],
  ([bucket, f]) => {
    router.replace({
      query: {
        ...route.query,
        bucket: bucket === "overdue" ? undefined : bucket,
        ...Object.fromEntries(FILTER_KEYS.map((k) => [k, f[k] || undefined])),
      },
    });
  },
  { deep: true }
);

watch(
  () => FILTER_KEYS.map((k) => filters[k]),
  () => overview.reload()
);

const data = computed(() => overview.data as OverviewData | undefined);
const firstLoad = computed(() => overview.loading && !overview.data);
const counts = computed(
  () => data.value?.counts ?? ({} as Partial<Record<Bucket, number>>)
);
const active = computed<ActiveSplit>(
  () =>
    data.value?.active ?? {
      total: 0,
      overdue: 0,
      at_risk: 0,
      due_soon: 0,
      key: 0,
      other: 0,
    }
);
const projects = computed(() => data.value?.projects ?? []);
const attention = computed(() =>
  (data.value?.attention ?? []).slice(0, ATTENTION_SHOWN)
);

function share(bucket: Bucket) {
  const total = active.value.total;
  return total ? Math.round(((counts.value[bucket] ?? 0) / total) * 100) : 0;
}

function tileClass(bucket: Bucket) {
  return activeBucket.value === bucket
    ? "border-brand bg-brand-soft"
    : "border-outline-gray-2 bg-surface-base hover:border-outline-gray-3";
}

const tiles = computed<Record<Bucket, Tile>>(() => ({
  overdue: {
    key: "overdue",
    label: __("Overdue"),
    hint: __("Past the due date or SLA"),
    empty: __("Nothing is overdue."),
    icon: LucideAlarmClock,
    iconClass: "text-danger",
  },
  at_risk: {
    key: "at_risk",
    label: __("At risk"),
    hint: __("Likely to slip: not started, rescheduled or blocked"),
    empty: __("Nothing looks likely to slip right now."),
    icon: LucideTriangleAlert,
    iconClass: "text-warning",
  },
  due_soon: {
    key: "due_soon",
    label: __("Due soon"),
    hint: __("Due in the next 3 days"),
    empty: __("Nothing is due in the next 3 days."),
    icon: LucideCalendarClock,
    iconClass: "text-info",
  },
  key: {
    key: "key",
    label: __("Key"),
    hint: __("Key tasks and urgent or high priority tickets"),
    empty: __("No key work is open."),
    icon: LucideStar,
    iconClass: "text-ink-gray-5",
  },
  review: {
    key: "review",
    label: __("Waiting for review"),
    hint: __("Tasks waiting for the project lead's approval"),
    empty: __("No tasks are waiting for review."),
    icon: LucideClipboardCheck,
    iconClass: "text-ink-gray-5",
  },
  waiting_on_task: {
    key: "waiting_on_task",
    label: __("Waiting on task"),
    hint: __("Tickets blocked by project work"),
    empty: __("No tickets are waiting on a task."),
    icon: LucideHourglass,
    iconClass: "text-ink-gray-5",
  },
  on_hold: {
    key: "on_hold",
    label: __("On hold"),
    hint: __("Paused tasks; they don't count as overdue"),
    empty: __("No tasks are on hold."),
    icon: LucidePause,
    iconClass: "text-warning",
  },
}));

// the mockup's layout: a status column by the charts, tiles either side of Action required
const statusRows = computed(() =>
  (["overdue", "on_hold", "review"] as Bucket[]).map((k) => tiles.value[k])
);
const leftTiles = computed(() =>
  (["at_risk", "waiting_on_task"] as Bucket[]).map((k) => tiles.value[k])
);
const rightTiles = computed(() =>
  (["due_soon", "key"] as Bucket[]).map((k) => tiles.value[k])
);

const urgencyLabels = computed(
  () =>
    Object.fromEntries(
      (["overdue", "at_risk", "due_soon", "key"] as Urgency[]).map((k) => [
        k,
        tiles.value[k].label,
      ])
    ) as Record<Urgency, string>
);

const activeTile = computed(() => tiles.value[activeBucket.value]);

const visibleItems = computed<WorkItem[]>(
  () => data.value?.buckets?.[activeBucket.value] ?? []
);
</script>
