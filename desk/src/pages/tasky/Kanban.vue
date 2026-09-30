<template>
  <div class="flex h-full flex-col">
    <ProjectNav
      :project-id="projectId"
      :phases="phaseNames"
      @task-created="kanban.reload()"
    >
      <template #actions>
        <Button
          variant="ghost"
          :label="__('Refresh')"
          :loading="kanban.loading && !!kanban.data"
          @click="kanban.reload()"
        >
          <template #icon><LucideRefreshCw class="size-4" /></template>
        </Button>
      </template>
    </ProjectNav>

    <div class="min-h-0 flex-1 overflow-hidden">
      <TaskyState
        v-if="kanban.error && !kanban.data"
        error
        :icon="LucideCircleAlert"
        :title="__('Couldn\'t load the board')"
        :message="loadErrorMessage(kanban.error)"
      >
        <Button :label="__('Retry')" @click="kanban.reload()" />
      </TaskyState>

      <!-- Loading -->
      <div
        v-else-if="!kanban.data"
        class="flex h-full gap-3 overflow-x-auto p-4"
        aria-busy="true"
      >
        <div
          v-for="col in columnList"
          :key="col.key"
          class="flex w-72 shrink-0 flex-col gap-2 rounded-xl border border-outline-gray-1 bg-surface-gray-1 p-2"
        >
          <div
            class="mx-1 my-1.5 h-4 w-24 animate-pulse rounded bg-surface-gray-3"
          />
          <div
            v-for="i in 3"
            :key="i"
            class="flex flex-col gap-2 rounded-lg border border-outline-gray-2 bg-surface-base p-3"
          >
            <div class="h-3.5 w-4/5 animate-pulse rounded bg-surface-gray-2" />
            <div class="h-3 w-1/3 animate-pulse rounded bg-surface-gray-2" />
          </div>
        </div>
      </div>

      <div v-else class="flex h-full flex-col">
        <p
          v-if="totalTasks === 0"
          class="mx-4 mt-4 flex items-center gap-2 rounded-lg border border-outline-gray-2 bg-surface-base px-3 py-2.5 text-p-sm text-ink-gray-6"
        >
          <LucideInfo
            class="size-4 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
          {{
            __(
              "This board is empty. Add a task, or generate one from a template on the Checklist tab."
            )
          }}
        </p>

        <div class="flex min-h-0 flex-1 gap-3 overflow-x-auto p-4">
          <section
            v-for="col in columnList"
            :key="col.key"
            class="flex w-72 shrink-0 flex-col rounded-xl border bg-surface-gray-1 transition-colors"
            :class="
              dragOverCol === col.key
                ? 'border-outline-gray-4 bg-surface-gray-2'
                : 'border-outline-gray-1'
            "
            :aria-labelledby="`col-${col.key}`"
            @dragover.prevent="dragOverCol = col.key"
            @dragleave="onColumnDragLeave($event)"
            @drop.prevent="
              onDrop($event, col.key);
              dragOverCol = null;
            "
          >
            <header class="flex items-center justify-between gap-2 px-3 py-2.5">
              <h2
                :id="`col-${col.key}`"
                class="flex items-center gap-2 text-sm font-medium text-ink-gray-8"
              >
                <component
                  :is="taskStatusMeta(col.key).icon"
                  class="size-4"
                  :class="
                    col.key === 'Working' ? 'text-info' : 'text-ink-gray-5'
                  "
                  aria-hidden="true"
                />
                {{ __(taskStatusMeta(col.key).label) }}
              </h2>
              <span
                class="rounded bg-surface-gray-3 px-1.5 font-mono text-xs tabular-nums text-ink-gray-6"
                :aria-label="
                  __('{0} tasks', String(columnTasks[col.key]?.length ?? 0))
                "
              >
                {{ columnTasks[col.key]?.length ?? 0 }}
              </span>
            </header>

            <div
              class="flex min-h-[120px] flex-1 flex-col gap-2 overflow-y-auto px-2 pb-2"
              role="list"
            >
              <div
                v-if="!columnTasks[col.key]?.length"
                class="flex flex-1 items-center justify-center rounded-lg border border-dashed border-outline-gray-3 px-3 py-6 text-center text-xs text-ink-gray-5"
              >
                {{
                  col.key === "Completed"
                    ? __("Drop a task here to complete it")
                    : __("No tasks")
                }}
              </div>

              <article
                v-for="task in columnTasks[col.key]"
                :key="task.name"
                role="listitem"
                :draggable="col.key !== 'Completed'"
                class="relative rounded-lg border border-outline-gray-2 bg-surface-base p-3 shadow-sm transition-[box-shadow,opacity]"
                :class="{
                  'opacity-50': draggingTask === task.name,
                  'cursor-grab hover:border-outline-gray-3 active:cursor-grabbing':
                    col.key !== 'Completed',
                }"
                @dragstart="onDragStart($event, task)"
                @dragend="onDragEnd"
                @dragover.prevent="onCardDragOver($event, task)"
              >
                <div
                  v-if="dropTarget?.name === task.name"
                  class="pointer-events-none absolute inset-x-1 h-0.5 rounded-full bg-brand"
                  :class="dropTarget.above ? '-top-1.5' : '-bottom-1.5'"
                  aria-hidden="true"
                />

                <div class="flex items-start gap-2">
                  <LucideGripVertical
                    v-if="col.key !== 'Completed'"
                    class="-ml-1 mt-0.5 size-4 shrink-0 text-ink-gray-4"
                    aria-hidden="true"
                  />
                  <LucideCircleCheck
                    v-else
                    class="mt-0.5 size-4 shrink-0 text-success"
                    aria-hidden="true"
                  />
                  <span
                    class="min-w-0 flex-1 text-sm leading-snug"
                    :class="
                      col.key === 'Completed'
                        ? 'text-ink-gray-5 line-through'
                        : 'text-ink-gray-9'
                    "
                  >
                    {{ task.subject }}
                  </span>
                  <template v-if="task.is_key">
                    <LucideStar
                      class="mt-0.5 size-3.5 shrink-0 fill-current text-warning"
                      aria-hidden="true"
                    />
                    <span class="sr-only">{{ __("Key task") }}</span>
                  </template>
                </div>

                <!-- Timer -->
                <div
                  v-if="
                    timers[task.name]?.running && !timers[task.name]?.paused
                  "
                  class="mt-2 flex items-center gap-2 rounded-md bg-success-soft py-1 pl-2 pr-1 text-success"
                >
                  <span
                    class="size-1.5 animate-pulse rounded-full bg-success"
                    aria-hidden="true"
                  />
                  <span class="text-xs font-medium">{{ __("Tracking") }}</span>
                  <span class="font-mono text-xs tabular-nums">{{
                    formatElapsed(timers[task.name].elapsed)
                  }}</span>
                  <button
                    type="button"
                    class="ml-auto flex size-6 items-center justify-center rounded transition-colors hover:bg-surface-base"
                    :aria-label="__('Pause timer')"
                    @click.stop="togglePause(task)"
                  >
                    <LucidePause class="size-3.5" aria-hidden="true" />
                  </button>
                </div>
                <div
                  v-else-if="timers[task.name]?.paused"
                  class="mt-2 flex items-center gap-2 rounded-md bg-warning-soft py-1 pl-2 pr-1 text-warning"
                >
                  <LucideCirclePause class="size-3.5" aria-hidden="true" />
                  <span class="text-xs font-medium">{{ __("Paused") }}</span>
                  <span class="font-mono text-xs tabular-nums">{{
                    formatElapsed(timers[task.name].elapsed)
                  }}</span>
                  <button
                    type="button"
                    class="ml-auto flex size-6 items-center justify-center rounded transition-colors hover:bg-surface-base"
                    :aria-label="__('Resume timer')"
                    @click.stop="togglePause(task)"
                  >
                    <LucidePlay class="size-3.5" aria-hidden="true" />
                  </button>
                </div>

                <div class="mt-2.5 flex items-center gap-2">
                  <span
                    v-if="task.category"
                    class="truncate rounded bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-6"
                  >
                    {{ task.category }}
                  </span>
                  <span
                    v-if="task.due_date"
                    class="flex shrink-0 items-center gap-1 text-xs tabular-nums"
                    :class="
                      isOverdue(task)
                        ? 'font-medium text-danger'
                        : 'text-ink-gray-5'
                    "
                  >
                    <component
                      :is="isOverdue(task) ? LucideAlarmClock : LucideCalendar"
                      class="size-3.5"
                      aria-hidden="true"
                    />
                    {{ shortDate(task.due_date) }}
                    <span v-if="isOverdue(task)">· {{ __("Overdue") }}</span>
                  </span>
                  <div class="ml-auto flex shrink-0 items-center gap-1.5">
                    <component
                      :is="priorityIcon(task.priority)"
                      class="size-4"
                      :class="
                        task.priority === 'Urgent'
                          ? 'text-danger'
                          : 'text-ink-gray-5'
                      "
                      role="img"
                      :aria-label="
                        __('{0} priority', __(task.priority || 'Low'))
                      "
                    />
                    <span
                      v-if="task.assigned_to"
                      class="flex size-6 items-center justify-center rounded-full bg-surface-gray-3 text-2xs font-medium text-ink-gray-7"
                      :title="task.assigned_to"
                      role="img"
                      :aria-label="__('Assigned to {0}', task.assigned_to)"
                    >
                      {{ initials(task.assigned_to) }}
                    </span>
                  </div>
                </div>
              </article>
            </div>
          </section>
        </div>
      </div>
    </div>

    <Dialog
      v-model:open="completeDialogOpen"
      :title="__('Complete task')"
      :message="completingTask?.subject"
      size="md"
    >
      <form
        id="tasky-kanban-complete"
        class="flex flex-col gap-4"
        @submit.prevent="confirmComplete"
      >
        <div class="flex flex-col gap-1.5">
          <TextInput
            v-model.number="completeHours"
            type="number"
            step="0.25"
            min="0"
            :label="__('Hours worked')"
          />
          <p
            v-if="preFilledHours"
            class="flex items-center gap-1 text-xs text-ink-gray-5"
          >
            <LucideTimer class="size-3.5" aria-hidden="true" />
            {{ __("Filled in from the timer: {0} h", String(preFilledHours)) }}
          </p>
        </div>
        <Textarea
          v-model="completeNotes"
          :label="__('Notes')"
          :placeholder="__('What was done?')"
          :rows="3"
        />
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            type="submit"
            form="tasky-kanban-complete"
            :label="__('Submit timesheet')"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import {
  Button,
  Dialog,
  TextInput,
  Textarea,
  createResource,
  toast,
} from "frappe-ui";
import { computed, onUnmounted, ref, watch } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCalendar from "~icons/lucide/calendar";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCirclePause from "~icons/lucide/circle-pause";
import LucideGripVertical from "~icons/lucide/grip-vertical";
import LucideInfo from "~icons/lucide/info";
import LucidePause from "~icons/lucide/pause";
import LucidePlay from "~icons/lucide/play";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideStar from "~icons/lucide/star";
import LucideTimer from "~icons/lucide/timer";
import ProjectNav from "./components/ProjectNav.vue";
import TaskyState from "./components/TaskyState.vue";
import {
  initials,
  isOverdue,
  loadErrorMessage,
  priorityIcon,
  shortDate,
  taskStatusMeta,
} from "./taskMeta";

