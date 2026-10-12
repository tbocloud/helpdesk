<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <h1 class="text-lg-medium text-ink-gray-9">{{ __("In progress") }}</h1>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="resource.loading"
          :aria-label="__('Refresh')"
          @click="resource.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-7xl px-4 py-5 md:px-6">
        <p class="text-p-sm text-ink-gray-6">{{ intro }}</p>

        <!-- one line answers "what's going on"; it counts the whole view, before
             the two switches narrow the lanes -->
        <p
          class="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-base text-ink-gray-8"
          aria-live="polite"
        >
          <template v-if="data">
            <template v-for="(part, i) in summaryParts" :key="part.key">
              <span v-if="i" class="text-ink-gray-4" aria-hidden="true">·</span>
              <span
                class="inline-flex items-center gap-1.5"
                :class="part.alert ? 'font-medium text-danger' : ''"
              >
                <component
                  :is="part.icon"
                  class="size-4 shrink-0"
                  :class="part.alert ? '' : 'text-ink-gray-5'"
                  aria-hidden="true"
                />
                <span class="font-mono tabular-nums">{{ part.value }}</span>
                {{ part.label }}
              </span>
            </template>
          </template>
          <span
            v-else-if="firstLoad"
            class="h-5 w-80 max-w-full animate-pulse rounded bg-surface-gray-2"
          />
        </p>

        <div class="mt-4 flex flex-col gap-3">
          <div class="overflow-x-auto">
            <TabButtons
              :model-value="group"
              size="md"
              :aria-label="__('Group the work')"
              :options="
                groupOptions.map((o) => ({
                  label: o.label,
                  value: o.key,
                  iconLeft: o.icon,
                }))
              "
              @update:model-value="group = $event as InProgressGroup"
            />
          </div>
          <div
            class="grid grid-cols-1 gap-3 sm:grid-cols-[repeat(auto-fit,minmax(12rem,1fr))]"
            role="group"
            :aria-label="__('Filter the work')"
          >
            <Link
              v-model="filters.department"
              doctype="HD Department"
              :filters="{ is_active: 1 }"
              :label="__('Department')"
              :placeholder="__('All departments')"
            />
            <Link
              v-model="filters.customer"
              doctype="HD Customer"
              :label="__('Customer')"
              :placeholder="__('All customers')"
            />
            <Link
              v-if="teamScope"
              v-model="filters.person"
              doctype="User"
              hide-me
              :label="__('Person')"
              :placeholder="__('Anyone')"
            />
          </div>
          <div class="flex flex-wrap items-center gap-x-6 gap-y-2">
            <Switch
              v-model="filters.overdue"
              :label="__('Only overdue or escalated')"
            />
            <Switch v-model="filters.hideHold" :label="__('Hide on hold')" />
            <Button
              v-if="hasFilters"
              variant="ghost"
              class="ml-auto"
              :label="__('Clear filters')"
              @click="clear"
            >
              <template #prefix>
                <LucideX class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
        </div>

        <TaskyState
          v-if="resource.error && !data"
          class="mt-6"
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the work in progress')"
          :message="
            errorText(
              resource.error,
              __('Check your connection and try again.')
            )
          "
          error
        >
          <Button :label="__('Retry')" @click="resource.reload()" />
        </TaskyState>

        <div
          v-else-if="firstLoad"
          class="mt-5 flex flex-col gap-4"
          aria-busy="true"
        >
          <div
            v-for="i in 3"
            :key="i"
            class="h-40 animate-pulse rounded-xl border border-outline-gray-2 bg-surface-gray-1"
          />
        </div>

        <TaskyState
          v-else-if="!lanes.length"
          class="mt-6"
          :icon="LucideCircleCheck"
          :title="
            hasFilters
              ? __('Nothing matches these filters')
              : __('Nothing in progress')
          "
          :message="emptyMessage"
        >
          <Button
            v-if="hasFilters"
            :label="__('Clear filters')"
            @click="clear"
          />
        </TaskyState>

        <div
          v-else
          class="mt-5 flex flex-col gap-4"
          :aria-busy="resource.loading"
        >
          <SectionCard
            v-for="lane in lanes"
            :key="`${lane.kind}:${lane.key}`"
            :title="lane.title"
            :description="lane.subtitle || undefined"
            :icon="LANE_ICONS[lane.kind]"
            :count="lane.tasks.length + lane.posts.length"
          >
            <ul
              class="flex flex-wrap items-center gap-1.5 border-b border-outline-gray-1 px-4 py-2"
              role="list"
              :aria-label="__('In this lane')"
            >
              <li v-for="badge in laneBadges(lane)" :key="badge.key">
                <TaskyBadge
                  :tone="badge.tone"
                  :icon="badge.icon"
                  :label="badge.label"
                />
              </li>
            </ul>
            <ul role="list">
              <li
                v-for="task in shownTasks(lane)"
                :key="`task:${task.name}`"
                class="border-b border-outline-gray-1 last:border-b-0"
              >
                <WorkItemRow
                  :item="task"
                  show-assignees
                  opens
                  @open="openTask(task)"
                >
                  <!-- always passed, so every row keeps the same columns -->
                  <template #actions>
                    <TaskyBadge
                      v-if="timerOf(task)"
                      :tone="timerOf(task).running ? 'info' : 'neutral'"
                      :icon="
                        timerOf(task).running ? LucideTimer : LucideCirclePause
                      "
                      :title="
                        timerOf(task).running
                          ? __('Tracking time on this task')
                          : __('Timer paused')
                      "
                    >
                      <span class="hidden sm:inline">{{
                        timerOf(task).running ? __("Tracking") : __("Paused")
                      }}</span>
                      <span class="sr-only sm:hidden">{{
                        timerOf(task).running ? __("Tracking") : __("Paused")
                      }}</span>
                      <span class="font-mono tabular-nums">{{
                        formatElapsed(timerOf(task).elapsed, false)
                      }}</span>
                    </TaskyBadge>
                  </template>
                </WorkItemRow>
              </li>
              <li
                v-for="post in shownPosts(lane)"
                :key="`post:${post.name}`"
                class="border-b border-outline-gray-1 last:border-b-0"
              >
                <InProgressPostRow :post="post" @open="openPost(post)" />
              </li>
            </ul>
            <div
              v-if="hiddenCount(lane)"
              class="border-t border-outline-gray-1 px-4 py-2"
            >
              <Button
                variant="ghost"
                :label="
                  expanded.has(laneKey(lane))
                    ? __('Show fewer')
                    : __(
                        'Show all {0}',
                        String(lane.tasks.length + lane.posts.length)
                      )
                "
                @click="toggleLane(lane)"
              />
            </div>
          </SectionCard>

          <p v-if="data?.truncated" class="text-p-sm text-ink-gray-5">
            {{
              __(
                "Showing the first 1000 tasks and 500 posts. Filter by department, customer or person to see the rest."
              )
            }}
          </p>
        </div>
      </div>
    </div>

    <TaskDetailDialog
      v-model:task="detailTask"
      :mine="detailMine"
      @changed="resource.reload()"
    />
    <PostDialog
      v-model:open="postOpen"
      :post="selectedPost"
      @saved="resource.reload()"
    />
  </div>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import LayoutHeader from "@/components/LayoutHeader.vue";
