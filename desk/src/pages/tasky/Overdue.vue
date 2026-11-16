<template>
  <div class="flex h-full flex-col">
    <ProjectNav
      :project-id="projectId"
      :phases="phaseNames"
      @task-created="tasks.reload()"
    >
      <template #actions>
        <Button
          size="md"
          :label="__('Refresh')"
          :loading="tasks.loading && !!tasks.data"
          @click="tasks.reload()"
        >
          <template #icon
            ><LucideRefreshCw class="size-[18px]" aria-hidden="true"
          /></template>
        </Button>
      </template>
    </ProjectNav>

    <div class="relative flex-1 overflow-auto">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <TaskyState
          v-if="tasks.error && !tasks.data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load overdue tasks')"
          :message="loadErrorMessage(tasks.error)"
        >
          <Button :label="__('Retry')" @click="tasks.reload()" />
        </TaskyState>

        <template v-else>
          <!-- Summary -->
          <div
            class="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4"
          >
            <!-- a tone only once there is something to flag, as before -->
            <StatTile
              v-for="stat in stats"
              :key="stat.key"
              :label="stat.label"
              :value="stat.value"
              :icon="stat.icon"
              :loading="!tasks.data"
              :icon-tone="
                stat.key === 'ontrack'
                  ? 'success'
                  : stat.value
                  ? stat.key === 'overdue'
                    ? 'danger'
                    : 'warning'
                  : 'neutral'
              "
              :value-tone="
                stat.key === 'overdue' && stat.value ? 'danger' : 'neutral'
              "
            />
          </div>

          <!-- Loading -->
          <div
            v-if="!tasks.data"
            class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            aria-busy="true"
          >
            <div
              v-for="i in 4"
              :key="i"
              class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
            >
              <div
                class="size-4 animate-pulse rounded-full bg-surface-gray-3"
              />
              <div class="flex flex-1 flex-col gap-2">
                <div
                  class="h-3.5 w-2/5 animate-pulse rounded bg-surface-gray-3"
                />
                <div
                  class="h-3 w-1/4 animate-pulse rounded bg-surface-gray-3"
                />
              </div>
            </div>
          </div>

          <!-- All clear -->
          <div
            v-else-if="!overdue.length && !dueThisWeek.length"
            class="rounded-xl border border-outline-gray-2 bg-surface-base"
          >
            <TaskyState
              class="py-10"
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
              class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
              :aria-labelledby="`ov-${section.key}`"
            >
              <h2
                :id="`ov-${section.key}`"
                class="flex items-center gap-2 border-b border-outline-gray-2 px-4 py-3 text-base font-semibold text-ink-gray-9"
              >
                {{ section.label }}
                <span
                  class="min-w-[22px] rounded-full bg-surface-gray-3 px-[7px] py-px text-center text-xs font-semibold tabular-nums text-ink-gray-7"
                  >{{ section.tasks.length }}</span
                >
              </h2>
              <ul role="list" class="divide-y divide-outline-gray-1">
                <li
                  v-for="task in section.tasks"
                  :key="task.name"
                  class="flex items-center gap-3 px-4 py-3"
                >
                  <component
                    :is="section.icon"
                    class="size-4 shrink-0"
                    :class="section.iconClass"
                    aria-hidden="true"
                  />
                  <div class="min-w-0 flex-1">
                    <div
                      class="truncate text-[13px] font-medium text-ink-gray-9"
                    >
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
                    class="hidden max-w-[14rem] items-center gap-2 text-[12px] text-ink-gray-7 md:flex"
                  >
                    <PersonAvatar :name="task.assigned_to" size="md" />
                    <span class="truncate">{{ task.assigned_to }}</span>
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
import PersonAvatar from "@/components/PersonAvatar.vue";
import StatTile from "@/components/StatTile.vue";
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

// a task overdue by its estimate may have no due date: it goes last
const dueValue = (t: Task) =>
  t.due_date ? dayjs(t.due_date).valueOf() : Number.MAX_SAFE_INTEGER;
const byDue = (a: Task, b: Task) => dueValue(a) - dueValue(b);

const overdue = computed(() =>
  allTasks.value.filter((t) => isOverdue(t)).sort(byDue)
);
const dueThisWeek = computed(() =>
  allTasks.value
    .filter((t) => {
      // a task over its hours today is listed as overdue, not as due this week
      if (!t.due_date || isClosed(t) || isOnHold(t) || isOverdue(t))
        return false;
      const days = daysUntil(t.due_date);
      return days >= 0 && days <= 7;
    })
    .sort(byDue)
);
const onTrack = computed(() =>
  allTasks.value.filter(
    (t) =>
      !!t.due_date &&
      !isClosed(t) &&
      !isOnHold(t) &&
      !isOverdue(t) &&
      daysUntil(t.due_date) >= 0
  )
);

const stats = computed(() => [
  {
    key: "overdue",
    label: __("Overdue"),
    value: overdue.value.length,
    icon: LucideAlarmClock,
  },
  {
    key: "week",
    label: __("Due in 7 days"),
    value: dueThisWeek.value.length,
    icon: LucideCalendarClock,
  },
  {
    key: "ontrack",
    label: __("On track"),
    value: onTrack.value.length,
    icon: LucideCircleCheck,
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
  if (!task.due_date) return isOverdue(task) ? __("Past its estimate") : "—";
  const days = daysUntil(task.due_date);
  if (days < 0)
    return days === -1
      ? __("1 day overdue")
      : __("{0} days overdue", String(-days));
  // worked past its estimate before its due date: overdue already
  if (isOverdue(task)) return __("Past its estimate");
  if (days === 0) return __("Due today");
  if (days === 1) return __("Due tomorrow");
  return __("Due {0}", dayjs(task.due_date).format("ddd D MMM"));
}
</script>
