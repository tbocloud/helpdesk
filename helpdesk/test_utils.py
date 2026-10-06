import gzip
import json
from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.core.doctype.communication.test_communication import create_email_account
from frappe.utils import add_to_date, getdate

from helpdesk.api.settings.field_dependency import create_update_field_dependency
from helpdesk.integrations.erpnext.utils import create_customer_field
from helpdesk.utils import get_customers, is_frappe_version

if is_frappe_version("16", above=True):
    from frappe.tests.utils import make_test_objects
else:
    from frappe.test_runner import make_test_objects


SLA_PRIORITY_NAME = "SLA Priority"
TEST_HOLIDAY_LIST_NAME = "Test Holiday List"


def before_tests():
    frappe.db.set_single_value("HD Settings", "skip_email_workflow", 0)  # nosemgrep
    frappe.db.set_single_value(
        "HD Settings", "enable_email_ticket_feedback", 0
    )  # nosemgrep
    frappe.db.set_single_value("HD Settings", "default_priority", None)
    # frappe.flags.mute_emails = True
    make_holiday_list()
    make_new_sla()
    make_test_objects("Email Domain", reset=True)
    create_email_account()
    create_customer_field()
    complete_erpnext_setup()
    frappe.db.commit()  # nosemgrep


def make_new_sla():
    condition = "doc.priority in ['High', 'Urgent', 'Low']"
    sla_doc = make_sla(SLA_PRIORITY_NAME, condition)
    sla_doc = sla_doc.reload()
    sla_doc.holiday_list = TEST_HOLIDAY_LIST_NAME

    sla_doc.support_and_resolution = []
    for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
        service_day = frappe.get_doc(
            {
                "doctype": "HD Service Day",
                "workday": day,
                "start_time": "10:00:00",
                "end_time": "18:00:00",
            }
        )
        sla_doc.append("support_and_resolution", service_day)

    low_priority = frappe.get_doc(
        {
            "doctype": "HD Service Level Priority",
            "default_priority": 0,
            "priority": "Low",
            "response_time": 60 * 60 * 24,
            "resolution_time": 60 * 60 * 72,
        }
    )

    medium_priority = frappe.get_doc(
        {
            "doctype": "HD Service Level Priority",
            "default_priority": 1,
            "priority": "Medium",
            "response_time": 60 * 60 * 8,
            "resolution_time": 60 * 60 * 24,
        }
    )

    high_priority = frappe.get_doc(
        {
            "doctype": "HD Service Level Priority",
            "default_priority": 0,
            "priority": "High",
            "response_time": 60 * 60 * 1,
            "resolution_time": 60 * 60 * 4,
        }
    )

    urgent_priority = frappe.get_doc(
        {
            "doctype": "HD Service Level Priority",
            "default_priority": 0,
            "priority": "Urgent",
            "response_time": 60 * 30,
            "resolution_time": 60 * 60 * 2,
        }
    )
    sla_doc.priorities = []
    sla_doc.append("priorities", low_priority)
    sla_doc.append("priorities", medium_priority)
    sla_doc.append("priorities", high_priority)
    sla_doc.append("priorities", urgent_priority)

    sla_doc.save()


def make_holiday_list():
    if not frappe.db.exists("HD Service Holiday List", TEST_HOLIDAY_LIST_NAME):
        # from_date = first date of current year
        from_date = datetime(datetime.today().year, 1, 1).date()
        to_date = datetime(datetime.today().year + 1, 1, 15).date()
        frappe.get_doc(
            {
                "doctype": "HD Service Holiday List",
                "holiday_list_name": TEST_HOLIDAY_LIST_NAME,
                "from_date": from_date,
                "to_date": to_date,
            }
        ).insert()


def make_sla(sla_name: str = "Test SLA", condition: str = ""):
    def_sla = frappe.get_doc("HD Service Level Agreement", "Default")
    sla_doc = frappe.copy_doc(def_sla)
    sla_doc.service_level = sla_name
    sla_doc.condition = condition
    sla_doc.default_sla = 0
    sla_doc.insert(ignore_if_duplicate=True, ignore_permissions=True)
    return sla_doc


def make_ticket(
    subject: str = "Test Ticket",
    description: str = "This is a test ticket.",
    save: bool = True,
    **args,
):
    """
    Creates a test HD Ticket with the given subject, description, priority, and ticket type.
    """
    ticket = frappe.get_doc(
        {"doctype": "HD Ticket", "subject": subject, "description": description, **args}
    )
    if save:
        ticket.insert(ignore_if_duplicate=True, ignore_permissions=True)
    return ticket


def create_agent(
    email: str, first_name: str | None = None, last_name: str | None = None
):
    """
    Creates a test agent user with the Agent role.
    """
    if not frappe.db.exists("User", email):
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": first_name or email.split("@")[0],
                "last_name": last_name or "Agent",
                "send_welcome_email": 0,
            }
        )
        user.insert(ignore_permissions=True)
    else:
        user = frappe.get_doc("User", email)

    if "Agent" not in frappe.get_roles(email):
        user.add_roles("Agent")

    agent_name = f"{user.first_name} {user.last_name or ''}".strip()
    existing_agent = frappe.db.exists("HD Agent", {"user": email})
    if not existing_agent:
        frappe.get_doc(
            {
                "doctype": "HD Agent",
                "user": email,
                "agent_name": agent_name or email,
                "is_active": 1,
            }
        ).insert(ignore_permissions=True)

    return user


def get_current_week_monday(hours: int = 11):
    """
    Returns the current week's Monday date
    """

    current_date = getdate()
    # Get the current week's Monday
    monday = add_to_date(current_date, days=-current_date.weekday(), hours=hours)
    return monday


def get_priority_response_resolution_time(
    sla: str, priority: str, date=None, add_to_time: bool = True
):
    """
    Returns the expected response or resolution time for a given priority.
    """
    sla = frappe.get_doc("HD Service Level Agreement", sla)
    priorities = sla.get_priorities()
    high_priority = priorities[priority]
    first_response = high_priority.response_time
    resolution_time = high_priority.resolution_time
    if not add_to_time:
        return first_response, resolution_time

    date = date or get_current_week_monday()
    expected_response_by = add_to_date(date, seconds=first_response)

    expected_resolution_by = add_to_date(date, seconds=resolution_time)
    return expected_response_by, expected_resolution_by


def add_holiday(holiday_date, description="_Test Holiday"):
    """
    Adds a holiday to the system.
    """

    holiday_list_doc = frappe.get_doc("HD Service Holiday List", "Test Holiday List")
    holiday_list_doc.append(
        "holidays",
        {
            "holiday_date": holiday_date,
            "description": description,
        },
    )
    holiday_list_doc.save()


def remove_holidays():
    """
    Removes a holiday from the system.
    """
    holiday_list = frappe.get_doc("HD Service Holiday List", TEST_HOLIDAY_LIST_NAME)
    holiday_list.holidays = []
    holiday_list.save()


