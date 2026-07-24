<template>
  <div class="flex flex-col h-full">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">
          {{ __("Kanban Board") }}
        </div>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto p-4">
      <div
        v-if="!projectId"
        class="flex items-center justify-center h-full"
      >
        <div class="flex flex-col items-center gap-2">
          <GanttChartSquare class="size-12 text-ink-gray-4" />
          <div class="text-lg-medium text-ink-gray-8">
            {{ __("No project selected") }}
          </div>
        </div>
      </div>

      <div
        v-else-if="dashboard.loading"
        class="flex items-center justify-center h-full"
      >
        <div class="text-p-base text-ink-gray-6">{{ __("Loading...") }}</div>
      </div>

      <div
        v-else-if="dashboard.error"
        class="flex items-center justify-center h-full"
      >
        <div class="flex flex-col items-center gap-2">
          <AlertTriangle class="size-10 text-ink-gray-5" />
          <div class="text-p-base text-ink-gray-7">
            {{ __("Failed to load board. Please try again.") }}
          </div>
        </div>
      </div>

      <div v-else class="flex gap-4 h-full overflow-x-auto pb-4">
        <div
          v-for="column in columns"
          :key="column.status"
          class="flex flex-col w-64 shrink-0 bg-surface-gray-1 rounded-lg"
          @dragover.prevent
          @drop="onDrop($event, column.status)"
        >
          <div
            class="flex items-center justify-between px-3 py-3 border-b border-outline-gray-2"
          >
            <span class="text-sm-medium text-ink-gray-8">{{ __(column.label) }}</span>
            <span class="text-xs text-ink-gray-5 bg-surface-gray-3 px-2 py-0.5 rounded-full">
              {{ columnTasks[column.status]?.length ?? 0 }}
            </span>
          </div>

          <div class="flex-1 overflow-auto p-2 flex flex-col gap-2 min-h-[120px]">
            <div v-if="!columnTasks[column.status]?.length" class="flex items-center justify-center flex-1 text-xs text-ink-gray-4 py-4">
              {{ __("No tasks") }}
            </div>

            <div
              v-for="task in columnTasks[column.status]"
              :key="task.name"
              draggable="true"
              class="bg-surface-white border border-outline-gray-2 rounded-lg p-3 cursor-grab active:cursor-grabbing shadow-sm hover:shadow-md transition-shadow"
              :class="{ 'opacity-50': draggingTask === task.name }"
              @dragstart="onDragStart($event, task)"
              @dragend="onDragEnd"
            >
              <div class="flex items-start gap-2 mb-2">
                <GripVertical class="size-4 text-ink-gray-4 shrink-0 mt-0.5 cursor-grab" />
                <span class="text-sm text-ink-gray-9 leading-snug">{{ task.subject || task.title }}</span>
              </div>

              <div class="flex items-center justify-between">
                <span
                  v-if="task.category"
                  class="text-xs font-medium px-2 py-0.5 rounded-full"
                  :class="categoryClasses(task.category)"
                >
                  {{ task.category }}
                </span>
                <span v-else />

                <div class="flex items-center gap-2">
                  <span
                    class="size-2 rounded-full shrink-0"
                    :class="priorityDotClass(task.priority)"
                  />

                  <UserAvatar
                    v-if="task.assigned_to || task.assignee"
                    :name="task.assigned_to || task.assignee"
                    size="sm"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { createResource } from "frappe-ui";
import { __ } from "@/translation";
import LayoutHeader from "@/components/LayoutHeader.vue";
import { UserAvatar } from "@/components";
import GanttChartSquare from "~icons/lucide/gantt-chart-square";
import AlertTriangle from "~icons/lucide/alert-triangle";
import GripVertical from "~icons/lucide/grip-vertical";

const props = defineProps<{
  projectId?: string;
}>();

interface Task {
  name: string;
  subject?: string;
  title?: string;
  status: string;
  category?: string;
  priority?: string;
  assigned_to?: string;
  assignee?: string;
}

const columns = [
  { status: "Open", label: "Open" },
  { status: "Working", label: "Working" },
  { status: "Pending Review", label: "Pending Review" },
  { status: "Completed", label: "Completed" },
  { status: "Cancelled", label: "Cancelled" },
];

const dashboard = createResource({
  url: "helpdesk.tasky.api.get_project_dashboard",
  makeParams: () => ({ project: props.projectId }),
});

const updateTaskStatus = createResource({
  url: "helpdesk.tasky.api.update_task_status",
});

const columnTasks = reactive<Record<string, Task[]>>(
  Object.fromEntries(columns.map((c) => [c.status, []]))
);

const draggingTask = ref<string | null>(null);

watch(
  () => props.projectId,
  (val) => {
    if (val) {
      dashboard.reload();
    }
  },
  { immediate: true }
);

watch(
  () => dashboard.data,
  (data) => {
    if (!data) return;
    for (const col of columns) {
      columnTasks[col.status] = [];
    }

    const phases = data.phases ?? [];
    for (const phase of phases) {
      const tasks = phase.tasks ?? [];
      for (const task of tasks) {
        const status = task.status;
        if (status && columnTasks[status]) {
          columnTasks[status].push(task);
        }
      }
    }
  },
  { deep: true }
);

function onDragStart(e: DragEvent, task: Task) {
  draggingTask.value = task.name;
  if (e.dataTransfer) {
    e.dataTransfer.clearData();
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("application/x-task-name", task.name);
  }
}

function onDragEnd() {
  draggingTask.value = null;
}

function onDrop(e: DragEvent, newStatus: string) {
  const taskName = e.dataTransfer?.getData("application/x-task-name");
  if (!taskName) return;

  let task: Task | undefined;
  for (const col of columns) {
    task = columnTasks[col.status].find((t) => t.name === taskName);
    if (task) break;
  }
  if (!task || task.status === newStatus) return;

  const oldStatus = task.status;
  const idx = columnTasks[oldStatus].indexOf(task);
  if (idx !== -1) {
    columnTasks[oldStatus].splice(idx, 1);
  }
  task.status = newStatus;
  columnTasks[newStatus].push(task);

  updateTaskStatus.submit({ task: task.name, status: newStatus });
}

function categoryClasses(category: string) {
  const map: Record<string, string> = {
    Functional: "bg-ink-blue-1 text-ink-blue-8",
    Development: "bg-ink-purple-1 text-ink-purple-8",
    Support: "bg-ink-green-1 text-ink-green-8",
    Common: "bg-ink-gray-2 text-ink-gray-7",
  };
  return map[category] || map.Common;
}

function priorityDotClass(priority: string) {
  const map: Record<string, string> = {
    Urgent: "bg-ink-red-5",
    High: "bg-ink-amber-5",
    Medium: "bg-ink-blue-4",
    Low: "bg-ink-gray-4",
  };
  return map[priority] || map.Low;
}
</script>
