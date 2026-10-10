<template>
  <Dialog
    v-model:open="dialogOpen"
    :options="{
      title: task?.subject || detail?.subject,
      size: 'lg',
      actions: dialogActions,
    }"
  >
    <template #body-content>
      <div
        v-if="taskDetail.loading"
        class="flex flex-col gap-3 py-2"
        :aria-label="__('Loading')"
      >
        <div
          v-for="i in 3"
          :key="i"
          class="h-4 animate-pulse rounded bg-surface-gray-2"
        />
      </div>
      <p
        v-else-if="taskDetail.error"
        class="py-2 text-p-sm text-ink-gray-6"
        role="alert"
      >
        {{ errorText(taskDetail.error, __("Couldn't load this task.")) }}
      </p>
      <div v-else-if="detail" class="flex flex-col gap-5">
        <div
          v-if="isOnHold(detail)"
          class="flex flex-col gap-1 rounded-md bg-warning-soft px-3 py-2.5 text-sm text-warning"
        >
          <span class="flex items-center gap-2 font-medium">
            <LucidePause class="size-4 shrink-0" aria-hidden="true" />
            <span class="tabular-nums">{{
              holdDurationLabel(holdDays(detail))
            }}</span>
            <template v-if="detail.hold_reason">
              <span aria-hidden="true">·</span>
              <span>{{ __(detail.hold_reason) }}</span>
            </template>
          </span>
          <p v-if="detail.hold_note" class="pl-6 text-p-sm text-ink-gray-7">
            {{ detail.hold_note }}
          </p>
          <p
            v-if="holdByLabel(detail)"
            class="pl-6 text-p-sm tabular-nums text-ink-gray-5"
          >
            {{ holdByLabel(detail) }}
          </p>
        </div>
        <div
          v-if="detail.blocked && !isClosed(detail)"
          class="flex items-start gap-2 rounded-md bg-warning-soft px-3 py-2.5 text-p-sm text-warning"
        >
          <LucideLock class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            {{ waitingOnLabel(detail.depends_on_subject) }}.
            {{ __("It can't start or finish until that task is done.") }}
          </span>
        </div>
        <div
          v-if="detail.is_milestone || detail.slip_count"
          class="flex flex-wrap items-center gap-2"
        >
          <TaskyBadge
            v-if="detail.is_milestone"
            tone="info"
            :icon="LucideFlag"
            :label="__('Milestone')"
          />
          <SlipBadge v-if="detail.slip_count" :count="detail.slip_count" />
        </div>
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
          <div class="mb-1 flex items-center gap-2 text-xs text-ink-gray-5">
            {{ __("Description") }}
            <AiDraftedChip v-if="detail.ai_description" />
          </div>
          <!-- descriptions typed in the task dialogs are plain text, so keep their line breaks -->
          <div
            v-if="detail.description"
            class="prose prose-sm max-w-none whitespace-pre-line text-ink-gray-8"
            v-html="sanitizeRichText(detail.description)"
          />
          <p v-else class="text-p-sm text-ink-gray-5">
            {{ __("No description") }}
          </p>
        </div>
        <p
          v-if="detail.custom_recurring_task && project"
          class="flex items-center gap-1.5 text-p-sm text-ink-gray-6"
        >
          <LucideRepeat class="size-4 shrink-0" aria-hidden="true" />
          <span>{{ __("Created by a recurring schedule.") }}</span>
          <router-link
            :to="{ name: 'TaskyRecurring', params: { projectId: project } }"
            class="rounded text-ink-gray-8 underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            @click="close"
            >{{ __("See the schedule") }}</router-link
          >
        </p>
        <TaskPullRequests :pull-requests="detail.pull_requests" />
        <MeetingsCard
          reference-doctype="Task"
          :reference-name="detail.name"
          flush
        />
        <!-- every step in this dialog closes it first, so reopening loads fresh activity -->
        <TaskActivity
          :task="detail.name"
          class="border-t border-outline-gray-1 pt-4"
        />
      </div>
    </template>
  </Dialog>

  <CompleteTaskDialog v-model:task="completingTask" @completed="changed" />
  <HoldTaskDialog v-model:task="holdingTask" @held="changed" />
  <RequestHelpDialog v-model:task="helpingTask" @requested="changed" />
  <HandOverTaskDialog v-model:task="handingOverTask" @handed-over="changed" />
  <ResumeTaskDialog v-model:task="resumingTask" @resumed="changed" />
  <EditTaskDialog
    v-model:task="editingTask"
    @saved="changed"
    @plan="(t) => (planningTask = t as TaskDetail)"
  />
  <TaskPlanDialog v-model:task="planningTask" @saved="changed" />
  <SendBackTaskDialog v-model:task="sendingBackTask" @sent="changed" />
  <MoveTaskDialog v-model:task="movingTask" @moved="changed" />
  <RecurringTaskDialog
    v-if="recurringFrom?.project"
    :open="!!recurringFrom"
    :project-id="recurringFrom.project"
    :from-task="recurringFrom.name"
    @update:open="(v: boolean) => !v && (recurringFrom = null)"
  />
