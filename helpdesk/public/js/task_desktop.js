// The Frappe task form (testing fixes 7): "Open in TBO Copilot" for people who may use the desktop
// app, on an open task, as on TBO Support's own task dialogs (desk/src/pages/tasky/openInCopilot.ts).
frappe.ui.form.on("Task", {
  refresh(frm) {
    if (frm.is_new() || ["Completed", "Cancelled"].includes(frm.doc.status))
      return;
    tbo_may_use_desktop().then((ok) => {
      if (ok) {
        frm.add_custom_button(__("Open in TBO Copilot"), () =>
          tbo_open_in_copilot(frm.doc.name)
        );
      }
    });
  },
});

let tbo_desktop_asked = null;

// asked once per page; a person who is not an agent, or an older hub, simply gets no button
function tbo_may_use_desktop() {
  tbo_desktop_asked =
    tbo_desktop_asked ||
    frappe
      .xcall("helpdesk.api.copilot_desktop.desktop")
      .then((r) => Boolean(r && r.may_use))
      .catch(() => false);
  return tbo_desktop_asked;
}

// the desktop app takes tbo-copilot:// links and asks before it does anything with one; a browser
// without the app stays on the page, and the notice points to the install page
function tbo_open_in_copilot(task) {
  const site = encodeURIComponent(window.location.origin);
  const frame = document.createElement("iframe");
  frame.style.display = "none";
  frame.src = `tbo-copilot://task/${encodeURIComponent(task)}?site=${site}`;
  document.body.appendChild(frame);
  window.setTimeout(() => frame.remove(), 3000);
  frappe.show_alert(
    {
      message: __("Opening TBO Copilot. Nothing opened? {0}", [
        `<a href="/copilot-desktop" target="_blank" rel="noopener">${__(
          "Install the app"
        )}</a>`,
      ]),
      indicator: "blue",
    },
    8
  );
}
