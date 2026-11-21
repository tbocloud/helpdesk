// "Open in TBO Copilot" wherever a task opens (Phase 22; testing fixes 7): the task in the desktop
// app, in its project's folders. Shown to people who may use the desktop app, on any open task.
import { __ } from "@/translation";
import { createResource, toast } from "frappe-ui";
import { computed } from "vue";

// asked once per page: the desktop sign-in's own rule (helpdesk.api.copilot_desktop)
const desktop = createResource({
  url: "helpdesk.api.copilot_desktop.desktop",
  cache: "helpdesk:copilot-desktop",
  auto: true,
});

export const mayOpenInCopilot = computed(() =>
  Boolean((desktop.data as { may_use?: boolean } | undefined)?.may_use)
);

// the desktop app takes tbo-copilot:// links; it asks before it does anything with one. The
// link goes through a hidden frame, so a browser without the app installed stays on this page
// (Phase 23, A25), and the notice offers the install page
export function openInCopilot(task: string) {
  const site = encodeURIComponent(window.location.origin);
  const frame = document.createElement("iframe");
  frame.style.display = "none";
  frame.src = `tbo-copilot://task/${encodeURIComponent(task)}?site=${site}`;
  document.body.appendChild(frame);
  window.setTimeout(() => frame.remove(), 3000);
  toast.info(__("Opening TBO Copilot. Nothing opened? Install the app."), {
    action: {
      label: __("Install"),
      onClick: () =>
        window.open(`${window.location.origin}/copilot-desktop`, "_blank"),
    },
  });
}
