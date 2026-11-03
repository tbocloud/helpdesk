// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

frappe.ui.form.on("Business Health Check", {
  refresh(frm) {
    if (isHealthCheckWebLink(frm.doc.report_link)) {
      frm.add_custom_button(__("Open Report"), () => {
        // read the link when clicked, so an edited (unsaved) link is the one opened
        const link = frm.doc.report_link;
        if (isHealthCheckWebLink(link)) {
          window.open(link, "_blank", "noopener");
        }
      });
    }
    if (frm.is_new()) {
      return;
    }
    if (frm.doc.lead) {
      frm.add_custom_button(__("Open Lead"), () => {
        const lead = encodeURIComponent(frm.doc.lead);
        window.open(`/helpdesk/leads/${lead}`, "_blank", "noopener");
      });
    } else {
      frm.add_custom_button(__("Create Lead"), () =>
        createHealthCheckLead(frm)
      );
    }
  },
});

// only real web links (the website always sends https://…/results/#id=…&k=…)
function isHealthCheckWebLink(link) {
  return /^https?:\/\//i.test(link || "");
}

// the lead is made from the saved record, on the ERP site (Leads), as the signed-in person
function createHealthCheckLead(frm, allowDuplicate = 0) {
  if (frm.is_dirty()) {
    frappe.msgprint(__("Save the record first, then create the lead."));
    return;
  }
  frm
    .call({
      doc: frm.doc,
      method: "create_lead",
      args: { allow_duplicate: allowDuplicate },
      freeze: true,
      freeze_message: __("Creating the lead…"),
    })
    .then((r) => {
      const result = r.message || {};
      if (result.duplicate) {
        // another lead has this email or phone: make one only when the person says so
        frappe.confirm(
          `${frappe.utils.escape_html(result.duplicate)}<br><br>${__(
            "Create a new lead anyway?"
          )}`,
          () => createHealthCheckLead(frm, 1)
        );
        return;
      }
      frm.reload_doc();
      if (result.noted) {
        frappe.show_alert({
          message: __("Lead {0} created", [result.lead]),
          indicator: "green",
        });
      } else {
        frappe.msgprint(
          __(
            "Lead {0} was created, but the report link couldn't be added to it. Add the link as a note on the lead.",
            [result.lead]
          )
        );
      }
    });
}
