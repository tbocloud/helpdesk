<template>
  <div class="flex flex-col h-full">
    <LayoutHeader
      :title="__('My Tasks')"
      :subtitle="__('Every task assigned to you, across all your projects.')"
    >
      <template #right-header>
        <Button
          size="md"
          :loading="tasks.loading"
          :aria-label="__('Refresh')"
          @click="tasks.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-[18px]" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="relative flex-1 overflow-auto">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <TaskyState
          v-if="tasks.error && !tasks.data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load your tasks')"
          :message="__('Check your connection and try again.')"
        >
          <Button :label="__('Retry')" @click="tasks.reload()" />
        </TaskyState>

        <template v-else>
          <!-- Summary -->
          <div
            class="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4"
          >
            <StatTile
              v-for="stat in stats"
              :key="stat.key"
              :label="stat.label"
              :value="stat.value"
              :icon="stat.icon"
              :icon-tone="
                stat.key === 'overdue'
                  ? 'danger'
                  : stat.key === 'completed'
                  ? 'success'
                  : 'brand'
              "
              :sub="stat.hint"
              :meter="stat.progress"
              :tone="stat.progress !== undefined ? 'success' : undefined"
              :loading="tasks.loading && !tasks.data"
              :pressed="activeFilter === stat.filter"
              @click="setFilter(stat.filter)"
            />
          </div>

          <!-- Filters -->
          <div class="max-w-full overflow-x-auto">
            <ViewTabs
              :model-value="activeFilter"
              :aria-label="__('Filter tasks by status')"
              :options="
                tabs.map((t) => ({
                  label: __(t.label),
                  value: t.key,
                  count: countFor(t.key),
                }))
              "
              @update:model-value="setFilter($event)"
            />
          </div>

          <!-- List -->
          <section
            class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            :aria-label="__('Tasks')"
          >
            <div class="border-b border-outline-gray-2 px-4 py-4 md:px-4">
              <TextInput
                v-model="search"
                type="search"
                size="md"
                class="w-full md:max-w-sm"
                :placeholder="__('Search tasks or projects')"
                :aria-label="__('Search tasks')"
              >
                <template #prefix>
                  <LucideSearch
                    class="size-[18px] text-ink-gray-6"
                    aria-hidden="true"
                  />
                </template>
              </TextInput>
            </div>
            <div
              class="hidden h-11 grid-cols-[1fr_8rem_7rem_9rem] items-center gap-4 border-b border-outline-gray-2 bg-surface-gray-1 px-4 text-left text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6 md:grid md:px-4"
              aria-hidden="true"
            >
              <span>{{ __("Task") }}</span>
              <span>{{ __("Priority") }}</span>
              <span>{{ __("Status") }}</span>
              <span class="text-right">{{ __("Due") }}</span>
            </div>

            <template v-if="tasks.loading && !tasks.data">
              <div
                v-for="i in 5"
                :key="i"
                class="flex h-14 items-center gap-3 border-b border-outline-gray-1 px-4 last:border-b-0 md:px-4"
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
            </template>

            <TaskyState
              v-else-if="!visibleTasks.length"
              class="py-10"
              :icon="emptyState.icon"
              :title="emptyState.title"
              :message="emptyState.message"
            >
              <Button
                v-if="search || activeFilter !== 'All'"
                :label="__('Show all tasks')"
                @click="resetFilters"
              />
              <Button
                v-else
                :label="__('Browse projects')"
                @click="router.push({ name: 'TaskyProjects' })"
              />
            </TaskyState>

            <ul v-else role="list">
              <li
                v-for="task in visibleTasks"
                :key="task.name"
                class="border-b border-outline-gray-1 last:border-b-0"
              >
                <button
                  type="button"
                  class="grid min-h-16 w-full grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 px-4 py-3 text-left transition-colors hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none md:grid-cols-[1fr_8rem_7rem_9rem] md:px-4"
                  @click="openTask(task)"
                >
                  <div class="flex min-w-0 items-start gap-3">
                    <component
                      :is="statusMeta(task.status).icon"
                      class="mt-0.5 size-4 shrink-0 text-ink-gray-6"
                      aria-hidden="true"
                    />
                    <div class="min-w-0">
                      <div class="flex min-w-0 items-center gap-1.5">
                        <span
                          class="truncate text-[13px] font-medium"
                          :class="
                            isClosed(task)
                              ? 'text-ink-gray-5 line-through'
                              : 'text-ink-gray-9'
                          "
                        >
                          {{ task.subject }}
                        </span>
                        <NewTaskBadge
                          v-if="task.assignment_state"
                          :state="task.assignment_state"
                        />
                        <MilestoneMark v-if="task.is_milestone" />
                        <SlipBadge
                          v-if="task.slip_count && !isClosed(task)"
                          :count="task.slip_count"
                        />
                        <EscalationBadge
                          v-if="!isClosed(task)"
                          :level="task.escalation_level"
                        />
                      </div>
                      <div
                        class="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-1.5 text-[12px] text-ink-gray-6"
                      >
                        <span class="truncate">{{
                          task.project_name || task.project
                        }}</span>
                        <template v-if="task.phase">
                          <span aria-hidden="true">·</span>
                          <span class="truncate">{{ task.phase }}</span>
                        </template>
                        <template v-if="task.category">
                          <span aria-hidden="true">·</span>
                          <span>{{ task.category }}</span>
                        </template>
                        <template v-if="isOnHold(task)">
                          <span aria-hidden="true">·</span>
                          <span class="inline-flex min-w-0 items-center gap-1">
                            <LucidePause
                              class="size-3 shrink-0 text-warning"
                              aria-hidden="true"
                            />
                            <span class="sr-only">{{ __("On hold:") }}</span>
                            <span class="truncate">{{
                              __(task.hold_reason || "On hold")
                            }}</span>
                          </span>
                        </template>
                        <template v-if="task.blocked && !isClosed(task)">
                          <span aria-hidden="true">·</span>
                          <WaitingOn :subject="task.depends_on_subject" />
                        </template>
                      </div>
                      <HoldNote
                        v-if="isOnHold(task)"
                        :note="task.hold_note"
                        :by-name="task.hold_by_name"
                        class="mt-0.5"
                      />
                    </div>
                  </div>

                  <div
                    class="hidden items-center gap-1.5 text-sm text-ink-gray-7 md:flex"
                  >
                    <component
                      :is="priorityIcon(task.priority)"
                      class="size-4 text-ink-gray-6"
                      aria-hidden="true"
                    />
                    {{ task.priority || __("Low") }}
                  </div>

                  <div class="hidden md:block">
                    <TaskStatusBadge :status="task.status" />
                  </div>

                  <div
                    class="flex items-center justify-end gap-1 whitespace-nowrap text-sm tabular-nums"
                    :class="
                      isOnHold(task)
                        ? 'font-medium text-warning'
                        : isOverdue(task)
                        ? 'font-medium text-danger'
                        : 'text-ink-gray-5'
                    "
                    :title="
                      isOnHold(task) && task.due_date
                        ? __(
                            'Due {0}',
                            dayjs(task.due_date).format('D MMM YYYY')
                          )
                        : undefined
                    "
                  >
                    <LucidePause
                      v-if="isOnHold(task)"
                      class="size-3.5"
                      aria-hidden="true"
                    />
                    <LucideAlarmClock
                      v-else-if="isOverdue(task)"
                      class="size-3.5"
                      aria-hidden="true"
                    />
                    {{ dueLabel(task) }}
                  </div>
                </button>
              </li>
            </ul>
          </section>
        </template>
      </div>
    </div>

    <TaskDetailDialog v-model:task="selectedTask" @changed="tasks.reload()" />
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import StatTile from "@/components/StatTile.vue";
import ViewTabs from "@/components/ViewTabs.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { Button, TextInput, createResource, dayjs } from "frappe-ui";
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideListTodo from "~icons/lucide/list-todo";
import LucidePause from "~icons/lucide/pause";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSearch from "~icons/lucide/search";
import LucideSearchX from "~icons/lucide/search-x";
import HoldNote from "./components/HoldNote.vue";
import MilestoneMark from "./components/MilestoneMark.vue";
import NewTaskBadge from "./components/NewTaskBadge.vue";
import SlipBadge from "./components/SlipBadge.vue";
import EscalationBadge from "@/components/EscalationBadge.vue";
import TaskDetailDialog from "./components/TaskDetailDialog.vue";
import TaskStatusBadge from "./components/TaskStatusBadge.vue";
import WaitingOn from "./components/WaitingOn.vue";
import {
  ON_HOLD,
  type AssignmentState,
  holdDays,
  holdDurationLabel,
  isClosed,
  isOnHold,
  isOverdue,
  priorityIcon,
  taskStatusMeta,
} from "./taskMeta";