const props = defineProps<{ projectId: string }>();

const columnList = [
  { key: "Open" },
  { key: "Working" },
  { key: "Pending Review" },
  { key: "Completed" },
  { key: "Cancelled" },
];
const columnKeys = columnList.map((c) => c.key);
const columnTasks = ref<Record<string, Task[]>>({});
const draggingTask = ref<string | null>(null);
const dragOverCol = ref<string | null>(null);
const dropTarget = ref<{ name: string; above: boolean } | null>(null);

interface Task {
  name: string;
  subject: string;
  category?: string;
  phase?: string;
  status: string;
  priority?: string;
  assigned_to?: string;
  due_date?: string;
  estimated_hours?: number;
  custom_timer_start?: string;
  custom_timer_elapsed?: number;
  is_key?: boolean;
}

const kanban = createResource({
  url: "helpdesk.tasky.api.get_kanban_tasks",
  makeParams: () => ({ project: props.projectId }),
  onSuccess(d: any) {
    columnTasks.value = d.columns ?? {};
    restoreTimers(d.columns);
  },
  onError() {},
});

// Moves are applied optimistically; on failure, reload so the board matches the server again.
const moveTaskApi = createResource({
  url: "helpdesk.tasky.api.move_task",
  onError(e: any) {
    toast.error(errorText(e, __("Couldn't move the task.")));
    kanban.reload();
  },
});
const completeResource = createResource({
  url: "helpdesk.tasky.api.complete_task",
  onSuccess() {
    kanban.reload();
  },
  onError(e: any) {
    toast.error(errorText(e, __("Couldn't complete the task.")));
    kanban.reload();
  },
});

