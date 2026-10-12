import { errorText } from "@/utils";
import { __ } from "@/translation";
import { createResource, toast } from "frappe-ui";
import { h } from "vue";
import TaskQuality from "./components/TaskQuality.vue";

// long enough to pick a rating; hovering over the toast pauses it
const RATE_PROMPT_MS = 15_000;

/** One-click sign-off for a task in Pending Review (project managers and leads),
 * optionally with its quality rating (Needs rework, Good, Excellent).
 *
 * Approved without a rating, the approver is offered one in the success toast
 * (TaskQuality's compact chips with Skip) when they may rate the task: never
 * the people who did it. `offerRating: false` is for the task dialog, which
 * already shows the rating next to Approve. */
export function useApproveTask(
  onDone: (task?: Record<string, any>) => void,
  { offerRating = true }: { offerRating?: boolean } = {}
) {
  const resource = createResource({
    url: "helpdesk.tasky.api.approve_task",
    onSuccess(data: Record<string, any>) {
      const message = __("Approved: {0}", data?.subject || data?.name || "");
      const quality = data?.quality;
      if (offerRating && quality?.can_rate && !quality.rating) {
        const id = `rate-${data.name}`;
        toast.success(message, {
          id,
          duration: RATE_PROMPT_MS,
          // a render function, not componentProps: Sonner would pass those to
          // the title too
          description: () =>
            h(TaskQuality, {
              task: data.name,
              quality,
              compact: true,
              onRated: () => toast.dismiss(id),
              onSkip: () => toast.dismiss(id),
            }),
        });
      } else {
        toast.success(message);
      }
      onDone(data);
    },
    onError(e: any) {
      toast.error(errorText(e, __("Couldn't approve the task.")));
      onDone();
    },
  });

  function approve(task: { name: string }, rating?: string) {
    if (resource.loading) return;
    return resource.submit({ task: task.name, rating: rating || null });
  }

  return { approve, resource };
}
