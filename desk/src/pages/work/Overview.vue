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
        <p class="text-p-sm text-ink-gray-6">
          {{
            __(
              "Open tasks and tickets across the projects you run: what's late, what may slip, and who is on it."
            )
          }}
        </p>

        <!-- Filters: the grid fits one more filter without layout changes -->
        <div
          class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-[repeat(auto-fit,minmax(12rem,1fr))]"
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
          <!-- KPI row: buckets open their list below; the last two go to their page -->
          <div
            class="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6"
            :aria-label="__('Work at a glance')"
            role="group"
          >
            <StatTile
              v-for="tile in kpiTiles"
              :key="tile.key"
              :label="tile.label"
              :value="counts[tile.key] ?? 0"
              :icon="tile.icon"
              :icon-tone="tile.tone"
              :loading="firstLoad"
              :pressed="activeBucket === tile.key"
              :aria-controls="listId"
              @click="selectBucket(tile.key)"
            />
            <StatTile
              :label="__('Open projects')"
              :value="data?.open_projects ?? 0"
              :icon="LucideFolderKanban"
              :loading="firstLoad"
              :to="{ name: 'TaskyProjects' }"
            />
            <StatTile
              :label="__('People busy')"
              :value="data?.people_busy ?? 0"
              :icon="LucideUsers"
              :loading="firstLoad"
              :to="teamRoute"
            />
          </div>

          <!-- Dashboard: charts on top, what needs action below.
               Dense flow lets the two-column tablet layout fill its gaps. -->
          <div
            class="mt-4 grid grid-cols-1 gap-4 md:grid-flow-row-dense md:grid-cols-2 lg:grid-cols-12"
            :aria-busy="overview.loading"
          >
            <SectionCard :title="__('Active work')" class="lg:col-span-3">
              <div class="p-4">
                <div
                  v-if="firstLoad"
                  class="mx-auto size-44 animate-pulse rounded-full bg-surface-gray-2"
                />
                <OverviewDonut
                  v-else
                  :split="active"
                  :selected="activeBucket"
                  :labels="urgencyLabels"
                  @select="selectBucket"
                />
              </div>
            </SectionCard>

            <SectionCard
              :title="__('Tasks by project')"
              :description="
                filters.project
                  ? __('Click the bar again to see every project')
                  : __(
                      'Open tasks in the busiest projects; click one to filter'
                    )
              "
              class="md:col-span-2 lg:col-span-6"
            >
              <div class="flex h-full flex-col p-4">
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
              </div>
            </SectionCard>

            <!-- Overdue, waiting for review and waiting on a task -->
            <SectionCard :title="__('Work status')" class="lg:col-span-3">
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
                    @click="selectBucket(row.key)"
                  >
                    <span class="flex items-center justify-between gap-2">
                      <span
                        class="flex items-center gap-1.5 text-sm text-ink-gray-7"
                      >
                        <component
                          :is="row.icon"
                          class="size-4"
                          :class="
                            row.tone === 'neutral'
                              ? 'text-ink-gray-5'
                              : INK[row.tone]
                          "
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
            </SectionCard>

            <!-- What needs action first -->
            <SectionCard
              :title="__('Action required')"
              :description="
                __(
                  '{0} overdue · {1} at risk',
                  String(counts.overdue ?? 0),
                  String(counts.at_risk ?? 0)
                )
              "
              :icon="LucideTriangleAlert"
              icon-class="text-danger"
              class="order-last md:col-span-2 lg:order-none lg:col-span-9"
            >
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
            </SectionCard>

            <!-- Due soon, key -->
            <div
              class="grid grid-cols-2 content-start gap-4 md:col-span-2 lg:col-span-3 lg:grid-cols-1"
            >
              <StatTile
                v-for="tile in sideTiles"
                :key="tile.key"
                :label="tile.label"
                :value="counts[tile.key] ?? 0"
                :sub="progressText(tile.key)"
                :icon="tile.icon"
                :icon-tone="tile.tone"
                :loading="firstLoad"
                :pressed="activeBucket === tile.key"
                :aria-controls="listId"
                @click="selectBucket(tile.key)"
              />
            </div>
          </div>

          <!-- The selected bucket's list -->
          <SectionCard
            :id="listId"
            ref="listCard"
            :title="activeTile.label"
            :count="firstLoad ? undefined : visibleItems.length"
            :description="activeTile.hint"
            class="mt-6 scroll-mt-4 overflow-hidden"
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
          </SectionCard>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import LayoutHeader from "@/components/LayoutHeader.vue";