function errorText(e: any, fallback: string) {
  return e?.messages?.length ? e.messages.join(" ") : e?.message || fallback;
}

const totalTasks = computed(() =>
  Object.values(columnTasks.value).reduce(
    (n, list) => n + (list?.length ?? 0),
    0
  )
);

const phaseNames = computed(() =>
  Object.values(columnTasks.value)
    .flat()
    .map((t) => t.phase || "")
    .filter(Boolean)
);

const completingTask = ref<Task | null>(null);
const completeHours = ref(0);
const completeNotes = ref("");
const preFilledHours = ref(0);

const completeDialogOpen = computed({
  get: () => !!completingTask.value,
  set: (open: boolean) => {
    if (!open) completingTask.value = null;
  },
});

interface TimerState {
  running: boolean;
  paused: boolean;
  elapsed: number;
}
const timers = ref<Record<string, TimerState>>({});
let tickInterval: ReturnType<typeof setInterval> | null = null;

(function startTick() {
  tickInterval = setInterval(() => {
    for (const k of Object.keys(timers.value)) {
      if (timers.value[k]?.running && !timers.value[k]?.paused) {
        timers.value[k].elapsed += 1;
      }
    }
  }, 1000);
})();
onUnmounted(() => {
  if (tickInterval) clearInterval(tickInterval);
});

