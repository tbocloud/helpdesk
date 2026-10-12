<template>
  <div class="flex h-full flex-col">
    <template v-if="projectId">
      <ProjectNav
        :project-id="projectId"
        :phases="phases.map((p) => p.phase_name)"
        @task-created="dashboard.reload()"
      >
        <template #actions>
          <Button
            variant="ghost"
            :label="__('Refresh')"
            :loading="
              (dashboard.loading || projectDetail.loading) && !!dashboard.data
            "
            @click="reload"
          >
            <template #icon><LucideRefreshCw class="size-4" /></template>
          </Button>
        </template>
      </ProjectNav>
    </template>
    <LayoutHeader v-else>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">
          {{ __("Project dashboard") }}
        </div>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <TaskyState
          v-if="!projectId"
          :icon="LucideGanttChartSquare"
          :title="__('No project selected')"
          :message="__('Pick a project to see its progress, phases and team.')"
        >
          <Button
            :label="__('Browse projects')"
            @click="router.push({ name: 'TaskyProjects' })"
          />
        </TaskyState>

        <TaskyState
          v-else-if="
            (dashboard.error || projectDetail.error) && !dashboard.data
          "
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the dashboard')"
          :message="loadErrorMessage(dashboard.error, projectDetail.error)"
        >
          <Button :label="__('Retry')" @click="reload" />
        </TaskyState>

        <template v-else>
          <!-- Overview -->
          <div
            class="rounded-xl border border-outline-gray-2 bg-surface-base p-4 shadow-sm md:p-5"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <TaskStatusBadge
                    v-if="projectDetail.data"
                    kind="project"
                    :status="projectDetail.data.status"
                  />
                  <span class="truncate font-mono text-xs text-ink-gray-5">{{
                    projectId
                  }}</span>
                </div>
                <div
                  v-if="projectDetail.data?.customer || dateRange"
                  class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-gray-6"
                >
                  <span
                    v-if="projectDetail.data?.customer"
                    class="flex items-center gap-1"
                  >
                    <LucideBuilding2 class="size-3.5" aria-hidden="true" />
                    {{ projectDetail.data.customer }}
                  </span>
                  <span
                    v-if="dateRange"
                    class="flex items-center gap-1 tabular-nums"
                  >
                    <LucideCalendar class="size-3.5" aria-hidden="true" />
                    {{ dateRange }}
                  </span>
                </div>
              </div>
              <div class="text-right">
                <div class="text-xs text-ink-gray-5">
                  {{ progressLabel }}
                </div>
                <div class="text-2xl-semibold tabular-nums text-ink-gray-9">
                  <span
                    v-if="!dashboard.data"
                    class="inline-block h-7 w-14 animate-pulse rounded bg-surface-gray-2"
                  />
                  <template v-else>{{ progressPercent }}%</template>
                </div>
              </div>
            </div>
            <div
              class="mt-4 h-2 w-full overflow-hidden rounded-full bg-surface-gray-2"
              role="progressbar"
              :aria-valuenow="progressPercent"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-label="progressLabel"
            >
              <div
                class="h-full rounded-full bg-surface-gray-7 transition-[width] duration-500"
                :style="{ width: progressPercent + '%' }"
              />
            </div>
          </div>

          <div
            v-if="projectDetail.data?.can_coordinate && undatedCount"
            class="-mb-1 mt-3 flex justify-end"
          >
            <Button
              variant="ghost"
              size="sm"
              :loading="estimateDates.loading"
              :disabled="estimating"
              :label="
                estimating
                  ? __('AI is setting due dates…')
                  : __('Set due dates with AI ({0})', String(undatedCount))
              "
              :title="__('Open tasks without a due date get one from the AI')"
              @click="estimateDates.submit({ project: projectId })"
            >
              <template #prefix>
                <LucideSparkles class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>

          <!-- Stats -->
          <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile
              v-for="card in statCards"
              :key="card.key"
              :label="card.label"
              :value="card.value"
              :icon="card.icon"
              :icon-tone="card.key === 'completed' ? 'success' : card.tone"
              :value-tone="card.tone"
              :loading="!dashboard.data"
              :to="card.to"
              :aria-label="`${card.action}: ${card.value}`"
            />
          </div>

          <!-- Milestones -->
          <section
            v-if="milestones.length || projectDetail.data?.can_coordinate"
            aria-labelledby="pm-milestones"
            class="mt-6"
          >
            <h2
              id="pm-milestones"
              class="mb-2 flex items-center gap-2 text-sm font-medium text-ink-gray-7"
            >
              {{ __("Milestones") }}
              <span
                v-if="milestones.length"
                class="font-mono text-xs tabular-nums text-ink-gray-5"
              >
                {{ milestonesDone }}/{{ milestones.length }}
              </span>
            </h2>
            <div
              class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base shadow-sm"
            >
              <p
                v-if="!milestones.length"
                class="flex items-center gap-2 px-4 py-4 text-p-sm text-ink-gray-6"
              >
                <LucideFlag
                  class="size-4 shrink-0 text-ink-gray-5"
                  aria-hidden="true"
                />
                {{
                  __(
                    "No milestones yet. Mark a task as a milestone from its Plan menu on the checklist or board."
                  )
                }}
              </p>
              <ol v-else role="list">
                <li
                  v-for="m in milestones"
                  :key="m.name"
                  class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-2.5 last:border-b-0"
                >
                  <component
                    :is="milestoneIcon(m)"
                    class="size-4 shrink-0"
                    :class="milestoneIconClass(m)"
                    aria-hidden="true"
                  />
                  <div class="min-w-0 flex-1">
                    <div class="flex min-w-0 items-center gap-2">
                      <span
                        class="truncate text-sm"
                        :class="
                          isClosed(m)
                            ? 'text-ink-gray-5 line-through'
                            : 'text-ink-gray-8'
                        "
                      >
                        {{ m.subject }}
                      </span>
                      <SlipBadge
                        v-if="m.slip_count && !isClosed(m)"
                        :count="m.slip_count"
                      />
                    </div>
                    <div
                      class="mt-0.5 flex items-center gap-1 font-mono text-xs tabular-nums sm:hidden"
                      :class="
                        m.is_overdue
                          ? 'font-medium text-danger'
                          : 'text-ink-gray-5'
                      "
                    >
                      {{ milestoneDate(m) }}
                      <span v-if="m.is_overdue" class="font-sans"
                        >· {{ __("Overdue") }}</span
                      >
                    </div>
                  </div>
                  <span
                    class="hidden w-32 shrink-0 items-center justify-end gap-1 font-mono text-xs tabular-nums sm:flex"
                    :class="
                      m.is_overdue
                        ? 'font-medium text-danger'
                        : 'text-ink-gray-5'
                    "
                  >
                    <LucideAlarmClock
                      v-if="m.is_overdue"
                      class="size-3.5"
                      aria-hidden="true"
                    />
                    {{ milestoneDate(m) }}
                    <span v-if="m.is_overdue" class="sr-only">{{
                      __("Overdue")
                    }}</span>
                  </span>
                  <div class="flex w-28 shrink-0 justify-end">
                    <TaskStatusBadge :status="m.status" />
                  </div>
                </li>
              </ol>
            </div>
          </section>

          <div class="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_20rem]">
            <!-- Phases -->
            <section aria-labelledby="pm-phases">
              <h2
                id="pm-phases"
                class="mb-2 text-sm font-medium text-ink-gray-7"
              >
                {{ __("Phases") }}
              </h2>
              <div
                class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base shadow-sm"
              >
                <template v-if="!dashboard.data">
                  <div
                    v-for="i in 3"
                    :key="i"
                    class="flex flex-col gap-2 border-b border-outline-gray-1 p-4 last:border-b-0"
                    aria-hidden="true"
                  >
                    <div
                      class="h-3.5 w-1/3 animate-pulse rounded bg-surface-gray-2"
                    />
                    <div
                      class="h-1.5 w-full animate-pulse rounded-full bg-surface-gray-2"
                    />
                  </div>
                </template>
                <div
                  v-else-if="phases.length === 0"
                  class="flex flex-col items-center gap-2 px-6 py-10 text-center"
                >
                  <p class="text-p-sm text-ink-gray-6">
                    {{
                      __("No phases yet. Tasks with a phase are grouped here.")
                    }}
                  </p>
                  <Button
                    :label="__('Open checklist')"
                    @click="
                      router.push({
                        name: 'TaskyChecklist',
                        params: { projectId },
                      })
                    "
                  />
                </div>
                <ul v-else role="list">
                  <li
                    v-for="phase in phases"
                    :key="phase.name"
                    class="flex items-center gap-4 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
                  >
                    <div class="min-w-0 flex-1">
                      <div class="flex items-center justify-between gap-2">
                        <span
                          class="flex min-w-0 items-center gap-1.5 text-sm text-ink-gray-8"
                        >
                          <LucideCircleCheck
                            v-if="
                              phase.total_count &&
                              phase.completed_count === phase.total_count
                            "
                            class="size-4 shrink-0 text-success"
                            role="img"
                            :aria-label="__('Phase complete')"
                          />
                          <span class="truncate">{{ phase.phase_name }}</span>
                        </span>
                        <span
                          class="shrink-0 font-mono text-xs tabular-nums text-ink-gray-5"
                        >
                          {{ phase.completed_count }}/{{ phase.total_count }}
                        </span>
                      </div>
                      <div
                        class="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-surface-gray-2"
                      >
                        <div
                          class="h-full rounded-full bg-surface-gray-7 transition-[width] duration-500"
                          :style="{ width: phase.progress_pct + '%' }"
                        />
                      </div>
                    </div>
                    <span
                      class="w-12 shrink-0 text-right font-mono text-xs tabular-nums text-ink-gray-6"
                    >
                      {{ phase.progress_pct }}%
                    </span>
                  </li>
                </ul>
              </div>
            </section>

            <!-- Team -->
            <section aria-labelledby="pm-team">
              <h2
                id="pm-team"
                class="mb-2 flex items-center gap-2 text-sm font-medium text-ink-gray-7"
              >
                {{ __("Team") }}
                <span
                  v-if="teamWorkload.length"
                  class="font-mono text-xs tabular-nums text-ink-gray-5"
                >
                  {{ teamWorkload.length }}
                </span>
              </h2>
              <div
                class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base shadow-sm"
              >
                <template v-if="!projectDetail.data">
                  <div
                    v-for="i in 3"
                    :key="i"
                    class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
                    aria-hidden="true"
                  >
                    <div
                      class="size-6 animate-pulse rounded-full bg-surface-gray-2"
                    />
                    <div
                      class="h-3.5 w-1/2 animate-pulse rounded bg-surface-gray-2"
                    />
                  </div>
                </template>
                <p
                  v-else-if="teamWorkload.length === 0"
                  class="px-4 py-10 text-center text-p-sm text-ink-gray-6"
                >
                  {{ __("No team members yet") }}
                </p>
                <ul v-else role="list">
                  <li
                    v-for="member in teamWorkload"
                    :key="member.user"
                    class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-2.5 last:border-b-0"
                  >
                    <span
                      class="flex size-7 shrink-0 items-center justify-center rounded-full bg-surface-gray-3 text-xs font-medium text-ink-gray-7"
                      aria-hidden="true"
                    >
                      {{ initials(member.full_name || member.user) }}
                    </span>
                    <div class="min-w-0 flex-1">
                      <div class="truncate text-sm text-ink-gray-8">
                        {{ member.full_name || member.user }}
                      </div>
                      <div
                        v-if="member.full_name"
                        class="truncate font-mono text-xs text-ink-gray-5"
                      >
                        {{ member.user }}
                      </div>
                    </div>
                    <!-- with only your own tasks loaded, the count would be partial -->
                    <span
                      v-if="seesAllTasks"
                      class="shrink-0 font-mono text-xs tabular-nums text-ink-gray-6"
                      :title="__('Open tasks assigned')"
                    >
                      {{ openCountFor(member.user) }}
                      <span class="sr-only">{{ __("open tasks") }}</span>
                    </span>
                  </li>
                </ul>
              </div>
            </section>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { errorText } from "@/utils";
