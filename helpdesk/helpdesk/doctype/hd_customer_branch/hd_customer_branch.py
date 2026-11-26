# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""A branch of an HD Customer (Roxy's Kochi, Kinassery, Thondayad shops) for the Content
Calendar. Each branch has its own posts, monthly plan, approvers and, through its
own project, its own Meta page. Customers without branches work as before.
"""

import frappe
from frappe import _
from frappe.model.document import Document

BRANCH = "HD Customer Branch"


class HDCustomerBranch(Document):
    def autoname(self):
        self.name = self.branch_label(self.customer, self.branch_name)

    def validate(self):
        self.clean_branch_name()
        self.clean_approvers()
        self.validate_project()

    def clean_branch_name(self):
        self.branch_name = (self.branch_name or "").strip()
        if not self.branch_name:
            frappe.throw(_("Give the branch a name, e.g. Kochi."))

    def clean_approvers(self):
        seen = set()
        for row in self.approvers:
            row.email = (row.email or "").strip().lower()
            frappe.utils.validate_email_address(row.email, throw=True)
            if row.email in seen:
                frappe.throw(_("{0} is listed twice as an approver.").format(row.email))
            seen.add(row.email)

    def validate_project(self):
        """The branch's project must be the customer's, and no other branch's."""
        if not self.project:
            return
        from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
            project_customer_fields,
        )

        values = frappe.db.get_value(
            "Project", self.project, project_customer_fields(), as_dict=True
        )
        if not values or self.customer not in values.values():
            frappe.throw(
                _("Project {0} isn't {1}'s. Set {1} as its customer first.").format(
                    frappe.bold(self.project), frappe.bold(self.customer)
                )
            )
        other = frappe.db.get_value(
            BRANCH, {"project": self.project, "name": ("!=", self.name)}, "name"
        )
        if other:
            frappe.throw(
                _("Project {0} already belongs to the branch {1}.").format(
                    frappe.bold(self.project), frappe.bold(other)
                )
            )

    @staticmethod
    def branch_label(customer: str, branch_name: str) -> str:
        return f"{customer} - {(branch_name or '').strip()}"


def branch_projects(customer: str) -> list[str]:
    """Projects that belong to one of the customer's branches."""
    return [
        p
        for p in frappe.get_all(
            BRANCH, filters={"customer": customer}, pluck="project", distinct=True
        )
        if p
    ]


def branch_approvers(branch: str) -> list[str]:
    """The emails that approve this branch's posts."""
    return frappe.get_all(
        "HD Customer Branch Approver",
        filters={"parent": branch, "parenttype": BRANCH},
        pluck="email",
        order_by="idx asc",
    )


def branches_for_email(email: str) -> list[str]:
    """Every enabled branch this email approves for."""
    if not email:
        return []
    Approver = frappe.qb.DocType("HD Customer Branch Approver")
    Branch = frappe.qb.DocType(BRANCH)
    return sorted(
        frappe.qb.from_(Approver)
        .join(Branch)
        .on(Branch.name == Approver.parent)
        .select(Branch.name)
        .distinct()
        .where(Approver.parenttype == BRANCH)
        .where(Approver.email == email)
        .where(Branch.enabled == 1)
        .run(pluck=True)
    )