import SectionCard from "@/components/SectionCard.vue";
import StatTile from "@/components/StatTile.vue";
import { INK, type Tone } from "@/pages/performance/performanceMeta";
import TaskyState from "@/pages/tasky/components/TaskyState.vue";
import { __ } from "@/translation";
import { Button, createResource } from "frappe-ui";
import {
  computed,
  nextTick,
  reactive,
  ref,
  useId,
  watch,
  type Component,
} from "vue";
import { useRoute, useRouter, type RouteLocationRaw } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClipboardCheck from "~icons/lucide/clipboard-check";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideLayers from "~icons/lucide/layers";
import LucidePause from "~icons/lucide/pause";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideStar from "~icons/lucide/star";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUserX from "~icons/lucide/user-x";
import LucideUsers from "~icons/lucide/users";
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
  /** the icon's colour, only where it means something */
  tone: Tone;
}

const route = useRoute();
const router = useRouter();
const uid = useId();
const listId = `work-overview-list-${uid}`;
const listCard = ref<InstanceType<typeof SectionCard> | null>(null);

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}

const activeBucket = ref<Bucket>(
  BUCKETS.includes(route.query.bucket as Bucket)
    ? (route.query.bucket as Bucket)
    : "overdue"
);

// the KPI row sits far above the list, so bring the list into view when it's off screen
function selectBucket(bucket: Bucket) {
  activeBucket.value = bucket;
  nextTick(() => {
    const el = listCard.value?.$el as HTMLElement | undefined;
    if (!el || el.getBoundingClientRect().top < window.innerHeight) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    el.scrollIntoView({
      behavior: reduce.matches ? "auto" : "smooth",
      block: "start",
    });
  });
}

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

// the Team page has no assignee or department filter; it keeps the rest
const teamRoute = computed<RouteLocationRaw>(() => ({
  name: "TeamWorkload",
  query: {
    project: filters.project || undefined,
    customer: filters.customer || undefined,
  },
}));

function share(bucket: Bucket) {
  const total = active.value.total;
  return total ? Math.round(((counts.value[bucket] ?? 0) / total) * 100) : 0;
}

/** "N open · M in progress": in progress is a task someone has started. */
function progressText(bucket: Bucket) {
  const items = data.value?.buckets?.[bucket] ?? [];
  const working = items.filter(
    (i) => i.kind === "task" && i.status === "Working"
  ).length;
  return __(
    "{0} open · {1} in progress",
    String(items.length - working),
    String(working)
  );
}

const tiles = computed<Record<Bucket, Tile>>(() => ({
  all: {
    key: "all",
    label: __("Active work"),
    hint: __("Every open task and ticket, overdue first"),
    empty: __("No open work."),
    icon: LucideLayers,
    tone: "neutral",
  },
  unassigned: {
    key: "unassigned",
    label: __("Unassigned"),
    hint: __("Open work nobody is assigned to"),
    empty: __("Everything open has someone on it."),
    icon: LucideUserX,
    tone: "neutral",
  },
  overdue: {
    key: "overdue",
    label: __("Overdue"),
    hint: __("Past the due date or SLA"),
    empty: __("Nothing is overdue."),
    icon: LucideAlarmClock,
    tone: "danger",
  },
  at_risk: {
    key: "at_risk",
    label: __("At risk"),
    hint: __("Likely to slip: not started, rescheduled or blocked"),
    empty: __("Nothing looks likely to slip right now."),
    icon: LucideTriangleAlert,
    tone: "warning",
  },
  due_soon: {
    key: "due_soon",
    label: __("Due soon"),
    hint: __("Due in the next 3 days"),
    empty: __("Nothing is due in the next 3 days."),
    icon: LucideCalendarClock,
    tone: "neutral",
  },
  key: {
    key: "key",
    label: __("Key"),
    hint: __("Key tasks and urgent or high priority tickets"),
    empty: __("No key work is open."),
    icon: LucideStar,
    tone: "neutral",
  },
  review: {
    key: "review",
    label: __("Waiting for review"),
    hint: __("Tasks waiting for the project lead's approval"),
    empty: __("No tasks are waiting for review."),
    icon: LucideClipboardCheck,
    tone: "neutral",
  },
  waiting_on_task: {
    key: "waiting_on_task",
    label: __("Waiting on task"),
    hint: __("Tickets blocked by project work"),
    empty: __("No tickets are waiting on a task."),
    icon: LucideHourglass,
    tone: "neutral",
  },
  on_hold: {
    key: "on_hold",
    label: __("On hold"),
    hint: __("Paused tasks; they don't count as overdue"),
    empty: __("No tasks are on hold."),
    icon: LucidePause,
    tone: "warning",
  },
}));

// each bucket appears once on the page: the KPI row, the status column, or beside Action required
const pick = (keys: Bucket[]) =>
  computed(() => keys.map((k) => tiles.value[k]));
const kpiTiles = pick(["all", "unassigned", "at_risk", "on_hold"]);
const statusRows = pick(["overdue", "review", "waiting_on_task"]);
const sideTiles = pick(["due_soon", "key"]);

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