</template>

<script setup lang="ts">
import MeetingsCard from "@/components/meetings/MeetingsCard.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { errorText, sanitizeRichText } from "@/utils";
import { Dialog, createResource, dayjs, toast } from "frappe-ui";
import { computed, ref, watch, type Ref } from "vue";
import { useRouter } from "vue-router";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCheckCheck from "~icons/lucide/check-check";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideFlag from "~icons/lucide/flag";
import LucideFolderInput from "~icons/lucide/folder-input";
import LucideLock from "~icons/lucide/lock";
import LucidePause from "~icons/lucide/pause";
import LucidePencil from "~icons/lucide/pencil";
import LucidePlay from "~icons/lucide/play";
import LucideRepeat from "~icons/lucide/repeat";
import LucideUndo2 from "~icons/lucide/undo-2";
import LucideUserPlus from "~icons/lucide/user-plus";
import type { TaskPullRequest } from "../pullRequestMeta";
import {
  assignedByName,
  holdByLabel,
  holdDays,
  holdDurationLabel,
  isClosed,
  isOnHold,
  isPendingReview,
  priorityIcon,
  taskStatusMeta,
  waitingOnLabel,
} from "../taskMeta";
import { useApproveTask } from "../useApproveTask";
import AiDraftedChip from "./AiDraftedChip.vue";
import CompleteTaskDialog from "./CompleteTaskDialog.vue";
import EditTaskDialog from "./EditTaskDialog.vue";
import HandOverTaskDialog from "./HandOverTaskDialog.vue";
import HoldTaskDialog from "./HoldTaskDialog.vue";
import MoveTaskDialog from "./MoveTaskDialog.vue";
import RecurringTaskDialog from "./RecurringTaskDialog.vue";
import RequestHelpDialog from "./RequestHelpDialog.vue";
import ResumeTaskDialog from "./ResumeTaskDialog.vue";
import SendBackTaskDialog from "./SendBackTaskDialog.vue";
import SlipBadge from "./SlipBadge.vue";
import TaskActivity from "./TaskActivity.vue";
import TaskPlanDialog from "./TaskPlanDialog.vue";
import TaskPullRequests from "./TaskPullRequests.vue";

/** What the opener knows about the task; the dialog loads the rest. */
export interface TaskRef {
  name: string;
  subject?: string;
  project?: string | null;
  project_name?: string | null;
}

/** A step the opener asks for straight away, skipping the details. */
export type TaskAction = "plan" | "resume" | "complete" | "hold";