watch(
  () => props.projectId,
  () => {
    if (props.projectId) kanban.reload();
  },
  { immediate: true }
);

function restoreTimers(cols: Record<string, any[]>) {
  if (!cols) return;
  for (const col of Object.values(cols)) {
    for (const task of col || []) {
      if (task.status === "Working" && task.custom_timer_start) {
        const start = new Date(task.custom_timer_start).getTime();
        const now = Date.now();
        const elapsed = Math.floor((now - start) / 1000);
        const pausedElapsed = (task.custom_timer_elapsed || 0) * 3600;
        timers.value[task.name] = {
          running: true,
          paused: false,
          elapsed: elapsed + pausedElapsed,
        };
      } else if (task.custom_timer_elapsed > 0) {
        timers.value[task.name] = {
          running: false,
          paused: true,
          elapsed: (task.custom_timer_elapsed || 0) * 3600,
        };
      }
    }
  }
}

const PAUSE_STATUSES = ["Open", "Pending Review"];

function startOrResumeTimer(task: Task) {
  const existing = timers.value[task.name];
  if (existing && existing.paused) {
    existing.paused = false;
    existing.running = true;
  } else if (existing && existing.running) {
    return;
  } else {
    timers.value[task.name] = { running: true, paused: false, elapsed: 0 };
  }
}

function pauseTimer(task: Task) {
  const t = timers.value[task.name];
  if (t) {
    t.paused = true;
    t.running = false;
  }
}