import LayoutHeader from "@/components/LayoutHeader.vue";
import { __ } from "@/translation";
import { Button, createResource, dayjs, toast } from "frappe-ui";
import { computed, onBeforeUnmount, ref, watch, type Component } from "vue";
import { useRouter, type RouteLocationRaw } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideBuilding2 from "~icons/lucide/building-2";
import LucideCalendar from "~icons/lucide/calendar";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideEye from "~icons/lucide/eye";
import LucideFlag from "~icons/lucide/flag";
import LucideGanttChartSquare from "~icons/lucide/gantt-chart-square";
import LucideListTodo from "~icons/lucide/list-todo";
import LucidePause from "~icons/lucide/pause";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSparkles from "~icons/lucide/sparkles";
import ProjectNav from "./components/ProjectNav.vue";
import SlipBadge from "./components/SlipBadge.vue";
import TaskStatusBadge from "./components/TaskStatusBadge.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import type { Tone } from "@/components/tone";
import {
  CHECKLIST_FILTERS,
  initials,
  isClosed,
  loadErrorMessage,
} from "./taskMeta";

const props = defineProps<{
  projectId?: string;
}>();

const router = useRouter();

const dashboard = createResource({
  url: "helpdesk.tasky.api.get_project_dashboard",
  makeParams: () => ({ project: props.projectId }),
  onError() {},
});

