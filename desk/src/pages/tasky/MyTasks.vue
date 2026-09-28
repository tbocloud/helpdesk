<template>
  <div class="flex flex-col h-full">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("My Tasks") }}</div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="tasks.loading"
          :aria-label="__('Refresh')"
          @click="tasks.reload()"
        >
          <template #icon><LucideRefreshCw class="size-4" /></template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <div
          v-if="tasks.error"
          class="flex flex-col items-center gap-3 py-24 text-center"
        >
          <LucideCircleAlert
            class="size-8 text-ink-gray-5"
            aria-hidden="true"
          />
          <div class="text-base-medium text-ink-gray-8">
            {{ __("Couldn't load your tasks") }}
          </div>
          <Button :label="__('Try again')" @click="tasks.reload()" />
        </div>

        <template v-else>
          <!-- Summary -->
          <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
            <button
              v-for="stat in stats"
              :key="stat.key"
              type="button"
              class="group flex flex-col gap-3 rounded-lg border p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              :class="
                activeFilter === stat.filter
                  ? 'border-outline-gray-4 bg-surface-gray-1'
                  : 'border-outline-gray-2 bg-surface-base hover:border-outline-gray-3'
              "
              :aria-pressed="activeFilter === stat.filter"
              @click="setFilter(stat.filter)"
            >
              <div class="flex items-center justify-between">
                <span class="text-sm text-ink-gray-6">{{ stat.label }}</span>
                <component
                  :is="stat.icon"
                  class="size-4 text-ink-gray-5"
                  aria-hidden="true"
                />
              </div>
              <div class="flex items-end justify-between gap-2">
                <span class="text-2xl-semibold text-ink-gray-9 tabular-nums">
                  <span
                    v-if="tasks.loading && !tasks.data"
                    class="inline-block h-7 w-8 animate-pulse rounded bg-surface-gray-2"
                  />
                  <template v-else>{{ stat.value }}</template>
                </span>
                <span v-if="stat.hint" class="text-xs text-ink-gray-5">
                  {{ stat.hint }}
                </span>
              </div>
              <div
                v-if="stat.progress !== undefined"
                class="h-1 w-full overflow-hidden rounded-full bg-surface-gray-2"
                role="progressbar"
                :aria-valuenow="stat.progress"
                aria-valuemin="0"
                aria-valuemax="100"
              >
                <div
                  class="h-full rounded-full bg-surface-gray-7 transition-[width] duration-500"
                  :style="{ width: `${stat.progress}%` }"
                />
              </div>
            </button>
          </div>

          <!-- Filters -->
          <div
            class="mt-6 flex flex-col gap-3 md:flex-row md:items-center md:justify-between"
          >
            <div
              class="-mx-1 flex gap-1 overflow-x-auto px-1"
              role="tablist"
              :aria-label="__('Filter tasks by status')"
            >
              <button
                v-for="tab in tabs"
                :key="tab.key"
                type="button"
                role="tab"
                :aria-selected="activeFilter === tab.key"
                class="flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                :class="
                  activeFilter === tab.key
                    ? 'bg-surface-gray-3 text-ink-gray-9'
                    : 'text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-8'
                "
                @click="setFilter(tab.key)"
              >
                {{ __(tab.label) }}
                <span
                  class="rounded px-1 text-xs tabular-nums"
                  :class="
                    activeFilter === tab.key
                      ? 'bg-surface-base text-ink-gray-8'
                      : 'text-ink-gray-5'
                  "
                >
                  {{ countFor(tab.key) }}
                </span>
              </button>
            </div>
            <TextInput
              v-model="search"
              type="search"
              class="w-full md:w-64"
              :placeholder="__('Search tasks or projects')"
              :aria-label="__('Search tasks')"
            >
              <template #prefix>
                <LucideSearch
                  class="size-4 text-ink-gray-5"
                  aria-hidden="true"
                />
              </template>
            </TextInput>
          </div>

          <!-- List -->
          <div
            class="mt-3 overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-base"
          >
            <div
              class="hidden grid-cols-[1fr_8rem_7rem_9rem] gap-4 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2 text-xs text-ink-gray-5 md:grid"
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
            </template>

            <div
              v-else-if="!visibleTasks.length"
              class="flex flex-col items-center gap-2 px-6 py-16 text-center"
            >
              <div
                class="mb-1 flex size-12 items-center justify-center rounded-full bg-surface-gray-2"
              >
                <component
                  :is="emptyState.icon"
                  class="size-5 text-ink-gray-6"
                  aria-hidden="true"
                />
              </div>
              <div class="text-base-medium text-ink-gray-8">
                {{ emptyState.title }}
              </div>
              <p class="max-w-sm text-p-sm text-ink-gray-6">
                {{ emptyState.message }}
              </p>
              <Button
                v-if="search || activeFilter !== 'All'"
                class="mt-2"
                :label="__('Show all tasks')"
                @click="resetFilters"
              />
              <Button
                v-else
                class="mt-2"
                :label="__('Browse projects')"
                @click="router.push({ name: 'TaskyProjects' })"
              />
            </div>

            <ul v-else role="list">
              <li
                v-for="task in visibleTasks"
                :key="task.name"
                class="border-b border-outline-gray-1 last:border-b-0"
              >
                <button
                  type="button"
                  class="grid w-full grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 px-4 py-3 text-left transition-colors hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none md:grid-cols-[1fr_8rem_7rem_9rem]"
                  @click="openTask(task)"
                >
                  <div class="flex min-w-0 items-start gap-3">
                    <component
                      :is="statusMeta(task.status).icon"
                      class="mt-0.5 size-4 shrink-0 text-ink-gray-6"
                      aria-hidden="true"
                    />
                    <div class="min-w-0">
                      <div
                        class="truncate text-base"
                        :class="
                          isClosed(task)
                            ? 'text-ink-gray-5 line-through'
                            : 'text-ink-gray-9'
                        "
                      >
                        {{ task.subject }}
                      </div>
                      <div
                        class="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-1.5 text-sm text-ink-gray-5"
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
                      </div>
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
                    <span
                      class="inline-flex items-center rounded-full bg-surface-gray-2 px-2 py-0.5 text-xs text-ink-gray-7"
                    >
                      {{ statusMeta(task.status).label }}
                    </span>
                  </div>

                  <div
                    class="flex items-center justify-end gap-1 text-sm tabular-nums"
                    :class="
                      isOverdue(task)
                        ? 'font-medium text-ink-gray-9'
                        : 'text-ink-gray-5'
                    "
                  >
                    <LucideAlarmClock
                      v-if="isOverdue(task)"
                      class="size-3.5"
                      aria-hidden="true"
                    />
                    {{ dueLabel(task) }}
                  </div>
                </button>
              </li>
            </ul>
          </div>
        </template>
      </div>
    </div>

    <Dialog
      v-model:open="dialogOpen"
      :options="{
        title: selectedTask?.subject,
        size: 'lg',
        actions: selectedTask?.project
          ? [
              {
                label: __('Open project board'),
                variant: 'solid',
                onClick: openBoard,
              },
            ]
          : [],
      }"
    >
      <template #body-content>
        <div v-if="taskDetail.loading" class="flex flex-col gap-3 py-2">
          <div
            v-for="i in 3"
            :key="i"
            class="h-4 animate-pulse rounded bg-surface-gray-2"
          />
        </div>
        <div
          v-else-if="taskDetail.error"
          class="py-2 text-p-sm text-ink-gray-6"
        >
          {{ __("Couldn't load this task.") }}
        </div>
        <div v-else-if="detail" class="flex flex-col gap-5">
          <dl class="grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
            <div v-for="row in detailRows" :key="row.label">
              <dt class="text-xs text-ink-gray-5">{{ row.label }}</dt>
              <dd class="mt-1 flex items-center gap-1.5 text-ink-gray-8">
                <component
                  :is="row.icon"
                  v-if="row.icon"
                  class="size-4 text-ink-gray-6"
                  aria-hidden="true"
                />
                {{ row.value }}
              </dd>
            </div>
          </dl>
          <div>
            <div class="mb-1 text-xs text-ink-gray-5">
              {{ __("Description") }}
            </div>
            <div
              v-if="detail.description"
              class="prose prose-sm max-w-none text-ink-gray-8"
              v-html="detail.description"
            />
            <p v-else class="text-p-sm text-ink-gray-5">
              {{ __("No description") }}
            </p>
          </div>
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import { __ } from "@/translation";
import { Button, Dialog, TextInput, createResource, dayjs } from "frappe-ui";
import { computed, ref, watch, type Component } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCircle from "~icons/lucide/circle";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideEye from "~icons/lucide/eye";
import LucideListTodo from "~icons/lucide/list-todo";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSearch from "~icons/lucide/search";
import LucideSearchX from "~icons/lucide/search-x";
import LucideSignal from "~icons/lucide/signal";
import LucideSignalHigh from "~icons/lucide/signal-high";
import LucideSignalLow from "~icons/lucide/signal-low";
import LucideSignalMedium from "~icons/lucide/signal-medium";

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
  estimated_hours?: number;
  description?: string;
}

