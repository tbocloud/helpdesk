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
      <div v-if="kanban.loading" class="flex items-center justify-center h-full"><div class="text-p-base text-ink-gray-6">Loading...</div></div>
      <div v-else class="flex gap-4 h-full overflow-x-auto pb-4">
        <div v-for="col in columns" :key="col" class="flex flex-col w-64 shrink-0 bg-surface-gray-1 rounded-lg" @dragover.prevent @drop="onDrop($event, col)">
          <div class="flex items-center justify-between px-3 py-3 border-b border-outline-gray-2">
            <div class="flex items-center gap-2">
              <span class="text-sm-medium text-ink-gray-8">{{ col }}</span>
              <span v-if="col === 'Working'" class="size-1.5 rounded-full bg-ink-green-5 animate-pulse" />
            </div>
            <span class="text-xs text-ink-gray-5 bg-surface-gray-3 px-2 py-0.5 rounded-full">{{ columnTasks[col]?.length ?? 0 }}</span>
          </div>
          <div class="flex-1 overflow-auto p-2 flex flex-col gap-2 min-h-[120px]">
            <div v-if="!columnTasks[col]?.length" class="flex items-center justify-center flex-1 text-xs text-ink-gray-4 py-4">No tasks</div>
            <div v-for="task in columnTasks[col]" :key="task.name" draggable="true"
              class="bg-surface-white border rounded-lg p-3 cursor-grab active:cursor-grabbing shadow-sm hover:shadow-md transition-shadow"
              :class="{ 'opacity-50': draggingTask === task.name, 'border-ink-red-3 bg-ink-red-0': isOverdue(task), 'border-outline-gray-2': !isOverdue(task) }"
              @dragstart="onDragStart($event, task)" @dragend="onDragEnd">
              <div class="flex items-start justify-between gap-2 mb-2">
                <div class="flex items-start gap-2 min-w-0">
                  <GripVertical class="size-4 text-ink-gray-4 shrink-0 mt-0.5 cursor-grab" />
                  <span class="text-sm text-ink-gray-9 leading-snug" :class="{ 'text-ink-red-7': isOverdue(task) }">{{ task.subject }}</span>
                </div>
              </div>

              <div v-if="task.due_date" class="text-xs mb-2" :class="isOverdue(task) ? 'text-ink-red-6 font-medium' : 'text-ink-gray-5'">
                <LucideClock class="size-3 inline mr-1" />{{ formatDate(task.start_date || task.due_date) }}{{ task.start_date ? ' - ' + formatDate(task.due_date) : '' }}
                <span v-if="isOverdue(task)" class="ml-1 text-ink-red-6 font-medium">Overdue</span>
              </div>

              <div v-if="task.status === 'Working' && timers[task.name]?.running" class="flex items-center gap-2 mb-2 px-2 py-1 rounded bg-ink-green-0 border border-ink-green-2">
                <span class="size-2 rounded-full bg-ink-green-5 animate-pulse" />
                <span class="text-xs font-mono text-ink-green-8 tabular-nums">{{ formatElapsed(timers[task.name].elapsed) }}</span>
                <button @click="togglePause(task)" class="ml-auto size-6 flex items-center justify-center rounded hover:bg-ink-green-2 text-ink-green-7 transition-colors" :title="'Pause timer'"><LucidePause class="size-3.5" /></button>
              </div>

              <div v-if="timers[task.name]?.paused" class="flex items-center gap-2 mb-2 px-2 py-1 rounded bg-ink-amber-0 border border-ink-amber-2">
                <LucidePauseCircle class="size-3.5 text-ink-amber-6" />
                <span class="text-xs text-ink-amber-8">{{ formatElapsed(timers[task.name].elapsed) }} (paused)</span>
                <button @click="togglePause(task)" class="ml-auto size-6 flex items-center justify-center rounded hover:bg-ink-amber-2 text-ink-amber-7 transition-colors" :title="'Resume timer'"><LucidePlay class="size-3.5" /></button>
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
        <div class="text-base-semibold text-ink-gray-9 mb-1">Complete Task</div>
        <div class="text-sm text-ink-gray-6 mb-4 truncate">{{ completingTask.subject }}</div>
        <div class="flex flex-col gap-3 mb-4">
          <div>
            <label class="text-xs text-ink-gray-5">Hours Worked</label>
            <input v-model.number="completeHours" type="number" step="0.25" min="0" class="w-full border border-outline-gray-2 rounded px-3 py-1.5 text-sm bg-surface-white focus:outline-none mt-1" />
            <div v-if="preFilledHours" class="text-xs text-ink-gray-4 mt-0.5">Auto-filled from timer: {{ preFilledHours }}h</div>
          </div>
          <div>
            <label class="text-xs text-ink-gray-5">Notes</label>
            <input v-model="completeNotes" class="w-full border border-outline-gray-2 rounded px-3 py-1.5 text-sm bg-surface-white focus:outline-none mt-1" placeholder="What was done?" />
          </div>
        </div>
        <div class="flex justify-end gap-2">
          <button @click="completingTask = null" class="px-4 py-2 text-sm text-ink-gray-7 hover:bg-surface-gray-2 rounded-lg">Cancel</button>
          <button @click="confirmComplete" class="px-5 py-2 text-sm font-medium rounded-lg bg-ink-gray-9 text-ink-white hover:bg-ink-gray-8">Mark Complete</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted } from "vue";
