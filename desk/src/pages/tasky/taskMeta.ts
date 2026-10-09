import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { dayjs, dayjsLocal } from "frappe-ui";
import type { Component } from "vue";
import LucideCircle from "~icons/lucide/circle";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideEye from "~icons/lucide/eye";
import LucidePause from "~icons/lucide/pause";
import LucideSignal from "~icons/lucide/signal";
import LucideSignalHigh from "~icons/lucide/signal-high";
import LucideSignalLow from "~icons/lucide/signal-low";
import LucideSignalMedium from "~icons/lucide/signal-medium";

export interface StatusMeta {
  label: string;
  icon: Component;
  tone: Tone;
}

// Labels are untranslated keys; callers pass them through __() at render time
// so translations loaded after module evaluation still apply.
const TASK_STATUS: Record<string, StatusMeta> = {
  Open: { label: "Open", icon: LucideCircle, tone: "neutral" },
  Working: { label: "In progress", icon: LucideCircleDot, tone: "info" },
  "Pending Review": { label: "In review", icon: LucideEye, tone: "warning" },
  "On Hold": { label: "On hold", icon: LucidePause, tone: "warning" },
  Completed: { label: "Completed", icon: LucideCircleCheck, tone: "success" },
  Cancelled: { label: "Cancelled", icon: LucideCircleX, tone: "neutral" },
};

const PROJECT_STATUS: Record<string, StatusMeta> = {
  Open: { label: "Open", icon: LucideCircleDot, tone: "info" },
  Completed: { label: "Completed", icon: LucideCircleCheck, tone: "success" },
  Cancelled: { label: "Cancelled", icon: LucideCircleX, tone: "neutral" },
};

const PRIORITY_ICONS: Record<string, Component> = {
  Urgent: LucideSignal,
  High: LucideSignalHigh,
  Medium: LucideSignalMedium,
  Low: LucideSignalLow,
};

export const TASK_STATUSES = Object.keys(TASK_STATUS);
// keep in step with Task.custom_category in helpdesk/setup/install.py
export const CATEGORIES = [
  "Functional",
  "Development",
  "DevOps",
  "Support",
  "Digital Marketing",
  "Social Media",
  "Content Writing",
  "Graphic Design",
  "Video",
  "Motion Graphics",
  "Coordination",
  "Common",
];
// Project User roles; template tasks of a category go to members with the matching role
export const PROJECT_ROLES = [
  "Project Manager",
  "Project Coordinator",
  "Developer",
  "Functional Consultant",
  "DevOps Engineer",
  "Support Engineer",
  "Digital Marketing Specialist",
  "Social Media Executive",
  "Content Writer / Copywriter",
  "Graphic Designer",
  "Videographer cum Editor",
  "Motion Graphics Artist / Animator",
];
export const PRIORITIES = ["Low", "Medium", "High", "Urgent"];

export function categoryOptions() {
  return CATEGORIES.map((c) => ({ label: __(c), value: c }));
}

export function priorityOptions() {
  return PRIORITIES.map((p) => ({ label: __(p), value: p }));
}

export function taskStatusMeta(status?: string): StatusMeta {
  return TASK_STATUS[status ?? "Open"] ?? TASK_STATUS.Open;
}

export function projectStatusMeta(status?: string): StatusMeta {
  return (
    PROJECT_STATUS[status ?? "Open"] ?? {
      label: status || "Open",
      icon: LucideCircle,
      tone: "neutral",
    }
  );
}

export function priorityIcon(priority?: string): Component {
  return PRIORITY_ICONS[priority ?? "Low"] ?? LucideSignalLow;
}

export function isClosed(task: { status?: string }) {
  return task.status === "Completed" || task.status === "Cancelled";
}

export const ON_HOLD = "On Hold";

// Exact values of Task.hold_reason; translated at render time.
export const HOLD_REASONS = [
  "Laptop / system issue",
  "Leave",
  "Waiting on customer",
  "Waiting on another task",
  "Other",
];

export function isOnHold(task: { status?: string }) {
  return task.status === ON_HOLD;
}

/** Whole days since the hold began (0 on the first day). */
export function holdDays(task: { hold_since?: string | null }) {
  if (!task.hold_since) return 0;
  return Math.max(
    dayjs().startOf("day").diff(dayjs(task.hold_since).startOf("day"), "day"),
    0
  );
}

export function holdDurationLabel(days: number) {
  if (days <= 0) return __("On hold since today");
  if (days === 1) return __("On hold 1 day");
  return __("On hold {0} days", String(days));
}

// Due dates are date-only, so a task is overdue from the day after it's due, or on
// its due day once it has been worked longer than its estimate (server: is_task_overdue).
// A task on hold is never overdue: its due date moves out when it resumes.
export function isOverdue(
  task: {
    status?: string;
    due_date?: string | null;
    estimated_hours?: number | null;
    custom_timer_start?: string | null;
    custom_timer_elapsed?: number | null;
  },
  now = dayjs()
) {
  if (!task.due_date || isClosed(task) || isOnHold(task)) return false;
  const due = dayjs(task.due_date);
  if (due.isBefore(now, "day")) return true;
  return due.isSame(now, "day") && isOverEstimate(task, now);
}