def create_field_dependency():
    parent_field = "ticket_type"
    child_field = "priority"
    mapping = '{"Unspecified":["Urgent","High"],"Question":["Medium","High"],"Bug":["Medium"],"Incident":["Urgent","High","Medium","Low"]}'
    enabled = 1
    fields_criteria = '{"display":{"enabled":true,"value":[{"label":"Any","value":"Any"}]},"mandatory":{"enabled":true,"value":[{"label":"Question","value":"Question"},{"label":"Bug","value":"Bug"}]}}'

    create_update_field_dependency(
        parent_field, child_field, mapping, enabled, fields_criteria
    )


def make_status(name: str = "Test Status", category: str = "Open"):
    if frappe.db.exists("HD Ticket Status", name):
        return frappe.get_doc("HD Ticket Status", name)

    doc = frappe.get_doc(
        {
            "doctype": "HD Ticket Status",
            "label_agent": name,
            "category": category,
            "is_default": 0,
        }
    )
    return doc.insert(ignore_if_duplicate=True)


def make_agent_status(agent_status: str, category="Away", enable=1, status_order=None):
    return frappe.get_doc(
        {
            "doctype": "HD Agent Status",
            "agent_status": agent_status,
            "category": category,
            "enable": enable,
            "status_order": status_order,
        }
    ).insert()


def make_agent(email: str, first_name: str = "Test Agent"):
    """
    Creates a test user and HD Agent if they don't exist.
    Returns the user email.
    """
    if not frappe.db.exists("User", email):
        frappe.get_doc(
            {"doctype": "User", "first_name": first_name, "email": email}
        ).insert(ignore_permissions=True)

    if not frappe.db.exists("HD Agent", {"user": email}):
        frappe.get_doc(
            {"doctype": "HD Agent", "user": email, "agent_name": first_name}
        ).insert(ignore_permissions=True)

    return email


def get_latest_ticket_communication(ticket_name: str):
    """
    Returns the latest Communication doc linked to the given HD Ticket.
    """
    name = frappe.get_all(
        "Communication",
        filters={
            "reference_doctype": "HD Ticket",
            "reference_name": ticket_name,
        },
        pluck="name",
        limit=1,
    )
    if not name:
        return None
    return frappe.get_doc("Communication", name[0])


def add_comment(
    ticket: str,
    content: str = "This is a test comment.",
    comment_by: str | None = None,
    save: bool = True,
):
    """
    Creates a test HD Ticket Comment for a given ticket.
    """
    comment = frappe.get_doc(
        {
            "doctype": "HD Ticket Comment",
            "reference_ticket": ticket,
            "content": content,
            "comment_by": comment_by,
        }
    )
    if save:
        return comment.insert()
    return comment


def set_ticket_status_and_communication_date(ticket_name, status, communication_date):
    """Force a ticket's status and the date of all its communications directly in the
    database, bypassing controller side effects. Useful for testing scheduled jobs that
    key off communication_date (auto close, SLA escalation, reminders)."""
    frappe.db.set_value(
        "HD Ticket", ticket_name, "status", status, update_modified=False
    )
    for comm_name in frappe.get_all(
        "Communication",
        filters={"reference_doctype": "HD Ticket", "reference_name": ticket_name},
        pluck="name",
    ):
        frappe.db.set_value(
            "Communication",
            comm_name,
            "communication_date",
            communication_date,
            update_modified=False,
        )


def create_contact(name, email, user=True, role="HD Customer"):
    result = {}

    # Delete any existing contacts with this email so we always start clean
    existing = frappe.db.get_all("Contact", filters={"email_id": email}, pluck="name")
    for c in existing:
        frappe.delete_doc("Contact", c, force=True)

    contact = frappe.get_doc(
        {
            "doctype": "Contact",
            "first_name": name,
            # top-level email_id is what set_contact() queries via
            # frappe.db.get_value("Contact", {"email_id": email_id})
            "email_id": email,
        }
    )
    contact.append("email_ids", {"email_id": email, "is_primary": 1})
    contact.insert()

    result["contact"] = contact.name
    if not user:
        return result

    if frappe.db.exists("User", email):
        # User may have linked docs (tickets) — just strip roles and reuse
        _user = frappe.get_doc("User", email)
        _user.roles = []
        _user.save(ignore_permissions=True)
    else:
        _user = frappe.get_doc({"doctype": "User", "first_name": name, "email": email})
        _user.insert(ignore_permissions=True)

    _user.add_roles(role)

    # link the user to the contact so get_customers(user=email) resolves correctly
    frappe.db.set_value("Contact", contact.name, "user", _user.name)

    result["user"] = _user.name
    return result


def create_customer(name, contacts=[]):
    if frappe.db.exists("HD Customer", name):
        frappe.delete_doc("HD Customer", name, force=True)

    customer = frappe.get_doc({"doctype": "HD Customer", "customer_name": name})

    for c in contacts:
        customer.append("contacts", c)
    return customer.insert()


def create_user(email: str):
    """Create (or fetch) a plain User with no helpdesk roles."""
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    return frappe.get_doc(
        doctype="User",
        email=email,
        first_name=email.split("@")[0],
        send_welcome_email=0,
    ).insert(ignore_permissions=True)


def get_invitation(email: str):
    """Return the helpdesk User Invitation raised for an email, if any."""
    return frappe.db.get_value(
        "User Invitation",
        {"email": email, "app_name": "helpdesk"},
        ["name", "customer", "contact"],
        as_dict=True,
    )


def update_role_in_customer(customer, contact, role="HD Customer", is_primary=False):
    frappe.set_user("Administrator")
    is_manager = True if role == "HD Customer Manager" else False

    for c in customer.get("contacts", []):
        if c.get("contact_name") != contact:
            continue
        c.is_manager = is_manager

    if is_primary:
        customer.primary_contact = contact

    customer.save()


def add_contact_in_customer(customer, contact, is_manager=False, is_primary=False):
    frappe.set_user("Administrator")
    customer.append(
        "contacts",
        {"contact_name": contact, "is_manager": is_manager},
    )
    if is_primary:
        customer.primary_contact = contact

    customer.save()


def cleanup_contact_users(contacts, customers=[]):
    frappe.set_user("Administrator")
    for contact in contacts:
        contact_name = contact.get("contact")
        user_email = contact.get("user")

        # remove from any customer
        linked_customers = get_customers(contact=contact_name)
        for customer in linked_customers:
            customer_doc = frappe.get_doc("HD Customer", customer)
            customer_doc.contacts = [
                c
                for c in customer_doc.contacts
                if c.get("contact_name") != contact_name
            ]
            customer_doc.save()

        if user_email and frappe.db.exists("User", user_email):
            frappe.delete_doc("User", user_email, force=True)

        existing = (
            frappe.db.get_all("Contact", filters={"email_id": user_email}, pluck="name")
            if user_email
            else []
        )
        for c in existing:
            frappe.delete_doc("Contact", c, force=True)

    for c in customers:
        if frappe.db.exists("HD Customer", c):
            frappe.delete_doc("HD Customer", c, force=True)
        if frappe.db.exists("HD Customer", c):
            frappe.delete_doc("HD Customer", c, force=True)
            frappe.delete_doc("HD Customer", c, force=True)
            frappe.delete_doc("HD Customer", c, force=True)
            frappe.delete_doc("HD Customer", c, force=True)
            frappe.delete_doc("HD Customer", c, force=True)


