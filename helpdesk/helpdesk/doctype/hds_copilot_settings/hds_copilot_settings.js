// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

// Copilot People (Phase 23): who Copilot goes to today for every role and each customer, the
// empty places, and handing over someone's places when they leave or change job.
frappe.ui.form.on("HDS Copilot Settings", {
  refresh(frm) {
    render_people(frm);
    if (frm.perm[0] && frm.perm[0].write) {
      frm.add_custom_button(__("Hand over someone's places"), () =>
        hand_over(frm)
      );
    }
  },
});

function render_people(frm) {
  const field = frm.get_field("people_overview");
  if (!field) return;
  field.$wrapper.html(`<p class="text-muted">${__("Loading…")}</p>`);
  frappe
    .call("helpdesk.copilot.people.overview")
    .then(({ message }) => {
      const esc = frappe.utils.escape_html;
      const muted = (text) =>
        text ? ` <span class="text-muted">(${esc(text)})</span>` : "";
      const warnings = (message.warnings || [])
        .map(
          (w) =>
            `<div class="alert alert-warning" style="margin-bottom:8px">${esc(
              w
            )}</div>`
        )
        .join("");
      const roles = (message.common || [])
        .map(
          (r) => `<tr>
            <td>${esc(r.role)}</td>
            <td>${esc(r.set || "—")}</td>
            <td><b>${esc(r.today || __("nobody"))}</b>${muted(r.why)}</td>
          </tr>`
        )
        .join("");
      const from = {
        owner: __("ticket owners"),
        customer: __("own"),
        common: __("common"),
      };
      const customers = (message.customers || [])
        .map(
          (r) => `<tr>
            <td>${esc(r.customer)}${
            r.copilot ? "" : muted(__("Copilot off"))
          }</td>
            <td>${esc(r.developers || "—")}${muted(
            from[r.developers_from] || ""
          )}</td>
            <td>${esc(r.fix_approvers || "—")}</td>
            <td>${esc(r.coordinators || "—")}${muted(
            from[r.coordinators_from] || ""
          )}</td>
            <td><b>${esc(
              r.today || __("nobody")
            )}</b><br><span class="text-muted">${esc(r.why || "")}</span></td>
            <td>${(r.empty || [])
              .map(
                (e) =>
                  `<span class="indicator-pill orange" style="white-space:normal;margin:2px">${esc(
                    e
                  )}</span>`
              )
              .join("")}</td>
          </tr>`
        )
        .join("");
      field.$wrapper.html(`${warnings}
        <h6>${__("Every customer")}</h6>
        <div class="table-responsive"><table class="table table-bordered table-sm">
          <thead><tr>
            <th>${__("Role")}</th><th>${__("Set (level)")}</th>
            <th>${__("Copilot goes to today")}</th>
          </tr></thead>
          <tbody>${roles}</tbody>
        </table></div>
        <h6>${__("Customers that use Copilot or have their own people")}</h6>
        <div class="table-responsive"><table class="table table-bordered table-sm">
          <thead><tr>
            <th>${__("Customer")}</th><th>${__("Developers")}</th>
            <th>${__("Fix approver")}</th><th>${__("Project coordinators")}</th>
            <th>${__("Copilot goes to today")}</th><th>${__("Not set")}</th>
          </tr></thead>
          <tbody>${
            customers ||
            `<tr><td colspan="6">${__(
              "No customer uses Copilot yet"
            )}</td></tr>`
          }</tbody>
        </table></div>`);
    })
    .catch(() =>
      field.$wrapper.html(
        `<p class="text-muted">${__("The overview could not load.")}</p>`
      )
    );
}

// someone leaves or changes job: every row they hold goes to another person, and their waiting
// fix approvals move along the chain; the counts are shown before anything changes
function hand_over(frm) {
  const dialog = new frappe.ui.Dialog({
    title: __("Hand over someone's places"),
    fields: [
      {
        fieldname: "from_user",
        fieldtype: "Link",
        options: "User",
        label: __("From"),
        reqd: 1,
      },
      {
        fieldname: "to_user",
        fieldtype: "Link",
        options: "User",
        label: __("To"),
        reqd: 1,
      },
      {
        fieldname: "customer",
        fieldtype: "Link",
        options: "HD Customer",
        label: __("Only for this customer"),
        description: __("Empty: the settings and every customer"),
      },
    ],
    primary_action_label: __("Count first"),
    primary_action(values) {
      frappe
        .call({
          method: "helpdesk.copilot.people.hand_over_places",
          args: { ...values, dry_run: 1 },
        })
        .then(({ message }) => {
          frappe.confirm(
            __(
              "{0} rows in Copilot People and {1} waiting fix approvals will move. Hand them over?",
              [message.rows, message.approvals]
            ),
            () =>
              frappe
                .call({
                  method: "helpdesk.copilot.people.hand_over_places",
                  args: { ...values, dry_run: 0 },
                  freeze: true,
                })
                .then(({ message: done }) => {
                  dialog.hide();
                  frappe.show_alert({
                    message: __("Handed over: {0} rows, {1} approvals moved.", [
                      done.rows,
                      done.moved,
                    ]),
                    indicator: "green",
                  });
                  frm.reload_doc();
                })
          );
        });
    },
  });
  dialog.show();
}
