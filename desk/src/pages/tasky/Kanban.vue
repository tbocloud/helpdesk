<template>
  <div class="flex h-full flex-col">
    <!-- without a project it's the person's own board, across all their projects -->
    <LayoutHeader v-if="!projectId">
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("My board") }}</div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :label="__('Refresh')"
          :loading="kanban.loading && !!kanban.data"
          @click="kanban.reload()"
        >
          <template #icon><LucideRefreshCw class="size-4" /></template>
        </Button>
      </template>
    </LayoutHeader>
    <ProjectNav
      v-else
      ref="nav"
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
            projectId
              ? __(
                  "This board is empty. Add a task, or generate one from a template on the Checklist tab."
                )
              : __(
                  "No tasks assigned to you. Tasks given to you in any project show up here."
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
                    col.key === 'Working'
                      ? 'text-info'
                      : col.key === ON_HOLD
                      ? 'text-warning'
                      : 'text-ink-gray-5'
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
                    : col.key === ON_HOLD
                    ? __("Drop a task here to put it on hold")
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
                  <!-- a click (not a drag) on the title opens Edit -->
                  <button
                    v-if="canEdit(task)"
                    type="button"
                    class="min-w-0 flex-1 rounded text-left text-sm leading-snug underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                    :class="
                      col.key === 'Completed'
                        ? 'text-ink-gray-5 line-through'
                        : 'text-ink-gray-9'
                    "
                    :aria-label="__('Edit {0}', task.subject)"
                    @click.stop="editingTask = task"
                  >
                    {{ task.subject }}
                  </button>
                  <span
                    v-else
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
                  <MilestoneMark v-if="task.is_milestone" class="mt-0.5" />
                  <Dropdown
                    v-if="cardActions(task).length"
                    :options="cardActions(task)"
                    align="end"
                  >
                    <Button
                      variant="ghost"
                      size="sm"
                      class="-mr-1 -mt-0.5 shrink-0"
                      :aria-label="__('Actions for {0}', task.subject)"
                    >
                      <template #icon>
                        <LucideMoreHorizontal
                          class="size-4"
                          aria-hidden="true"
                        />
                      </template>
                    </Button>
                  </Dropdown>
                </div>

                <p
                  v-if="!projectId && task.project"
                  class="mt-1 truncate pl-5 text-xs font-medium text-ink-gray-7"
                >
                  {{ task.project_name || task.project }}
                </p>
                <p
                  v-if="assignedByName(task)"
                  class="mt-1 truncate pl-5 text-xs text-ink-gray-5"
                >
                  {{ __("Assigned by {0}", assignedByName(task)) }}
                </p>

                <div
                  v-if="task.blocked && col.key !== 'Completed'"
                  class="mt-2 flex min-w-0"
                >
                  <WaitingOn :subject="task.depends_on_subject" />
                </div>

                <template v-if="isOnHold(task)">
                  <div
                    class="mt-2 flex items-center gap-2 rounded-md bg-warning-soft py-1 pl-2 pr-1 text-warning"
                  >
                    <LucidePause class="size-3.5 shrink-0" aria-hidden="true" />
                    <span class="sr-only">{{ __("On hold:") }}</span>
                    <span class="min-w-0 truncate text-xs font-medium">{{
                      __(task.hold_reason || "On hold")
                    }}</span>
                    <span
                      class="shrink-0 font-mono text-xs tabular-nums"
                      :aria-label="holdDurationLabel(holdDays(task))"
                      :title="holdDurationLabel(holdDays(task))"
                    >
                      {{ __("{0}d", String(holdDays(task))) }}
                    </span>
                    <button
                      type="button"
                      class="ml-auto flex size-6 shrink-0 items-center justify-center rounded transition-colors hover:bg-surface-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                      :aria-label="__('Resume {0}', task.subject)"
                      :title="__('Resume')"
                      @click.stop="resumingTask = task"
                    >
                      <LucidePlay class="size-3.5" aria-hidden="true" />
                    </button>
                  </div>
                  <HoldNote
                    :note="task.hold_note"
                    :by-name="task.hold_by_name"
                    class="mt-1 pl-2"
                  />
                </template>

                <!-- Timer -->
                <div
                  v-else-if="
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
                    class="ml-auto flex size-6 items-center justify-center rounded transition-colors hover:bg-surface-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4 disabled:opacity-50"
                    :aria-label="__('Pause the timer on {0}', task.subject)"
                    :disabled="savingTimer === task.name"
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
                    class="ml-auto flex size-6 items-center justify-center rounded transition-colors hover:bg-surface-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4 disabled:opacity-50"
                    :aria-label="__('Resume the timer on {0}', task.subject)"
                    :disabled="savingTimer === task.name"
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
                  <SlipBadge
                    v-if="task.slip_count && !isClosed(task)"
                    :count="task.slip_count"
                  />
                  <PullRequestChip
                    v-if="task.pull_request"
                    :pr="task.pull_request"
                  />
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
                      class="flex min-w-0 items-center gap-1.5"
                      :title="task.assigned_to"
                    >
                      <span
                        class="flex size-6 shrink-0 items-center justify-center rounded-full bg-surface-gray-3 text-2xs font-medium text-ink-gray-7"
                        aria-hidden="true"
                      >
                        {{
                          initials(task.assigned_to_name || task.assigned_to)
                        }}
                      </span>
                      <!-- the visible name is what screen readers announce -->
                      <span
                        class="max-w-[9rem] truncate text-xs text-ink-gray-7"
                        ><span class="sr-only">{{ __("Assigned to") }} </span
                        >{{ task.assigned_to_name || task.assigned_to }}</span
                      >
                    </span>
                  </div>
                </div>

                <div
                  v-if="canManage && isPendingReview(task)"
                  class="mt-2.5 flex items-center justify-end gap-1.5 border-t border-outline-gray-1 pt-2.5"
                >
                  <Button
                    size="sm"
                    variant="ghost"
                    :label="__('Send back')"
                    @click.stop="sendingBackTask = task"
                  >
                    <template #prefix>
                      <LucideUndo2 class="size-3.5" aria-hidden="true" />
                    </template>
                  </Button>
                  <Button
                    size="sm"
                    variant="subtle"
                    :label="__('Approve')"
                    :loading="
                      approveResource.loading &&
                      approveResource.params?.task === task.name
                    "
                    @click.stop="approve(task)"
                  >
                    <template #prefix>
                      <LucideCheckCheck class="size-3.5" aria-hidden="true" />
                    </template>
                  </Button>
                </div>
              </article>
            </div>
          </section>
        </div>
      </div>
    </div>

    <HoldTaskDialog v-model:task="holdingTask" @held="onHoldChanged" />
    <ResumeTaskDialog v-model:task="resumingTask" @resumed="onHoldChanged" />
    <RequestHelpDialog
      v-model:task="helpingTask"
      :project-id="projectId || helpingTask?.project || ''"
      @requested="kanban.reload()"
    />
    <HandOverTaskDialog
      v-model:task="handingOverTask"
      :project-id="projectId || handingOverTask?.project || ''"
      @handed-over="kanban.reload()"
    />
    <EditTaskDialog
      v-model:task="editingTask"
      :project-id="projectId || editingTask?.project || ''"
      :phases="phasesOf(editingTask?.project)"
      @saved="kanban.reload()"
      @plan="(t) => (planningTask = t as Task)"
    />
    <TaskPlanDialog
      v-model:task="planningTask"
      :project-id="projectId || planningTask?.project || ''"
      @saved="kanban.reload()"
    />
    <SendBackTaskDialog
      v-model:task="sendingBackTask"
      @sent="kanban.reload()"
    />
    <MoveTaskDialog v-model:task="movingTask" @moved="kanban.reload()" />
    <RecurringTaskDialog
      v-if="canManage"
      :open="!!recurringFrom"
      :project-id="projectId"
      :from-task="recurringFrom?.name"
      @update:open="(v: boolean) => !v && (recurringFrom = null)"
    />

    <CompleteTaskDialog
      v-model:task="completingTask"
      :tracked-hours="completingTrackedHours"
      @completed="onCompleted"
    />
  </div>
</template>

<script setup lang="ts">
import { errorText } from "@/utils";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { Button, Dropdown, call, createResource, toast } from "frappe-ui";
import { computed, onUnmounted, ref, watch } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideCalendar from "~icons/lucide/calendar";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCheckCheck from "~icons/lucide/check-check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCirclePause from "~icons/lucide/circle-pause";
import LucideFolderInput from "~icons/lucide/folder-input";
import LucideGripVertical from "~icons/lucide/grip-vertical";
import LucideInfo from "~icons/lucide/info";
import LucideMoreHorizontal from "~icons/lucide/more-horizontal";
import LucidePause from "~icons/lucide/pause";
import LucidePencil from "~icons/lucide/pencil";
import LucidePlay from "~icons/lucide/play";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideRepeat from "~icons/lucide/repeat";
import LucideStar from "~icons/lucide/star";
import LucideUndo2 from "~icons/lucide/undo-2";
import LucideUserPlus from "~icons/lucide/user-plus";
import CompleteTaskDialog from "./components/CompleteTaskDialog.vue";
import EditTaskDialog from "./components/EditTaskDialog.vue";
import HandOverTaskDialog from "./components/HandOverTaskDialog.vue";
import HoldNote from "./components/HoldNote.vue";
import HoldTaskDialog from "./components/HoldTaskDialog.vue";
import MilestoneMark from "./components/MilestoneMark.vue";
import MoveTaskDialog from "./components/MoveTaskDialog.vue";
import LayoutHeader from "@/components/LayoutHeader.vue";
import ProjectNav from "./components/ProjectNav.vue";
import RecurringTaskDialog from "./components/RecurringTaskDialog.vue";
import RequestHelpDialog from "./components/RequestHelpDialog.vue";
import ResumeTaskDialog from "./components/ResumeTaskDialog.vue";
import PullRequestChip from "./components/PullRequestChip.vue";
import SendBackTaskDialog from "./components/SendBackTaskDialog.vue";
import SlipBadge from "./components/SlipBadge.vue";
import TaskPlanDialog from "./components/TaskPlanDialog.vue";
import TaskyState from "@/components/TaskyState.vue";
import WaitingOn from "./components/WaitingOn.vue";
import type { TaskPullRequest } from "./pullRequestMeta";
import {
  ON_HOLD,
  assignedByName,
  blockedMessage,
  blocksMove,
  holdDays,
  holdDurationLabel,
  initials,
  isClosed,
  isOnHold,
  isOverdue,
  isPendingReview,
  loadErrorMessage,
  priorityIcon,
  shortDate,
  taskStatusMeta,
  taskTimer,
  type TaskTimer,
} from "./taskMeta";
import { useApproveTask } from "./useApproveTask";

// no project: the current user's own tasks across every project (sidebar's Board)
const props = defineProps<{ projectId?: string }>();

const nav = ref<InstanceType<typeof ProjectNav> | null>(null);
const canManage = computed(() => !!nav.value?.canManage);
const authStore = useAuthStore();

const columnList = [
  { key: "Open" },
  { key: "Working" },
  { key: "Pending Review" },
  { key: ON_HOLD },
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
  assigned_to_name?: string;
  assignees?: string[];
  assigned_by?: string | null;
  assigned_by_name?: string | null;
  can_move?: boolean;
  custom_recurring_task?: string | null;
  content_post?: string | null;
  project?: string;
  project_name?: string | null;
  due_date?: string;
  estimated_hours?: number;
  custom_timer_start?: string;
  custom_timer_elapsed?: number;
  is_key?: boolean;
  hold_reason?: string | null;
  hold_note?: string | null;
  hold_since?: string | null;
  hold_by_name?: string | null;
  is_milestone?: boolean;
  slip_count?: number;
  depends_on_task?: string | null;
  depends_on_subject?: string | null;
  blocked?: boolean;
  pull_request?: TaskPullRequest | null;
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
  onSuccess(data: { status?: string }) {
    // the server can store a different status (e.g. review before done)
    if (data?.status && data.status !== moveTaskApi.params?.new_status)
      kanban.reload();
  },
  onError(e: any) {
    toast.error(errorText(e, __("Couldn't move the task.")));
    kanban.reload();
  },
});