def make_team(team_name, members=[], disabled=False):
    """Create an HD Team with optional members. A default agent is created if no members are provided."""
    if not members:
        members = [make_agent("default_team_agent@example.com")]

    if frappe.db.exists("HD Team", team_name):
        team = frappe.get_doc("HD Team", team_name)
        team.disabled = disabled
        team.users = []
        for member in members:
            team.append("users", {"user": member})
        team.save(ignore_permissions=True)
        return team

    # Create new team - this will trigger after_insert which creates assignment rule
    team = frappe.get_doc(
        {
            "doctype": "HD Team",
            "team_name": team_name,
        }
    )
    for member in members:
        team.append("users", {"user": member})
    team.disabled = disabled
    team.insert(ignore_permissions=True)
    return team


def complete_erpnext_setup():
    """
    Run the ERPNext setup wizard once, so fixtures like Warehouse Type
    exist before test records (e.g. Company) are created.
    """
    if "erpnext" not in frappe.get_installed_apps():
        return
    if frappe.get_all("Company", limit=1):
        return

    from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

    year = datetime.today().year
    setup_complete(
        {
            "currency": "INR",
            "full_name": "Test User",
            "company_name": "_Test Company",
            "timezone": "Asia/Kolkata",
            "company_abbr": "_TC",
            "industry": "Manufacturing",
            "country": "India",
            "fy_start_date": f"{year}-01-01",
            "fy_end_date": f"{year}-12-31",
            "language": "english",
            "company_tagline": "Testing",
            "email": "test@erpnext.com",
            "password": "test",
            "chart_of_accounts": "Standard",
        }
    )


def upload_test_file(file_name: str) -> str:
    """Upload an image from desk/src/assets/images/ as a standalone private File, returning its name."""
    file_path = frappe.get_app_path(
        "helpdesk", "..", "desk", "src", "assets", "images", file_name
    )
    with open(file_path, "rb") as f:
        content = f.read()
    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "is_private": 1,
            "content": content,
        }
    ).insert(ignore_permissions=True)
    return file_doc.name


def make_tasky_user(email: str, full_name: str, roles: tuple[str, ...] = ()):
    """Creates an agent user for tasky tests, plus any extra roles (e.g. "Project Manager")."""
    first_name, _, last_name = full_name.partition(" ")
    create_agent(email, first_name, last_name or None)
    missing = [r for r in roles if r not in frappe.get_roles(email)]
    if missing:
        frappe.get_doc("User", email).add_roles(*missing)
    return email


def make_project(
    project_name: str,
    members: list[tuple[str, str]] | None = None,
    owner: str | None = None,
):
    """Creates a Project directly, bypassing the tasky API.

    `members` is a list of (user, project role) pairs; `owner` defaults to the session user.
    """
    doc = frappe.get_doc(
        {
            "doctype": "Project",
            "project_name": project_name,
            "status": "Open",
            "users": [{"user": u, "custom_role": role} for u, role in members or []],
        }
    )
    doc.insert(ignore_permissions=True)
    if owner:
        # insert always records the session user as owner
        doc.db_set("owner", owner, update_modified=False)
    return doc


def make_content_campaign(campaign_name: str, customer: str, **kwargs):
    """Creates an HD Content Campaign for `customer`."""
    return frappe.get_doc(
        {
            "doctype": "HD Content Campaign",
            "campaign_name": campaign_name,
            "customer": customer,
            **kwargs,
        }
    ).insert(ignore_permissions=True)


def hold_commits(test_case):
    """Rolls back everything a test wrote, even where Frappe commits mid-test.

    Assigning a task sends the assignee an email, and in tests that email is sent
    at once and commits; without this a post's tasks would leak into other tests.
    """
    test_case.addCleanup(frappe.db.rollback)
    commit = patch.object(frappe.db, "commit")
    commit.start()
    test_case.addCleanup(commit.stop)


def make_content_post(title: str, customer: str | None = None, **kwargs):
    """Creates an HD Content Post: an Instagram Idea a week out unless overridden.

    Every post needs a posting date; pass `publish_on` to choose it.
    """
    from frappe.utils import add_to_date, now_datetime

    return frappe.get_doc(
        {
            "doctype": "HD Content Post",
            "title": title,
            "customer": customer,
            "channel": "Instagram",
            "status": "Idea",
            "publish_on": add_to_date(now_datetime(), days=7),
            **kwargs,
        }
    ).insert(ignore_permissions=True)


def make_content_post_due(title: str, customer: str, days: int, **kwargs):
    """Creates a Drafting HD Content Post due at 10:00, `days` from today (negative: past)."""
    from frappe.utils import add_days, nowdate

    return make_content_post(
        title,
        customer,
        status="Drafting",
        publish_on=f"{add_days(nowdate(), days)} 10:00:00",
        **kwargs,
    )


def make_support_connection(
    customer: str, site_url: str = "https://erp.example.com", **kwargs
):
    """Creates a Connected HDS Support Connection for `customer` (no real credentials)."""
    return frappe.get_doc(
        {
            "doctype": "HDS Support Connection",
            "customer_name": customer,
            "site_url": site_url,
            "connection_status": "Connected",
            **kwargs,
        }
    ).insert(ignore_permissions=True)


def make_ticket_communication(
    ticket: str,
    content: str,
    sender: str = "customer@example.com",
    sent_or_received: str = "Received",
):
    """Creates an email Communication on an HD Ticket, as if received from (or sent to) the customer."""
    return frappe.get_doc(
        {
            "doctype": "Communication",
            "communication_type": "Communication",
            "communication_medium": "Email",
            "sent_or_received": sent_or_received,
            "subject": f"Re: {ticket}",
            "sender": sender,
            "content": content,
            "reference_doctype": "HD Ticket",
            "reference_name": ticket,
        }
    ).insert(ignore_permissions=True)


def make_ai_support_session(ticket: str, connection: str | None = None, **kwargs):
    """Creates an HDS AI Support Session for `ticket` (no investigation is run)."""
    return frappe.get_doc(
        {
            "doctype": "HDS AI Support Session",
            "ticket": ticket,
            "connection": connection,
            **kwargs,
        }
    ).insert(ignore_permissions=True)


def make_assignment(doctype: str, name: str, user: str):
    """Assigns a document to `user` the normal way (ToDo), which is what sets `_assign`."""
    from frappe.desk.form import assign_to

    assign_to._add(
        {"doctype": doctype, "name": str(name), "assign_to": [user]},
        ignore_permissions=True,
    )


