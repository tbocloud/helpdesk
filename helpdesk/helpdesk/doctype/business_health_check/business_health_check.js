// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

frappe.ui.form.on("Business Health Check", {
  refresh(frm) {
    const link = frm.doc.report_link || "";
    // only real web links (the website always sends https://…/results/#id=…&k=…)
    if (!/^https?:\/\//i.test(link)) {
      return;
    }
    frm.add_custom_button(__("Open Report"), () => {
      window.open(link, "_blank", "noopener");
    });
  },
});