const holdingTask = ref<Task | null>(null);
const resumingTask = ref<Task | null>(null);
const planningTask = ref<Task | null>(null);
const editingTask = ref<Task | null>(null);
const sendingBackTask = ref<Task | null>(null);
const helpingTask = ref<Task | null>(null);
const handingOverTask = ref<Task | null>(null);
const movingTask = ref<Task | null>(null);
const recurringFrom = ref<Task | null>(null);

const { approve, resource: approveResource } = useApproveTask(() =>
  kanban.reload()
);

// the assignee may edit the description; leads and managers everything
function canEdit(task: Task) {
  return canManage.value || !!task.assignees?.includes(authStore.userId);
}

function cardActions(task: Task) {
  const actions: Record<string, any>[] = [];
  if (canEdit(task))
    actions.push({
      label: __("Edit"),
      icon: LucidePencil,
      onClick: () => (editingTask.value = task),
    });
  if (canEdit(task) && !isClosed(task)) {
    // a task waits on one other task, so asking for help needs it free
    if (!task.blocked)
      actions.push({
        label: __("Ask a teammate for help"),
        icon: LucideUserPlus,
        onClick: () => (helpingTask.value = task),
      });
    actions.push({
      label: __("Hand over"),
      icon: LucideArrowRight,
      onClick: () => (handingOverTask.value = task),
    });
  }
  // whoever assigned it, or the project's manager or lead (the server decides)
  if (task.can_move)
    actions.push({
      label: __("Move to project…"),
      icon: LucideFolderInput,
      onClick: () => (movingTask.value = task),
    });
  if (!canManage.value) return actions;
  // a task a schedule created already repeats
  if (!task.custom_recurring_task)
    actions.push({
      label: __("Make recurring…"),
      icon: LucideRepeat,
      onClick: () => (recurringFrom.value = task),
    });
  if (isClosed(task)) return actions;
  actions.push({
    label: __("Plan"),
    icon: LucideCalendarClock,
    onClick: () => (planningTask.value = task),
  });
  if (isPendingReview(task)) {
    actions.push(
      {
        label: __("Approve"),
        icon: LucideCheckCheck,
        onClick: () => approve(task),
      },
      {
        label: __("Send back"),
        icon: LucideUndo2,
        onClick: () => (sendingBackTask.value = task),
      }
    );
  }
  return actions;
}

