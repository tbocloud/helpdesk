// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

// Who Copilot goes to today (Phase 22): each customer's people and why, and every empty place.
frappe.ui.form.on("HDS Copilot Settings", {
  refresh(frm) {
    render_people(frm);
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
      const warnings = (message.warnings || [])
        .map(
          (w) =>
            `<div class="alert alert-warning" style="margin-bottom:8px">${esc(
              w
            )}</div>`
        )
        .join("");
      const rows = (message.customers || [])
        .map(
          (r) => `<tr>
						<td>${esc(r.customer)}</td>
						<td>${esc(r.first || "—")}</td>
						<td>${esc(r.second || "—")}</td>
						<td>${esc(r.fix_approver || "—")}</td>
						<td>${esc(r.coordinators || "—")}${
            r.coordinators_from === "common" && r.coordinators
              ? ` <span class="text-muted">(${esc(__("common"))})</span>`
              : ""
          }</td>
						<td><b>${esc(r.today || __("nobody"))}</b><br><span class="text-muted">${esc(
            r.why || ""
          )}</span></td>
						<td>${
              r.empty && r.empty.length
                ? `<span class="indicator-pill orange">${esc(
                    r.empty.join(", ")
                  )}</span>`
                : ""
            }</td>
					</tr>`
        )
        .join("");
      field.$wrapper.html(`${warnings}
				<div class="table-responsive"><table class="table table-bordered table-sm">
					<thead><tr>
						<th>${__("Customer")}</th><th>${__("First developer")}</th>
						<th>${__("Second developer")}</th><th>${__("Fix approver")}</th>
						<th>${__("Project coordinators")}</th><th>${__("Copilot goes to today")}</th>
						<th>${__("Not set")}</th>
					</tr></thead>
					<tbody>${rows || `<tr><td colspan="7">${__("No customers")}</td></tr>`}</tbody>
				</table></div>`);
    })
    .catch(() => field.$wrapper.html(""));
}
