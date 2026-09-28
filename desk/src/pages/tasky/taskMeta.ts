import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import type { Component } from "vue";
import LucideCircle from "~icons/lucide/circle";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideEye from "~icons/lucide/eye";
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
export const CATEGORIES = ["Functional", "Development", "Support", "Common"];
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

// Due dates are date-only, so a task is overdue from the day after it's due.
export function isOverdue(task: { status?: string; due_date?: string | null }) {
  return (
    !!task.due_date &&
    !isClosed(task) &&
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
