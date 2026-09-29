import { __ } from "@/translation";
import { createResource, toast } from "frappe-ui";
import { errorText } from "./taskMeta";

/** One-click sign-off for a task in Pending Review (project managers and leads). */
export function useApproveTask(onDone: (task?: Record<string, any>) => void) {
  const resource = createResource({
    url: "helpdesk.tasky.api.approve_task",
    onSuccess(data: Record<string, any>) {
      toast.success(__("Approved: {0}", data?.subject || data?.name || ""));
      onDone(data);
    },
    onError(e: any) {
      toast.error(errorText(e, __("Couldn't approve the task.")));
      onDone();
    },
  });

  function approve(task: { name: string }) {
    if (resource.loading) return;
    return resource.submit({ task: task.name });
  }

  return { approve, resource };
}