/**
 * The task's timer has passed its estimated hours. The timer starts when the task
 * moves to Working and stops while paused, so the clock runs from when work began.
 */
export function isOverEstimate(
  task: Parameters<typeof taskTimer>[0] & { estimated_hours?: number | null },
  now = dayjs()
) {
  const estimate = Number(task.estimated_hours) || 0;
  if (!estimate) return false;
  const timer = taskTimer(task, now);
  return !!timer && timer.elapsed > estimate * 3600;
}

export function daysUntil(date: string) {
  return dayjs(date).startOf("day").diff(dayjs().startOf("day"), "day");
}

// an end date further out than this says nothing urgent
const PROJECT_ENDING_DAYS = 14;

/**
 * What an open project's end date says about what's left: "3 days past end"
 * (late) or "Ends in 5 days"; null when it's far off, missing or not open.
 */
export function projectEndNote(project: {
  status?: string | null;
  expected_end_date?: string | null;
}): { late: boolean; text: string } | null {
  const end = project.expected_end_date;
  if (!end || (project.status || "Open") !== "Open") return null;
  const days = daysUntil(end);
  if (days < 0)
    return {
      late: true,
      text:
        days === -1
          ? __("1 day past end")
          : __("{0} days past end", String(-days)),
    };
  if (days === 0) return { late: false, text: __("Ends today") };
  if (days <= PROJECT_ENDING_DAYS)
    return {
      late: false,
      text:
        days === 1 ? __("Ends tomorrow") : __("Ends in {0} days", String(days)),
    };
  return null;
}

export function shortDate(date?: string | null) {
  return date ? dayjs(date).format("D MMM") : "—";
}

export function initials(name?: string | null) {
  if (!name) return "";
  return name
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export const PENDING_REVIEW = "Pending Review";

export function isPendingReview(task: { status?: string }) {
  return task.status === PENDING_REVIEW;
}

/** Short chip text for a task whose due date was pushed later. */
export function slipLabel(count: number) {
  return __("Moved {0}×", String(count));
}

export function slipTitle(count: number) {
  return count === 1
    ? __("Due date moved later 1 time")
    : __("Due date moved later {0} times", String(count));
}

export function waitingOnLabel(subject?: string | null) {
  return subject
    ? __("Waiting on {0}", subject)
    : __("Waiting on another task");
}

// Statuses the server refuses while the task's dependency is still open.
const BLOCKED_STATUSES = ["Working", PENDING_REVIEW, "Completed"];

export function blocksMove(
  task: { blocked?: boolean; depends_on_subject?: string | null },
  newStatus: string
) {
  return !!task.blocked && BLOCKED_STATUSES.includes(newStatus);
}

export function blockedMessage(task: { depends_on_subject?: string | null }) {
  return task.depends_on_subject
    ? __("Finish {0} first: this task depends on it.", task.depends_on_subject)
    : __("Finish the task this one depends on first.");
}

/** The description is still the AI's text, unedited (`aiText` is what the AI wrote). */
export function isAiDrafted(description: string, aiText: string | null) {
  return (
    aiText !== null && !!aiText.trim() && description.trim() === aiText.trim()
  );
}

// A refused project reads like an outage otherwise, so say who can open it
export function loadErrorMessage(...errors: unknown[]) {
  const denied = errors.some(
    (e) => (e as { exc_type?: string } | null)?.exc_type === "PermissionError"
  );
  return denied
    ? __(
        "You're not on this project. Ask its project manager to add you as a member."
      )
    : __("Check your connection and try again.");
}

/** Who gave the task out, or "" when nobody did or the assignee took it themselves. */
export function assignedByName(task: {
  assigned_by?: string | null;
  assigned_by_name?: string | null;
  assignees?: string[];
}) {
  const by = task.assigned_by;
  if (!by || task.assignees?.includes(by)) return "";
  return task.assigned_by_name || by;
}

export interface TaskTimer {
  running: boolean;
  paused: boolean;
  /** Seconds tracked: the banked time plus the running stretch. */
  elapsed: number;
}

/**
 * A task's timer, from the server's fields alone. It runs only while the task is
 * in progress with a start time; otherwise banked time shows as paused. Pausing
 * and resuming go through the server, so reloading the board (after working on
 * another task, or coming back to it) never restarts a paused timer.
 */
export function taskTimer(
  task: {
    status?: string;
    custom_timer_start?: string | null;
    custom_timer_elapsed?: number | null;
  },
  now = dayjs()
): TaskTimer | null {
  const banked = Math.round((Number(task.custom_timer_elapsed) || 0) * 3600);
  if (task.status === "Working" && task.custom_timer_start) {
    // the start is stored in the server's time zone
    const since = now.diff(dayjsLocal(task.custom_timer_start), "second");
    return {
      running: true,
      paused: false,
      elapsed: banked + Math.max(since, 0),
    };
  }
  return banked > 0 ? { running: false, paused: true, elapsed: banked } : null;
}
