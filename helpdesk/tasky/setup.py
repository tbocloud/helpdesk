"""Helpdesk's additions to ERPNext's Task, Project, Project User, Timesheet and Employee.

Helpdesk used to ship its own copies of these doctypes (and Timesheet Detail). Two apps
can't define the same doctype, so on migrate those copies replaced ERPNext's:
the forms lost most of their fields and ERPNext's controllers stopped running.
Helpdesk now extends ERPNext's doctypes instead, with custom fields, property
setters and role permissions, and runs its Task logic from doc_events.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.permissions import add_permission, update_permission_property

PTYPES = (
    "read",
    "write",
    "create",
    "delete",
    "email",
    "print",
    "report",
    "export",
    "share",
    "submit",
    "cancel",
    "amend",
)
FULL_ACCESS = set(PTYPES) - {"submit", "cancel", "amend"}
SUBMIT_ACCESS = set(PTYPES)
# the access helpdesk's own Task / Project doctypes used to grant, per doctype
ROLE_ACCESS = {
    "Task": {
        "System Manager": FULL_ACCESS,
        "Agent Manager": FULL_ACCESS,
        "Project Manager": FULL_ACCESS,
        "Agent": {"read", "write", "create", "print", "report"},
    },
    "Project": {
        "System Manager": FULL_ACCESS,
        "Agent Manager": FULL_ACCESS,
        "Project Manager": FULL_ACCESS,
        # agents see projects; creating and editing is for project managers
        "Agent": {"read", "print", "report"},
    },
    # Tasky logs time against the user's Employee record when a task is completed
    "Timesheet": {
        "System Manager": SUBMIT_ACCESS,
        "Agent Manager": SUBMIT_ACCESS,
        "Project Manager": {"read", "write", "create", "print", "report", "submit"},
        "Agent": {"read", "write", "create", "print", "report", "submit"},
    },
    "Employee": {
        "System Manager": FULL_ACCESS,
        "Agent Manager": FULL_ACCESS,
        "Project Manager": {"read", "report"},
        "Agent": {"read", "report"},
    },
}
PROPERTY_SETTERS = (
    # (doctype, fieldname, property, value, property_type)
    ("Project", "status", "options", "Open\nOn hold\nCompleted\nCancelled", "Text"),
    ("Task", "status", "default", "Open", "Text"),
    (
        "Task",
        "status",
        "options",
        "Open\nWorking\nPending Review\nOn Hold\nOverdue\nTemplate\nCompleted\nCancelled",
        "Text",
    ),
    ("Task", "priority", "default", "Medium", "Text"),
    # the members table decides who sees a project, so don't hide it in a collapsed section
    ("Project", "users_section", "collapsible", "0", "Check"),
)


# ERPNext's Project Type links to records; these are the types the AI estimates know
PROJECT_TYPES = (
    "ERP Implementation",
    "Mobile App",
    "Website",
    "Content Calendar",
    "Support",
    "Other",
)


def erpnext_installed() -> bool:
    return "erpnext" in frappe.get_installed_apps()


def get_project_custom_fields() -> dict:
    return {
        "Task": [
            {
                "fieldname": "is_key",
                "fieldtype": "Check",
                "label": "Key Task",
                "insert_after": "priority",
                "in_list_view": 1,
                "in_standard_filter": 1,
                "description": "Important for the project: gets earlier reminders and shows on the PM overview.",
            },
            {
                "fieldname": "hd_ticket",
                "fieldtype": "Link",
                "label": "Support Ticket",
                "options": "HD Ticket",
                "insert_after": "project",
                "search_index": 1,
                "description": "Ticket this task was created from; completing the task reopens it.",
            },
            {
                "fieldname": "content_post",
                "fieldtype": "Link",
                "label": "Content Post",
                "options": "HD Content Post",
                "insert_after": "hd_ticket",
                "search_index": 1,
                "read_only": 1,
                "description": "Created when someone was assigned to this post.",
            },
            {
                "fieldname": "content_role",
                "fieldtype": "Select",
                "label": "Content Role",
                "options": "\nwriter\ndesigner\nmarketer",
                "insert_after": "content_post",
                "read_only": 1,
                "depends_on": "content_post",
            },
            {
                "fieldname": "is_milestone",
                "fieldtype": "Check",
                "label": "Milestone",
                "insert_after": "is_key",
                "in_standard_filter": 1,
                "description": "A checkpoint for the customer (e.g. go-live). Slips are escalated like key tasks.",
            },
            {
                # one task to wait on; ERPNext's own depends_on table is for templates and Gantt
                "fieldname": "depends_on_task",
                "fieldtype": "Link",
                "label": "Waits On",
                "options": "Task",
                "insert_after": "content_role",
                "search_index": 1,
                "description": "This task can't start or be completed until that task is done.",
            },
            {
                "fieldname": "hold_section",
                "fieldtype": "Section Break",
                "label": "On Hold",
                "insert_after": "depends_on_task",
                "collapsible": 1,
                "depends_on": "eval:doc.status=='On Hold' || doc.hold_days_total",
            },
            {
                "fieldname": "hold_reason",
                "fieldtype": "Select",
                "label": "Hold Reason",
                "options": "\nLaptop / system issue\nLeave\nWaiting on customer\nWaiting on another task\nOther",
                "insert_after": "hold_section",
                "depends_on": "eval:doc.status=='On Hold'",
                "mandatory_depends_on": "eval:doc.status=='On Hold'",
            },
            {
                "fieldname": "hold_note",
                "fieldtype": "Small Text",
                "label": "Hold Note",
                "insert_after": "hold_reason",
                "depends_on": "eval:doc.status=='On Hold'",
            },
            {
                "fieldname": "column_break_hold",
                "fieldtype": "Column Break",
                "insert_after": "hold_note",
            },
            {
                "fieldname": "hold_since",
                "fieldtype": "Date",
                "label": "On Hold Since",
                "insert_after": "column_break_hold",
                "read_only": 1,
                "depends_on": "eval:doc.status=='On Hold'",
            },
            {
                "fieldname": "hold_days_total",
                "fieldtype": "Int",
                "label": "Days On Hold",
                "insert_after": "hold_since",
                "read_only": 1,
                "default": "0",
                "description": "All days this task has spent on hold. They're added to the due date on resume.",
            },
            {
                "fieldname": "hold_previous_status",
                "fieldtype": "Data",
                "label": "Status Before Hold",
                "insert_after": "hold_days_total",
                "hidden": 1,
                "read_only": 1,
            },
            {
                "fieldname": "slip_count",
                "fieldtype": "Int",
                "label": "Times Rescheduled",
                "insert_after": "exp_end_date",
                "read_only": 1,
                "default": "0",
                "description": "How often the due date was moved later (holds don't count).",
            },
            {
                "fieldname": "ai_estimated",
                "fieldtype": "Check",
                "label": "Due Date Set by AI",
                "insert_after": "slip_count",
                "read_only": 1,
                "default": "0",
            },
            {
                "fieldname": "estimate_note",
                "fieldtype": "Small Text",
                "label": "Estimate Note",
                "insert_after": "ai_estimated",
                "read_only": 1,
                "depends_on": "ai_estimated",
            },
        ],
        "Project": [
            {
                "fieldname": "project_lead",
                "fieldtype": "Link",
                "label": "Project Lead",
                "options": "User",
                "insert_after": "status",
                "in_list_view": 1,
                "in_standard_filter": 1,
                "search_index": 1,
                "description": "Can create and assign tasks in this project. Rotate it among the project's developers.",
            },
            {
                # ERPNext's own `customer` links to Customer; helpdesk works with HD Customer
                "fieldname": "hd_customer",
                "fieldtype": "Link",
                "label": "Helpdesk Customer",
                "options": "HD Customer",
                "insert_after": "customer",
                "in_standard_filter": 1,
                "search_index": 1,
            },
            {
                "fieldname": "review_before_done",
                "fieldtype": "Check",
                "label": "Review Before Done",
                "insert_after": "project_lead",
                "default": "0",
                "description": "When a team member completes a task, it goes to the project lead for review first.",
            },
        ],
        "Project User": [
            {
                "fieldname": "custom_role",
                "fieldtype": "Select",
                "label": "Role",
                "options": "Project Manager\nFunctional Consultant\nDeveloper\nSupport Engineer",
                "insert_after": "user",
                # shown as a column, so members' roles are set right in the table
                "in_list_view": 1,
                "columns": 2,
            },
        ],
    }


def setup_erpnext_projects():
    """Idempotent: safe on install, on every migrate and from patches."""
    if not erpnext_installed():
        return
    create_custom_fields(get_project_custom_fields(), update=True)
    for doctype, fieldname, prop, value, prop_type in PROPERTY_SETTERS:
        make_property_setter(
            doctype,
            fieldname,
            prop,
            value,
            prop_type,
            validate_fields_for_doctype=False,
        )
    add_role_permissions()
    add_project_types()


def add_project_types():
    for project_type in PROJECT_TYPES:
        if not frappe.db.exists("Project Type", project_type):
            frappe.get_doc(
                {"doctype": "Project Type", "project_type": project_type}
            ).insert(ignore_permissions=True)


def add_role_permissions():
    for doctype, roles in ROLE_ACCESS.items():
        for role, rights in roles.items():
            if not frappe.db.exists("Role", role):
                continue
            if not frappe.db.exists(
                "Custom DocPerm",
                {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
            ):
                # also copies the doctype's standard permissions, which a Custom DocPerm replaces
                add_permission(doctype, role, 0)
            for ptype in PTYPES:
                update_permission_property(
                    doctype, role, 0, ptype, int(ptype in rights), validate=False
                )


def backfill_hd_customer():
    """Link existing projects to the HD Customer matching their ERPNext customer."""
    Project = frappe.qb.DocType("Project")
    projects = (
        frappe.qb.from_(Project)
        .select(Project.name, Project.customer)
        .where(Project.customer.isnotnull() & (Project.customer != ""))
        .where(Project.hd_customer.isnull() | (Project.hd_customer == ""))
        .run(as_dict=True)
    )
    for project in projects:
        hd_customer = frappe.db.exists(
            "HD Customer", project.customer
        ) or frappe.db.get_value(
            "HD Customer", {"erpnext_customer": project.customer}, "name"
        )
        if hd_customer:
            frappe.db.set_value(
                "Project",
                project.name,
                "hd_customer",
                hd_customer,
                update_modified=False,
            )


def erpnext_customer_for(hd_customer: str | None) -> str | None:
    """The ERPNext Customer to put in Project.customer for an HD Customer, if there is one."""
    if not hd_customer or not erpnext_installed():
        return None
    linked = frappe.db.get_value("HD Customer", hd_customer, "erpnext_customer")
    for candidate in (linked, hd_customer):
        if candidate and frappe.db.exists("Customer", candidate):
            return candidate
    return None