import SectionCard from "@/components/SectionCard.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import type { Tone } from "@/components/tone";
import PostDialog from "@/pages/content/components/PostDialog.vue";
import TaskDetailDialog, {
  type TaskRef,
} from "@/pages/tasky/components/TaskDetailDialog.vue";
import { formatElapsed, taskTimer } from "@/pages/tasky/taskMeta";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useEventListener, useIntervalFn } from "@vueuse/core";
import { Button, createResource, dayjs, Switch, TabButtons } from "frappe-ui";
import { computed, reactive, ref, watch, type Component } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideBuilding2 from "~icons/lucide/building-2";
import LucideCalendarDays from "~icons/lucide/calendar-days";
import LucideChevronsUp from "~icons/lucide/chevrons-up";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideCirclePause from "~icons/lucide/circle-pause";
import LucideEye from "~icons/lucide/eye";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucidePause from "~icons/lucide/pause";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideTimer from "~icons/lucide/timer";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUser from "~icons/lucide/user";
import LucideUsers from "~icons/lucide/users";
import LucideX from "~icons/lucide/x";
import InProgressPostRow from "./components/InProgressPostRow.vue";
import WorkItemRow from "./components/WorkItemRow.vue";
import {
  IN_PROGRESS_GROUPS,
  type InProgressData,
  type InProgressGroup,
  type InProgressLane,
  type InProgressPost,
  type InProgressTask,
} from "./inProgressMeta";

