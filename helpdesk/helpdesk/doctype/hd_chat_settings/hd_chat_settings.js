// Copyright (c) 2026, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("HD Chat Settings", {
  refresh(frm) {
    frm.add_custom_button(__("Send test message"), () => {
      if (frm.is_dirty()) {
        frappe.msgprint(__("Save the settings first."));
        return;
      }
      frappe.call({
        method: "helpdesk.chat_notifications.send_test_message",
        freeze: true,
        callback: () =>
          frappe.show_alert({ message: __("Test sent"), indicator: "green" }),
      });
    });
  },
});
