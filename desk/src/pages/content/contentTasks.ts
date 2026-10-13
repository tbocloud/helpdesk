// The content calendar's role tasks (helpdesk.api.content_tasks.get_content_tasks):
// the Tasks view, the "Your tasks" strip, the role boxes' one step and each board
// card's "parts done · waiting on" line. See docs/content-calendar.md "Tasks view".
import type { TaskAction, TaskRef } from "@/pages/tasky/components/TaskDetailDialog.vue";
import { daysUntil } from "@/pages/tasky/taskMeta";
import { useApproveTask } from "@/pages/tasky/useApproveTask";
import type { PendingPart } from "@/pages/work/inProgressMeta";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { call, dayjs, toast } from "frappe-ui";
import { type Component, ref, watch } from "vue";
import LucideCheck from "~icons/lucide/check";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucidePause from "~icons/lucide/pause";
import LucidePlay from "~icons/lucide/play";
import LucideUserPen from "~icons/lucide/user-pen";
import type { ContentPost, TeamRole } from "./constants";

/** The queue's columns, in order (the server's `stage`). */
export type TaskStage = "todo" | "in_progress" | "review" | "on_hold" | "done";

/** A step the server says the viewer may take (`actions`). */
export type TaskStep =
  | "start"
  | "pause"
  | "resume_timer"
  | "complete"
  | "hold"
  | "resume"
  | "approve"
  | "reassign";

export interface ContentTask {
  name: string;
  subject: string;
  status: string;
  stage: TaskStage;
  /** In review: "Lead's review", or the post's stage ("Client approval"). */
  review_label: string | null;
  /** The post's part; null for the one task shared by the whole post. */
  role: TeamRole | null;
  role_label: string;
  post: string;
  publish_on: string | null;
  project: string | null;
  project_name: string | null;
  assignees: string[];
  assignee_names: Record<string, string>;
  mine: boolean;
  due: string | null;
  is_overdue: boolean;
  hold_reason: string | null;
  hold_note: string | null;
  hold_by_name: string | null;
  hold_days: number | null;
  custom_timer_start: string | null;
  custom_timer_elapsed: number;
  estimated_hours: number;
  escalation_level: number;
  /** The open task this one depends on; it can't start or finish before that. */
  waiting_on: string | null;
  actions: TaskStep[];
}

export type WaitingOn =
  | { kind: "review"; label: string }
  | ({ kind: "part" } & PendingPart);

export interface PostProgress {
  /** Roles with someone on them. */
  parts: number;
  /** Of those, the ones whose task is completed. */
  done: number;
  waiting_on: WaitingOn | null;
}

export interface TaskPost extends ContentPost {
  is_missed: boolean;
  progress: PostProgress;
}

export interface ContentTasksData {
  /** A content lead: gets every content task, not only their own. */
  sees_all: boolean;
  can_edit: boolean;
  tasks: ContentTask[];
  counts: Record<TaskStage, number>;
  posts: Record<string, TaskPost>;
  truncated: boolean;
}

// labels are untranslated keys, passed through __() where shown
export const STEPS: Record<TaskStep, { label: string; icon: Component }> = {
  start: { label: "Start", icon: LucidePlay },
  pause: { label: "Pause", icon: LucidePause },
  resume_timer: { label: "Resume timer", icon: LucidePlay },
  complete: { label: "Complete", icon: LucideCircleCheck },
  hold: { label: "Put on hold", icon: LucidePause },
  resume: { label: "Resume", icon: LucidePlay },
  approve: { label: "Approve", icon: LucideCheck },
  reassign: { label: "Reassign", icon: LucideUserPen },
};

/**
 * A role box's one step for its assignee, by the task's state: Start an open task,
 * Pause a running timer, Complete one in progress with its timer paused. Resuming the
 * timer and holding are on the Tasks view's card and in the task dialog.
 */
export function boxStep(task?: ContentTask | null): TaskStep | null {
  if (!task?.mine) return null;
  return (
    (["start", "pause", "complete"] as const).find((s) =>
      task.actions.includes(s)
    ) ?? null
  );
}

