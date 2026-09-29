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
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <!-- Filters -->
        <div
          class="grid grid-cols-1 gap-3 sm:grid-cols-3"
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
          <!-- Buckets; with five tiles in two columns the last one spans the row -->
          <div
            class="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
          >
            <button
              v-for="tile in tiles"
              :key="tile.key"
              type="button"
              class="flex flex-col gap-3 rounded-lg border p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              :class="[
                activeBucket === tile.key
                  ? 'border-outline-gray-4 bg-surface-gray-1'
                  : 'border-outline-gray-2 bg-surface-base hover:border-outline-gray-3',
                tile.key === 'on_hold' ? 'col-span-2 sm:col-span-1' : '',
              ]"
              :aria-pressed="activeBucket === tile.key"
              :aria-controls="listId"
              @click="activeBucket = tile.key"
            >
              <div class="flex items-center justify-between">
                <span class="text-sm text-ink-gray-6">{{ tile.label }}</span>
                <component
                  :is="tile.icon"
                  class="size-4"
                  :class="tile.iconClass"
                  aria-hidden="true"
                />
              </div>
              <span class="text-2xl-semibold tabular-nums text-ink-gray-9">
                <span
                  v-if="overview.loading && !overview.data"
                  class="inline-block h-7 w-8 animate-pulse rounded bg-surface-gray-2"
                />
                <template v-else>{{ counts[tile.key] ?? 0 }}</template>
              </span>
            </button>
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

            <div v-if="overview.loading && !overview.data">
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
import LucideHourglass from "~icons/lucide/hourglass";
import LucidePause from "~icons/lucide/pause";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideStar from "~icons/lucide/star";
import LucideX from "~icons/lucide/x";
import WorkItemRow from "./components/WorkItemRow.vue";
import { itemKey, type WorkItem } from "./workMeta";

type Bucket = "overdue" | "due_soon" | "key" | "waiting_on_task" | "on_hold";

interface OverviewData {
  buckets: Record<Bucket, WorkItem[]>;
  counts: Record<Bucket, number>;
}

const route = useRoute();
const router = useRouter();
const listId = `work-overview-list-${useId()}`;

const BUCKETS: Bucket[] = [
  "overdue",
  "due_soon",
  "key",
  "waiting_on_task",
  "on_hold",
];

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}

const activeBucket = ref<Bucket>(
  BUCKETS.includes(route.query.bucket as Bucket)
    ? (route.query.bucket as Bucket)
    : "overdue"
);

const filters = reactive({
  project: queryValue("project"),
  customer: queryValue("customer"),
  assignee: queryValue("assignee"),
});

const hasFilters = computed(
  () => !!(filters.project || filters.customer || filters.assignee)
);

function clear() {
  filters.project = "";
  filters.customer = "";
  filters.assignee = "";
}

const overview = createResource({
  url: "helpdesk.api.work.get_overview",
  makeParams: () => ({
    project: filters.project || null,
    customer: filters.customer || null,
    assignee: filters.assignee || null,
  }),
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
        project: f.project || undefined,
        customer: f.customer || undefined,
        assignee: f.assignee || undefined,
      },
    });
  },
  { deep: true }
);

watch(
  () => [filters.project, filters.customer, filters.assignee],
  () => overview.reload()
);

const data = computed(() => overview.data as OverviewData | undefined);
const counts = computed(
  () => data.value?.counts ?? ({} as Partial<Record<Bucket, number>>)
);

const tiles = computed<
  {
    key: Bucket;
    label: string;
    hint: string;
    empty: string;
    icon: Component;
    iconClass: string;
  }[]
>(() => [
  {
    key: "overdue",
    label: __("Overdue"),
    hint: __("Past the due date or SLA"),
    empty: __("Nothing is overdue."),
    icon: LucideAlarmClock,
    iconClass: "text-danger",
  },
  {
    key: "due_soon",
    label: __("Due soon"),
    hint: __("Due in the next 3 days"),
    empty: __("Nothing is due in the next 3 days."),
    icon: LucideCalendarClock,
    iconClass: "text-ink-gray-5",
  },
  {
    key: "key",
    label: __("Key"),
    hint: __("Key tasks and urgent or high priority tickets"),
    empty: __("No key work is open."),
    icon: LucideStar,
    iconClass: "text-ink-gray-5",
  },
  {
    key: "waiting_on_task",
    label: __("Waiting on task"),
    hint: __("Tickets blocked by project work"),
    empty: __("No tickets are waiting on a task."),
    icon: LucideHourglass,
    iconClass: "text-ink-gray-5",
  },
  {
    key: "on_hold",
    label: __("On hold"),
    hint: __("Paused tasks; they don't count as overdue"),
    empty: __("No tasks are on hold."),
    icon: LucidePause,
    iconClass: "text-warning",
  },
]);

const activeTile = computed(
  () => tiles.value.find((t) => t.key === activeBucket.value) ?? tiles.value[0]
);

const visibleItems = computed<WorkItem[]>(
  () => data.value?.buckets?.[activeBucket.value] ?? []
);
</script>
