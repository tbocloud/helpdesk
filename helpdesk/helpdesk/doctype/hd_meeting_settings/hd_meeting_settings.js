// Copyright (c) 2026, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("HD Meeting Settings", {
  refresh(frm) {
    frm.add_custom_button(__("Test connection"), () => {
      frappe.call({
        method: "helpdesk.api.meetings.test_connection",
        freeze: true,
        callback(r) {
          if (r.message) {
            frappe.msgprint(
              __("Connected. Teams meetings will be created in {0}.", [
                r.message.mailbox,
              ])
            );
          }
        },
      });
    });
  },
});
