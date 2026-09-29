import { __ } from "@/translation";
import { dayjs } from "frappe-ui";

export interface WorkItem {
  kind: "task" | "ticket";
  name: string;
  title: string;
  status: string;
  priority?: string;
  /** "YYYY-MM-DD" for tasks, a datetime string (SLA resolution) for tickets. */
  deadline: string | null;
  is_key: boolean;
  is_overdue: boolean;
  assignees: string[];
  project?: string | null;
  project_name?: string | null;
  hd_ticket?: string | null;
  customer?: string | null;
}

export interface DeadlineInfo {
  label: string;
  overdue: boolean;
}

function taskDeadline(item: WorkItem): DeadlineInfo {
  const days = dayjs(item.deadline)
    .startOf("day")
    .diff(dayjs().startOf("day"), "day");
  if (item.is_overdue || days < 0) {
    const late = Math.max(-days, 1);
    return {
      label:
        late === 1 ? __("1 day overdue") : __("{0} days overdue", String(late)),
      overdue: true,
    };
  }
  if (days === 0) return { label: __("Due today"), overdue: false };
  if (days === 1) return { label: __("Due tomorrow"), overdue: false };
  if (days < 14)
    return { label: __("Due in {0} days", String(days)), overdue: false };
  return {
    label: __("Due {0}", dayjs(item.deadline).format("D MMM")),
    overdue: false,
  };
}

function ticketDeadline(item: WorkItem): DeadlineInfo {
  if (item.is_overdue) return { label: __("SLA breached"), overdue: true };
  const minutes = dayjs(item.deadline).diff(dayjs(), "minute");
  // the SLA clock stops while a ticket is paused, so a past deadline isn't a breach
  if (minutes < 0) return { label: __("SLA paused"), overdue: false };
  if (minutes < 60)
    return {
      label: __("SLA in {0}m", String(Math.max(minutes, 1))),
      overdue: false,
    };
  const hours = Math.floor(minutes / 60);
  if (hours < 48)
    return { label: __("SLA in {0}h", String(hours)), overdue: false };
  return {
    label: __("SLA in {0}d", String(Math.floor(hours / 24))),
    overdue: false,
  };
}

/** Deadline in plain language: "Due tomorrow", "3 days overdue", "SLA in 4h". */
export function deadlineInfo(item: WorkItem): DeadlineInfo {
  if (!item.deadline) return { label: __("No deadline"), overdue: false };
  return item.kind === "ticket" ? ticketDeadline(item) : taskDeadline(item);
}

export function itemRoute(item: WorkItem) {
  if (item.kind === "ticket")
    return { name: "TicketAgent", params: { ticketId: item.name } };
  if (item.project)
    return { name: "TaskyProject", params: { projectId: item.project } };
  return null;
}

export function itemKey(item: WorkItem) {
  return `${item.kind}:${item.name}`;
}