interface TaskDetail {
  name: string;
  subject: string;
  status: string;
  phase?: string;
  priority?: string;
  project?: string;
  due_date?: string;
  estimated_hours?: number;
  description?: string;
  ai_description?: boolean;
  hold_reason?: string | null;
  hold_note?: string | null;
  hold_since?: string | null;
  hold_by_name?: string | null;
  is_key?: boolean;
  is_milestone?: boolean;
  slip_count?: number;
  depends_on_task?: string | null;
  depends_on_subject?: string | null;
  blocked?: boolean;
  pull_requests?: TaskPullRequest[];
  custom_timer_start?: string | null;
  custom_timer_elapsed?: number;
  assigned_to?: string | null;
  assigned_to_name?: string | null;
  assignees?: string[];
  assigned_by?: string | null;
  assigned_by_name?: string | null;
  can_move?: boolean;
  custom_recurring_task?: string | null;
  content_post?: string | null;
}

const props = withDefaults(
  defineProps<{
    /** The task to show; the dialog is open while this is set. */
    task: TaskRef | null;
    /** Opens that step's dialog once the task has loaded, instead of the details. */
    action?: TaskAction | null;
    /**
     * The viewer is the task's assignee. When they look at someone else's
     * work, only the steps a lead or manager may take are offered.
     */
    mine?: boolean;
  }>(),
  { action: null, mine: true }
);

const emit = defineEmits<{
  "update:task": [value: null];
  /** The task changed: reload whatever lists it. */
  changed: [];
}>();

const router = useRouter();

const taskDetail = createResource({
  url: "helpdesk.tasky.api.get_task_detail",
  // shown in the dialog, or as a toast when a step was asked for directly
  onError(e: unknown) {
    if (props.action) {
      toast.error(errorText(e, __("Couldn't load this task.")));
      close();
    }
  },
  onSuccess(d: TaskDetail) {
    if (!props.action || d.name !== props.task?.name) return;
    const target = {
      plan: planningTask,
      resume: resumingTask,
      complete: completingTask,
      hold: holdingTask,
    }[props.action];
    close();
    target.value = d;
  },
});
const detail = computed<TaskDetail | null>(() =>
  taskDetail.data?.name === props.task?.name ? taskDetail.data : null
);

// plan and review actions are for whoever runs the project's tasks; schedules for its managers
const projectAccess = createResource({
  url: "helpdesk.tasky.api.get_project_detail",
  onError() {},
});
const project = computed(
  () => props.task?.project || detail.value?.project || ""
);
const projectLoaded = computed(
  () =>
    !!project.value &&
    !projectAccess.loading &&
    projectAccess.params?.project === project.value
);
const canManage = computed(
  () => projectLoaded.value && !!projectAccess.data?.can_manage
);
// runs the project's tasks: managers, the lead and coordinators
const canCoordinate = computed(
  () => projectLoaded.value && !!projectAccess.data?.can_coordinate
);

watch(
  () => props.task?.name,
  (name) => {
    if (!name) return;
    taskDetail.submit({ task: name });
    const p = props.task?.project;
    if (p && projectAccess.params?.project !== p)
      projectAccess.submit({ project: p });
  },
  { immediate: true }
);

// the details stay closed while a step asked for straight away loads
const dialogOpen = computed({
  get: () => !!props.task && !props.action,
  set: (open: boolean) => {
    if (!open) close();
  },
});

function close() {
  emit("update:task", null);
}

function statusMeta(status: string) {
  const meta = taskStatusMeta(status);
  return { label: __(meta.label), icon: meta.icon };
}

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
      value: props.task?.project_name || d.project || "—",
    },
    { label: __("Phase"), value: d.phase || "—" },
    {
      label: __("Assigned to"),
      value: d.assigned_to_name || d.assigned_to || __("Unassigned"),
    },
    { label: __("Assigned by"), value: assignedByName(d) || "—" },
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