// Holding stops the server timer and resuming may start it or move the due date,
// so drop local timer state and take the server's view.
function onHoldChanged(task: { name: string }) {
  delete timers.value[task.name];
  kanban.reload();
}

const totalTasks = computed(() =>
  Object.values(columnTasks.value).reduce(
    (n, list) => n + (list?.length ?? 0),
    0
  )
);

const phaseNames = computed(() => phasesOf(props.projectId));

// phases already used in a project, offered when editing one of its tasks
function phasesOf(project?: string) {
  return Object.values(columnTasks.value)
    .flat()
    .filter((t) => !project || !t.project || t.project === project)
    .map((t) => t.phase || "")
    .filter(Boolean);
}

const completingTask = ref<Task | null>(null);
// what the card's timer shows, so the dialog offers the same hours
const completingTrackedHours = computed(() => {
  const timer = completingTask.value && timers.value[completingTask.value.name];
  return timer ? timer.elapsed / 3600 : null;
});

const timers = ref<Record<string, TaskTimer>>({});
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
  () => kanban.reload(),
  { immediate: true }
);

// The server is the one record of every timer: each load replaces the local state,
// so a timer paused on the server can't come back running from a stale copy.
function restoreTimers(cols: Record<string, Task[]>) {
  const next: Record<string, TaskTimer> = {};
  for (const task of Object.values(cols ?? {}).flat()) {
    const timer = taskTimer(task);
    if (timer) next[task.name] = timer;
  }
  timers.value = next;
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

const savingTimer = ref<string | null>(null);

// Pause and resume are saved on the server, which keeps the task in progress;
// resuming a task that has left In progress moves it back there, like a drop.
async function togglePause(task: Task) {
  const t = timers.value[task.name];
  if (!t || savingTimer.value) return;
  if (t.paused && task.status !== "Working") {
    changeStatus(task, "Working");
    return;
  }
  const pausing = !t.paused;
  savingTimer.value = task.name;
  if (pausing) pauseTimer(task);
  else startOrResumeTimer(task);
  try {
    await call(
      pausing
        ? "helpdesk.tasky.api.stop_timer"
        : "helpdesk.tasky.api.start_timer",
      { task: task.name }
    );
  } catch (e) {
    toast.error(
      errorText(
        e,
        pausing
          ? __("Couldn't pause the timer.")
          : __("Couldn't resume the timer.")
      )
    );
  } finally {
    savingTimer.value = null;
    kanban.reload();
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
  if (task) changeStatus(task, newStatus);
}

function changeStatus(task: Task, newStatus: string) {
  if (task.status === newStatus || task.status === "Completed") return;

  // the server refuses these moves while the dependency is open; don't move the card at all
  if (blocksMove(task, newStatus)) {
    dropTarget.value = null;
    toast.error(blockedMessage(task));
    return;
  }

  // a hold needs a reason, so the move happens only once the dialog is submitted
  if (newStatus === ON_HOLD) {
    dropTarget.value = null;
    if (task.status === "Cancelled") {
      toast.error(__("Cancelled tasks can't be put on hold."));
      return;
    }
    holdingTask.value = task;
    return;
  }

  const fromWorking = task.status === "Working";
  const toWorking = newStatus === "Working";
  const fromHold = isOnHold(task);
  const movesDueDate = fromHold && !!task.due_date && holdDays(task) > 0;

  let targetIdx = -1;
  if (dropTarget.value && columnTasks.value[newStatus]) {
    const arr = columnTasks.value[newStatus];
    const targetTask = arr.find((t) => t.name === dropTarget.value!.name);
    if (targetTask) {
      targetIdx = arr.indexOf(targetTask);
      if (!dropTarget.value.above) targetIdx++;
    }
  }

  // completing records the time worked, so it happens once the dialog is submitted
  // (that also sends it to review when the project wants one); a lead dropping a
  // reviewed task on Completed signs it off instead
  if (newStatus === "Pending Review") {
    dropTarget.value = null;
    completingTask.value = task;
    return;
  }
  if (newStatus === "Completed") {
    dropTarget.value = null;
    if (isPendingReview(task) && canManage.value) approve(task);
    else completingTask.value = task;
    return;
  }

  moveToColumn(task, newStatus, targetIdx);

  if (fromHold) {
    const name = task.name;
    moveTaskApi.submit(
      { task: name, new_status: newStatus },
      {
        onSuccess() {
          toast.success(
            movesDueDate
              ? __("Task resumed. The days on hold were added to its due date.")
              : __("Task resumed")
          );
          onHoldChanged({ name });
        },
      }
    );
    dropTarget.value = null;
    return;
  }

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

// the server stopped the timer and may have sent the task for review
function onCompleted(task: { name: string }) {
  delete timers.value[task.name];
  kanban.reload();
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
