"""Customers' ticket owners (docs/ticket-owners.md): who gets a customer's new tickets.

Set from the customer page (one customer) or the Customers list (several at once). The
rules (who may set them, active agents only, a backup unlike the owner) live in
HDCustomer.validate_ticket_owners; this only applies them to each customer.
"""

import frappe
from frappe import _

from helpdesk.helpdesk.doctype.hd_customer.hd_customer import can_set_ticket_owner
from helpdesk.utils import agent_only


@frappe.whitelist(methods=["POST"])
@agent_only
def set_ticket_owner(
    customers: list[str] | str,
    ticket_owner: str = "",
    backup_ticket_owner: str | None = None,
) -> dict:
    """Give `customers` a ticket owner, all or none: one that can't be saved stops the lot.

    An empty `ticket_owner` clears the owner and the backup. `backup_ticket_owner` None
    keeps each customer's backup, except where it is the new owner (then it's cleared);
    "" clears it.
    """
    if not can_set_ticket_owner():
        frappe.throw(
            _("Only managers and department heads can set ticket owners."),
            frappe.PermissionError,
        )
    names = frappe.parse_json(customers) if isinstance(customers, str) else customers
    if not names:
        frappe.throw(_("Pick at least one customer."))
    for name in names:
        doc = frappe.get_doc("HD Customer", name)
        doc.check_permission("read")
        doc.ticket_owner = ticket_owner or None
        if not ticket_owner:
            doc.backup_ticket_owner = None
        elif backup_ticket_owner is not None:
            doc.backup_ticket_owner = backup_ticket_owner or None
        elif doc.backup_ticket_owner == ticket_owner:
            doc.backup_ticket_owner = None
        # agents can't edit customers; validate_ticket_owners checks who may set owners
        doc.save(ignore_permissions=True)
    return {"updated": len(names)}