const holdingTask = ref<TaskDetail | null>(null);
const resumingTask = ref<TaskDetail | null>(null);
const planningTask = ref<TaskDetail | null>(null);
const editingTask = ref<TaskDetail | null>(null);
const sendingBackTask = ref<TaskDetail | null>(null);
const completingTask = ref<TaskDetail | null>(null);
const helpingTask = ref<TaskDetail | null>(null);
const handingOverTask = ref<TaskDetail | null>(null);
const movingTask = ref<TaskDetail | null>(null);
const recurringFrom = ref<TaskDetail | null>(null);

const { approve } = useApproveTask(() => {
  close();
  changed();
});

const dialogActions = computed(() => {
  const d = detail.value;
  const actions: Record<string, any>[] = [];
  if (!d || taskDetail.loading) return actions;
  const open = !isClosed(d);
  // the assignee can at least edit the description; others need to run the project's tasks
  if (props.mine || canCoordinate.value) {
    actions.push({
      label: __("Edit"),
      iconLeft: LucidePencil,
      onClick: () => handOff(editingTask),
    });
  }
  if (canCoordinate.value) {
    if (isPendingReview(d)) {
      actions.push(
        {
          label: __("Send back"),
          iconLeft: LucideUndo2,
          onClick: () => handOff(sendingBackTask),
        },
        {
          label: __("Approve"),
          iconLeft: LucideCheckCheck,
          variant: "subtle",
          onClick: () => approve(d),
        }
      );
    }
    // a task a schedule created already repeats; schedules are the managers' and lead's
    if (canManage.value && !d.custom_recurring_task) {
      actions.push({
        label: __("Make recurring…"),
        icon: LucideRepeat,
        tooltip: __("Make recurring"),
        onClick: () => handOff(recurringFrom),
      });
    }
    if (open) {
      actions.push({
        label: __("Plan"),
        icon: LucideCalendarClock,
        tooltip: __("Plan"),
        onClick: () => handOff(planningTask),
      });
    }
  }
  if (props.mine && open) {
    // done work goes through the Complete dialog, which logs the hours to a timesheet
    if (!isPendingReview(d) && !d.blocked) {
      actions.push({
        label: __("Complete"),
        iconLeft: LucideCircleCheck,
        variant: "subtle",
        onClick: () => handOff(completingTask),
      });
    }
  }
  // the assignee, or whoever runs the project's tasks, holds, resumes and hands it over
  if ((props.mine || canCoordinate.value) && open) {
    if (isOnHold(d)) {
      actions.push({
        label: __("Resume"),
        icon: LucidePlay,
        onClick: () => handOff(resumingTask),
      });
    } else {
      actions.push({
        label: __("Put on hold"),
        icon: LucidePause,
        onClick: () => handOff(holdingTask),
      });
    }
    // a task waits on one other task, so asking for help needs it free
    if (props.mine && !d.blocked)
      actions.push({
        label: __("Ask a teammate for help"),
        icon: LucideUserPlus,
        tooltip: __("Ask a teammate for help"),
        onClick: () => handOff(helpingTask),
      });
    actions.push({
      label: __("Hand over"),
      icon: LucideArrowRight,
      tooltip: __("Hand over to a teammate"),
      onClick: () => handOff(handingOverTask),
    });
  }
  // the assigner and the project's manager or lead; never the assignee alone
  if (d.can_move) {
    actions.push({
      label: __("Move to project…"),
      icon: LucideFolderInput,
      tooltip: __("Move to another project"),
      onClick: () => handOff(movingTask),
    });
  }
  if (project.value) {
    actions.push({
      label: __("Open project board"),
      variant: "solid",
      onClick: openBoard,
    });
  }
  return actions;
});

// close the detail first so only one modal holds focus
function handOff(target: Ref<TaskDetail | null>) {
  const d = detail.value;
  if (!d) return;
  close();
  target.value = d;
}

function changed() {
  emit("changed");
}

function openBoard() {
  const p = project.value;
  close();
  router.push({ name: "TaskyKanban", params: { projectId: p } });
}
</script>
