// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

frappe.ui.form.on("HDS Site Registry", {
  refresh(frm) {
    if (frm.is_new() || !frm.doc.connection) {
      return;
    }
    // every app, commit and branch the site runs, read through its connection
    frm.add_custom_button(__("Refresh from the site"), () =>
      frappe
        .call({
          method: "helpdesk.api.copilot.refresh_site_card",
          args: { registry: frm.doc.name },
          freeze: true,
          freeze_message: __("Reading the site's apps…"),
        })
        .then((r) => {
          const found = r.message || {};
          frappe.show_alert({
            message: __("{0} apps read from the site", [found.apps || 0]),
            indicator: (found.drift || []).length ? "orange" : "green",
          });
          frm.reload_doc();
        })
    );
  },
});