interface Task {
  name: string;
  subject: string;
  status: string;
  category?: string;
  phase?: string;
  priority?: string;
  project?: string;
  project_name?: string;
  due_date?: string;
  hold_reason?: string | null;
  hold_note?: string | null;
  hold_since?: string | null;
  hold_by_name?: string | null;
  is_milestone?: boolean;
  slip_count?: number;
  escalation_level?: number;
  depends_on_subject?: string | null;
  blocked?: boolean;
  assignment_state?: AssignmentState | null;
}

type Filter =
  | "All"
  | "Open"
  | "Working"
  | "Pending Review"
  | "On Hold"
  | "Completed"
  | "Cancelled"
  | "Overdue";

const route = useRoute();
const router = useRouter();

const tasks = createResource({
  url: "helpdesk.tasky.api.get_my_tasks",
  params: { limit: 500 },
  auto: true,
  transform: (data: Task[]) => data ?? [],
});

const tabs: { key: Filter; label: string }[] = [
  { key: "All", label: "All" },
  { key: "Open", label: "Open" },
  { key: "Working", label: "In progress" },
  { key: "Pending Review", label: "In review" },
  { key: ON_HOLD, label: "On hold" },
  { key: "Overdue", label: "Overdue" },
  { key: "Completed", label: "Completed" },
  { key: "Cancelled", label: "Cancelled" },
];

