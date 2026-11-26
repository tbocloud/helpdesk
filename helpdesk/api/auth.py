import frappe

from helpdesk import chatwoot_sso
from helpdesk.adoption import can_see_adoption
from helpdesk.api.work import can_see_overview
from helpdesk.content_team import (
    can_edit_content,
    can_work_tickets,
    in_content_team,
    in_sales,
    is_content_only,
    is_dm_employee,
    is_dm_head,
    is_erp_only,
    is_sales_bd_role,
    is_sales_employee,
    manages_sales,
)
from helpdesk.divisions import (
    division_info,
    division_without_site,
    leads_closed_by_site,
)
from helpdesk.helpdesk.doctype.hd_customer.hd_customer import can_set_ticket_owner
from helpdesk.integrations.crm.leads import can_use_lead_bank, can_use_leads
from helpdesk.sales_targets import (
    can_assign_targets,
    has_own_targets,
    hides_todays_calls,
)
from helpdesk.tasky.permissions import is_project_manager as tasky_is_project_manager
from helpdesk.utils import agent_only, get_agent_name, get_agents_team
from helpdesk.utils import is_agent as _is_agent
from helpdesk.weekly_lead_report import report_division


@frappe.whitelist()
def get_user():
    current_user = frappe.session.user
    filters = {"name": current_user}
    fields = [
        "first_name",
        "full_name",
        "name",
        "user_image",
        "username",
        "time_zone",
        "language",
        "hd_new_ticket_sound",
    ]
    user = frappe.get_value(
        doctype="User",
        filters=filters,
        fieldname=fields,
        as_dict=True,
    )

    roles = frappe.get_roles(current_user)
    is_admin = "System Manager" in roles or "Administrator" in roles

    is_agent = _is_agent()
    agent_name = get_agent_name()
    has_agent_record = bool(agent_name)
    has_desk_access = is_agent or is_admin
    availability = (
        frappe.db.get_value(
            "HD Agent",
            agent_name,
            ["availability", "availability_changed_on"],
            as_dict=True,
        )
        if agent_name
        else None
    ) or {}
    user_image = user.user_image
    user_first_name = user.first_name
    user_name = user.full_name
    user_id = user.name
    username = user.username
    is_manager = ("Agent Manager") in frappe.get_roles(current_user)
    is_project_manager = tasky_is_project_manager(current_user)
    language = user.language or frappe.db.get_single_value(
        "System Settings", "language"
    )
    user_team = get_agents_team()
    user_team_names = [team["team_name"] for team in user_team]
    # Ride the boot so the onboarding guard decides without an extra round-trip.
    persona_captured = bool(
        frappe.db.get_single_value("HD Settings", "persona_captured")
    )

    return {
        "has_desk_access": has_desk_access,
        "is_admin": is_admin,
        "is_agent": is_agent,
        "has_agent_record": has_agent_record,
        "user_id": user_id,
        "is_manager": is_manager,
        "is_project_manager": is_project_manager,
        "can_set_ticket_owner": can_set_ticket_owner(current_user),
        "can_see_overview": can_see_overview(current_user)
        and not is_content_only(current_user),
        "can_see_adoption": can_see_adoption(current_user),
        "is_content_team": is_content_only(current_user),
        "is_dm_head": is_dm_head(current_user),
        "can_edit_content": can_edit_content(current_user),
        # the only people who see the content calendar and content performance
        "in_content_team": in_content_team(current_user),
        # ERP Employees: no work Calendar either (and no Digital department, server side)
        "is_erp_only": is_erp_only(current_user),
        # DM Employees: no tickets, customers, contacts, templates, KB or reports
        "is_dm_employee": is_dm_employee(current_user),
        # Sales Employees: the sales screens only (Leads, Scoreboard), docs/departments.md
        "is_sales_employee": is_sales_employee(current_user),
        # a Sales Employee who is no manager: Leads shows them their own calls and leads only
        # (a department head is told apart by the Leads options, from the ERP site)
        "is_sales_bd": is_sales_bd_role(current_user),
        # Sales → Dashboard is a salesperson's own day: not for Sales Heads or Sales Managers
        "has_own_sales_dashboard": not manages_sales(current_user),
        # the Sales area of the sidebar: only the people in sales
        "in_sales": in_sales(current_user),
        # the Tickets list and New ticket: System / Agent Managers and the ERP team
        "can_work_tickets": can_work_tickets(current_user),
        # the Leads page, live from the CRM site (docs/leads.md)
        "can_use_leads": can_use_leads(current_user)
        and not division_without_site(current_user)
        and not leads_closed_by_site(current_user),
        # Add a lead and My leads: every active agent while Leads is on (docs/lead-bank.md)
        "can_use_lead_bank": can_use_lead_bank(current_user),
        # Sales targets: Sales Heads set each month's targets (docs/sales-targets.md)
        "can_assign_sales_targets": can_assign_targets(current_user),
        # Sales targets (their own): Presales Executives and Sales Users read theirs
        "has_sales_targets": has_own_targets(current_user),
        # Sales → Lead report, in a division that keeps it (docs/weekly-lead-report.md)
        "has_weekly_lead_report": bool(report_division(current_user)),
        # Presales Executives don't get Today's calls: no sidebar item, no pill on Leads
        "hide_todays_calls": hides_todays_calls(current_user),
        # lets the frontend skip call-integration checks when telephony isn't installed
        "telephony_installed": "telephony" in frappe.get_installed_apps(),
        "user_image": user_image,
        "user_first_name": user_first_name,
        "user_name": user_name,
        "username": username,
        "time_zone": user.time_zone,
        "language": language,
        # chime with a new ticket's notice (Settings → Preferences, default off)
        "new_ticket_sound": bool(user.hd_new_ticket_sound),
        "user_teams": user_team_names,
        # divisions, the active one and what the person may do with them (docs/divisions.md)
        **division_info(current_user),
        "availability": availability.get("availability"),
        "availability_changed_on": availability.get("availability_changed_on"),
        "persona_captured": persona_captured,
        # Open TBO Chat in the profile menu (helpdesk.api.chatwoot_sso.login)
        "can_open_chat": bool(
            frappe.db.get_single_value("HD Chatwoot Settings", "sso_enabled")
        )
        and chatwoot_sso.is_active_agent(current_user),
    }


@frappe.whitelist()
@agent_only
def get_current_user_email_info():
    user = frappe.session.user

    email_signature, email = frappe.db.get_value(
        "User", user, ["email_signature", "email"]
    )
    user_emails = frappe.db.get_all(
        "User Email",
        filters={"parent": user},
        fields=["email_account", "email_id"],
    )
    outgoing_account_names = frappe.db.get_all(
        "Email Account",
        filters={"enable_outgoing": 1},
        pluck="name",
    )

    outgoing_emails = [
        row for row in user_emails if row.email_account in outgoing_account_names
    ]

    available_emails = frappe.db.get_all(
        "Email Account",
        filters={"enable_outgoing": 1},
        fields=["name", "email_id"],
    )

    return {
        "email_signature": email_signature,
        "email": email,
        "outgoing_emails": outgoing_emails,
        "available_emails": available_emails,
    }