// rows a lane shows before "Show all", so every project fits on a screen or two
const LANE_ROWS = 6;
const LANE_ICONS: Record<InProgressLane["kind"], Component> = {
  project: LucideFolderKanban,
  person: LucideUser,
  department: LucideBuilding2,
  content: LucideCalendarDays,
};

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}

const group = ref<InProgressGroup>(
  IN_PROGRESS_GROUPS.includes(route.query.group as InProgressGroup)
    ? (route.query.group as InProgressGroup)
    : "project"
);
const filters = reactive({
  department: queryValue("department"),
  customer: queryValue("customer"),
  person: queryValue("person"),
  overdue: queryValue("overdue") === "1",
  hideHold: queryValue("hold") === "hide",
});

const hasFilters = computed(
  () =>
    !!(filters.department || filters.customer || filters.person) ||
    filters.overdue ||
    filters.hideHold
);

function clear() {
  Object.assign(filters, {
    department: "",
    customer: "",
    person: "",
    overdue: false,
    hideHold: false,
  });
}

const resource = createResource({
  url: "helpdesk.api.in_progress.get_in_progress",
  makeParams: () => ({
    group_by: group.value,
    department: filters.department || null,
    customer: filters.customer || null,
    person: filters.person || null,
    only_overdue: filters.overdue ? 1 : 0,
    hide_on_hold: filters.hideHold ? 1 : 0,
  }),
  auto: true,
});

// the grouping and filters live in the URL, so a view can be shared
watch([group, () => ({ ...filters })], ([g, f]) => {
  router.replace({
    query: {
      ...route.query,
      group: g === "project" ? undefined : g,
      department: f.department || undefined,
      customer: f.customer || undefined,
      person: f.person || undefined,
      overdue: f.overdue ? "1" : undefined,
      hold: f.hideHold ? "hide" : undefined,
    },
  });
  resource.reload();
});

// live-ish: coming back to the tab fetches again; tasks publish no realtime events
useEventListener(window, "focus", () => {
  if (!resource.loading) resource.reload();
});

const data = computed(() => resource.data as InProgressData | undefined);
const firstLoad = computed(() => resource.loading && !data.value);
const lanes = computed(() => data.value?.lanes ?? []);
const teamScope = computed(() => data.value?.scope !== "own");

const intro = computed(() =>
  teamScope.value
    ? __(
        "Everything started across the projects you run, and the content posts in production."
      )
    : __("Your started tasks, and the content posts you're working on.")
);

const emptyMessage = computed(() => {
  if (hasFilters.value)
    return __("Nothing started matches. Clear the filters to see everything.");
  return teamScope.value
    ? __("Nobody has started a task, and no post is in production.")
    : __("You have nothing started. Start a task from My Work or the board.");
});

const groupOptions = computed(() => [
  { key: "project", label: __("By project"), icon: LucideFolderKanban },
  { key: "person", label: __("By person"), icon: LucideUsers },
  { key: "department", label: __("By department"), icon: LucideBuilding2 },
]);

interface SummaryPart {
  key: string;
  value: number;
  label: string;
  icon: Component;
  /** red with its icon: late or escalated work */
  alert?: boolean;
}

