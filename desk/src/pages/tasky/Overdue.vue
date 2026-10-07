<template>
  <div class="flex h-full flex-col">
    <ProjectNav
      :project-id="projectId"
      :phases="phaseNames"
      @task-created="tasks.reload()"
    >
      <template #actions>
        <Button
          variant="ghost"
          :label="__('Refresh')"
          :loading="tasks.loading && !!tasks.data"
          @click="tasks.reload()"
        >
          <template #icon><LucideRefreshCw class="size-4" /></template>
        </Button>
      </template>
    </ProjectNav>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-5xl px-4 py-5 md:px-6">
        <TaskyState
          v-if="tasks.error && !tasks.data"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load overdue tasks')"
          :message="loadErrorMessage(tasks.error)"
        >
          <Button :label="__('Retry')" @click="tasks.reload()" />
        </TaskyState>

        <template v-else>
          <!-- Summary -->
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div
              v-for="stat in stats"
              :key="stat.key"
              class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 bg-surface-base p-4"
            >
              <div class="flex items-center justify-between">
                <span class="text-sm text-ink-gray-6">{{ stat.label }}</span>
                <component
                  :is="stat.icon"
                  class="size-4"
                  :class="stat.iconClass"
                  aria-hidden="true"
                />
              </div>
              <span
                class="text-2xl-semibold tabular-nums"
                :class="stat.valueClass"
              >
                <span
                  v-if="!tasks.data"
                  class="inline-block h-7 w-8 animate-pulse rounded bg-surface-gray-2"
                />
                <template v-else>{{ stat.value }}</template>
              </span>
            </div>
          </div>

          <!-- Loading -->
          <div
            v-if="!tasks.data"
            class="mt-6 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            aria-busy="true"
          >
            <div
              v-for="i in 4"
              :key="i"
              class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0"
            >
              <div
                class="size-4 animate-pulse rounded-full bg-surface-gray-2"
              />
              <div class="flex flex-1 flex-col gap-2">
                <div
                  class="h-3.5 w-2/5 animate-pulse rounded bg-surface-gray-2"
                />
                <div
                  class="h-3 w-1/4 animate-pulse rounded bg-surface-gray-2"
                />
              </div>
            </div>
          </div>

          <!-- All clear -->
          <div
            v-else-if="!overdue.length && !dueThisWeek.length"
            class="mt-6 rounded-xl border border-outline-gray-2 bg-surface-base"
          >
            <TaskyState
              :icon="LucideCircleCheck"
              :title="__('All tasks are on track')"
              :message="__('Nothing is overdue or due in the next 7 days.')"
            >
              <Button
                :label="__('Open board')"
                @click="
                  router.push({ name: 'TaskyKanban', params: { projectId } })
                "
              />
            </TaskyState>
          </div>

          <template v-else>
            <section
              v-for="section in sections"
              :key="section.key"
              class="mt-6"
              :aria-labelledby="`ov-${section.key}`"
            >
              <h2
                :id="`ov-${section.key}`"
                class="mb-2 flex items-center gap-2 text-sm font-medium text-ink-gray-7"
              >
                {{ section.label }}
                <span class="font-mono text-xs tabular-nums text-ink-gray-5">{{
                  section.tasks.length
                }}</span>
              </h2>
              <ul
                role="list"
                class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base shadow-sm"
              >
                <li
                  v-for="task in section.tasks"
                  :key="task.name"
                  class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
                >
                  <component
                    :is="section.icon"
                    class="size-4 shrink-0"
                    :class="section.iconClass"
                    aria-hidden="true"
                  />
                  <div class="min-w-0 flex-1">
                    <div class="truncate text-sm text-ink-gray-9">
                      {{ task.subject }}
                    </div>
                    <div
                      class="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-xs text-ink-gray-5"
                    >
                      <span v-if="task.phase" class="truncate">{{
                        task.phase
                      }}</span>
                      <span v-if="task.phase" aria-hidden="true">·</span>
                      <span
                        class="tabular-nums"
                        :class="
                          section.key === 'overdue'
                            ? 'font-medium text-danger'
                            : ''
                        "
                      >
                        {{ dueLabel(task) }}
                      </span>
                    </div>
                  </div>
                  <span
                    v-if="task.assigned_to"
                    class="hidden max-w-[12rem] truncate text-xs text-ink-gray-6 md:block"
                  >
                    {{ task.assigned_to }}
                  </span>
                  <TaskStatusBadge :status="task.status" />
                </li>
              </ul>
            </section>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, createResource, dayjs } from "frappe-ui";