/** "due today", "due tomorrow", "due Thu 15 Oct", "2 days late"; `late` once it has passed. */
export function dueText(due: string | null) {
  if (!due) return { text: "", late: false };
  const days = daysUntil(due);
  if (days < -1) return { text: __("{0} days late", String(-days)), late: true };
  if (days === -1) return { text: __("1 day late"), late: true };
  if (days === 0) return { text: __("due today"), late: false };
  if (days === 1) return { text: __("due tomorrow"), late: false };
  return { text: __("due {0}", dayjs(due).format("ddd D MMM")), late: false };
}

function firstName(name: string) {
  return (name || "").trim().split(/\s+/)[0] || name;
}

/** "waiting on Writer (Ajmal)" or "waiting on Client approval". */
export function waitingText(waiting: WaitingOn) {
  if (waiting.kind === "review") return __("waiting on {0}", waiting.label);
  const people = waiting.people.map((p) => firstName(p.full_name)).join(", ");
  return people
    ? __("waiting on {0} ({1})", waiting.label, people)
    : __("waiting on {0}", waiting.label);
}

/** "3 of 4 parts done" (or "All 4 parts done"). */
export function partsText(progress: PostProgress) {
  if (progress.parts && progress.done === progress.parts)
    return progress.parts === 1
      ? __("The one part is done")
      : __("All {0} parts done", String(progress.parts));
  return __(
    "{0} of {1} parts done",
    String(progress.done),
    String(progress.parts)
  );
}

/**
 * Runs a step on a content task through the existing task APIs: Start moves it to
 * In progress (`move_task`, which starts the timer), Pause and Resume timer bank and
 * restart the timer, Approve uses `useApproveTask` (with its rating offer); Complete,
 * Put on hold and Resume open the shared task dialog straight on that step. `onDone`
 * runs after every change, to reload what lists the task.
 */
export function useContentTaskSteps(onDone: () => void) {
  const busy = ref<string | null>(null);
  // the shared TaskDetailDialog: open while `dialogTask` is set
  const dialogTask = ref<TaskRef | null>(null);
  const dialogAction = ref<TaskAction | null>(null);
  const dialogMine = ref(false);

  // the dialog closes itself once a step has loaded, so the spinner can stop
  watch(dialogTask, (task) => {
    if (task) return;
    dialogAction.value = null;
    busy.value = null;
  });

  const { approve } = useApproveTask(() => {
    busy.value = null;
    onDone();
  });

  function open(task: TaskRef, mine: boolean, action: TaskAction | null = null) {
    dialogMine.value = mine;
    dialogAction.value = action;
    dialogTask.value = task;
  }

  const CALLS: Partial<
    Record<TaskStep, { url: string; args?: object; ok: string; fail: string }>
  > = {
    start: {
      url: "helpdesk.tasky.api.move_task",
      args: { new_status: "Working" },
      ok: __("Started"),
      fail: __("Couldn't start the task."),
    },
    pause: {
      url: "helpdesk.tasky.api.stop_timer",
      ok: __("Timer paused"),
      fail: __("Couldn't pause the timer."),
    },
    resume_timer: {
      url: "helpdesk.tasky.api.start_timer",
      ok: __("Timer running"),
      fail: __("Couldn't resume the timer."),
    },
  };

  async function run(step: TaskStep, task: ContentTask) {
    if (busy.value) return;
    const target = {
      name: task.name,
      subject: task.subject,
      project: task.project,
      project_name: task.project_name,
    };
    if (step === "complete" || step === "hold" || step === "resume") {
      busy.value = task.name;
      open(target, task.mine, step);
      return;
    }
    if (step === "approve") {
      busy.value = task.name;
      // another approval is already running; don't leave this one spinning
      if (!approve({ name: task.name })) busy.value = null;
      return;
    }
    const request = CALLS[step];
    if (!request) return;
    busy.value = task.name;
    try {
      await call(request.url, { task: task.name, ...request.args });
      toast.success(request.ok);
    } catch (e) {
      toast.error(errorText(e, request.fail));
    } finally {
      busy.value = null;
      onDone();
    }
  }

  return { busy, dialogTask, dialogAction, dialogMine, open, run };
}