type Filter =
  | "All"
  | "Open"
  | "Working"
  | "Pending Review"
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

const taskDetail = createResource({
  url: "helpdesk.tasky.api.get_task_detail",
});

const STATUS_META: Record<string, { label: string; icon: Component }> = {
  Open: { label: __("Open"), icon: LucideCircle },
  Working: { label: __("In progress"), icon: LucideCircleDot },
  "Pending Review": { label: __("In review"), icon: LucideEye },
  Completed: { label: __("Completed"), icon: LucideCircleCheck },
  Cancelled: { label: __("Cancelled"), icon: LucideCircleX },
};

const PRIORITY_ICONS: Record<string, Component> = {
  Urgent: LucideSignal,
  High: LucideSignalHigh,
  Medium: LucideSignalMedium,
  Low: LucideSignalLow,
};

const tabs: { key: Filter; label: string }[] = [
  { key: "All", label: "All" },
  { key: "Open", label: "Open" },
  { key: "Working", label: "In progress" },
  { key: "Pending Review", label: "In review" },
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
  return STATUS_META[status] ?? STATUS_META.Open;
}

function priorityIcon(priority?: string) {
  return PRIORITY_ICONS[priority ?? "Low"] ?? LucideSignalLow;
}

function isClosed(task: Task) {
  return task.status === "Completed" || task.status === "Cancelled";
}

