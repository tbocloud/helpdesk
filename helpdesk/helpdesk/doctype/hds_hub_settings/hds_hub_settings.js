// Copyright (c) 2026, Frappe Technologies and contributors
// For license information, please see license.txt

// Monitoring: when the watcher was last heard from (its heartbeat is kept in the cache, not a field)
function show_watcher_status(frm) {
  const field = frm.get_field("watcher_status");
  if (!field) return;
  const s = (frm.doc.__onload || {}).watcher_status;
  let html;
  if (!s || !s.last_seen) {
    html = `<span class="indicator-pill gray">${__("Never heard from")}</span>`;
  } else {
    const ago =
      s.seconds_ago < 120
        ? __("{0} seconds ago", [s.seconds_ago])
        : __("{0} minutes ago", [Math.round(s.seconds_ago / 60)]);
    const pill = s.quiet
      ? `<span class="indicator-pill red">${__("Quiet")}</span>`
      : `<span class="indicator-pill green">${__("Heard from")}</span>`;
    html = `${pill} ${frappe.datetime.str_to_user(s.last_seen)} (${ago})`;
  }
  field.$wrapper.html(
    `<div class="form-group"><div class="clearfix"><label class="control-label">${__(
      "Watcher last seen"
    )}</label></div><div class="control-value like-disabled-input">${html}</div></div>`
  );
}

frappe.ui.form.on("HDS Hub Settings", {
  refresh(frm) {
    show_watcher_status(frm);
    frm.add_custom_button(__("Create TBO AI user"), () => {
      frappe.prompt(
        [
          {
            fieldname: "email",
            fieldtype: "Data",
            options: "Email",
            label: __("Email"),
            reqd: 1,
            description: __("e.g. ai@teambackoffice.com"),
          },
          {
            fieldname: "full_name",
            fieldtype: "Data",
            label: __("Name"),
            default: "TBO AI",
            reqd: 1,
          },
        ],
        (values) =>
          frappe.call({
            method: "helpdesk.automation.create_automation_user",
            args: values,
            freeze: true,
            callback(r) {
              if (!r.message) return;
              frm.reload_doc();
              frappe.show_alert({
                message: __("The hub's own work is now shown as {0}.", [
                  r.message,
                ]),
                indicator: "green",
              });
            },
          }),
        __("Create TBO AI user"),
        __("Create")
      );
    });
  },
});