def make_task(project: str, subject: str, exp_end_date=None, **kwargs):
    """Creates an open Task in `project` directly, bypassing the tasky API."""
    return frappe.get_doc(
        {
            "doctype": "Task",
            "subject": subject,
            "project": project,
            "status": "Open",
            "exp_end_date": exp_end_date,
            **kwargs,
        }
    ).insert(ignore_permissions=True)


def make_employee(user: str, employee_name: str | None = None):
    """Creates an active Employee linked to `user` (the hub doesn't need one per agent)."""
    return frappe.get_doc(
        {
            "doctype": "Employee",
            "employee_name": employee_name or user,
            "user_id": user,
            "status": "Active",
        }
    ).insert(ignore_permissions=True)


def get_task_timesheets(task: str) -> list[str]:
    """Names of the Timesheets that have a time log for `task`."""
    return frappe.get_all(
        "Timesheet Detail",
        filters={"parenttype": "Timesheet", "task": task},
        pluck="parent",
        distinct=True,
    )


def make_work_summary(customer: str, **kwargs):
    """Creates an HD Work Summary for `customer` for the last 7 days, without stats or AI."""
    from frappe.utils import add_days, nowdate

    return frappe.get_doc(
        {
            "doctype": "HD Work Summary",
            "customer": customer,
            "period_start": add_days(nowdate(), -6),
            "period_end": nowdate(),
            "summary": "<p>Test summary</p>",
            "stats": "{}",
            **kwargs,
        }
    ).insert(ignore_permissions=True)


def run_as_user(user: str, fn):
    """Calls `fn()` as `user`, then switches back to Administrator."""
    frappe.set_user(user)
    try:
        return fn()
    finally:
        frappe.set_user("Administrator")


def get_reminder_messages(user: str, reference_name) -> list[str]:
    """Messages of the Reminder HD Notifications sent to `user` about a document."""
    return frappe.get_all(
        "HD Notification",
        filters={
            "user_to": user,
            "notification_type": "Reminder",
            "reference_name": str(reference_name),
        },
        pluck="message",
    )


# shaped like Teams Workflows URLs, so HD Chat Settings accepts them
TEST_TEAMS_DIRECT_URL = (
    "https://prod-01.westeurope.logic.azure.com/workflows/direct/triggers/manual/"
    "paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=test-direct"
)
TEST_TEAMS_CHANNEL_URL = (
    "https://default0000.f5.environment.api.powerplatform.com/powerautomate/automations/"
    "direct/workflows/channel/triggers/manual/paths/invoke?api-version=1&sp=x&sv=1.0&sig=test-channel"
)


def enable_chat_notifications(platform: str = "Microsoft Teams", **settings):
    """Turns on HD Chat Settings for `platform` with dummy webhooks/token, plus any overrides."""
    doc = frappe.get_doc("HD Chat Settings")
    doc.update(
        {
            "enabled": 1,
            "platform": platform,
            "email_when_unreachable": 1,
            "slack_bot_token": "xoxb-test-token",
            "slack_escalation_channel": "",
            "teams_direct_webhook": TEST_TEAMS_DIRECT_URL,
            "teams_channel_webhook": "",
            **settings,
        }
    )
    doc.save(ignore_permissions=True)
    frappe.clear_document_cache("HD Chat Settings", "HD Chat Settings")
    frappe.cache.delete_keys("helpdesk:slack_user:")
    return doc


def make_error_log(title: str, at=None):
    """Creates an Error Log entry titled `title`, logged at `at` (default: now)."""
    doc = frappe.get_doc(
        {"doctype": "Error Log", "method": title, "error": "Traceback (test)"}
    ).insert(ignore_permissions=True)
    if at:
        frappe.db.set_value(
            "Error Log", doc.name, "creation", at, update_modified=False
        )
    return doc


def enable_teams_meetings(**values):
    """Turns on HD Meeting Settings with a dummy Microsoft Connected App (no real Graph call)."""
    app_name = "Test Microsoft Graph"
    if not frappe.db.exists("Connected App", {"provider_name": app_name}):
        frappe.get_doc(
            {
                "doctype": "Connected App",
                "provider_name": app_name,
                "client_id": "test-client-id",
                "client_secret": "test-client-secret",
                "token_uri": "https://login.example/tenant/oauth2/v2.0/token",
            }
        ).insert(ignore_permissions=True)
    app = frappe.db.get_value("Connected App", {"provider_name": app_name}, "name")
    doc = frappe.get_doc("HD Meeting Settings")
    doc.update(
        {
            "enabled": 1,
            "connected_app": app,
            "organizer": "The calendar of the person scheduling",
            "default_duration": 30,
            "reminder_minutes": 10,
            **values,
        }
    )
    doc.save(ignore_permissions=True)
    frappe.clear_document_cache("HD Meeting Settings", "HD Meeting Settings")
    frappe.cache.delete_value(f"helpdesk:graph_token:{app}")
    return doc


def make_meeting(
    reference_doctype: str,
    reference_name: str,
    starts_on,
    attendees: list[str],
    scheduled_by: str = "Administrator",
    **values,
):
    """Creates a scheduled HD Meeting as if Teams had already made it (no Graph call)."""
    return frappe.get_doc(
        {
            "doctype": "HD Meeting",
            "subject": values.pop("subject", "Test meeting"),
            "starts_on": starts_on,
            "ends_on": frappe.utils.add_to_date(starts_on, minutes=30),
            "reference_doctype": reference_doctype,
            "reference_name": str(reference_name),
            "organizer": values.pop("organizer", "organizer@meetings.example"),
            "scheduled_by": scheduled_by,
            "external_id": values.pop("external_id", "AAMk-test"),
            "join_url": values.pop(
                "join_url", "https://teams.microsoft.com/l/meetup-join/x"
            ),
            "attendees": [{"email": email} for email in attendees],
            **values,
        }
    ).insert(ignore_permissions=True)