const allTasks = computed<Task[]>(() => tasks.data ?? []);

const activeFilter = ref<Filter>(
  tabs.some((t) => t.key === route.query.status)
    ? (route.query.status as Filter)
    : "All"
);
const search = ref("");

// keep the filter in the URL so it survives reloads and can be shared
watch(activeFilter, (status) => {
  router.replace({
    query: { ...route.query, status: status === "All" ? undefined : status },
  });
});

function setFilter(filter: Filter) {
  activeFilter.value =
    activeFilter.value === filter && filter !== "All" ? "All" : filter;
}

function resetFilters() {
  activeFilter.value = "All";
  search.value = "";
}

function statusMeta(status: string) {
  const meta = taskStatusMeta(status);
  return { label: __(meta.label), icon: meta.icon };
}

function dueLabel(task: Task) {
  if (isOnHold(task)) return holdDurationLabel(holdDays(task));
  if (!task.due_date) return isOverdue(task) ? __("Past its estimate") : "—";
  const due = dayjs(task.due_date);
  if (isClosed(task)) return due.format("D MMM");
  const days = due.startOf("day").diff(dayjs().startOf("day"), "day");
  if (days < 0)
    return days === -1
      ? __("1 day overdue")
      : __("{0} days overdue", String(-days));
  // worked past its estimate before its due date: overdue already
  if (isOverdue(task)) return __("Past its estimate");
  if (days === 0) return __("Due today");
  if (days === 1) return __("Due tomorrow");
  if (days < 7) return __("Due {0}", due.format("ddd"));
  return due.format("D MMM");
}

function matches(task: Task, filter: Filter) {
  if (filter === "All") return true;
  if (filter === "Overdue") return isOverdue(task);
  return task.status === filter;
}

function countFor(filter: Filter) {
  return allTasks.value.filter((t) => matches(t, filter)).length;
}

// overdue first, then by due date; finished work sinks to the bottom
function sortKey(task: Task) {
  const due = task.due_date
    ? dayjs(task.due_date).valueOf()
    : Number.MAX_SAFE_INTEGER;
  return [isClosed(task) ? 1 : 0, due] as const;
}

const visibleTasks = computed<Task[]>(() => {
  const q = search.value.trim().toLowerCase();
  return allTasks.value
    .filter((t) => matches(t, activeFilter.value))
    .filter(
      (t) =>
        !q ||
        t.subject.toLowerCase().includes(q) ||
        (t.project_name || t.project || "").toLowerCase().includes(q)
    )
    .sort((a, b) => {
      const [ca, da] = sortKey(a);
      const [cb, db] = sortKey(b);
      return ca - cb || da - db;
    });
});

const completed = computed(() => countFor("Completed"));
const completionPercent = computed(() =>
  allTasks.value.length
    ? Math.round((completed.value / allTasks.value.length) * 100)
    : 0
);

const stats = computed(() => [
  {
    key: "total",
    label: __("Assigned"),
    value: allTasks.value.length,
    icon: LucideListTodo,
    filter: "All" as Filter,
  },
  {
    key: "working",
    label: __("In progress"),
    value: countFor("Working"),
    icon: LucideCircleDot,
    filter: "Working" as Filter,
  },
  {
    key: "overdue",
    label: __("Overdue"),
    value: countFor("Overdue"),
    icon: LucideAlarmClock,
    filter: "Overdue" as Filter,
  },
  {
    key: "completed",
    label: __("Completed"),
    value: completed.value,
    icon: LucideCircleCheck,
    filter: "Completed" as Filter,
    hint: `${completionPercent.value}%`,
    progress: completionPercent.value,
  },
]);

const emptyState = computed(() => {
  if (search.value.trim()) {
    return {
      icon: LucideSearchX,
      title: __("No matching tasks"),
      message: __("Try a different search, or clear the filters."),
    };
  }
  if (activeFilter.value !== "All") {
    const tab = tabs.find((t) => t.key === activeFilter.value);
    return {
      icon: LucideCircleCheck,
      title: __("Nothing here"),
      message: __(
        "You have no {0} tasks right now.",
        __(tab?.label ?? "").toLowerCase()
      ),
    };
  }
  return {
    icon: LucideListTodo,
    title: __("No tasks assigned to you yet"),
    message: __(
      "When a project manager assigns you work, it will show up here."
    ),
  };
});

// --- detail dialog ---

const selectedTask = ref<Task | null>(null);

function openTask(task: Task) {
  // opening it marks it seen (TaskDetailDialog), so the mark goes at once
  task.assignment_state = null;
  selectedTask.value = task;
}
</script>
