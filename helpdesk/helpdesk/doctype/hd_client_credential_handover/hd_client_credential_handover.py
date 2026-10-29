# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""The login details a client hands over to the team when a project starts (Received from
client), and the team's hand-back when the client leaves (Returned to client).

Everything goes through helpdesk.api.client_credentials, which decides who may see or
change them; the doctype itself is for System Managers. A hand-back copies the received
credentials without their passwords (it points at the received rows) and closes the
project. See docs/client-credentials.md."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today
from frappe.utils.password import delete_all_passwords_for

RECEIVED = "Received from client"
RETURNED = "Returned to client"
# a closed project can't be handed back again
CLOSED_PROJECT_STATUSES = ("Completed", "Cancelled")
CLOSED_STATUS = "Cancelled"
# what a person types for one credential; the row's name and link stay ours
ITEM_FIELDS = (
    "platform",
    "account_url",
    "username",
    "password",
    "two_factor_contact",
    "notes",
)


class HDClientCredentialHandover(Document):
    def before_insert(self):
        self.fill_returned_items()

    def validate(self):
        self.validate_returned()
        self.validate_items()

    def after_insert(self):
        self.log_on_project()
        self.close_project()

    def on_trash(self):
        self.delete_passwords()

    def fill_returned_items(self):
        """A hand-back lists every credential the team received, by reference: the
        passwords are not copied, they are read from the received rows."""
        if self.direction != RETURNED or self.items:
            return
        for row in received_credentials(self.project):
            self.append(
                "items",
                {
                    **{f: row.get(f) for f in ITEM_FIELDS if f != "password"},
                    "returned_from": row.name,
                },
            )

    def validate_returned(self):
        if self.direction != RETURNED:
            return
        if getdate(self.signed_on) > getdate(today()):
            frappe.throw(_("The sign-off can't be dated in the future."))
        if self.is_new() and (
            frappe.db.get_value("Project", self.project, "status")
            in CLOSED_PROJECT_STATUSES
        ):
            frappe.throw(_("This project is already closed."))

    def validate_items(self):
        for row in self.items:
            row.platform = row.platform or "Other"
            row.username = (row.username or "").strip()
            row.account_url = (row.account_url or "").strip()

    def log_on_project(self):
        """A line in the project's timeline; never the passwords."""
        project = frappe.get_doc("Project", self.project)
        project.add_comment(
            "Info",
            _("Client credentials {0} ({1}): {2} login(s).").format(
                _("received") if self.direction == RECEIVED else _("handed back"),
                self.name,
                len(self.items),
            ),
        )

    def close_project(self):
        """A hand-back ends the engagement: the project is Cancelled, with the reason in
        its timeline. Saved once."""
        if self.direction != RETURNED:
            return
        project = frappe.get_doc("Project", self.project)
        project.status = CLOSED_STATUS
        project.save(ignore_permissions=True)
        project.add_comment(
            "Info",
            _(
                "Closed after the client credentials were handed back to {0}: {1}"
            ).format(self.client_signoff_name, self.close_reason),
        )

    def delete_passwords(self):
        for row in self.items:
            delete_all_passwords_for("HD Client Credential", row.name)

    def set_items(self, items: list[dict]):
        """Make the rows what `items` says. A row sent with its `name` keeps its password
        unless a new one is sent; a row left out is removed with its password. The caller
        saves."""
        kept = {row.name: row for row in self.items}
        wanted = []
        for item in items:
            row = kept.get(item.get("name"))
            if not row:
                row = self.append("items", {})
            for field in ITEM_FIELDS:
                # an empty password box on an existing row means "unchanged"
                if field == "password" and row.name in kept and not item.get(field):
                    continue
                row.set(field, item.get(field) or None)
            wanted.append(row.name)
        for name, row in kept.items():
            if name not in wanted:
                self.remove(row)
                delete_all_passwords_for("HD Client Credential", name)


def received_credentials(project: str) -> list:
    """Every credential row of the project's received handovers, oldest first."""
    handover = frappe.qb.DocType("HD Client Credential Handover")
    row = frappe.qb.DocType("HD Client Credential")
    return (
        frappe.qb.from_(row)
        .join(handover)
        .on(row.parent == handover.name)
        .select(row.star)
        .where(handover.project == project)
        .where(handover.direction == RECEIVED)
        .orderby(row.creation)
        .run(as_dict=True)
    )