def fake_graph_token(roles: list[str] | None = None) -> str:
    """An unsigned JWT shaped like a Microsoft access token, carrying `roles`."""
    import base64

    def part(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    return f"{part({'alg': 'none'})}.{part({'roles': roles or []})}.signature"


def graph_response(payload: dict | None = None, status: int = 200):
    """A fake requests response from Microsoft Graph or its token endpoint."""
    from unittest.mock import MagicMock

    response = MagicMock(status_code=status)
    response.json.return_value = payload or {}
    return response


def set_work_settings(**values):
    """Saves HD Work Settings (AI estimates, weekly off, morning brief) with `values`."""
    doc = frappe.get_doc("HD Work Settings")
    doc.update(values)
    doc.save(ignore_permissions=True)
    frappe.clear_document_cache("HD Work Settings", "HD Work Settings")
    return doc


REPLAY_START_MS = 1_790_000_000_000
REPLAY_ERROR_MESSAGE = "Posting Date cannot be before the Invoice Date"


def make_replay_events(
    start_ms: int = REPLAY_START_MS, filler_clicks: int = 0
) -> list[dict]:
    """rrweb events for a short synthetic session on a customer's ERPNext.

    The customer opens a new Sales Invoice, types a posting date, clicks Save,
    hits a server ValidationError (with a msgprint and a console error), closes
    the dialog and raises the ticket 20s after the first event. `filler_clicks`
    adds that many alternating Save/Close clicks before the ticket is raised,
    for testing the line cap.
    """

    def at(seconds, event_type, data):
        return {
            "type": event_type,
            "timestamp": start_ms + seconds * 1000,
            "data": data,
        }

    def element(node_id, tag, attributes=None, children=None):
        return {
            "id": node_id,
            "type": 2,
            "tagName": tag,
            "attributes": attributes or {},
            "childNodes": children or [],
        }

    def text(node_id, content):
        return {"id": node_id, "type": 3, "textContent": content}

    def click(seconds, node_id):
        return at(seconds, 3, {"source": 2, "type": 2, "id": node_id, "x": 10, "y": 10})

    snapshot = {
        "id": 1,
        "type": 0,
        "childNodes": [
            element(
                2,
                "html",
                children=[
                    element(
                        3,
                        "body",
                        children=[
                            element(
                                4,
                                "div",
                                {
                                    "class": "frappe-control",
                                    "data-fieldname": "posting_date",
                                },
                                [
                                    element(
                                        5,
                                        "label",
                                        {"class": "control-label"},
                                        [text(6, "Posting Date")],
                                    ),
                                    element(
                                        7,
                                        "input",
                                        {
                                            "type": "text",
                                            "data-fieldname": "posting_date",
                                        },
                                    ),
                                ],
                            ),
                            element(
                                8,
                                "button",
                                {"class": "btn btn-primary primary-action"},
                                [element(9, "span", children=[text(10, "Save")])],
                            ),
                        ],
                    )
                ],
            )
        ],
    }
    events = [
        at(
            0,
            4,
            {
                "href": "https://erp.example.com/app/sales-invoice/new",
                "width": 1440,
                "height": 900,
            },
        ),
        at(0, 2, {"node": snapshot, "initialOffset": {"top": 0, "left": 0}}),
        at(
            1,
            5,
            {
                "tag": "frappe-route",
                "payload": {
                    "route": ["Form", "Sales Invoice", "new"],
                    "url": "/app/sales-invoice/new",
                },
            },
        ),
        at(5, 3, {"source": 5, "id": 7, "text": "••-••-••••", "isChecked": False}),
        at(6, 3, {"source": 5, "id": 7, "text": "••-••-••••", "isChecked": False}),
        at(
            8,
            3,
            {
                "source": 0,
                "adds": [
                    {
                        "parentId": 3,
                        "nextId": None,
                        "node": element(
                            20,
                            "button",
                            {"aria-label": "Close", "class": "btn-modal-close"},
                        ),
                    }
                ],
                "removes": [],
                "texts": [],
                "attributes": [],
            },
        ),
        click(12, 10),
        at(
            13,
            5,
            {
                "tag": "frappe-call-error",
                "payload": {
                    "method": "frappe.desk.form.save.savedocs",
                    "status": 417,
                    "exc_type": "ValidationError",
                    "message": REPLAY_ERROR_MESSAGE,
                },
            },
        ),
        at(
            13,
            5,
            {
                "tag": "frappe-msgprint",
                "payload": {
                    "title": "Message",
                    "message": f"<p>{REPLAY_ERROR_MESSAGE}</p>",
                },
            },
        ),
        at(
            14,
            6,
            {
                "plugin": "rrweb/console@1",
                "payload": {
                    "level": "error",
                    "payload": ['"Uncaught TypeError: frm.doc is undefined"'],
                    "trace": [],
                },
            },
        ),
        click(15, 20),
    ]
    events += [
        click(15 + (i + 1) * 0.01, 10 if i % 2 == 0 else 20)
        for i in range(filler_clicks)
    ]
    events.append(at(20, 5, {"tag": "raise-ticket", "payload": {}}))
    return events


def make_replay(events: list[dict] | None = None) -> dict:
    """A session-replay.json.gz payload (before gzip) wrapping `events`."""
    events = events if events is not None else make_replay_events()
    return {
        "version": 1,
        "minutes": 5,
        "privacy": "mask-numbers",
        "started_at": events[0]["timestamp"] if events else REPLAY_START_MS,
        "ended_at": events[-1]["timestamp"] if events else REPLAY_START_MS,
        "events": events,
    }


def make_diagnostics(**overrides) -> dict:
    """A session-diagnostics.json payload as the helpdesk_client recorder writes it."""
    return {
        "version": 1,
        "captured_at": REPLAY_START_MS + 20_000,
        "url": "https://erp.example.com/app/sales-invoice/new",
        "route": ["Form", "Sales Invoice", "new"],
        "title": "New Sales Invoice",
        "user_agent": "Mozilla/5.0",
        "browser": "Chrome 128",
        "os": "macOS 14",
        "viewport": {"w": 1440, "h": 900},
        "screen": {"w": 1920, "h": 1080},
        "timezone": "Asia/Dubai",
        "language": "en",
        "versions": {"frappe": "15.40.0", "erpnext": "15.35.1", "hrms": "15.20.0"},
        "site": "erp.example.com",
        "recent_errors": [
            {
                "time": REPLAY_START_MS + 13_000,
                "kind": "call",
                "message": REPLAY_ERROR_MESSAGE,
                "method": "frappe.desk.form.save.savedocs",
                "status": 417,
                "exc_type": "ValidationError",
            }
        ],
        **overrides,
    }


def make_session_files(
    ticket: str,
    replay: dict | None = None,
    diagnostics: dict | None = None,
    with_replay: bool = True,
) -> dict:
    """Attaches a gzipped session replay and a diagnostics JSON to an HD Ticket as
    private Files, the way the ticket puller stores them. `with_replay=False` mimics
    a client that skipped a too-large replay. Returns {"replay", "diagnostics"} File docs."""
    files = {}
    for key, file_name, content in (
        (
            "replay",
            "session-replay.json.gz",
            gzip.compress(json.dumps(replay or make_replay()).encode()),
        ),
        (
            "diagnostics",
            "session-diagnostics.json",
            json.dumps(diagnostics or make_diagnostics()).encode(),
        ),
    ):
        if key == "replay" and not with_replay:
            continue
        files[key] = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": file_name,
                "attached_to_doctype": "HD Ticket",
                "attached_to_name": str(ticket),
                "is_private": 1,
                "content": content,
            }
        ).insert(ignore_permissions=True)
    return files


def make_download_response(content: bytes):
    """A stand-in for the streamed `requests.get` response the ticket puller reads files from."""
    from unittest.mock import MagicMock

    response = MagicMock()
    response.raw.read.side_effect = lambda amount, decode_content=True: content[:amount]
    return response


