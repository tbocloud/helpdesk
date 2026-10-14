import { capture } from "@/telemetry";
import { call } from "frappe-ui";

/** A line in the ticket's activity, e.g. "assigned reshma@tbo.in". */
export function logTicketActivity(ticket: string, action: string) {
  return call("frappe.client.insert", {
    doc: { doctype: "HD Ticket Activity", ticket, action },
  });
}

/**
 * Assign a ticket the way the ticket page does: the same endpoint (so the
 * permission check and the assignment notifications are the same) and the same
 * activity line.
 */
export async function assignTicket(ticket: string, users: string[]) {
  await call("frappe.desk.form.assign_to.add", {
    doctype: "HD Ticket",
    name: ticket,
    assign_to: users,
  });
  // the assignment stands even if its activity line or telemetry fails
  await logTicketActivity(ticket, `assigned ${users.join(", ")}`).catch(
    () => undefined
  );
  try {
    capture("ticket_assigned", { data: { doctype: "HD Ticket" } });
  } catch {
    // telemetry is best effort
  }
}