function finalizeTimer(task: Task): number {
  const t = timers.value[task.name];
  if (!t) return 0;
  const hours = t.elapsed / 3600;
  delete timers.value[task.name];
  return Math.round(hours * 100) / 100;
}

function togglePause(task: Task) {
  const t = timers.value[task.name];
  if (!t) return;
  if (t.paused) {
    startOrResumeTimer(task);
  } else {
    pauseTimer(task);
  }
}

function onDragStart(e: DragEvent, task: Task) {
  if (task.status === "Completed") {
    e.preventDefault();
    return;
  }
  draggingTask.value = task.name;
  if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
  e.dataTransfer?.setData("application/x-task-name", task.name);
}
function onDragEnd() {
  draggingTask.value = null;
  dropTarget.value = null;
  dragOverCol.value = null;
}

// dragleave also fires when moving onto a child card; only clear when the pointer leaves the column
function onColumnDragLeave(e: DragEvent) {
  const column = e.currentTarget as HTMLElement;
  if (!column.contains(e.relatedTarget as Node | null))
    dragOverCol.value = null;
}

function onCardDragOver(e: DragEvent, task: Task) {
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
  const above = e.clientY < rect.top + rect.height / 2;
  dropTarget.value = { name: task.name, above };
}

function onDrop(e: DragEvent, newStatus: string) {
  dragOverCol.value = null;
  const taskName = e.dataTransfer?.getData("application/x-task-name");
  if (!taskName) return;
  let task: Task | undefined;
  for (const col of columnKeys) {
    const arr = columnTasks.value[col];
    if (!arr) continue;
    task = arr.find((t) => t.name === taskName);
    if (task) break;
  }
  if (!task || task.status === newStatus || task.status === "Completed") return;

  const fromWorking = task.status === "Working";
  const toWorking = newStatus === "Working";

  let targetIdx = -1;
  if (dropTarget.value && columnTasks.value[newStatus]) {
    const arr = columnTasks.value[newStatus];
    const targetTask = arr.find((t) => t.name === dropTarget.value!.name);
    if (targetTask) {
      targetIdx = arr.indexOf(targetTask);
      if (!dropTarget.value.above) targetIdx++;
    }
  }

  if (newStatus === "Completed") {
    preFilledHours.value = fromWorking ? finalizeTimer(task) : 0;
    completingTask.value = task;
    completeHours.value = preFilledHours.value || task.estimated_hours || 0;
    completeNotes.value = "";
    dropTarget.value = null;
    return;
  }

  moveToColumn(task, newStatus, targetIdx);

  if (toWorking) {
    startOrResumeTimer(task);
  } else if (fromWorking) {
    if (PAUSE_STATUSES.includes(newStatus)) {
      pauseTimer(task);
    } else {
      finalizeTimer(task);
    }
  }

  moveTaskApi.submit({ task: task.name, new_status: newStatus });
  dropTarget.value = null;
}

function confirmComplete() {
  const task = completingTask.value;
  if (!task) return;
  completeResource.submit({
    task: task.name,
    hours_worked: completeHours.value || 0.25,
    notes: completeNotes.value,
  });
  finalizeTimer(task);
  moveToColumn(task, "Completed");
  completingTask.value = null;
  dropTarget.value = null;
}

function moveToColumn(task: Task, newStatus: string, insertAt: number = -1) {
  const arr = columnTasks.value[task.status];
  if (arr) {
    const idx = arr.indexOf(task);
    if (idx !== -1) arr.splice(idx, 1);
  }
  task.status = newStatus;
  if (!columnTasks.value[newStatus]) columnTasks.value[newStatus] = [];
  if (insertAt >= 0) {
    columnTasks.value[newStatus].splice(insertAt, 0, task);
  } else {
    columnTasks.value[newStatus].push(task);
  }
}

function formatElapsed(s: number) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return `${h > 0 ? h + "h " : ""}${String(m).padStart(2, "0")}m ${String(
    sec
  ).padStart(2, "0")}s`;
}
</script>
