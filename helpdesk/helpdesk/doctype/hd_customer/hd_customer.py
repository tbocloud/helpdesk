# Copyright (c) 2022, Frappe Technologies and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.core.api.user_invitation import invite_by_email
from frappe.model.document import Document
from frappe.utils import validate_email_address

from helpdesk.integrations.erpnext.utils import (
    cascade_rename,
    in_cascade,
    map_source_to_target_values,
)
from helpdesk.integrations.erpnext.utils import should_sync as should_sync_with_erpnext
from helpdesk.integrations.erpnext.utils import (
    sync_related_fields,
    validate_rename_conflict,
)
from helpdesk.tasky.permissions import can_manage_team, is_project_manager
from helpdesk.utils import agent_only, get_customers, is_agent
from helpdesk.work_calendar import on_leave

CUSTOMER_ROLES = ("HD Customer", "HD Customer Manager")
TICKET_OWNER_FIELDS = ("ticket_owner", "backup_ticket_owner")


class HDCustomer(Document):
    @staticmethod
    def default_list_data():
        columns = [
            {
                "label": "Name",
                "key": "name",
                "width": "17rem",
                "type": "Data",
            },
            {
                "label": "Customer Type",
                "key": "customer_type",
                "width": "10rem",
                "type": "Select",
            },
            {
                "label": "Email ID",
                "key": "email_id",
                "width": "17rem",
                "type": "Data",
            },
            {
                "label": "Mobile No",
                "key": "mobile_no",
                "width": "12rem",
                "type": "Data",
            },
            {
                "label": "Created On",
                "key": "creation",
                "width": "8rem",
                "type": "Datetime",
            },
        ]
        rows = [
            "customer_name",
            "customer_type",
            "email_id",
            "mobile_no",
            "creation",
            "image",
        ]

        return {"columns": columns, "rows": rows}

    def validate(self):
        self.validate_contacts()
        self.validate_ticket_owners()

    def validate_ticket_owners(self):
        """Only the people who may set ticket owners change them, and both are active
        agents; the backup needs an owner and is someone else (docs/ticket-owners.md)."""
        previous = self.get_doc_before_save()
        changed = [
            field
            for field in TICKET_OWNER_FIELDS
            # an empty Link can be None or "": both mean no owner
            if ((previous.get(field) if previous else None) or None)
            != (self.get(field) or None)
        ]
        if not changed:
            return
        if not can_set_ticket_owner():
            frappe.throw(
                _("Only managers and department heads can set ticket owners."),
                frappe.PermissionError,
            )
        if self.backup_ticket_owner and not self.ticket_owner:
            frappe.throw(_("Set a ticket owner before a backup."))
        if self.backup_ticket_owner and self.backup_ticket_owner == self.ticket_owner:
            frappe.throw(_("The backup must be someone other than the ticket owner."))
        chosen = [self.get(field) for field in changed if self.get(field)]
        inactive = set(chosen) - active_agents(chosen)
        if inactive:
            frappe.throw(
                _("{0} isn't an active agent, so they can't own tickets.").format(
                    ", ".join(sorted(inactive))
                )
            )

    def ticket_owner_today(self) -> dict | None:
        """Who takes this customer's new tickets today: the owner, else the backup while
        the owner is on approved leave (a half day still counts as working) or inactive.
        None when neither can, and the assignment rules decide as before.

        Returns {"user", "backup", "away": the owner when the backup takes it, "until":
        the last day of the owner's leave, or None when the owner is inactive}.
        """
        if not self.ticket_owner:
            return None
        people = [p for p in (self.ticket_owner, self.backup_ticket_owner) if p]
        working = active_agents(people)
        away = on_leave(users=people)
        if self.ticket_owner in working and self.ticket_owner not in away:
            return {"user": self.ticket_owner, "backup": False}
        backup = self.backup_ticket_owner
        if not backup or backup not in working or backup in away:
            return None
        return {
            "user": backup,
            "backup": True,
            "away": self.ticket_owner,
            "until": away.get(self.ticket_owner),
        }

    def validate_contacts(self):
        if not self.contacts:
            return

        contact_names = [contact.contact_name for contact in self.contacts]
        if len(contact_names) != len(set(contact_names)):
            frappe.throw(_("Duplicate contacts are not allowed"))

        if self.primary_contact and self.primary_contact not in contact_names:
            frappe.throw(_("Primary contact must be one of the listed contacts"))

    def before_save(self):
        self.ensure_primary_contact_is_manager()
        self.handle_roles()
        self.cleanup_primary_contact_fields()

    def ensure_primary_contact_is_manager(self):
        # the primary is optional, but whoever is set as primary is a manager
        if not self.contacts or not self.primary_contact:
            return
        for contact in self.contacts:
            if contact.contact_name == self.primary_contact:
                contact.is_manager = True

    def handle_roles(self):
        # Sync customer roles only for contacts whose manager flag actually changed
        if not self.has_value_changed("contacts"):
            return
        previous = self.get_doc_before_save()
        was_manager = (
            {row.contact_name: row.is_manager for row in previous.contacts}
            if previous
            else {}
        )
        for contact in self.contacts:
            if contact.is_manager == was_manager.get(contact.contact_name):
                continue
            self.sync_contact_role(contact)

    def sync_contact_role(self, contact):
        """Grant the manager/member role to a single contact's user in one save."""
        user = self.get_user(contact.contact_name, throw_error=False)
        if not user:
            return
        user_doc = frappe.get_doc("User", user)
        if contact.is_manager:
            user_doc.append_roles("HD Customer Manager", "HD Customer")
        else:
            user_doc.append_roles("HD Customer")
            if not self.is_manager_in_other_customers(contact.contact_name):
                user_doc.set(
                    "roles",
                    [r for r in user_doc.roles if r.role != "HD Customer Manager"],
                )
        user_doc.save(ignore_permissions=True)

    def is_manager_in_other_customers(self, contact_name: str) -> bool:
        """Whether the contact manages a customer other than this one. If yes, dont demote the role, just remove the is_manager check."""
        return bool(
            frappe.db.exists(
                "HD Customer Member",
                {
                    "contact_name": contact_name,
                    "is_manager": 1,
                    "parent": ("!=", self.name),
                },
            )
        )

    def cleanup_primary_contact_fields(self):
        """Clear the email and mobile fields if the primary contact is removed."""
        if not self.has_value_changed("contacts"):
            return

        if not len(self.contacts) and self.primary_contact:
            self.primary_contact = None
            self.email_id = None
            self.mobile_no = None
            return

    def get_user(self, contact_name, throw_error=True):
        user = frappe.db.get_value("Contact", contact_name, "user")
        if user:
            return user

        # fallback to email if user is not set for the contact
        email = frappe.get_value("Contact", contact_name, "email_id")
        if email:
            if user := frappe.db.exists("User", email):
                frappe.db.set_value("Contact", contact_name, "user", user)
            return user
        elif throw_error:
            frappe.throw(_("No user linked to contact {0}").format(contact_name))
        else:
            return None

    @frappe.whitelist()
    @agent_only
    def get_contacts(self):
        contact_names = [contact.contact_name for contact in self.contacts]
        details = self.get_contact_details(contact_names)
        ticket_counts = self.get_pending_ticket_counts(contact_names)
        last_active = self.get_last_active([d.user for d in details.values() if d.user])

        result = []
        for contact in self.contacts:
            info = details.get(contact.contact_name)
            if not info:
                continue
            result.append(
                {
                    "contact_name": contact.contact_name,
                    "is_primary": int(contact.contact_name == self.primary_contact),
                    "is_manager": contact.is_manager,
                    "email_id": info.email_id,
                    "mobile_no": info.mobile_no or info.phone,
                    "image": info.image,
                    "last_active": last_active.get(info.user),
                    "ticket_count": ticket_counts.get(contact.contact_name, 0),
                }
            )
        result.sort(key=lambda row: (not row["is_primary"], not row["is_manager"]))
        return result

    def get_contact_details(self, contact_names: list[str]) -> dict:
        """Fetch every member's contact info in one query, keyed by contact name."""
        if not contact_names:
            return {}
        rows = frappe.get_all(
            "Contact",
            filters={"name": ["in", contact_names]},
            fields=["name", "email_id", "mobile_no", "phone", "image", "user"],
        )
        return {row.name: row for row in rows}

    def get_pending_ticket_counts(self, contact_names: list[str]) -> dict:
        """Count open/paused tickets per contact (matched by raised_by or contact)."""
        counts = dict.fromkeys(contact_names, 0)
        if not contact_names:
            return counts
        tickets = frappe.get_list(
            "HD Ticket",
            filters={"status_category": ["in", ["Open", "Paused"]]},
            or_filters=[
                ["raised_by", "in", contact_names],
                ["contact", "in", contact_names],
            ],
            fields=["raised_by", "contact"],
        )
        for ticket in tickets:
            for name in {ticket.raised_by, ticket.contact} & counts.keys():
                counts[name] += 1
        return counts

    def get_last_active(self, users: list[str]) -> dict:
        """Map each user to their last_active timestamp in one query."""
        if not users:
            return {}
        rows = frappe.get_all(
            "User", filters={"name": ["in", users]}, fields=["name", "last_active"]
        )
        return {row.name: row.last_active for row in rows}

    @frappe.whitelist()
    def add_contacts(self, contacts: str | list, role: str = "HD Customer") -> dict:
        """Add contacts that already have a linked user; invite the rest by email.

        Each entry can be a Contact name or an email address. Returns the
        contact names added directly and the result of the sent invitations.
        """
        self.validate_contact_update_permission(role)
        entries = frappe.parse_json(contacts) if isinstance(contacts, str) else contacts
        if not entries:
            frappe.throw(_("No contacts to add"))

        added, to_invite = [], []
        for entry in entries:
            contact_name, email = self.resolve_contact_entry(entry)
            if contact_name and self.get_user(contact_name, throw_error=False):
                if self.add_contact(contact_name, role):
                    added.append(contact_name)
            else:
                to_invite.append({"email": email, "contact": contact_name})

        if added:
            self.save()
        return {"added": added, "invite_result": self.invite_contacts(to_invite, role)}

    def validate_contact_update_permission(self, role: str) -> None:
        if role not in CUSTOMER_ROLES:
            frappe.throw(_("Invalid role {0}").format(role))
        roles = frappe.get_roles()
        if "System Manager" not in roles and "Agent Manager" not in roles:
            frappe.throw(
                _("You do not have permission to update contacts"),
                frappe.PermissionError,
            )

    def resolve_contact_entry(self, entry: str) -> tuple[str | None, str]:
        """Resolve an entry to a (contact name, email) pair."""
        if frappe.db.exists("Contact", entry):
            email = frappe.db.get_value("Contact", entry, "email_id")
            if not email:
                frappe.throw(_("Contact {0} has no email address").format(entry))
            return entry, email
        validate_email_address(entry, throw=True)
        return frappe.db.get_value("Contact", {"email_id": entry}, "name"), entry

    def add_contact(self, contact_name: str, role: str = "HD Customer") -> bool:
        """Add a contact to membership. Returns False if already a member."""
        if any(row.contact_name == contact_name for row in self.contacts):
            return False
        self.append(
            "contacts",
            {
                "contact_name": contact_name,
                "is_manager": role == "HD Customer Manager",
            },
        )
        return True

    def remove_contact(self, contact_name: str) -> None:
        """Drop a contact from membership, clearing primary state if it was primary."""
        self.contacts = [r for r in self.contacts if r.contact_name != contact_name]
        if self.primary_contact == contact_name:
            self.clear_primary()

    def set_primary(self, contact_name: str) -> None:
        """Make a contact the primary contact, ensuring it is a manager member."""
        self.add_contact(contact_name, "HD Customer Manager")
        self.primary_contact = contact_name

    def clear_primary(self) -> None:
        """Drop the primary contact and the fields fetched from it."""
        self.primary_contact = None
        self.email_id = None
        self.mobile_no = None

    def invite_contacts(self, to_invite: list[dict], role: str) -> dict:
        result = {
            "invited_emails": [],
            "pending_invite_emails": [],
            "accepted_invite_emails": [],
            "disabled_user_emails": [],
        }
        for item in to_invite:
            params = {"customer": self.name}
            if item["contact"]:
                params["contact"] = item["contact"]
            response = invite_by_email(
                item["email"],
                roles=[role],
                redirect_to_path="/helpdesk",
                app_name="helpdesk",
                **params,
            )
            for key, emails in response.items():
                result.setdefault(key, []).extend(emails)
        return result

    @frappe.whitelist()
    def get_pending_invites(self):
        if "Agent Manager" not in frappe.get_roles():
            frappe.throw(
                _("You do not have permission to access this resource"),
                frappe.PermissionError,
            )
        pending_invites = frappe.db.get_all(
            "User Invitation",
            filters={
                "app_name": "helpdesk",
                "status": "Pending",
                "customer": self.name,
            },
            fields=[
                "name",
                "email",
                "invited_by",
                "creation",
            ],
        )
        res = []
        for pending_invitation in pending_invites:
            roles = frappe.db.get_all(
                "User Role",
                fields=["role"],
                filters={"parent": pending_invitation.name},
            )
            res.append(
                {
                    "name": pending_invitation.name,
                    "email": pending_invitation.email,
                    "invited_by": pending_invitation.invited_by,
                    "invited_on": pending_invitation.creation,
                    "roles": [r.role for r in roles],
                }
            )
        return res

    def after_insert(self):
        if should_sync_with_erpnext() and not self.flags.get("ignore_erpnext_sync"):
            self.create_customer_in_erpnext()

    def create_customer_in_erpnext(self):
        if self.erpnext_customer:
            return

        erpnext_customer_exists = frappe.db.exists(
            "Customer", {"hd_customer": self.name}
        )
        if erpnext_customer_exists:
            return

        # create a new customer in ERPNext with the same name as the HD Customer and link them together
        erp_doc = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": self.customer_name,
                "hd_customer": self.name,
                **map_source_to_target_values(self),
            }
        )
        erp_doc.flags.ignore_erpnext_sync = True
        erp_doc.insert(ignore_permissions=True)
        frappe.db.set_value("HD Customer", self.name, "erpnext_customer", erp_doc.name)

    def on_update(self):
        if not should_sync_with_erpnext() or self.flags.get("ignore_erpnext_sync"):
            return

        sync_related_fields(self)

    def before_rename(self, olddn, newdn, merge=False):
        validate_rename_conflict("HD Customer", olddn, newdn, merge)

    def after_rename(self, olddn, newdn, merge=False):
        cascade_rename("HD Customer", olddn, newdn, merge)

    def on_trash(self):
        self.unlink_tickets()
        self.unlink_invitations()
        if in_cascade() or not should_sync_with_erpnext():
            return

        erpnext_customer = frappe.db.get_value(
            "Customer", {"hd_customer": self.name}, "name"
        )
        if erpnext_customer:
            # Clear the back-link first so CustomCustomer.on_trash won't try to
            # delete this HD Customer again (it's already being deleted).
            frappe.db.set_value("Customer", erpnext_customer, "hd_customer", None)
            frappe.delete_doc("Customer", erpnext_customer, ignore_permissions=True)

    def unlink_tickets(self) -> None:
        """Delete or detach the tickets linked to this customer on delete."""
        if self.flags.get("delete_tickets"):
            self.delete_linked_tickets()
        else:
            self.unlink_linked_tickets()

    def delete_linked_tickets(self) -> None:
        tickets = frappe.get_all("HD Ticket", {"customer": self.name}, pluck="name")
        for ticket in tickets:
            frappe.delete_doc("HD Ticket", ticket, ignore_permissions=True)

    def unlink_linked_tickets(self) -> None:
        frappe.db.set_value("HD Ticket", {"customer": self.name}, "customer", None)

    def unlink_invitations(self) -> None:
        frappe.db.set_value(
            "User Invitation",
            {"app_name": "helpdesk", "customer": self.name},
            "customer",
            None,
        )


