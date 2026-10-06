import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
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

export type Tone = "neutral" | "info" | "warning" | "success" | "danger";

// Full class strings (not interpolated) so Tailwind's scanner picks them up.
export const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-surface-gray-2 text-ink-gray-7",
  info: "bg-info-soft text-info",
  warning: "bg-warning-soft text-warning",
  success: "bg-success-soft text-success",
  danger: "bg-danger-soft text-danger",
};

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

// Due dates are date-only, so a task is overdue from the day after it's due.
// A task on hold is never overdue: its due date moves out when it resumes.
export function isOverdue(task: { status?: string; due_date?: string | null }) {
  return (
    !!task.due_date &&
    !isClosed(task) &&
    !isOnHold(task) &&
    dayjs(task.due_date).isBefore(dayjs(), "day")
  );
}

export function daysUntil(date: string) {
  return dayjs(date).startOf("day").diff(dayjs().startOf("day"), "day");
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

export function errorText(e: any, fallback: string) {
  return e?.messages?.length ? e.messages.join(" ") : e?.message || fallback;
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