const projectDetail = createResource({
  url: "helpdesk.tasky.api.get_project_detail",
  makeParams: () => ({ project: props.projectId }),
  onError() {},
});

// members who don't run the project get stats of their own tasks only (task_query)
const seesAllTasks = computed(() => !!projectDetail.data?.sees_all_tasks);
// until the project detail says whose tasks these are (or if it fails), claim neither
const progressLabel = computed(() => {
  if (!projectDetail.data) return __("Progress");
  return seesAllTasks.value ? __("Overall progress") : __("Your progress");
});

function reload() {
  dashboard.reload();
  projectDetail.reload();
}

watch(
  () => props.projectId,
  (val) => {
    if (val) reload();
  },
  { immediate: true }
);

interface PhaseItem {
  name: string;
  phase_name: string;
  total_count: number;
  completed_count: number;
  progress_pct: number;
}

interface TeamMember {
  user: string;
  full_name: string;
}

const progressPercent = computed(() => {
  if (dashboard.data?.stats?.completion_pct != null) {
    return dashboard.data.stats.completion_pct;
  }
  return projectDetail.data?.progress ?? 0;
});

const dateRange = computed(() => {
  const d = projectDetail.data;
  if (!d) return "";
  const fmt = (v: string) => dayjs(v).format("D MMM YYYY");
  if (d.expected_start_date && d.expected_end_date) {
    return `${fmt(d.expected_start_date)} – ${fmt(d.expected_end_date)}`;
  }
  if (d.expected_end_date) return __("Due {0}", fmt(d.expected_end_date));
  if (d.expected_start_date) return __("From {0}", fmt(d.expected_start_date));
  return "";
});

