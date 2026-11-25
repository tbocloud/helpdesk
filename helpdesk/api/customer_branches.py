"""Customer branches (HD Customer Branch): the content pages' pickers and the customer
page's Branches tab."""

import json

import frappe
from frappe import _

BRANCH = "HD Customer Branch"
# what the Branches tab may set; the customer and name are fixed once created
BRANCH_FIELDS = ("enabled", "project")


@frappe.whitelist()
def get_branches() -> list[dict]:
    """Every customer branch, for the calendar's filters and the post dialogs."""
    frappe.has_permission("HD Content Post", "read", throw=True)
    return frappe.get_all(
        BRANCH,
        fields=["name", "customer", "branch_name", "enabled"],
        order_by="customer asc, branch_name asc",
    )


@frappe.whitelist()
def get_customer_branches(customer: str) -> dict:
    """The customer's branches with their project and approvers (Branches tab)."""
    frappe.has_permission("HD Customer", "read", customer, throw=True)
    branches = []
    for name in frappe.get_all(
        BRANCH,
        filters={"customer": customer},
        pluck="name",
        order_by="branch_name asc",
    ):
        doc = frappe.get_doc(BRANCH, name)
        branches.append(
            {
                "name": doc.name,
                "branch_name": doc.branch_name,
                "enabled": doc.enabled,
                "project": doc.project,
                "project_name": doc.project
                and frappe.db.get_value("Project", doc.project, "project_name"),
                "approvers": [row.email for row in doc.approvers],
                "has_plan": bool(
                    frappe.db.exists("HD Content Package", {"branch": doc.name})
                ),
            }
        )
    return {
        "branches": branches,
        "can_edit": bool(frappe.has_permission(BRANCH, "write")),
    }


@frappe.whitelist(methods=["POST"])
def save_branch(customer: str, values: str | dict, name: str | None = None) -> str:
    """Add a branch to the customer, or update it when `name` is given."""
    values = json.loads(values) if isinstance(values, str) else values
    if name:
        doc = frappe.get_doc(BRANCH, name)
        doc.check_permission("write")
        if doc.customer != customer:
            frappe.throw(_("{0} isn't a branch of {1}.").format(name, customer))
    else:
        frappe.has_permission(BRANCH, "create", throw=True)
        doc = frappe.new_doc(BRANCH)
        doc.customer = customer
        doc.branch_name = values.get("branch_name")
    doc.update({field: values.get(field) for field in BRANCH_FIELDS if field in values})
    if "approvers" in values:
        doc.set(
            "approvers",
            [{"email": email} for email in values.get("approvers") or [] if email],
        )
    doc.save()
    return doc.name
