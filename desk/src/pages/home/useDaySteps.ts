import type {
  TaskAction,
  TaskRef,
} from "@/pages/tasky/components/TaskDetailDialog.vue";
import { useApproveTask } from "@/pages/tasky/useApproveTask";
import type { WorkItem } from "@/pages/work/workMeta";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { createResource, toast } from "frappe-ui";
import { ref, watch, type Component } from "vue";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCheck from "~icons/lucide/check";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucidePlay from "~icons/lucide/play";
import type { DayTask } from "./homeMeta";

export interface DayStep {
  label: string;
  icon: Component;
  run: (item: DayTask) => void;
}

/**
 * The one next step on a task of the user's day (sign it off, date it, pick it
 * back up, start or finish it), shared by "Do next" and "Your day" so both offer
 * the same buttons. The caller renders a TaskDetailDialog bound to
 * `detailTask` / `detailAction`.
 */
export function useDaySteps(onChanged: () => void) {
  // the task whose button shows a spinner while its step loads
  const busy = ref<string | null>(null);
  const detailTask = ref<TaskRef | null>(null);
  const detailAction = ref<TaskAction | null>(null);

  // the dialog closes itself once its step is done, so the spinner can stop
  watch(detailTask, (task) => {
    if (task) return;
    detailAction.value = null;
    busy.value = null;
  });

  function openStep(item: WorkItem, action: TaskAction) {
    busy.value = item.name;
    detailAction.value = action;
    detailTask.value = {
      name: item.name,
      subject: item.title,
      project: item.project,
      project_name: item.project_name,
    };
  }

  function done(message: string) {
    toast.success(message);
    busy.value = null;
    onChanged();
  }

  function failed(e: unknown, fallback: string) {
    toast.error(errorText(e, fallback));
    busy.value = null;
  }

  const start = createResource({
    url: "helpdesk.tasky.api.update_task_status",
    onSuccess: () => done(__("Started")),
    onError: (e: unknown) => failed(e, __("Couldn't start the task.")),
  });

  const resumeTimer = createResource({
    url: "helpdesk.tasky.api.start_timer",
    onSuccess: () => done(__("Timer resumed")),
    onError: (e: unknown) => failed(e, __("Couldn't resume the timer.")),
  });

  const { approve } = useApproveTask(() => {
    busy.value = null;
    onChanged();
  });

  /** `planSection` is true in the list of tasks without a date, where Set date comes first. */
  function stepFor(item: DayTask, planSection = false): DayStep | null {
    if (item.kind !== "task") return null;
    if (item.status === "Pending Review") {
      return item.can_approve
        ? {
            label: __("Approve"),
            icon: LucideCheck,
            run: (task) => {
              busy.value = task.name;
              if (!approve({ name: task.name })) busy.value = null;
            },
          }
        : null;
    }
    if (item.status === "On Hold") {
      return {
        label: __("Resume"),
        icon: LucidePlay,
        run: (task) => openStep(task, "resume"),
      };
    }
    if (planSection && item.can_plan) {
      return {
        label: __("Set date"),
        icon: LucideCalendarClock,
        run: (task) => openStep(task, "plan"),
      };
    }
    if (item.timer === "paused") {
      return {
        label: __("Resume timer"),
        icon: LucidePlay,
        run: (task) => {
          busy.value = task.name;
          resumeTimer.submit({ task: task.name });
        },
      };
    }
    // the server refuses to start or finish a task while its dependency is open
    if (item.waiting_on) return null;
    if (item.status === "Open") {
      return {
        label: __("Start"),
        icon: LucidePlay,
        run: (task) => {
          busy.value = task.name;
          start.submit({ task: task.name, status: "Working" });
        },
      };
    }
    if (item.status === "Working" || item.status === "Overdue") {
      return {
        label: __("Complete"),
        icon: LucideCircleCheck,
        run: (task) => openStep(task, "complete"),
      };
    }
    return null;
  }

  return { busy, detailTask, detailAction, stepFor };
}
