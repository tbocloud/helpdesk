// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

// A release of other people's merges (Phase 7): decide it, let it through without green CI, or cancel it.
// A Copilot fix's deploy is handled on its ticket instead.
frappe.ui.form.on("HDS Deploy Request", {
  refresh(frm) {
    if (frm.is_new() || frm.doc.run) return;
    frappe
      .call("helpdesk.api.copilot.get_release", { release: frm.doc.name })
      .then(({ message: release }) => {
        const decide = (approve, when, note) =>
          frappe
            .call("helpdesk.api.copilot.decide_release", {
              release: frm.doc.name,
              approve,
              when,
              note: note || "",
              expected_hash: release.hash,
            })
            .then(() => frm.reload_doc());
        if (release.may_decide) {
          const group = __("Decide");
          frm.add_custom_button(
            __("Approve for tonight"),
            () => decide(1, "tonight"),
            group
          );
          if (release.may_deploy_now) {
            frm.add_custom_button(
              __("Approve and deploy now"),
              () => decide(1, "now"),
              group
            );
          }
          frm.add_custom_button(
            __("Reject"),
            () =>
              frappe.prompt(
                {
                  fieldname: "note",
                  fieldtype: "Small Text",
                  label: __("Why"),
                  reqd: 1,
                },
                ({ note }) => decide(0, "tonight", note),
                __("Reject the release")
              ),
            group
          );
        } else if (release.why_not) {
          frm.dashboard.set_headline(release.why_not);
        }
        if (release.may_override_ci) {
          frm.add_custom_button(__("Let through without green CI"), () =>
            frappe.prompt(
              {
                fieldname: "reason",
                fieldtype: "Small Text",
                label: __("Why"),
                reqd: 1,
              },
              ({ reason }) =>
                frappe
                  .call("helpdesk.api.copilot.override_release_ci", {
                    release: frm.doc.name,
                    reason,
                  })
                  .then(() => frm.reload_doc()),
              __("Let it through without green CI")
            )
          );
        }
        if (release.may_cancel) {
          frm.add_custom_button(__("Cancel release"), () =>
            frappe.prompt(
              {
                fieldname: "reason",
                fieldtype: "Small Text",
                label: __("Why"),
              },
              ({ reason }) =>
                frappe
                  .call("helpdesk.api.copilot.cancel_release", {
                    release: frm.doc.name,
                    reason: reason || "",
                  })
                  .then(() => frm.reload_doc()),
              __("Cancel the release")
            )
          );
        }
      });
  },
});