function isOverdue(task: Task) {
  return (
    !!task.due_date &&
    !isClosed(task) &&
    dayjs(task.due_date).isBefore(dayjs(), "day")
  );
}

function dueLabel(task: Task) {
  if (!task.due_date) return "—";
  const due = dayjs(task.due_date);
  if (isClosed(task)) return due.format("D MMM");
  const days = due.startOf("day").diff(dayjs().startOf("day"), "day");
  if (days < 0)
    return days === -1
      ? __("1 day overdue")
      : __("{0} days overdue", String(-days));
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
const dialogOpen = computed({
  get: () => !!selectedTask.value,
  set: (open: boolean) => {
    if (!open) selectedTask.value = null;
  },
});
const detail = computed<Task | null>(() => taskDetail.data ?? null);

const detailRows = computed(() => {
  const d = detail.value;
  if (!d) return [];
  return [
    {
      label: __("Status"),
      value: statusMeta(d.status).label,
      icon: statusMeta(d.status).icon,
    },
    {
      label: __("Priority"),
      value: d.priority || __("Low"),
      icon: priorityIcon(d.priority),
    },
    {
      label: __("Project"),
      value: selectedTask.value?.project_name || d.project || "—",
    },
    { label: __("Phase"), value: d.phase || "—" },
    {
      label: __("Due"),
      value: d.due_date ? dayjs(d.due_date).format("D MMM YYYY") : "—",
    },
    {
      label: __("Estimate"),
      value: d.estimated_hours ? __("{0} hrs", String(d.estimated_hours)) : "—",
    },
  ];
});

function openTask(task: Task) {
  selectedTask.value = task;
  taskDetail.submit({ task: task.name });
}

function openBoard() {
  if (!selectedTask.value?.project) return;
  router.push({
    name: "TaskyKanban",
    params: { projectId: selectedTask.value.project },
  });
}
</script>