def make_puller_mcp(site_url: str = "https://erp.example.com"):
    """An MCPClient stand-in carrying the connection details `_attach_recording` downloads with."""
    from unittest.mock import MagicMock

    mcp = MagicMock()
    mcp.site_url = site_url
    mcp.api_key = "key"
    mcp.api_secret = "secret"
    return mcp


def set_content_settings(**values):
    """Overwrite HD Content Settings fields for a test (callers roll back afterwards)."""
    frappe.db.set_single_value("HD Content Settings", values)


def make_content_package(customer: str, items: list[tuple[str, str, int]], **kwargs):
    """Creates a monthly HD Content Package; `items` are (channel, format, posts per month)."""
    return frappe.get_doc(
        {
            "doctype": "HD Content Package",
            "customer": customer,
            "items": [
                {"channel": channel, "format": fmt, "posts_per_month": count}
                for channel, fmt, count in items
            ],
            **kwargs,
        }
    ).insert(ignore_permissions=True)


def content_plan_values(customer: str, **overrides) -> dict:
    """What the Monthly plans page sends to save a plan: 6 Instagram posts and
    2 LinkedIn articles a month, weekdays at 18:30, planning automatically."""
    return {
        "customer": customer,
        "items": [
            {"channel": "Instagram", "format": "Post", "posts_per_month": 6},
            {"channel": "LinkedIn", "format": "Article", "posts_per_month": 2},
        ],
        "posting_days": "Monday to Friday",
        "publish_time": "18:30",
        "enabled": 1,
        **overrides,
    }


def make_content_occasion(
    name: str, date: str, region: str = "Everywhere", repeats_yearly: int = 0, **kwargs
):
    """Creates an HD Content Occasion on `date` (a one-off unless `repeats_yearly`)."""
    return frappe.get_doc(
        {
            "doctype": "HD Content Occasion",
            "occasion_name": name,
            "occasion_date": date,
            "region": region,
            "repeats_yearly": repeats_yearly,
            **kwargs,
        }
    ).insert(ignore_permissions=True)


def make_portal_contact(customer: str, email: str):
    """Adds a user-less Contact with `email` to `customer`, so that email can sign in to the content portal."""
    contact = create_contact(email.split("@")[0], email, user=False)["contact"]
    add_contact_in_customer(frappe.get_doc("HD Customer", customer), contact)
    return contact


def make_article(title: str, content: str, status: str = "Published"):
    """Creates an HD Article with `title` and HTML `content` (Published unless `status` says otherwise)."""
    return frappe.get_doc(
        {
            "doctype": "HD Article",
            "title": title,
            "content": content,
            "status": status,
        }
    ).insert(ignore_permissions=True)


GITHUB_TEST_SECRET = "test-github-webhook-secret"
GITHUB_TEST_REPO = "tbocloud/helpdesk"


def enable_github_sync(**values):
    """Turns on HD GitHub Settings with the test webhook secret, tbocloud/* allowed, plus any overrides."""
    doc = frappe.get_doc("HD GitHub Settings")
    doc.update(
        {
            "enabled": 1,
            "webhook_secret": GITHUB_TEST_SECRET,
            "allowed_repos": "tbocloud/*",
            "complete_on_merge": 1,
            "unlinked_pr_project": None,
            "github_token": None,
            **values,
        }
    )
    doc.save(ignore_permissions=True)
    return doc


def make_github_payload(event: str, action: str = "", **overrides) -> dict:
    """A minimal GitHub webhook payload shaped like the real one for `event`.

    Overrides: repo, number, title, body, branch, draft, merged, closed, login,
    comments, review_state, review_body, reviewer, conclusion, sha, workflow,
    pull_requests (workflow_run: PR numbers the run belongs to).
    """
    repo = overrides.get("repo", GITHUB_TEST_REPO)
    number = overrides.get("number", 7)
    login = overrides.get("login", "dev-octocat")
    sha = overrides.get("sha", "a1b2c3d")
    branch = overrides.get("branch", "feature/invoice-print")
    merged = overrides.get("merged", False)
    closed = overrides.get("closed", merged)
    payload = {
        "action": action,
        "repository": {"full_name": repo, "name": repo.split("/")[-1]},
        "sender": {"login": login},
    }
    if event == "workflow_run":
        payload["workflow_run"] = {
            "name": overrides.get("workflow", "Server Tests"),
            "head_branch": branch,
            "head_sha": sha,
            "status": "completed",
            "conclusion": overrides.get("conclusion", "success"),
            "pull_requests": [
                {"number": n, "head": {"ref": branch, "sha": sha}}
                for n in overrides.get("pull_requests", [number])
            ],
        }
        return payload

    payload["number"] = number
    payload["pull_request"] = {
        "number": number,
        "title": overrides.get("title", "Invoice print format"),
        "body": overrides.get("body", ""),
        "html_url": f"https://github.com/{repo}/pull/{number}",
        "state": "closed" if closed else "open",
        "draft": overrides.get("draft", False),
        "merged": merged,
        "merged_at": "2026-09-30T10:00:00Z" if merged else None,
        "closed_at": "2026-09-30T10:00:00Z" if closed else None,
        "merged_by": {"login": "lead-octocat"} if merged else None,
        "comments": overrides.get("comments", 0),
        "user": {"login": login},
        "head": {"ref": branch, "sha": sha},
        "base": {"ref": "main"},
    }
    if event == "pull_request_review":
        payload["review"] = {
            "state": overrides.get("review_state", "approved"),
            "body": overrides.get("review_body", ""),
            "user": {"login": overrides.get("reviewer", "lead-octocat")},
        }
    return payload


def github_signature(body: bytes, secret: str = GITHUB_TEST_SECRET) -> str:
    """The X-Hub-Signature-256 header GitHub would send for `body`."""
    import hashlib
    import hmac

    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def send_github_webhook(
    event: str,
    payload: dict | None = None,
    delivery: str | None = None,
    signature: str | None = "sign",
    body: bytes | None = None,
):
    """Calls helpdesk.api.github.webhook with a fake request carrying GitHub's headers.

    `signature="sign"` signs the body with the test secret; None leaves the header out.
    """
    from werkzeug.test import EnvironBuilder
    from werkzeug.wrappers import Request

    from helpdesk.api.github import webhook

    body = body if body is not None else json.dumps(payload or {}).encode()
    headers = {
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery or frappe.generate_hash(length=20),
    }
    if signature == "sign":
        headers["X-Hub-Signature-256"] = github_signature(body)
    elif signature:
        headers["X-Hub-Signature-256"] = signature
    builder = EnvironBuilder(
        path="/api/method/helpdesk.api.github.webhook",
        method="POST",
        base_url="http://localhost",
        headers=headers,
        data=body,
        content_type="application/json",
    )
    previous = getattr(frappe.local, "request", None)
    frappe.local.request = Request(builder.get_environ())
    try:
        return webhook()
    finally:
        frappe.local.request = previous