# Custom perms for list query. Only the `WHERE` part
# Used so that contact raising the ticket can see the customers they are part of
def permission_query(user: str) -> str:
    if is_agent(user):
        return ""

    customers = get_customers(user)
    if not customers:
        return "1=0"

    names = ", ".join(frappe.db.escape(name) for name in customers)
    return f"`tabHD Customer`.name in ({names})"


def has_permission(doc: Document, ptype: str, user: str) -> bool:
    """Per-record access for HD Customer.

    Members of a customer can read it; only managers can write or delete it.
    Agents are unrestricted; non-members are denied.
    """
    if is_agent(user):
        return True

    membership = get_customer_membership(doc.name, user)
    if not membership:
        return False
    if ptype in ("write", "delete"):
        return bool(membership.get("is_manager"))
    return True


def get_customer_membership(customer: str, user: str) -> dict | None:
    """Return the user's membership row for `customer`, or None if not a member."""
    for member in get_customers(user, get_roles=True):
        if member.get("name") == customer:
            return member
    return None


def can_set_ticket_owner(user: str | None = None) -> bool:
    """Who sets customers' ticket owners: System and Agent Managers, Project Managers
    and department heads. Everyone else sees the owners read-only."""
    user = user or frappe.session.user
    return is_project_manager(user) or can_manage_team(user)