import { computed, watch } from "vue";
import { useRouter } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import ProjectNav from "./components/ProjectNav.vue";
import TaskStatusBadge from "./components/TaskStatusBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import {
  daysUntil,
  isClosed,
  isOnHold,
  isOverdue,
  loadErrorMessage,
} from "./taskMeta";

const props = defineProps<{ projectId: string }>();
const router = useRouter();

interface Task {
  name: string;
  subject: string;
  phase?: string;
  status: string;
  due_date?: string;
  assigned_to?: string;
}

const tasks = createResource({
  url: "helpdesk.tasky.api.get_project_dashboard",
  makeParams: () => ({ project: props.projectId }),
  auto: true,
  onError() {},
});
watch(
  () => props.projectId,
  () => {
    if (props.projectId) tasks.reload();
  }
);

const allTasks = computed<Task[]>(() => tasks.data?.tasks ?? []);
const phaseNames = computed(() =>
  allTasks.value.map((t) => t.phase || "").filter(Boolean)
);

const byDue = (a: Task, b: Task) =>
  dayjs(a.due_date).valueOf() - dayjs(b.due_date).valueOf();

const overdue = computed(() =>
  allTasks.value.filter((t) => isOverdue(t)).sort(byDue)
);
const dueThisWeek = computed(() =>
  allTasks.value
    .filter((t) => {
      if (!t.due_date || isClosed(t) || isOnHold(t)) return false;
      const days = daysUntil(t.due_date);
      return days >= 0 && days <= 7;
    })
    .sort(byDue)
);
const onTrack = computed(() =>
  allTasks.value.filter(
    (t) =>
      !!t.due_date && !isClosed(t) && !isOnHold(t) && daysUntil(t.due_date) >= 0
  )
);

const stats = computed(() => [
  {
    key: "overdue",
    label: __("Overdue"),
    value: overdue.value.length,
    icon: LucideAlarmClock,
    iconClass: overdue.value.length ? "text-danger" : "text-ink-gray-5",
    valueClass: overdue.value.length ? "text-danger" : "text-ink-gray-9",
  },
  {
    key: "week",
    label: __("Due in 7 days"),
    value: dueThisWeek.value.length,
    icon: LucideCalendarClock,
    iconClass: dueThisWeek.value.length ? "text-warning" : "text-ink-gray-5",
    valueClass: "text-ink-gray-9",
  },
  {
    key: "ontrack",
    label: __("On track"),
    value: onTrack.value.length,
    icon: LucideCircleCheck,
    iconClass: "text-success",
    valueClass: "text-ink-gray-9",
  },
]);

const sections = computed(() =>
  [
    {
      key: "overdue",
      label: __("Overdue"),
      tasks: overdue.value,
      icon: LucideAlarmClock,
      iconClass: "text-danger",
    },
    {
      key: "week",
      label: __("Due in the next 7 days"),
      tasks: dueThisWeek.value,
      icon: LucideCalendarClock,
      iconClass: "text-warning",
    },
  ].filter((section) => section.tasks.length)
);

function dueLabel(task: Task) {
  if (!task.due_date) return "—";
  const days = daysUntil(task.due_date);
  if (days < 0)
    return days === -1
      ? __("1 day overdue")
      : __("{0} days overdue", String(-days));
  if (days === 0) return __("Due today");
  if (days === 1) return __("Due tomorrow");
  return __("Due {0}", dayjs(task.due_date).format("ddd D MMM"));
}
</script>