def get_task_comments(task: str, like: str = "%") -> list[str]:
    """Contents of the Info comments on `task` matching the SQL LIKE pattern `like`."""
    return frappe.get_all(
        "Comment",
        filters={
            "reference_doctype": "Task",
            "reference_name": task,
            "comment_type": "Info",
            "content": ("like", like),
        },
        pluck="content",
    )


CHATWOOT_TEST_SECRET = "test-chatwoot-account-secret"
CHATWOOT_TEST_BOT_SECRET = "test-chatwoot-bot-secret"
CHATWOOT_TEST_URL = "https://chat.example.com"


def enable_chatwoot_bridge(**values):
    """Turns on HD Chatwoot Settings with test tokens and both webhook secrets, plus any overrides."""
    doc = frappe.get_doc("HD Chatwoot Settings")
    doc.update(
        {
            "enabled": 1,
            "base_url": CHATWOOT_TEST_URL,
            "account_id": 1,
            "api_access_token": "bridge-user-token",
            "bot_access_token": "ai-bot-token",
            "webhook_secret": CHATWOOT_TEST_SECRET,
            "bot_webhook_secret": CHATWOOT_TEST_BOT_SECRET,
            "ai_first_reply": 1,
            "max_ai_replies": 6,
            "handoff_team_id": 0,
            "default_customer": None,
            **values,
        }
    )
    doc.save(ignore_permissions=True)
    return doc


def make_chatwoot_payload(event: str, **overrides) -> dict:
    """A Chatwoot webhook payload shaped like the real one for `event`.

    Overrides: conversation_id, message_id, content, message_type, private,
    sender_type, attachments, status, labels, name, email, phone, contact_id,
    channel, inbox_id, hmac_verified, updated_at, account_id.
    """
    import time

    contact = {
        "id": overrides.get("contact_id", 77),
        "name": overrides.get("name", "Anita Rao"),
        "email": overrides.get("email", ""),
        "phone_number": overrides.get("phone", ""),
        "type": "contact",
    }
    account = {"id": overrides.get("account_id", 1), "name": "TBO"}
    conversation = {
        "id": overrides.get("conversation_id", 4242),
        "inbox_id": overrides.get("inbox_id", 3),
        "status": overrides.get("status", "pending"),
        "channel": overrides.get("channel", "Channel::WebWidget"),
        "labels": overrides.get("labels", []),
        "meta": {
            "sender": contact,
            "assignee": None,
            "hmac_verified": overrides.get("hmac_verified", False),
        },
        "updated_at": overrides.get("updated_at", time.time()),
        "timestamp": int(time.time()),
    }
    if event.startswith("message_"):
        sender_type = overrides.get("sender_type", "contact")
        sender = (
            contact
            if sender_type == "contact"
            else {"id": 5, "name": "TBO AI", "type": sender_type}
        )
        return {
            "event": event,
            "id": overrides.get("message_id", 1001),
            "content": overrides.get("content", "Hello, I need help."),
            "message_type": overrides.get("message_type", "incoming"),
            "content_type": "text",
            "private": overrides.get("private", False),
            "attachments": overrides.get("attachments", []),
            "account": account,
            "inbox": {"id": conversation["inbox_id"], "name": "Website"},
            "sender": sender,
            "conversation": conversation,
        }
    return {
        "event": event,
        "account": account,
        "changed_attributes": [],
        **conversation,
    }


def chatwoot_signature(body: bytes, timestamp: str, secret: str) -> str:
    """The X-Chatwoot-Signature header Chatwoot sends: HMAC-SHA256 over "{timestamp}.{body}"."""
    import hashlib
    import hmac

    signed = timestamp.encode() + b"." + body
    return "sha256=" + hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()


def send_chatwoot_webhook(
    source: str,
    payload: dict | None = None,
    signature: str | None = "sign",
    timestamp: str | None = None,
    token: str | None = None,
    body: bytes | None = None,
):
    """Calls helpdesk.api.chatwoot.<source>_webhook with a fake request carrying Chatwoot's headers.

    `signature="sign"` signs the body with the test secret of that webhook; None
    leaves the signature out. `token` goes in the query string.
    """
    import time

    from werkzeug.test import EnvironBuilder
    from werkzeug.wrappers import Request

    from helpdesk.api.chatwoot import account_webhook, bot_webhook

    body = body if body is not None else json.dumps(payload or {}).encode()
    timestamp = timestamp or str(int(time.time()))
    headers = {
        "X-Chatwoot-Timestamp": timestamp,
        "X-Chatwoot-Delivery": frappe.generate_hash(length=20),
    }
    if signature == "sign":
        secret = CHATWOOT_TEST_BOT_SECRET if source == "bot" else CHATWOOT_TEST_SECRET
        headers["X-Chatwoot-Signature"] = chatwoot_signature(body, timestamp, secret)
    elif signature:
        headers["X-Chatwoot-Signature"] = signature
    method = f"helpdesk.api.chatwoot.{source}_webhook"
    builder = EnvironBuilder(
        path=f"/api/method/{method}",
        method="POST",
        base_url="http://localhost",
        headers=headers,
        data=body,
        content_type="application/json",
        query_string={"token": token} if token else None,
    )
    previous = getattr(frappe.local, "request", None)
    frappe.local.request = Request(builder.get_environ())
    try:
        return bot_webhook() if source == "bot" else account_webhook()
    finally:
        frappe.local.request = previous


class FakeChatwootAPI:
    """Stands in for `requests.request` in helpdesk.chatwoot_bridge: records every call and answers like Chatwoot.

    GET .../messages returns `messages`; every POST returns a new message id.
    `fail=True` answers everything with HTTP 500.
    """

    def __init__(self, messages: list[dict] | None = None, fail: bool = False):
        self.messages = messages or []
        self.fail = fail
        self.calls = []

    def __call__(self, method, url, json=None, headers=None, timeout=None, **kwargs):
        from unittest.mock import MagicMock

        self.calls.append(
            {
                "method": method,
                "url": url,
                "body": json or {},
                "token": (headers or {}).get("Api-Access-Token"),
            }
        )
        response = MagicMock()
        if self.fail:
            response.status_code = 500
            response.text = "Internal Server Error"
            return response
        response.status_code = 200
        if method == "GET":
            response.json.return_value = {"payload": self.messages}
        else:
            response.json.return_value = {"id": 900000 + len(self.calls)}
        return response

    def calls_to(self, suffix: str, method: str = "POST") -> list[dict]:
        return [
            c for c in self.calls if c["method"] == method and c["url"].endswith(suffix)
        ]

    def posted(self, private: bool | None = None) -> list[str]:
        """Contents of the messages posted, optionally only private notes (True) or public ones (False)."""
        return [
            c["body"].get("content")
            for c in self.calls_to("/messages")
            if private is None or bool(c["body"].get("private")) == private
        ]

    def statuses(self) -> list[str]:
        """The statuses the bridge toggled conversations to, in order."""
        return [c["body"].get("status") for c in self.calls_to("/toggle_status")]


