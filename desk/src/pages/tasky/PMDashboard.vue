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
                  {{ __("Overall progress") }}
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
              :aria-label="__('Overall progress')"
            >
              <div
                class="h-full rounded-full bg-surface-gray-7 transition-[width] duration-500"
                :style="{ width: progressPercent + '%' }"
              />
            </div>
          </div>

          <!-- Stats -->
          <div
            class="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6"
          >
            <component
              :is="card.to ? 'router-link' : 'div'"
              v-for="card in statCards"
              :key="card.label"
              :to="card.to"
              class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 bg-surface-base p-4 transition-colors"
              :class="card.to ? 'hover:border-outline-gray-3' : ''"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm text-ink-gray-6">{{ card.label }}</span>
                <component
                  :is="card.icon"
                  class="size-4"
                  :class="card.alert ? 'text-danger' : 'text-ink-gray-5'"
                  aria-hidden="true"
                />
              </div>
              <span
                class="text-2xl-semibold tabular-nums"
                :class="card.alert ? 'text-danger' : 'text-ink-gray-9'"
              >
                <span
                  v-if="!dashboard.data"
                  class="inline-block h-7 w-8 animate-pulse rounded bg-surface-gray-2"
                />
                <template v-else>{{ card.value }}</template>
              </span>
            </component>
          </div>

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
                    <span
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
import LayoutHeader from "@/components/LayoutHeader.vue";
import { __ } from "@/translation";
import { Button, createResource, dayjs } from "frappe-ui";
import { computed, watch } from "vue";
import { useRouter } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideBuilding2 from "~icons/lucide/building-2";
import LucideCalendar from "~icons/lucide/calendar";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideEye from "~icons/lucide/eye";
import LucideGanttChartSquare from "~icons/lucide/gantt-chart-square";
import LucideListTodo from "~icons/lucide/list-todo";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import ProjectNav from "./components/ProjectNav.vue";
import TaskStatusBadge from "./components/TaskStatusBadge.vue";
import TaskyState from "./components/TaskyState.vue";
import { initials, isClosed, loadErrorMessage } from "./taskMeta";

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

const statCards = computed(() => {
  const stats = dashboard.data?.stats ?? {};
  const overdueRoute = {
    name: "TaskyOverdue",
    params: { projectId: props.projectId },
  };
  return [
    { label: __("Total tasks"), icon: LucideListTodo, value: stats.total ?? 0 },
    {
      label: __("Completed"),
      icon: LucideCircleCheck,
      value: stats.completed ?? 0,
    },
    {
      label: __("In progress"),
      icon: LucideCircleDot,
      value: stats.in_progress ?? 0,
    },
    { label: __("In review"), icon: LucideEye, value: stats.reviewing ?? 0 },
    {
      label: __("Overdue"),
      icon: LucideAlarmClock,
      value: stats.overdue ?? 0,
      alert: (stats.overdue ?? 0) > 0,
      to: overdueRoute,
    },
    {
      label: __("Cancelled"),
      icon: LucideCircleX,
      value: stats.cancelled ?? 0,
    },
  ];
});

const phases = computed<PhaseItem[]>(() => dashboard.data?.phases ?? []);

const teamWorkload = computed<TeamMember[]>(
  () => projectDetail.data?.users ?? []
);

function openCountFor(user: string) {
  return (dashboard.data?.tasks ?? []).filter(
    (t: { assigned_to?: string; status?: string }) =>
      t.assigned_to === user && !isClosed(t)
  ).length;
}
</script>
