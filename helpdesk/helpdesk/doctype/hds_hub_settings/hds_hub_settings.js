// Copyright (c) 2026, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("HDS Hub Settings", {
  refresh(frm) {
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