def make_chat_conversation(conversation_id: int, **values):
    """Creates an HD Chat Conversation row for `conversation_id` (Open, website chat) with any overrides."""
    return frappe.get_doc(
        {
            "doctype": "HD Chat Conversation",
            "conversation_id": conversation_id,
            "status": "Open",
            "channel": "Channel::WebWidget",
            "contact_name": "Anita Rao",
            **values,
        }
    ).insert(ignore_permissions=True)


def get_chat_conversation(conversation_id: int):
    """The HD Chat Conversation row of `conversation_id`, or None."""
    name = frappe.db.get_value(
        "HD Chat Conversation", {"conversation_id": conversation_id}
    )
    return frappe.get_doc("HD Chat Conversation", name) if name else None


def make_phone_contact(first_name: str, phone: str):
    """Creates a Contact whose only detail is the mobile number `phone`, stored as typed."""
    contact = frappe.get_doc({"doctype": "Contact", "first_name": first_name})
    contact.append("phone_nos", {"phone": phone, "is_primary_mobile_no": 1})
    return contact.insert(ignore_permissions=True)


def ai_chat_answer(reply: str, action: str = "answer", **fields) -> dict:
    """What call_haiku returns for a chat reply: `reply`, `action` and any ticket_subject / ticket_summary."""
    return {
        "response": {"reply": reply, "action": action, **fields},
        "usage": {},
        "cost": 0,
    }


def make_email_account(email_id: str, **kwargs):
    """Creates an Email Account for `email_id` on a fake server: send-only unless kwargs enable incoming."""
    name = kwargs.pop("email_account_name", email_id)
    if frappe.db.exists("Email Account", name):
        return frappe.get_doc("Email Account", name)
    return frappe.get_doc(
        {
            "doctype": "Email Account",
            "email_account_name": name,
            "email_id": email_id,
            "enable_outgoing": 1,
            "smtp_server": "smtp.example.com",
            "password": "password",
            **kwargs,
        }
    ).insert(ignore_permissions=True)


def make_pull_request(task: str, number: int, state: str = "Open", **kwargs):
    """Creates an HD Pull Request linking a GitHub PR (no real GitHub call) to `task`."""
    return frappe.get_doc(
        {
            "doctype": "HD Pull Request",
            "repo": "tbocloud/helpdesk",
            "number": number,
            "title": f"PR {number}",
            "url": f"https://github.com/tbocloud/helpdesk/pull/{number}",
            "task": task,
            "link_kind": "Refs",
            "state": state,
            "last_event_at": frappe.utils.now_datetime(),
            **kwargs,
        }
    ).insert(ignore_permissions=True)


def make_timesheet(project: str, hours: float, from_time, task: str | None = None):
    """Creates a draft Timesheet with one time log of `hours` on `project` (and `task`)."""
    return frappe.get_doc(
        {
            "doctype": "Timesheet",
            "time_logs": [
                {
                    "project": project,
                    "task": task,
                    "hours": hours,
                    "from_time": from_time,
                }
            ],
        }
    ).insert(ignore_permissions=True)


class FakeCRM:
    """In-memory stand-in for the TBO CRM site's REST API (helpdesk.integrations.crm.client)."""

    def __init__(
        self,
        users: list[dict] | None = None,
        failing: tuple = (),
        organizations: list[str] | None = None,
    ):
        self.users = {u["name"]: {"roles": [], "enabled": 1, **u} for u in users or []}
        self.failing = set(failing)
        self.role_calls: list[tuple[tuple, str]] = []
        self.orgs = [{"name": o, "organization_name": o} for o in organizations or []]
        self.erp = []

    def logged_user(self):
        return "api@crm.example"

    def get_user(self, email):
        from helpdesk.integrations.crm.client import CRMError

        if email in self.failing:
            raise CRMError("CRM said no")
        return self.users.get(email)

    def create_user(self, email, full_name, send_welcome_email):
        self.users[email] = {
            "name": email,
            "full_name": full_name,
            "enabled": 1,
            "roles": [],
            "welcome_email": send_welcome_email,
        }
        return self.users[email]

    def enable_user(self, email):
        self.users[email]["enabled"] = 1

    def disable_user(self, email):
        self.users[email]["enabled"] = 0

    def crm_users(self):
        return [
            {"email": u["name"], "full_name": u.get("full_name") or ""}
            for u in self.users.values()
            if u.get("enabled") and u.get("roles")
        ]

    def organizations(self):
        return list(self.orgs)

    def erp_customers(self):
        return [{"name": c, "organization_name": c} for c in self.erp]

    def create_organization(self, name, website=None):
        self.orgs.append({"name": name, "organization_name": name, "website": website})
        return self.orgs[-1]

    def add_to_crm(self, emails, role):
        self.role_calls.append((tuple(emails), role))
        for email in emails:
            self.users[email]["roles"].append({"role": role})


class FakeS3:
    """In-memory stand-in for a boto3 S3 client, so storage tests never reach a real bucket."""

    def __init__(self, fail_uploads: bool = False):
        self.objects: dict[str, bytes] = {}
        self.fail_uploads = fail_uploads

    def upload_file(self, path, bucket, key, ExtraArgs=None):
        if self.fail_uploads:
            raise ConnectionError("bucket unreachable")
        with open(path, "rb") as f:
            self.objects[key] = f.read()

    def put_object(self, Bucket, Key, Body):
        self.objects[Key] = Body

    def get_object(self, Bucket, Key):
        import io

        return {"Body": io.BytesIO(self.objects[Key])}

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)

    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f"https://bucket.example/{Params['Key']}?expires={ExpiresIn}"


def enable_file_storage(doctypes=("HD Content Post",), keep_local_copy=0):
    """Turns S3 file storage on for attachments of `doctypes` (pair with a patched FakeS3 client)."""
    settings = frappe.get_single("HD File Storage Settings")
    settings.update(
        {
            "enabled": 1,
            "bucket": "test-bucket",
            "region": "ap-south-1",
            "access_key_id": "AKIATEST",
            "secret_access_key": "test-secret",
            "key_prefix": "test-site",
            "link_expiry_seconds": 600,
            "delete_from_bucket": 1,
            "keep_local_copy": keep_local_copy,
        }
    )
    settings.set("document_types", [{"document_type": d} for d in doctypes])
    settings.save(ignore_permissions=True)
    frappe.clear_document_cache("HD File Storage Settings", "HD File Storage Settings")
    # lets storage run in tests; callers must patch s3.get_client with FakeS3
    frappe.flags.hd_fake_s3 = True
    return settings


def make_attachment(doctype: str, name: str, file_name: str, content: bytes, private=1):
    """A File with `content` attached to the given document."""
    return frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "attached_to_doctype": doctype,
            "attached_to_name": name,
            "is_private": private,
            "content": content,
        }
    ).insert(ignore_permissions=True)