import { useRoute } from "vue-router";
import { createResource } from "frappe-ui";
import { __ } from "@/translation";
import LayoutHeader from "@/components/LayoutHeader.vue";
import GripVertical from "~icons/lucide/grip-vertical";
import LucideClock from "~icons/lucide/clock";
import LucidePause from "~icons/lucide/pause";
import LucidePauseCircle from "~icons/lucide/pause-circle";
import LucidePlay from "~icons/lucide/play";

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
const moveTaskApi = createResource({ url: "helpdesk.tasky.api.move_task" });
const completeResource = createResource({
  url: "helpdesk.tasky.api.complete_task",
  onSuccess() { kanban.reload(); },
  onError(e: any) { alert("Failed to complete: " + (e?.message || e)); },
});

const completingTask = ref<Task | null>(null);
const completeHours = ref(0);
const completeNotes = ref("");
const preFilledHours = ref(0);

const timers = ref<Record<string, { running: boolean; elapsed: number; paused: boolean }>>({});
let tickInterval: any = null;

(function startTick() {
  tickInterval = setInterval(() => {
    for (const k of Object.keys(timers.value)) {
      if (timers.value[k]?.running && !timers.value[k]?.paused) {
        timers.value[k].elapsed += 1;
      }
    }
  }, 1000);
})();
onUnmounted(() => { if (tickInterval) clearInterval(tickInterval); });

watch(() => props.projectId, () => { if (props.projectId) kanban.reload(); });

function stopTimer(task: Task): number {
  const t = timers.value[task.name];
  if (!t) return 0;
  const hours = t.elapsed / 3600;
  frappe.call("helpdesk.tasky.api.stop_timer", { task: task.name }).catch(() => {});
  delete timers.value[task.name];
  return Math.round(hours * 100) / 100;
}

function togglePause(task: Task) {
  const t = timers.value[task.name];
  if (!t) return;
  if (t.paused) {
    t.paused = false;
    frappe.call("helpdesk.tasky.api.start_timer", { task: task.name }).catch(() => {});
  } else {
    t.paused = true;
    frappe.call("helpdesk.tasky.api.stop_timer", { task: task.name }).catch(() => {});
  }
}

function onDragStart(e: DragEvent, task: Task) { draggingTask.value = task.name; e.dataTransfer?.setData("application/x-task-name", task.name); }
function onDragEnd() { draggingTask.value = null; }
function onDrop(e: DragEvent, newStatus: string) {
  const taskName = e.dataTransfer?.getData("application/x-task-name");
  if (!taskName) return;
  let task: Task | undefined;
  for (const col of columns) { task = columnTasks.value[col]?.find((t) => t.name === taskName); if (task) break; }
  if (!task || task.status === newStatus) return;

  if (newStatus === "Completed") {
    preFilledHours.value = stopTimer(task);
    completingTask.value = task;
    completeHours.value = preFilledHours.value || task.estimated_hours || 0;
    completeNotes.value = "";
    return;
  }

  moveTask(task, newStatus);
}

function confirmComplete() {
  const task = completingTask.value;
  if (!task) return;
  completeResource.submit({ task: task.name, hours_worked: completeHours.value, notes: completeNotes.value });
  moveToColumn(task, "Completed");
  completingTask.value = null;
}

function moveTask(task: Task, newStatus: string) {
  if (task.status === "Working") stopTimer(task);
  if (newStatus === "Working" && task.status !== "Working") {
    timers.value[task.name] = { running: true, elapsed: 0, paused: false };
  }
  moveTaskApi.submit({ task: task.name, new_status: newStatus });
  moveToColumn(task, newStatus);
}

function moveToColumn(task: Task, newStatus: string) {
  const arr = columnTasks.value[task.status];
  if (arr) {
    const idx = arr.indexOf(task);
    if (idx !== -1) arr.splice(idx, 1);
  }
  task.status = newStatus;
  if (!columnTasks.value[newStatus]) columnTasks.value[newStatus] = [];
  columnTasks.value[newStatus].push(task);
}

function formatDate(d: string) { return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric" }); }
function formatElapsed(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${h > 0 ? h + 'h ' : ''}${String(m).padStart(2,'0')}m ${String(s).padStart(2,'0')}s`;
}
function getInitials(n: string) { return n.split(" ").map((x) => x[0]).slice(0, 2).join("").toUpperCase(); }
function isOverdue(t: Task) { if (!t.due_date || ["Completed","Cancelled"].includes(t.status)) return false; return new Date(t.due_date) < new Date(); }
function categoryClasses(c: string) { const m: Record<string,string>={Functional:"bg-ink-blue-1 text-ink-blue-8",Development:"bg-ink-purple-1 text-ink-purple-8",Support:"bg-ink-green-1 text-ink-green-8",Common:"bg-ink-gray-2 text-ink-gray-7"}; return m[c]||m.Common; }
function priorityDotClass(p: string) { const m: Record<string,string>={Urgent:"bg-ink-red-5",High:"bg-ink-amber-5",Medium:"bg-ink-blue-4",Low:"bg-ink-gray-4"}; return m[p]||m.Low; }
</script>