interface StatCard {
  key: string;
  label: string;
  /** the link's accessible name, e.g. "Show on hold tasks" */
  action: string;
  icon: Component;
  value: number;
  tone: Tone;
  to: RouteLocationRaw;
}

const STAT_ICONS: Record<string, Component> = {
  completed: LucideCircleCheck,
  in_progress: LucideCircleDot,
  reviewing: LucideEye,
  on_hold: LucidePause,
  rescheduled: LucideCalendarClock,
  cancelled: LucideCircleX,
};

// colour only where a non-zero count needs someone's attention
const ALERT_TONES: Record<string, Tone> = {
  reviewing: "info",
  overdue: "danger",
  on_hold: "warning",
  rescheduled: "warning",
};

// each tile opens exactly the tasks it counts: Total the whole checklist,
// Overdue its own page, the rest the checklist filtered by the same key
const statCards = computed<StatCard[]>(() => {
  const stats = dashboard.data?.stats ?? {};
  const params = { projectId: props.projectId };
  const tone = (key: string): Tone =>
    (stats[key] ?? 0) > 0 && ALERT_TONES[key] ? ALERT_TONES[key] : "neutral";
  const filterCard = (key: string): StatCard => ({
    key,
    label: __(CHECKLIST_FILTERS[key].label),
    action: __(CHECKLIST_FILTERS[key].action),
    icon: STAT_ICONS[key],
    value: stats[key] ?? 0,
    tone: tone(key),
    to: { name: "TaskyChecklist", params, query: { status: key } },
  });
  return [
    {
      key: "total",
      label: __("Total tasks"),
      action: __("Show all tasks"),
      icon: LucideListTodo,
      value: stats.total ?? 0,
      tone: "neutral",
      to: { name: "TaskyChecklist", params },
    },
    filterCard("completed"),
    filterCard("in_progress"),
    filterCard("reviewing"),
    {
      key: "overdue",
      label: __("Overdue"),
      action: __("Show overdue tasks"),
      icon: LucideAlarmClock,
      value: stats.overdue ?? 0,
      tone: tone("overdue"),
      to: { name: "TaskyOverdue", params },
    },
    filterCard("on_hold"),
    filterCard("rescheduled"),
    filterCard("cancelled"),
  ];
});