def active_agents(users: list[str]) -> set[str]:
    """The `users` who can take tickets: an active HD Agent with an enabled account."""
    users = [u for u in users if u]
    if not users:
        return set()
    agent = frappe.qb.DocType("HD Agent")
    account = frappe.qb.DocType("User")
    rows = (
        frappe.qb.from_(agent)
        .join(account)
        .on(account.name == agent.user)
        .select(agent.name)
        .where(agent.name.isin(users) & (agent.is_active == 1) & (account.enabled == 1))
        .run(pluck=True)
    )
    return set(rows)


def add_customer_contact(customer: str, email: str) -> bool:
    """Make `email` a contact of `customer`; True if a new Contact was created.

    The member row is inserted directly, not through HD Customer.save(): saving grants
    the HD Customer role to any existing User with this email, and these emails are
    often staff. Ticket intake and the content portal only need the contact link.
    """
    contact = frappe.db.get_value("Contact", {"email_id": email}, "name")
    created = not contact
    if created:
        contact = (
            frappe.get_doc(
                {
                    "doctype": "Contact",
                    "first_name": email.split("@")[0],
                    "email_id": email,
                    "email_ids": [{"email_id": email, "is_primary": 1}],
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    if frappe.db.exists(
        "HD Customer Member",
        {"parent": customer, "parenttype": "HD Customer", "contact_name": contact},
    ):
        return created
    frappe.get_doc(
        {
            "doctype": "HD Customer Member",
            "parent": customer,
            "parenttype": "HD Customer",
            "parentfield": "contacts",
            "contact_name": contact,
            "is_manager": 0,
            "idx": frappe.db.count("HD Customer Member", {"parent": customer}) + 1,
        }
    ).db_insert()
    return created


def normalize_domain(value: str | None) -> str:
    """ "https://www.Example.com/about" → "example.com"; "" when there is none."""
    text = (value or "").strip().lower()
    text = text.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0]
    text = text.rsplit("@", 1)[-1].split(":", 1)[0].strip(".")
    return text.removeprefix("www.") if "." in text else ""


def customer_domains(domain: str | None, email_domains: str | None) -> set[str]:
    """A customer's mail domains: Domain plus its Other Email Domains."""
    values = [domain, *re.split(r"[\s,;]+", email_domains or "")]
    return {d for d in (normalize_domain(v) for v in values) if d}


def public_email_domains() -> set[str]:
    """Domains anyone can have an address at (Settings → Ticket intake)."""
    text = frappe.db.get_single_value("HD Intake Settings", "public_email_domains")
    return {d for d in (normalize_domain(v) for v in (text or "").split()) if d}


def customer_for_email(email: str | None) -> str | None:
    """The one customer whose domains match the sender's (a subdomain counts), or None
    for a public mail domain, no match or more than one."""
    domain = normalize_domain((email or "").rpartition("@")[2])
    if not domain or domain in public_email_domains():
        return None
    customers = frappe.get_all(
        "HD Customer",
        or_filters={"domain": ("is", "set"), "email_domains": ("is", "set")},
        fields=["name", "domain", "email_domains"],
        limit_page_length=0,
    )
    matches = {
        c.name
        for c in customers
        if any(
            domain == d or domain.endswith("." + d)
            for d in customer_domains(c.domain, c.email_domains)
        )
    }
    return matches.pop() if len(matches) == 1 else None
