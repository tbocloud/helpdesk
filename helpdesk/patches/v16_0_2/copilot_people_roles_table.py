import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from helpdesk.copilot import people
from helpdesk.setup.install import get_custom_fields


def execute():
    """Phase 23: every person Copilot goes to moves into one table, HDS Copilot Settings → People
    and each customer's Copilot People, with main and fallback people. Once, and only where the
    new table is still empty:
    - the settings' Phase 22 tables become rows (Approvers with Senior ticked are Senior and Fix
      Approver; Infrastructure People with Senior ticked are Infrastructure Senior);
    - each customer's first and second developer become Developer rows only when they differ from
      its ticket owners (an empty Developer follows the owners); its fix approver and project
      coordinators become rows;
    - a customer with no project coordinator anywhere gets its open projects' Project
      Coordinators, so they keep writing in the ticket chat (the owner's decision 3).
    The old fields stay, hidden, for one version. The custom fields are made first: patches run
    before after_migrate adds them."""
    create_custom_fields({"HD Customer": get_custom_fields()["HD Customer"]})
    frappe.reload_doc("helpdesk", "doctype", "hds_copilot_role_person")
    _settings()
    _customers()


def _settings():
    settings = frappe.get_single(people.SETTINGS)
    if settings.get(people.TABLE):
        return
    old = {
        field: [
            {"user": row.user, "active": row.active, "senior": row.get("senior")}
            for row in settings.get(field) or []
        ]
        for field in (
            "approvers",
            "project_coordinators",
            "risk_alert_people",
            "deploy_notice_people",
            "infrastructure_people",
        )
    }
    _insert(
        people.SETTINGS,
        people.SETTINGS,
        people.TABLE,
        people.rows_from_old_settings(old),
    )
    frappe.clear_document_cache(people.SETTINGS, people.SETTINGS)


def _customers():
    from helpdesk.ticket_assignment import coordinators as project_coordinators

    common_coordinators = bool(
        frappe.get_all(
            people.ROLE_PERSON,
            filters={
                "parenttype": people.SETTINGS,
                "parentfield": people.TABLE,
                "role": people.COORDINATOR,
            },
            limit=1,
        )
    )
    for row in frappe.get_all(
        people.CUSTOMER,
        fields=[
            "name",
            "ticket_owner",
            "backup_ticket_owner",
            "custom_assigned_developer",
            "custom_first_developer",
            "custom_second_developer",
            "custom_fix_approver",
        ],
    ):
        if frappe.db.exists(
            people.ROLE_PERSON,
            {
                "parenttype": people.CUSTOMER,
                "parentfield": people.CUSTOMER_TABLE,
                "parent": row.name,
            },
        ):
            continue
        row.coordinators = frappe.get_all(
            "HDS Copilot Person",
            filters={
                "parenttype": people.CUSTOMER,
                "parentfield": "custom_copilot_coordinators",
                "parent": row.name,
                "active": 1,
            },
            pluck="user",
            order_by="idx asc",
        )
        if not row.coordinators and not common_coordinators:
            row.coordinators = project_coordinators(row.name)
        _insert(
            people.CUSTOMER,
            row.name,
            people.CUSTOMER_TABLE,
            people.rows_from_old_customer(row),
        )


def _insert(parenttype: str, parent: str, parentfield: str, rows: list[dict]):
    """The rows straight into the table: saving the settings or a customer here would run their
    own checks and hooks, which a half-set site may not pass."""
    for idx, row in enumerate(_unique(rows), start=1):
        child = frappe.new_doc(people.ROLE_PERSON)
        child.update(
            {
                **row,
                "parent": parent,
                "parenttype": parenttype,
                "parentfield": parentfield,
                "idx": idx,
                "full_name": frappe.db.get_value("User", row["person"], "full_name"),
            }
        )
        child.db_insert()


def _unique(rows: list[dict]) -> list[dict]:
    """One row per role, person and level, people whose account exists."""
    seen, found = set(), []
    for row in rows:
        key = (row["role"], row["person"], row["level"])
        if key in seen or not frappe.db.exists("User", row["person"]):
            continue
        seen.add(key)
        found.append(row)
    return found