const phases = computed<PhaseItem[]>(() => dashboard.data?.phases ?? []);

interface Milestone {
  name: string;
  subject: string;
  status: string;
  due_date: string | null;
  slip_count: number;
  is_overdue: boolean;
}

// the server sorts milestones by due date, undated last
const milestones = computed<Milestone[]>(
  () => dashboard.data?.milestones ?? []
);
const milestonesDone = computed(
  () => milestones.value.filter((m) => m.status === "Completed").length
);

function milestoneDate(m: Milestone) {
  return m.due_date ? dayjs(m.due_date).format("D MMM YYYY") : __("No date");
}

function milestoneIcon(m: Milestone) {
  if (m.status === "Completed") return LucideCircleCheck;
  if (m.status === "Cancelled") return LucideCircleX;
  if (m.is_overdue) return LucideAlarmClock;
  return LucideFlag;
}

function milestoneIconClass(m: Milestone) {
  if (m.status === "Completed") return "text-success";
  if (m.status === "Cancelled") return "text-ink-gray-5";
  if (m.is_overdue) return "text-danger";
  return "text-info";
}

const teamWorkload = computed<TeamMember[]>(
  () => projectDetail.data?.users ?? []
);

function openCountFor(user: string) {
  return (dashboard.data?.tasks ?? []).filter(
    (t: { assigned_to?: string; status?: string }) =>
      t.assigned_to === user && !isClosed(t)
  ).length;
}

const undatedCount = computed(
  () =>
    (dashboard.data?.tasks ?? []).filter(
      (t: { status?: string; due_date?: string | null }) =>
        !t.due_date && !isClosed(t) && t.status !== "Template"
    ).length
);

// the AI fills dates in the background, usually within a minute
const estimating = ref(false);
let reloadTimers: ReturnType<typeof setTimeout>[] = [];

function clearReloadTimers() {
  reloadTimers.forEach(clearTimeout);
  reloadTimers = [];
}

const estimateDates = createResource({
  url: "helpdesk.tasky.api.estimate_undated_tasks",
  onSuccess(data: { queued: number }) {
    if (!data.queued) {
      toast.info(__("Every open task already has a due date"));
      dashboard.reload();
      return;
    }
    toast.success(
      __("AI is setting due dates for {0} tasks", String(data.queued))
    );
    estimating.value = true;
    clearReloadTimers();
    reloadTimers = [
      setTimeout(() => dashboard.reload(), 5000),
      setTimeout(() => {
        estimating.value = false;
        dashboard.reload();
      }, 20000),
    ];
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't set due dates with AI.")));
  },
});

onBeforeUnmount(clearReloadTimers);
</script>