const summaryParts = computed<SummaryPart[]>(() => {
  const s = data.value?.summary;
  if (!s) return [];
  const parts: SummaryPart[] = [
    {
      key: "in_progress",
      value: s.in_progress,
      label: __("in progress"),
      icon: LucideCircleDot,
    },
    { key: "review", value: s.review, label: __("in review"), icon: LucideEye },
    {
      key: "overdue",
      value: s.overdue,
      label: __("overdue"),
      icon: LucideAlarmClock,
      alert: s.overdue > 0,
    },
    {
      key: "escalated",
      value: s.escalated,
      label: __("escalated"),
      icon: LucideChevronsUp,
      alert: s.escalated > 0,
    },
  ];
  if (auth.inContentTeam)
    parts.push({
      key: "posts",
      value: s.posts,
      label: __("content posts in production"),
      icon: LucideCalendarDays,
    });
  parts.push({
    key: "on_hold",
    value: s.on_hold,
    label: __("on hold"),
    icon: LucidePause,
  });
  return parts;
});

interface LaneBadge {
  key: string;
  label: string;
  tone: Tone;
  icon: Component;
}

function laneBadges(lane: InProgressLane): LaneBadge[] {
  const c = lane.counts;
  const all: (LaneBadge & { count: number })[] = [
    {
      key: "in_progress",
      count: c.in_progress,
      label: __("{0} in progress", String(c.in_progress)),
      tone: "neutral",
      icon: LucideCircleDot,
    },
    {
      key: "review",
      count: c.review,
      label: __("{0} in review", String(c.review)),
      tone: "neutral",
      icon: LucideEye,
    },
    {
      key: "on_hold",
      count: c.on_hold,
      label: __("{0} on hold", String(c.on_hold)),
      tone: "warning",
      icon: LucidePause,
    },
    {
      key: "overdue",
      count: c.overdue,
      label: __("{0} overdue", String(c.overdue)),
      tone: "danger",
      icon: LucideAlarmClock,
    },
    {
      key: "posts",
      count: c.posts,
      label: __("{0} in production", String(c.posts)),
      tone: "neutral",
      icon: LucideCalendarDays,
    },
    {
      key: "missed",
      count: c.missed,
      label: __("{0} missed", String(c.missed)),
      tone: "danger",
      icon: LucideAlarmClock,
    },
    {
      key: "at_risk",
      count: c.at_risk,
      label: __("{0} not approved, live soon", String(c.at_risk)),
      tone: "warning",
      icon: LucideTriangleAlert,
    },
  ];
  return all.filter((b) => b.count > 0);
}

// lanes show their first rows; "Show all" keeps the rest one click away
const expanded = ref(new Set<string>());
const laneKey = (lane: InProgressLane) => `${lane.kind}:${lane.key}`;

function toggleLane(lane: InProgressLane) {
  const next = new Set(expanded.value);
  const key = laneKey(lane);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  expanded.value = next;
}

function shownTasks(lane: InProgressLane) {
  return expanded.value.has(laneKey(lane))
    ? lane.tasks
    : lane.tasks.slice(0, LANE_ROWS);
}

function shownPosts(lane: InProgressLane) {
  if (expanded.value.has(laneKey(lane))) return lane.posts;
  return lane.posts.slice(0, Math.max(LANE_ROWS - lane.tasks.length, 0));
}

function hiddenCount(lane: InProgressLane) {
  const total = lane.tasks.length + lane.posts.length;
  return total > LANE_ROWS ? total - LANE_ROWS : 0;
}

// timers move by the minute here; the board shows the seconds
const now = ref(dayjs());
useIntervalFn(() => (now.value = dayjs()), 30_000);

function timerOf(task: InProgressTask) {
  return taskTimer(task, now.value);
}

const detailTask = ref<TaskRef | null>(null);
const detailMine = ref(true);

function openTask(task: InProgressTask) {
  detailMine.value = task.assignees.includes(auth.userId);
  detailTask.value = {
    name: task.name,
    subject: task.title,
    project: task.project,
    project_name: task.project_name,
  };
}

const postOpen = ref(false);
const selectedPost = ref<{ name: string; publish_on?: string } | null>(null);

function openPost(post: InProgressPost) {
  selectedPost.value = {
    name: post.name,
    publish_on: post.publish_on ?? undefined,
  };
  postOpen.value = true;
}
</script>
