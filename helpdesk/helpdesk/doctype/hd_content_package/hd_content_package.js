// Copyright (c) 2026, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("HD Content Package", {
  refresh(frm) {
    if (frm.is_new()) return;
    for (const [which, label] of [
      ["next", __("Plan next month")],
      ["this", __("Plan rest of this month")],
    ]) {
      frm.add_custom_button(
        label,
        () =>
          frm.call("plan", { which }).then((r) => {
            frappe.show_alert({
              message: __("{0} posts added to the Content Calendar", [
                r.message,
              ]),
              indicator: "green",
            });
            frm.reload_doc();
          }),
        __("Plan")
      );
    }
  },
});
