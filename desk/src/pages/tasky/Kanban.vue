<template>
  <div class="flex flex-col h-full">
    <LayoutHeader>
      <template #left-header><div class="text-lg-medium text-ink-gray-9">{{ __("Kanban Board") }}</div></template>
      <template #right-header>
        <div class="flex items-center gap-1">
          <router-link v-for="tab in projectTabs" :key="tab.to" :to="{ name: tab.to, params: { projectId } }" class="px-3 py-1.5 rounded text-sm transition-colors" :class="route.name === tab.to ? 'bg-surface-gray-3 text-ink-gray-9' : 'text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-8'">{{ __(tab.label) }}</router-link>
        </div>
      </template>
    </LayoutHeader>
    <div class="flex-1 overflow-auto p-4">
      <div v-if="kanban.loading" class="flex items-center justify-center h-full"><div class="text-p-base text-ink-gray-6">{{ __("Loading...") }}</div></div>
      <div v-else class="flex gap-4 h-full overflow-x-auto pb-4">
        <div v-for="col in columns" :key="col" class="flex flex-col w-64 shrink-0 bg-surface-gray-1 rounded-lg" @dragover.prevent @drop="onDrop($event, col)">
          <div class="flex items-center justify-between px-3 py-3 border-b border-outline-gray-2">
            <span class="text-sm-medium text-ink-gray-8">{{ __(col) }}</span>
            <span class="text-xs text-ink-gray-5 bg-surface-gray-3 px-2 py-0.5 rounded-full">{{ columnTasks[col]?.length ?? 0 }}</span>
          </div>
          <div class="flex-1 overflow-auto p-2 flex flex-col gap-2 min-h-[120px]">
            <div v-if="!columnTasks[col]?.length" class="flex items-center justify-center flex-1 text-xs text-ink-gray-4 py-4">{{ __("No tasks") }}</div>
            <div v-for="task in columnTasks[col]" :key="task.name" draggable="true"
              class="bg-surface-white border rounded-lg p-3 cursor-grab active:cursor-grabbing shadow-sm hover:shadow-md transition-shadow"
              :class="{ 'opacity-50': draggingTask === task.name, 'border-ink-red-3 bg-ink-red-0': isOverdue(task), 'border-outline-gray-2': !isOverdue(task) }"
              @dragstart="onDragStart($event, task)" @dragend="onDragEnd">
              <div class="flex items-start gap-2 mb-2">
                <GripVertical class="size-4 text-ink-gray-4 shrink-0 mt-0.5 cursor-grab" />
                <span class="text-sm text-ink-gray-9 leading-snug" :class="{ 'text-ink-red-7': isOverdue(task) }">{{ task.subject }}</span>
              </div>
              <div v-if="task.due_date" class="text-xs mb-2" :class="isOverdue(task) ? 'text-ink-red-6 font-medium' : 'text-ink-gray-5'">
                <span class="flex items-center gap-1"><LucideClock class="size-3" />{{ formatDate(task.start_date || task.due_date) }}{{ task.start_date ? ' - ' + formatDate(task.due_date) : '' }}<span v-if="isOverdue(task)" class="ml-1">Overdue</span></span>
              </div>
              <div class="flex items-center justify-between">
                <span v-if="task.category" class="text-xs font-medium px-2 py-0.5 rounded-full" :class="categoryClasses(task.category)">{{ task.category }}</span>
                <span v-else />
                <div class="flex items-center gap-2">
                  <span class="size-2 rounded-full shrink-0" :class="priorityDotClass(task.priority)" />
                  <span v-if="task.assigned_to" class="size-6 rounded-full bg-ink-blue-2 text-ink-blue-8 text-xs font-medium flex items-center justify-center shrink-0">{{ getInitials(task.assigned_to) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="completingTask" class="fixed inset-0 z-50 flex items-center justify-center bg-black/25 backdrop-blur-sm" @click.self="completingTask = null">
      <div class="bg-surface-white border border-outline-gray-2 rounded-xl shadow-xl w-full max-w-sm p-5">
        <div class="text-base-semibold text-ink-gray-9 mb-1">{{ __("Complete Task") }}</div>
        <div class="text-sm text-ink-gray-6 mb-4 truncate">{{ completingTask.subject }}</div>
        <div class="flex flex-col gap-3 mb-4">
          <div class="flex flex-col gap-1">
            <label class="text-xs text-ink-gray-5">{{ __("Hours Worked") }}</label>
            <input v-model.number="completeHours" type="number" step="0.5" min="0" class="border border-outline-gray-2 rounded px-3 py-1.5 text-sm bg-surface-white focus:outline-none" placeholder="e.g. 2.5" />
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-xs text-ink-gray-5">{{ __("Notes") }}</label>
            <input v-model="completeNotes" class="border border-outline-gray-2 rounded px-3 py-1.5 text-sm bg-surface-white focus:outline-none" placeholder="What was done?" />
          </div>
        </div>
        <div class="flex justify-end gap-2">
          <button @click="completingTask = null" class="px-4 py-2 text-sm text-ink-gray-7 hover:bg-surface-gray-2 rounded-lg">{{ __("Cancel") }}</button>
          <button @click="confirmKanbanComplete" class="px-5 py-2 text-sm font-medium rounded-lg bg-ink-gray-9 text-ink-white hover:bg-ink-gray-8">{{ __("Mark Complete") }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { useRoute } from "vue-router";
import { createResource } from "frappe-ui";
import { __ } from "@/translation";
import LayoutHeader from "@/components/LayoutHeader.vue";
import GripVertical from "~icons/lucide/grip-vertical";
import LucideClock from "~icons/lucide/clock";

const props = defineProps<{ projectId: string }>();
const route = useRoute();

const projectTabs = [
  { label: "Dashboard", to: "TaskyProject" }, { label: "Checklist", to: "TaskyChecklist" },
  { label: "Board", to: "TaskyKanban" }, { label: "Timeline", to: "TaskyTimeline" },
  { label: "Overdue", to: "TaskyOverdue" },
];

const columns = ["Open", "Working", "Pending Review", "Completed", "Cancelled"];
const columnTasks = ref<Record<string, Task[]>>({});
const draggingTask = ref<string | null>(null);

interface Task { name: string; subject: string; category?: string; status: string; priority?: string; assigned_to?: string; due_date?: string; start_date?: string; estimated_hours?: number; }

const kanban = createResource({ url: "helpdesk.tasky.api.get_kanban_tasks", params: { project: props.projectId }, auto: true, onSuccess(d: any) { columnTasks.value = d.columns ?? {}; } });
const updateTaskStatus = createResource({ url: "helpdesk.tasky.api.update_task_status" });
const completeResource = createResource({ url: "helpdesk.tasky.api.complete_task" });

const completingTask = ref<Task | null>(null);
const completeHours = ref(0);
const completeNotes = ref("");

watch(() => props.projectId, () => { if (props.projectId) kanban.reload(); });

function onDragStart(e: DragEvent, task: Task) { draggingTask.value = task.name; e.dataTransfer?.setData("application/x-task-name", task.name); }
function onDragEnd() { draggingTask.value = null; }
function onDrop(e: DragEvent, newStatus: string) {
  const taskName = e.dataTransfer?.getData("application/x-task-name");
  if (!taskName) return;
  let task: Task | undefined;
  for (const col of columns) { task = columnTasks.value[col]?.find((t) => t.name === taskName); if (task) break; }
  if (!task || task.status === newStatus) return;

  if (newStatus === "Completed") {
    completingTask.value = task;
    completeHours.value = task.estimated_hours || 0;
    completeNotes.value = "";
    return;
  }

  moveTask(task, newStatus);
}

function confirmKanbanComplete() {
  const task = completingTask.value;
  if (!task) return;
  completeResource.submit({
    task: task.name,
    hours_worked: completeHours.value,
    notes: completeNotes.value,
  });
  moveTask(task, "Completed");
  completingTask.value = null;
}

function moveTask(task: Task, newStatus: string) {
  const idx = columnTasks.value[task.status]?.indexOf(task);
  if (idx !== undefined && idx !== -1) columnTasks.value[task.status].splice(idx, 1);
  task.status = newStatus;
  if (!columnTasks.value[newStatus]) columnTasks.value[newStatus] = [];
  columnTasks.value[newStatus].push(task);
  updateTaskStatus.submit({ task: task.name, status: newStatus });
}
function categoryClasses(c: string) { const m: Record<string, string> = { Functional: "bg-ink-blue-1 text-ink-blue-8", Development: "bg-ink-purple-1 text-ink-purple-8", Support: "bg-ink-green-1 text-ink-green-8", Common: "bg-ink-gray-2 text-ink-gray-7" }; return m[c] || m.Common; }
function getInitials(n: string) { return n.split(" ").map((x) => x[0]).slice(0, 2).join("").toUpperCase(); }
function priorityDotClass(p: string) { const m: Record<string, string> = { Urgent: "bg-ink-red-5", High: "bg-ink-amber-5", Medium: "bg-ink-blue-4", Low: "bg-ink-gray-4" }; return m[p] || m.Low; }
function isOverdue(t: Task) { if (!t.due_date || ["Completed", "Cancelled"].includes(t.status)) return false; return new Date(t.due_date) < new Date(); }
function formatDate(d: string) { return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric" }); }
</script>
