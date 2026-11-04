// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

// only real web links (the website always sends https://…/results/#id=…&k=…)
const isWebLink = (link) => /^https?:\/\//i.test(link || "");

frappe.ui.form.on("Business Health Check", {
  refresh(frm) {
    if (!isWebLink(frm.doc.report_link)) {
      return;
    }
    frm.add_custom_button(__("Open Report"), () => {
      // read the link when clicked, so an edited (unsaved) link is the one opened
      const link = frm.doc.report_link;
      if (isWebLink(link)) {
        window.open(link, "_blank", "noopener");
      }
    });
  },
});
