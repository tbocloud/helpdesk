import gzip
import io
import json
from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.core.doctype.communication.test_communication import create_email_account
from frappe.utils import add_to_date, getdate, now_datetime

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


def make_assigned_ticket(subject: str, user: str, **values) -> str:
    """Creates a ticket assigned to `user` only and returns its name as a string.

    Whatever an assignment rule gave out is withdrawn first, so the ticket's ToDos (which
    the work lists match) and `_assign` name `user` alone; other `values` (e.g. status,
    status_category) are written straight to the ticket, after insert.
    """
    name = make_ticket(subject=subject, customer=values.pop("customer", None)).name
    frappe.db.set_value(
        "ToDo",
        {"reference_type": "HD Ticket", "reference_name": name},
        "status",
        "Cancelled",
    )
    make_assignment("HD Ticket", name, user)
    frappe.db.set_value("HD Ticket", name, {"_assign": json.dumps([user]), **values})
    return str(name)


def make_customer_ticket(customer: str, subject: str, **values) -> str:
    """Creates a ticket for `customer` and returns its name as a string.

    `values` (e.g. creation, status_category, agreement_status, feedback_rating)
    are written directly after insert, so SLA and status hooks can't change them.
    """
    name = make_ticket(subject=subject, customer=customer).name
    if values:
        frappe.db.set_value("HD Ticket", name, values, update_modified=False)
    return str(name)


def make_owned_customer(name: str, owner: str | None = None, backup: str | None = None):
    """Creates (or updates) an HD Customer whose new tickets go to `owner`, and to
    `backup` while the owner is away. Saved as the session user (Administrator in
    tests, who may set ticket owners)."""
    if frappe.db.exists("HD Customer", name):
        doc = frappe.get_doc("HD Customer", name)
    else:
        doc = frappe.get_doc({"doctype": "HD Customer", "customer_name": name})
    doc.ticket_owner = owner
    doc.backup_ticket_owner = backup
    doc.save(ignore_permissions=True)
    return doc


def get_open_assignees(ticket) -> list[str]:
    """The users a ticket is assigned to now (its open ToDos), sorted."""
    return sorted(
        frappe.get_all(
            "ToDo",
            filters={
                "reference_type": "HD Ticket",
                "reference_name": str(ticket),
                "status": "Open",
            },
            pluck="allocated_to",
        )
    )


def get_ticket_owner_activity(ticket) -> list[str]:
    """The ticket's activity lines that record a ticket owner (or backup) assignment."""
    return frappe.get_all(
        "HD Ticket Activity",
        filters={"ticket": str(ticket), "action": ("like", "%ticket owner of%")},
        pluck="action",
    )


def get_ticket_notices(ticket, notification_type: str) -> list[tuple[str, str]]:
    """The (user_to, message) pairs of a ticket's HD Notifications of one type
    (e.g. New Ticket, Ticket Update), sorted."""
    return sorted(
        (n.user_to, n.message)
        for n in frappe.get_all(
            "HD Notification",
            filters={
                "reference_ticket": str(ticket),
                "notification_type": notification_type,
            },
            fields=["user_to", "message"],
        )
    )


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


def make_sla_calendar(
    sla_name: str,
    workdays: list[str],
    holidays: list = (),
    start_time: str = "10:00:00",
    end_time: str = "18:00:00",
):
    """An SLA whose clock runs on `workdays` from `start_time` to `end_time`, skipping
    `holidays` (kept in its own holiday list). It has no condition, so no ticket picks it up
    by itself: point a ticket at it by setting `sla`."""
    dates = [getdate(day) for day in holidays] or [getdate()]
    holiday_list = frappe.get_doc(
        {
            "doctype": "HD Service Holiday List",
            "holiday_list_name": f"{sla_name} Holidays",
            "from_date": min(dates),
            "to_date": max(dates),
            "holidays": [
                {"holiday_date": day, "description": "Test holiday"} for day in holidays
            ],
        }
    ).insert(ignore_permissions=True)
    sla = make_sla(sla_name).reload()
    sla.holiday_list = holiday_list.name
    sla.support_and_resolution = []
    for day in workdays:
        sla.append(
            "support_and_resolution",
            {"workday": day, "start_time": start_time, "end_time": end_time},
        )
    sla.save(ignore_permissions=True)
    return sla


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


def make_dm_head(email: str, full_name: str, *roles: str):
    """Creates an agent with the Digital Marketing Head role, who approves posts after the
    client, plus any other `roles` (e.g. "DM Coordinator")."""
    from helpdesk.content_team import DM_HEAD_ROLE, ensure_role

    ensure_role()
    return make_tasky_user(email, full_name, roles=(DM_HEAD_ROLE, *roles))


def make_content_user(email: str, full_name: str, role: str):
    """Creates an agent with a content role, e.g. "DM Coordinator" (edits entries) or
    "DM Employee" (only attaches files)."""
    from helpdesk.content_team import ensure_role

    ensure_role()
    return make_tasky_user(email, full_name, roles=(role,))


def make_sales_employee(email: str, full_name: str, *roles: str):
    """Creates an agent with the Sales Employee role (sees Leads and the Scoreboard, no
    tasks, projects, tickets or content), plus any other `roles`."""
    from helpdesk.content_team import SALES_EMPLOYEE_ROLE, ensure_role

    ensure_role()
    return make_tasky_user(email, full_name, roles=(SALES_EMPLOYEE_ROLE, *roles))


def attach_file(doctype: str, name: str, file_name: str = "draft.png"):
    """Attaches a small private file to a document as the current user, the way the
    upload button does (it needs write permission on the document)."""
    return frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "attached_to_doctype": doctype,
            "attached_to_name": name,
            "is_private": 1,
            "content": b"x",
        }
    ).insert()


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


def make_customer_project(
    customer: str, project_name: str, members: list[tuple[str, str]] | None = None
) -> str:
    """Creates an open Project for `customer` (see make_project) and returns its name."""
    project = make_project(project_name, members=members).name
    frappe.db.set_value("Project", project, "customer", customer)
    return project


def make_project_file(
    project: str,
    file_name: str = "master-prompt.md",
    content: bytes = b"# Master prompt\n\nBe concise.",
    for_users: list[str] | None = None,
    user: str | None = None,
    folder: str | None = None,
) -> str:
    """Adds a file to a project (in `folder` when given) through the project files
    API, as `user` (default: the session user), and returns the File's name."""
    from helpdesk.api.project_files import add_project_file

    def add():
        return add_project_file(project, file_name, content, for_users, folder)["name"]

    return run_as_user(user, add) if user else add()


def make_image_bytes(fmt: str, colour: str = "teal") -> bytes:
    """A real 4×4 image in `fmt` (PNG, JPEG, WEBP, GIF), for upload tests."""
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (4, 4), colour).save(out, format=fmt)
    return out.getvalue()


def make_task_attachment(
    task: str,
    file_name: str = "screenshot.png",
    content: bytes = b"\x89PNG\r\n\x1a\n" + b"\0" * 64,
    user: str | None = None,
) -> str:
    """Attaches an image or video to a task through the task attachments API, as
    `user` (default: the session user), and returns the File's name. The default
    content starts with PNG's magic number, which is all the type check reads."""
    from helpdesk.api.task_attachments import add_task_attachment

    def add():
        return add_task_attachment(task, file_name, content)["name"]

    return run_as_user(user, add) if user else add()


def make_project_folder(
    project: str,
    folder_name: str = "Prompts",
    for_users: list[str] | None = None,
    user: str | None = None,
    parent_folder: str | None = None,
) -> str:
    """Creates a folder of project files (inside `parent_folder` when given) through
    the API, as `user` (default: the session user), and returns its name."""
    from helpdesk.api.project_files import create_project_folder

    def create():
        return create_project_folder(
            project, folder_name, for_users=for_users, parent_folder=parent_folder
        )["name"]

    return run_as_user(user, create) if user else create()


def call_project_files(user: str, method: str, **kwargs):
    """Calls helpdesk.api.project_files.<method> as `user` through frappe.call, so
    arguments the method doesn't take are dropped as they are for a request."""
    return run_as_user(
        user, lambda: frappe.call(f"helpdesk.api.project_files.{method}", **kwargs)
    )


def mark_project_item(
    user: str,
    project: str,
    kind: str,
    item: str,
    status: str = "Superseded",
    superseded_by: str | None = None,
    note: str | None = None,
) -> dict:
    """Sets a project file's or folder's status (Superseded by default) as `user`.
    `kind` is "file" (item = the File) or "folder"."""
    return call_project_files(
        user,
        "set_project_item_status",
        project=project,
        kind=kind,
        item=item,
        status=status,
        superseded_by=superseded_by,
        note=note,
    )


def make_project_item_comment(
    user: str,
    project: str,
    kind: str,
    item: str,
    content: str = "Is this the latest version?",
    mentions: list[str] | None = None,
) -> str:
    """Comments on a project file or folder as `user` and returns the Comment's name."""
    return call_project_files(
        user,
        "add_item_comment",
        project=project,
        kind=kind,
        item=item,
        content=content,
        mentions=mentions,
    )["name"]


def make_department(name: str, **kwargs):
    """Creates an active HD Department at the end of the list, or returns the existing one."""
    if frappe.db.exists("HD Department", name):
        return frappe.get_doc("HD Department", name)
    return frappe.get_doc(
        {"doctype": "HD Department", "department_name": name, **kwargs}
    ).insert(ignore_permissions=True)


def make_task_template(template_name: str, tasks: list[dict]):
    """Creates an HD Task Template; each of `tasks` is a template task row (task_name, category, ...)."""
    return frappe.get_doc(
        {
            "doctype": "HD Task Template",
            "template_name": template_name,
            "tasks": [{"sort_order": i, **task} for i, task in enumerate(tasks)],
        }
    ).insert(ignore_permissions=True)


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


def make_content_option(doctype: str, name: str, **kwargs):
    """Creates an HD Content Platform or HD Content Post Type named `name`, as the team would."""
    field = "platform_name" if doctype == "HD Content Platform" else "post_type_name"
    return frappe.get_doc({"doctype": doctype, field: name, **kwargs}).insert(
        ignore_permissions=True
    )


def hold_commits(test_case):
    """Rolls back everything a test wrote, even where Frappe commits mid-test.

    Assigning a task sends the assignee an email, and in tests that email is sent
    at once and commits; without this a post's tasks would leak into other tests.
    """
    test_case.addCleanup(frappe.db.rollback)
    commit = patch.object(frappe.db, "commit")
    commit.start()
    test_case.addCleanup(commit.stop)


def make_content_project(customer: str) -> str:
    """Returns the project the customer's post tasks go to, creating an open Content
    Calendar project for them if they have no open project.

    A post can't create tasks without one (HDContentPost.require_content_project)."""
    from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
        CONTENT_PROJECT_TYPE,
        content_project_for,
    )

    if project := content_project_for(customer):
        return project
    project = make_customer_project(customer, f"{customer} - Content calendar")
    frappe.db.set_value("Project", project, "project_type", CONTENT_PROJECT_TYPE)
    return project


def make_content_post(
    title: str, customer: str | None = None, with_project: bool = True, **kwargs
):
    """Creates an HD Content Post: an Instagram Idea a week out unless overridden.

    Every post needs a posting date; pass `publish_on` to choose it. The customer gets a
    project (make_content_project) unless `with_project` is False.
    """
    from frappe.utils import add_to_date, now_datetime

    if customer and with_project:
        make_content_project(customer)
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


def run_client_pull(connection: str, error: str | None = None) -> int:
    """Runs one ticket pull of `connection` with the customer site mocked: the call fails
    with `error`, or the site answers with no pending tickets. Returns tickets made."""
    from helpdesk import ticket_puller

    client = (
        patch.object(ticket_puller, "MCPClient", side_effect=RuntimeError(error))
        if error
        else patch.object(ticket_puller, "MCPClient")
    )
    with client, patch.object(ticket_puller, "_pending_tickets", return_value=[]):
        return ticket_puller.pull_connection(connection)


def get_outage_logs(connection: str) -> list[str]:
    """Titles of the Error Logs written about `connection` being unreachable."""
    return frappe.get_all(
        "Error Log",
        filters={
            "reference_doctype": "HDS Support Connection",
            "reference_name": connection,
        },
        pluck="method",
    )


def get_task_todos(task: str) -> list[tuple[str, str]]:
    """The task's ToDos as (allocated_to, status) pairs, oldest first."""
    return [
        (t.allocated_to, t.status)
        for t in frappe.get_all(
            "ToDo",
            filters={"reference_type": "Task", "reference_name": task},
            fields=["allocated_to", "status"],
            order_by="creation asc",
        )
    ]


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
    from helpdesk.utils import add_assignment

    add_assignment(
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


def make_task_in_status(project: str, subject: str, status: str, **values) -> str:
    """Creates a Task in `project` and sets its status and any other `values`
    (e.g. slip_count) straight in the database, skipping the hold, review and
    slip hooks; returns its name. For tests that need a project in every state."""
    task = make_task(project, subject).name
    frappe.db.set_value("Task", task, {"status": status, **values})
    return task


def start_task_timer(task: str, hours_ago: float, estimated_hours: float = 0):
    """Puts `task` in Working with its timer started `hours_ago`, as if the assignee began
    it then, and sets its estimated hours."""
    frappe.db.set_value(
        "Task",
        task,
        {
            "status": "Working",
            "custom_timer_start": add_to_date(now_datetime(), hours=-hours_ago),
            "custom_timer_elapsed": 0,
            "custom_estimated_hours": estimated_hours,
        },
    )


def make_assigned_task(
    project: str, subject: str, assignee: str, assigned_by: str, **kwargs
) -> str:
    """Creates an open Task in `project`, due in five days, that `assigned_by`
    creates and gives to `assignee` (so the ToDo names them as the assigner);
    returns its name."""
    from frappe.utils import add_days, nowdate

    kwargs.setdefault("description", f"{subject}: agreed with the customer.")

    def create():
        task = make_task(project, subject, add_days(nowdate(), 5), **kwargs).name
        make_assignment("Task", task, assignee)
        return task

    return run_as_user(assigned_by, create)


def make_planned_task(
    project: str, subject: str, assignee: str, hours: float, due, **kwargs
) -> str:
    """Creates an open Task in `project` estimated at `hours` and due on `due`, assigned
    to `assignee`; returns its name. For capacity planning tests."""
    task = make_task(project, subject, due, custom_estimated_hours=hours, **kwargs).name
    make_assignment("Task", task, assignee)
    return task


def make_done_task(
    project: str, subject: str, assignee: str, completed_on, due=None, **kwargs
) -> str:
    """Creates a Task in `project` assigned to `assignee`, due on `due`, and marks it
    Completed on `completed_on`; returns its name. For team dashboard tests."""
    task = make_task(project, subject, due, **kwargs).name
    make_assignment("Task", task, assignee)
    frappe.db.set_value(
        "Task", task, {"status": "Completed", "completed_on": completed_on}
    )
    return task


def make_self_made_done_task(
    project: str, subject: str, user: str, completed_on, due=None, **kwargs
) -> str:
    """Creates a Task that `user` makes and takes themselves (they create it and
    assign it to themselves), due on `due` and Completed on `completed_on`;
    returns its name. The Scoreboard weighs such tasks half."""
    task = make_assigned_task(project, subject, user, user, **kwargs)
    frappe.db.set_value(
        "Task",
        task,
        {"status": "Completed", "completed_on": completed_on, "exp_end_date": due},
    )
    return task


def score_stats(**values) -> dict:
    """A person's Scoreboard numbers (team_dashboard.blank) with `values` set.
    Unless given, the quality-weighted values equal the weights (unrated work)."""
    from helpdesk.team_dashboard import blank

    values.setdefault("value", values.get("weight", 0.0))
    values.setdefault("value_on_time", values.get("weight_on_time", 0.0))
    return {**blank(), **values}


def rate_task_as(user: str, task: str, rating: str | None):
    """`user` gives a completed task its quality rating through the API."""
    return call_as_user(user, "helpdesk.tasky.api.rate_task", task=task, rating=rating)


def make_done_ticket_task(project: str, subject: str, assignee: str, completed_on):
    """Creates a resolved HD Ticket and a completed Task made from it (hd_ticket),
    assigned to `assignee`; returns (ticket name, task name)."""
    ticket = make_ticket(subject=subject).name
    frappe.db.set_value(
        "HD Ticket", ticket, {"status": "Resolved", "status_category": "Resolved"}
    )
    task = make_done_task(project, subject, assignee, completed_on, hd_ticket=ticket)
    return ticket, task


def make_team_champion(
    period_type: str, start, end, user: str, score: float, department=None, **kwargs
):
    """Stores an HD Team Champion as if `close_period` had kept it, with a
    one-line breakdown; for reading closed periods back."""
    breakdown = [{"key": "tasks", "points": score, "detail": "Tasks done: 2"}]
    return frappe.get_doc(
        {
            "doctype": "HD Team Champion",
            "period_type": period_type,
            "period_start": start,
            "period_end": end,
            "department": department,
            "user": user,
            "score": score,
            "breakdown": json.dumps(breakdown),
            **kwargs,
        }
    ).insert(ignore_permissions=True)


def make_member_day(project: str, member: str, lead: str, teammate: str) -> dict:
    """A project member's open work like the day that showed a false "All clear" on
    Home: eight tasks `lead` gave `member` (one overdue, one due today, a key task
    in progress, one in progress with its timer paused, two on hold waiting on the
    customer, one without a due date, one due in three days), one `member` gave
    `teammate` that is overdue, and one of `teammate`'s own that `member` must not
    see. Returns the task names by those keys."""
    from frappe.utils import add_days, nowdate

    today = nowdate()

    def task(subject: str, assignee: str, by: str, **values) -> str:
        name = make_assigned_task(project, subject, assignee, by)
        frappe.db.set_value("Task", name, values)
        return name

    def held(subject: str, days: int) -> str:
        return task(
            subject,
            member,
            lead,
            status="On Hold",
            hold_reason="Waiting on customer",
            hold_note="Asked for the bank statement",
            hold_since=add_days(today, -days),
            hold_by=member,
        )

    tasks = {
        "overdue": task(
            "Fix the GST return", member, lead, exp_end_date=add_days(today, -2)
        ),
        "due_today": task("Post the Onam reel", member, lead, exp_end_date=today),
        "key_working": task(
            "Migrate the item master",
            member,
            lead,
            exp_end_date=add_days(today, 10),
            is_key=1,
        ),
        "paused": task(
            "Draft the user manual",
            member,
            lead,
            status="Working",
            exp_end_date=add_days(today, 20),
            custom_timer_elapsed=1.5,
        ),
        "held_long": held("Reconcile the bank feed", 3),
        "held_short": held("Map the cost centres", 1),
        "no_date": task("Clean up old leads", member, lead, exp_end_date=None),
        "coming_up": task(
            "Train the sales team", member, lead, exp_end_date=add_days(today, 3)
        ),
        "given_out": task(
            "Design the invoice print",
            teammate,
            member,
            exp_end_date=add_days(today, -1),
        ),
        "teammate_own": task(
            "Fix the payroll script", teammate, lead, exp_end_date=add_days(today, -4)
        ),
    }
    start_task_timer(tasks["key_working"], hours_ago=1)
    return tasks


def log_hours(
    user: str, project: str, hours: float, day, at: str = "10:00:00", **log
) -> str:
    """Creates a draft Timesheet of `hours` on `project` on `day` at `at`, logged by
    `user` (its owner); returns its name. `log` passes `task` or `notes` on."""
    sheet = make_timesheet(project, hours, f"{day} {at}", **log).name
    frappe.db.set_value("Timesheet", sheet, "owner", user, update_modified=False)
    return sheet


def call_team_dashboard(user: str, today, method: str = "get_team_dashboard", **kwargs):
    """Calls a helpdesk.api.team_dashboard endpoint as `user` with today fixed, so
    only the test's records fall in the period, and nothing cached carries over."""
    from helpdesk.team_dashboard import clear_cache

    clear_cache()
    with patch("helpdesk.api.team_dashboard.nowdate", return_value=str(today)):
        return run_as_user(
            user,
            lambda: frappe.call(f"helpdesk.api.team_dashboard.{method}", **kwargs),
        )


def call_repeat_issues(
    user: str,
    today,
    method: str = "helpdesk.api.repeat_issues.get_repeat_issues",
    **kwargs,
):
    """Calls a repeat issues endpoint (the web's, or the app's with `method`) as `user`
    with today fixed, so only the test's records fall in the window, and no detected
    clusters cached by an earlier call carry over."""
    from helpdesk.repeat_issues import CACHE_PREFIX

    frappe.cache.delete_keys(f"{CACHE_PREFIX}:")
    with patch("helpdesk.api.repeat_issues.nowdate", return_value=str(today)):
        return run_as_user(user, lambda: frappe.call(method, **kwargs))


def use_support_department(name: str | None):
    """Patches Settings → Follow-ups so tickets belong to the department `name`
    (None for no support department); use it as a context manager."""
    return patch(
        "helpdesk.follow_ups.get_settings",
        return_value=frappe._dict(ticket_department=name),
    )


def capture_list_updates(fn, doctype: str = "Task") -> list[str]:
    """Runs `fn()` and returns the names of the `doctype` records it announced
    through the `list_update` realtime event (Frappe's own on save, or ours)."""
    sent = []
    publish = frappe.publish_realtime

    def record(event=None, message=None, *args, **kwargs):
        if event == "list_update" and (message or {}).get("doctype") == doctype:
            sent.append(message["name"])
        return publish(event, message, *args, **kwargs)

    with patch("frappe.publish_realtime", side_effect=record):
        fn()
    return sent


def make_task_created_on(project: str, subject: str, day, **values) -> str:
    """Creates an open Task in `project` that reads as created on `day` (creation is
    written straight to the database), plus any other `values`; returns its name."""
    task = make_task(project, subject).name
    frappe.db.set_value(
        "Task", task, {"creation": f"{day} 10:00:00", **values}, update_modified=False
    )
    return task


def record_versions(test_case):
    """Turns version history on for every save in the test, including saves inside the
    APIs. Tests skip it unless a save asks, and a task's activity is read from it."""
    from frappe.model.document import Document

    save = Document._save

    def save_with_version(self, ignore_permissions=None, ignore_version=None):
        keep = False if ignore_version is None else ignore_version
        return save(self, ignore_permissions, keep)

    recording = patch.object(Document, "_save", save_with_version)
    recording.start()
    test_case.addCleanup(recording.stop)


def save_task_as(user: str, task: str, **values):
    """Sets `values` on the Task and saves it as `user`, the way the task form does."""

    def save():
        doc = frappe.get_doc("Task", task)
        doc.update(values)
        doc.save()

    run_as_user(user, save)


def use_date_format(test_case, date_format: str):
    """Sets the site's date format (e.g. "dd-mm-yyyy") for the test and restores it after.
    Version history stores dates in this format."""
    previous = frappe.db.get_default("date_format")

    def apply(value):
        frappe.db.set_default("date_format", value)
        frappe.local.user_date_format = None

    apply(date_format)
    test_case.addCleanup(apply, previous)


def get_task_activity_as(user: str, task: str, kind: str | None = None) -> list[dict]:
    """The task's activity items as `user` sees them, newest first; only `kind` if given."""
    items = call_as_user(user, "helpdesk.tasky.api.get_task_activity", task=task)[
        "items"
    ]
    return [i for i in items if not kind or i["kind"] == kind]


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


def call_as_user(as_user: str, method: str, **kwargs):
    """Calls the whitelisted `method` (a dotted path) through `frappe.call` as `as_user`,
    then switches back to Administrator. `as_user` leaves `user` free for the method."""
    return run_as_user(as_user, lambda: frappe.call(method, **kwargs))


def hand_over_task_as(
    user: str, task: str, teammate: str, reason: str = "Moving to the Galom go-live"
):
    """`user` hands `task` over to `teammate` through the whitelisted hand_over_task."""
    return call_as_user(
        user,
        "helpdesk.tasky.api.hand_over_task",
        task=task,
        teammate=teammate,
        reason=reason,
    )


def reassign_task_as(user: str, task: str, assignee: str):
    """`user` gives `task` to `assignee` through the whitelisted update_task (Edit task)."""
    return call_as_user(
        user, "helpdesk.tasky.api.update_task", task=task, assigned_to=assignee
    )


def get_content_task(post: str, role: str) -> str | None:
    """The Task a content post made for one role ("Writer", "Designer", …)."""
    return frappe.db.get_value(
        "Task", {"content_post": post, "content_role": role}, "name"
    )


def get_content_tasks_as(user: str, start, end, **filters) -> dict:
    """The content calendar's Tasks view (helpdesk.api.content_tasks.get_content_tasks)
    for `user`: the role tasks of the posts going live between `start` and `end`."""
    return call_as_user(
        user,
        "helpdesk.api.content_tasks.get_content_tasks",
        start=str(start),
        end=str(end),
        **filters,
    )


def get_department_walls_as(as_user: str, user: str) -> list[str]:
    """`user`'s department wall roles, as Settings → Agents asks for them as `as_user`."""
    return call_as_user(
        as_user, "helpdesk.api.departments.get_department_walls", users=[user]
    )[user]


def set_department_wall_as(as_user: str, user: str, role: str):
    """`as_user` sets `user`'s department wall ("" for none) from Settings → Agents."""
    return call_as_user(
        as_user,
        "helpdesk.api.departments.set_department_wall",
        user=user,
        role=role,
    )


def set_department_heads_as(as_user: str, department: str, heads: list[str]):
    """`as_user` sets who heads `department` from Settings → Departments."""
    return call_as_user(
        as_user,
        "helpdesk.api.departments.set_department_heads",
        department=department,
        heads=heads,
    )


def get_visible_tasks(user: str, project: str | None = None) -> set[str]:
    """Names of the Tasks `user` may list (through `frappe.get_list`, so `task_query`
    and the department walls apply), in `project` when given."""
    filters = {"project": project} if project else {}
    return set(
        run_as_user(
            user,
            lambda: frappe.get_list(
                "Task", filters=filters, pluck="name", limit_page_length=0
            ),
        )
    )


def get_session_user_as(user: str) -> dict:
    """What the app boots with for `user` (`helpdesk.api.auth.get_user`): their flags."""
    return call_as_user(user, "helpdesk.api.auth.get_user")


def get_content_team_as(as_user: str, users: list[str]) -> list[str]:
    """Which of `users` are in the content team, as Settings → Agents asks as `as_user`."""
    return call_as_user(
        as_user, "helpdesk.api.departments.get_content_team", users=users
    )


def get_visible_content_posts(user: str) -> set[str]:
    """Names of the HD Content Posts `user` may list (through `frappe.get_list`, so the
    post's permission query and the content team rule apply)."""
    return set(
        run_as_user(
            user,
            lambda: frappe.get_list(
                "HD Content Post", pluck="name", limit_page_length=0
            ),
        )
    )


def get_task_completed_notices(task: str) -> list:
    """The Task Completed HD Notifications sent about `task` (user_to, user_from, message)."""
    return frappe.get_all(
        "HD Notification",
        filters={"reference_name": task, "notification_type": "Task Completed"},
        fields=["user_to", "user_from", "message"],
    )


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


def get_assignment_notices(user: str, reference_name) -> list[str]:
    """Messages of the Assignment HD Notifications sent to `user` about a document, oldest first."""
    return frappe.get_all(
        "HD Notification",
        filters={
            "user_to": user,
            "notification_type": "Assignment",
            "reference_name": str(reference_name),
        },
        order_by="creation asc",
        pluck="message",
    )


def get_assignment_state(user: str, task: str, source: str = "my_work") -> str | None:
    """The New / Reassigned mark `user` sees on `task` in My Work (`source` "my_work")
    or My Tasks ("my_tasks"); None when the task is unmarked or not in the list."""
    if source == "my_work":
        rows = call_as_user(user, "helpdesk.api.work.get_my_work")["items"]
    else:
        rows = call_as_user(user, "helpdesk.tasky.api.get_my_tasks")
    return next((r.get("assignment_state") for r in rows if r["name"] == task), None)


def send_task_reminder(task: str, escalate: bool = False) -> str:
    """Reminds `task`'s assignees through notify_users (the panel plus chat or email),
    as any reminder reaches people; returns the message sent."""
    from helpdesk.work_reminders import notify_users

    doc = frappe.get_doc("Task", task)
    message = f"Due tomorrow: {doc.subject}"
    notify_users(doc.assignees(), "Task", task, message, escalate=escalate)
    return message


FOLLOW_UP_MONDAY = datetime(2026, 10, 12, 11, 0)


def follow_up_context(now=None, holidays=(), **settings):
    """A follow-ups Context at `now` (default: Monday 12 Oct 2026, 11:00, in working
    hours) on a Monday-to-Saturday calendar with Sundays and `holidays` off, with
    HD Follow Up Settings' defaults plus `settings`."""
    from helpdesk import follow_ups

    doc = frappe.get_doc(follow_ups.SETTINGS)
    doc.update(settings)
    holidays = {getdate(day) for day in holidays}
    with patch.object(
        follow_ups,
        "working_day_checker",
        return_value=lambda day: day.weekday() != 6 and day not in holidays,
    ):
        calendar = follow_ups.WorkCalendar(getdate(now or FOLLOW_UP_MONDAY))
    calendar.sla = None
    return follow_ups.Context(doc, now or FOLLOW_UP_MONDAY, calendar)


def get_follow_up_notices(user: str, reference_name) -> list[dict]:
    """The follow-up HD Notifications `user` has about a document: message, key, read."""
    return frappe.get_all(
        "HD Notification",
        filters={
            "user_to": user,
            "reference_name": str(reference_name),
            "dedupe_key": ("like", "follow-up:%"),
        },
        fields=["name", "message", "dedupe_key", "read"],
    )


def set_follow_up_settings(**values):
    """Saves HD Follow Up Settings with `values`."""
    doc = frappe.get_doc("HD Follow Up Settings")
    doc.update(values)
    doc.save(ignore_permissions=True)
    return doc


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


def get_chat_secret(fieldname: str) -> str | None:
    """The stored (decrypted) value of a Password field in HD Chat Settings, or None."""
    return frappe.get_doc("HD Chat Settings").get_password(
        fieldname, raise_exception=False
    )


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
    """A fake requests response (Microsoft Graph and its token endpoint, the Expo push
    service) whose json() is `payload`."""
    from unittest.mock import MagicMock

    response = MagicMock(status_code=status)
    response.json.return_value = payload or {}
    return response


def enable_mobile_push():
    frappe.db.set_single_value("HD Settings", "enable_mobile_push", 1)


def disable_mobile_push():
    frappe.db.set_single_value("HD Settings", "enable_mobile_push", 0)


TEST_MS_TENANT = "6f1c2b9e-0d4a-4c1e-9a57-3b2f8e4d1a10"
TEST_MS_CLIENT = "0b7e4c2a-91d3-4f6b-8e15-c2a9d7f3e604"


def make_oauth_client(app_name: str = "TBO Smart Test"):
    """Creates (or fetches) an OAuth Client set up like TBO Smart's: public app, scopes
    `all openid`, Agent and Agent Manager allowed."""
    name = frappe.db.get_value("OAuth Client", {"app_name": app_name})
    if name:
        return frappe.get_doc("OAuth Client", name)
    return frappe.get_doc(
        {
            "doctype": "OAuth Client",
            "app_name": app_name,
            "skip_authorization": 1,
            "scopes": "all openid",
            "redirect_uris": "tbosmart://oauth/callback",
            "default_redirect_uri": "tbosmart://oauth/callback",
            "grant_type": "Authorization Code",
            "response_type": "Code",
            "allowed_roles": [{"role": "Agent"}, {"role": "Agent Manager"}],
        }
    ).insert(ignore_permissions=True)


def enable_microsoft_sso(oauth_client: str):
    """Turns on TBO Smart's Microsoft single sign-in for the test tenant and app."""
    frappe.db.set_single_value(
        "HD Settings",
        {
            "enable_microsoft_sso": 1,
            "microsoft_tenant_id": TEST_MS_TENANT,
            "microsoft_client_id": TEST_MS_CLIENT,
            "mobile_oauth_client": oauth_client,
        },
    )


def disable_microsoft_sso():
    frappe.db.set_single_value("HD Settings", "enable_microsoft_sso", 0)


def issue_sso_token(user: str, client) -> dict:
    """An OAuth Bearer Token for `user` from `client`, as a Microsoft sign-in to TBO
    Smart issues it (no ID token needed)."""
    from helpdesk.api.mobile_auth import issue_tokens

    return issue_tokens(user, client)


def bearer_token_works(access_token: str) -> bool:
    """Whether Frappe's OAuth server accepts `access_token` on an API call, as it does
    for an `Authorization: Bearer` header."""
    from urllib.parse import urlencode

    from frappe.integrations.oauth2 import get_oauth_server

    uri = "https://hub.example/api/method/helpdesk.api.mobile.get_me?" + urlencode(
        {"access_token": access_token}
    )
    valid, _request = get_oauth_server().verify_request(
        uri, "GET", None, {}, ["all", "openid"]
    )
    return valid


def enable_offboarding(domains: str = "offboarding.example", **values):
    """Switches on offboarding from Microsoft for `domains`, out of dry run and with a
    limit of 5, reading the directory with enable_teams_meetings' app; `values`
    override HD Settings fields."""
    enable_teams_meetings()
    frappe.db.set_single_value(
        "HD Settings",
        {
            "offboard_removed_microsoft_users": 1,
            "offboarding_domains": domains,
            "offboarding_dry_run": 0,
            "offboarding_max_disables": 5,
            **values,
        },
    )


def microsoft_account(email: str, enabled: bool = True, **values) -> dict:
    """One account as Microsoft Graph's /users lists it."""
    return {
        "id": frappe.generate_hash(length=12),
        "accountEnabled": enabled,
        "mail": email,
        "userPrincipalName": email,
        "otherMails": [],
        "proxyAddresses": [f"SMTP:{email}"],
        **values,
    }


def mock_microsoft_directory(test_case, *pages: list, status: int = 200):
    """Microsoft Graph for the rest of the test: a fake app sign-in, then every read of
    /users answered with `pages` of accounts (chained by @odata.nextLink), or refused
    with `status`. Returns the mock of the Graph calls."""
    from helpdesk.teams_meetings import GRAPH

    pages = pages or ([],)
    marker = "$skiptoken=page"

    def answer(method, url, **kwargs):
        if status >= 300:
            error = {"code": "Authorization_RequestDenied", "message": "Denied"}
            return graph_response({"error": error}, status)
        number = int(url.rpartition(marker)[2]) if marker in url else 0
        body = {"value": pages[number]}
        if number + 1 < len(pages):
            body["@odata.nextLink"] = f"{GRAPH}/users?{marker}{number + 1}"
        return graph_response(body)

    token = patch(
        "helpdesk.teams_meetings.requests.post",
        return_value=graph_response(
            {"access_token": fake_graph_token(["User.Read.All"]), "expires_in": 3600}
        ),
    )
    calls = patch("helpdesk.teams_meetings.requests.request", side_effect=answer)
    token.start()
    test_case.addCleanup(token.stop)
    mocked = calls.start()
    test_case.addCleanup(calls.stop)
    return mocked


def make_rsa_key():
    """A fresh RSA private key, standing in for one of Microsoft's signing keys."""
    from cryptography.hazmat.primitives.asymmetric import rsa

    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def mock_microsoft_keys(test_case, key, kid: str = "test-key"):
    """Serves `key`'s public half as the tenant's JWKS (Entra's signing keys) for the
    rest of the test, and forgets keys cached by earlier tests."""
    from jwt import PyJWKClient
    from jwt.algorithms import RSAAlgorithm

    from helpdesk.api.mobile_auth import jwks_client

    jwk = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    jwks_client.cache_clear()
    test_case.addCleanup(jwks_client.cache_clear)
    fetch = patch.object(PyJWKClient, "fetch_data", return_value={"keys": [jwk]})
    fetch.start()
    test_case.addCleanup(fetch.stop)


def refresh_oauth_token(client_id: str, refresh_token: str) -> dict:
    """POSTs grant_type=refresh_token to Frappe's own get_token, the way the app
    refreshes, and returns its JSON answer (new tokens, or `error`). Frappe raises for
    a refresh token it has never issued (a 404 over HTTP); that is an `error` too."""
    from frappe.integrations.oauth2 import get_token
    from werkzeug.test import EnvironBuilder
    from werkzeug.wrappers import Request

    builder = EnvironBuilder(
        path="/api/method/frappe.integrations.oauth2.get_token",
        method="POST",
        base_url="https://hub.example",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
    )
    previous = getattr(frappe.local, "request", None), frappe.local.response
    frappe.local.request = Request(builder.get_environ())
    try:
        get_token()
        return dict(frappe.local.response)
    except frappe.DoesNotExistError:
        return {"error": "unknown_refresh_token"}
    finally:
        frappe.local.request, frappe.local.response = previous


def microsoft_id_token(key, email: str, kid: str = "test-key", **claims) -> str:
    """A Microsoft-shaped ID token for `email`, signed RS256 with `key`: valid for the
    test tenant and app unless `claims` override (or, with None, remove) a claim."""
    import time

    import jwt

    now = int(time.time())
    payload = {
        "iss": f"https://login.microsoftonline.com/{TEST_MS_TENANT}/v2.0",
        "aud": TEST_MS_CLIENT,
        "tid": TEST_MS_TENANT,
        "sub": "test-subject",
        "oid": "test-object-id",
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
        "uti": frappe.generate_hash(length=22),
        "email": email,
        "preferred_username": email,
        "name": email,
    }
    payload.update(claims)
    payload = {k: v for k, v in payload.items() if v is not None}
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


def call_mobile_as(as_user: str, method: str, **kwargs):
    """Calls helpdesk.api.mobile.<method> through `frappe.call` as `as_user`, the way
    the TBO Smart app does; returns the whole {"v", "data", …} answer. `as_user` leaves
    `user` free for the method."""
    return call_as_user(as_user, f"helpdesk.api.mobile.{method}", **kwargs)


def call_mobile_on(as_user: str, today, method: str, **kwargs):
    """call_mobile_as with today fixed and the Scoreboard's cached numbers dropped,
    so only the test's records fall in the period (as call_team_dashboard does)."""
    from helpdesk.team_dashboard import clear_cache

    clear_cache()
    with patch("helpdesk.api.mobile.nowdate", return_value=str(today)):
        return call_mobile_as(as_user, method, **kwargs)


def make_follow_up(
    doctype: str, name, user: str, level: int = 0, severity: str = "overdue"
):
    """A follow-up on a task or ticket for `user` (its owner and its only recipient) at
    `level`, shaped as the engine finds them; a "breach" is an SLA one."""
    from helpdesk.follow_ups import FollowUp

    return FollowUp(
        doctype=doctype,
        name=str(name),
        title=str(name),
        rule="sla" if severity == "breach" else "overdue",
        stage=f"L{level}",
        severity=severity,
        text=f"Follow up on {name}",
        recipients=[user],
        owners=[user],
        level=level,
    )


def register_device_as(user: str, token: str, platform: str = "ios") -> dict:
    """Registers a phone's push token for `user` through the mobile API; returns the
    device the API sends back."""
    return call_mobile_as(
        user, "register_device", token=token, platform=platform, app_version="1.0.0"
    )["data"]


def get_pushed_messages(post_mock, notification: str) -> list[dict]:
    """The Expo messages a mocked requests.post sent for one HD Notification."""
    return [
        message
        for call in post_mock.call_args_list
        for message in call.kwargs.get("json") or []
        if message["data"]["notification"] == notification
    ]


def set_work_settings(**values):
    """Saves HD Work Settings (AI estimates, weekly off, Saturdays off) with `values`."""
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


INTAKE_INBOX = "intake-inbox@example.com"


def set_intake_settings(rules: list[dict] | None = None, **values):
    """Overwrite HD Intake Settings for a test: `rules` (dicts of HD Intake Rule fields,
    enabled unless they say otherwise) replace the rule list when given; other values
    (apply_triage, default_team, routes, public_email_domains...) are set as they are.
    Callers roll back afterwards."""
    doc = frappe.get_single("HD Intake Settings")
    if rules is not None:
        doc.set("rules", [{"enabled": 1, **rule} for rule in rules])
    doc.update(values)
    doc.save(ignore_permissions=True)
    frappe.clear_document_cache("HD Intake Settings", "HD Intake Settings")


def make_mail_ticket(subject: str, sender: str, **values):
    """Creates an HD Ticket the way an incoming email opens one: through the intake
    inbox (an incoming Email Account), so the intake rules and the mail filter apply."""
    inbox = make_email_account(
        INTAKE_INBOX, enable_outgoing=0, enable_incoming=1, append_to="HD Ticket"
    )
    return make_ticket(
        subject=subject, raised_by=sender, email_account=inbox.name, **values
    )


def make_intake_mail(subject: str, sender: str, body: str = "Alert details") -> bytes:
    """A raw incoming email, as the mailbox hands it to Frappe's InboundMail."""
    return (
        f"From: {sender}\r\nTo: {INTAKE_INBOX}\r\nSubject: {subject}\r\n"
        f"Message-ID: <{frappe.generate_hash(length=12)}@mail.example>\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n\r\n{body}\r\n"
    ).encode()


def get_intake_logs(sender: str) -> list[dict]:
    """HD Intake Log rows for `sender`, oldest first: action, rule and ticket."""
    return frappe.get_all(
        "HD Intake Log",
        filters={"sender": sender},
        fields=["action", "rule", "ticket"],
        order_by="creation asc",
    )


def get_ticket_comments(ticket) -> list[str]:
    """The contents of a ticket's HD Ticket Comments, oldest first."""
    return frappe.get_all(
        "HD Ticket Comment",
        filters={"reference_ticket": str(ticket)},
        pluck="content",
        order_by="creation asc",
    )


def make_domain_customer(name: str, domain: str = "", email_domains: str = ""):
    """Creates (or updates) an HD Customer with a Domain and Other Email Domains."""
    doc = (
        frappe.get_doc("HD Customer", name)
        if frappe.db.exists("HD Customer", name)
        else frappe.get_doc({"doctype": "HD Customer", "customer_name": name})
    )
    doc.domain = domain
    doc.email_domains = email_domains
    doc.save(ignore_permissions=True)
    return doc


def make_ticket_type(name: str):
    """Creates an HD Ticket Type if the site doesn't have it yet."""
    if not frappe.db.exists("HD Ticket Type", name):
        frappe.get_doc({"doctype": "HD Ticket Type", "name": name}).insert(
            ignore_permissions=True
        )
    return name


def set_ticket_status(ticket, status: str):
    """Saves `status` on the ticket through the document, so its save hooks run."""
    doc = frappe.get_doc("HD Ticket", str(ticket))
    doc.status = status
    doc.save(ignore_permissions=True)
    return doc


def get_feedback_mails(sendmail_mock) -> list:
    """The feedback-request mails among the calls a patched frappe.sendmail received."""
    return [
        c
        for c in sendmail_mock.call_args_list
        if c.kwargs.get("email_headers", {}).get("X-Auto-Generated")
        == "hd-email-feedback"
    ]


def log_activity_as(user: str, ticket, action: str):
    """Records a ticket activity line (e.g. "set priority to Low") as made by `user`."""
    from helpdesk.helpdesk.doctype.hd_ticket_activity.hd_ticket_activity import (
        log_ticket_activity,
    )

    activity = log_ticket_activity(str(ticket), action)
    activity.db_set("owner", user, update_modified=False)
    return activity


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


def make_article(
    title: str, content: str, status: str = "Published", category: str | None = None
):
    """Creates an HD Article with `title` and HTML `content` (Published unless `status` says otherwise), optionally in `category`."""
    return frappe.get_doc(
        {
            "doctype": "HD Article",
            "title": title,
            "content": content,
            "status": status,
            "category": category,
        }
    ).insert(ignore_permissions=True)


def make_article_category(category_name: str):
    """Creates an HD Article Category named `category_name`."""
    return frappe.get_doc(
        {"doctype": "HD Article Category", "category_name": category_name}
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


def enable_merge_bot_trigger(**values):
    """Turns on the GitHub sync with the merge bot trigger and a GitHub token (plus any
    overrides), and forgets the last dispatch so the debounce starts fresh."""
    clear_merge_bot_debounce()
    return enable_github_sync(
        **{
            "trigger_merge_bot": 1,
            "github_token": "ghp_sync_token",
            "merge_bot_token": None,
            **values,
        }
    )


def clear_merge_bot_debounce():
    from helpdesk.merge_bot import DEBOUNCE_KEY

    frappe.cache.delete_value(DEBOUNCE_KEY)


def get_github_secret(fieldname: str) -> str | None:
    """The stored (decrypted) value of a Password field in HD GitHub Settings, or None."""
    return frappe.get_doc("HD GitHub Settings").get_password(
        fieldname, raise_exception=False
    )


def make_github_delivery(event: str = "pull_request", **values):
    """Records an HD GitHub Delivery (as receive_webhook does) without processing it."""
    return frappe.get_doc(
        {
            "doctype": "HD GitHub Delivery",
            "delivery_id": frappe.generate_hash(length=20),
            "event": event,
            "action": "opened",
            "repo": GITHUB_TEST_REPO,
            "status": "Processed",
            **values,
        }
    ).insert(ignore_permissions=True)


def make_github_payload(event: str, action: str = "", **overrides) -> dict:
    """A minimal GitHub webhook payload shaped like the real one for `event`.

    Overrides: repo, number, title, body, branch, draft, merged, closed, login,
    comments, labels (names), review_state, review_body, reviewer, conclusion, sha, workflow,
    pull_requests (workflow_run / check_suite: PR numbers the run belongs to).
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
    if event in ("workflow_run", "check_suite"):
        payload[event] = {
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
        "labels": [{"name": label} for label in overrides.get("labels", ())],
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
    `fail=True` answers everything with HTTP 500. `answers` maps "METHOD url-suffix"
    (e.g. "GET /agents") to the JSON to answer with, or to None for HTTP 500.
    """

    def __init__(
        self,
        messages: list[dict] | None = None,
        fail: bool = False,
        answers: dict | None = None,
    ):
        self.messages = messages or []
        self.fail = fail
        self.answers = answers or {}
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
        # the last matching key wins, so a later override beats a default
        answer = next(
            (
                (value,)
                for key, value in reversed(list(self.answers.items()))
                if key.split(" ", 1)[0] == method and url.endswith(key.split(" ", 1)[1])
            ),
            None,
        )
        if self.fail or (answer and answer[0] is None):
            response.status_code = 500
            response.text = "Internal Server Error"
            return response
        response.status_code = 200
        if answer:
            response.json.return_value = answer[0]
        elif method == "GET":
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


CHATWOOT_TEST_PLATFORM_TOKEN = "test-chatwoot-platform-token"
CHATWOOT_TEST_SIGN_IN = f"{CHATWOOT_TEST_URL}/app/login?email=x&sso_auth_token=one-time"


def enable_chatwoot_sso(**values):
    """Turns on sign-in through TBO Support (HD Chatwoot Settings) with the bridge's test
    settings and a test Platform App token, plus any overrides."""
    return enable_chatwoot_bridge(
        **{
            "sso_enabled": 1,
            "platform_api_token": CHATWOOT_TEST_PLATFORM_TOKEN,
            "sso_create_users": 1,
            "sso_default_role": "agent",
            "sso_managers_as_admins": 1,
            **values,
        }
    )


def fake_chatwoot_platform(
    test_case,
    agents: list[dict] | None = None,
    chat_user_id: int = 501,
    answers: dict | None = None,
):
    """Patches Chatwoot for TBO Chat sign-in and returns the FakeChatwootAPI.

    The account has `agents` ({id, email, role}); creating a user answers with
    `chat_user_id`, and its one-time link is CHATWOOT_TEST_SIGN_IN. `answers`
    overrides any route, e.g. {"GET /login": None} for an HTTP 500.
    """
    api = FakeChatwootAPI(
        answers={
            "GET /agents": agents or [],
            "POST /platform/api/v1/users": {"id": chat_user_id},
            f"GET /users/{chat_user_id}/login": {"url": CHATWOOT_TEST_SIGN_IN},
            **(answers or {}),
        }
    )
    request = patch("helpdesk.chatwoot_bridge.requests.request", api)
    request.start()
    test_case.addCleanup(request.stop)
    return api


def open_tbo_chat(user: str, referer: str | None = None, **query) -> dict:
    """Calls helpdesk.api.chatwoot_sso.login as `user` (or "Guest") in a GET request
    carrying `referer` and the `query` arguments, and returns what it answered:
    frappe.local.response, a redirect or a page."""
    from werkzeug.test import EnvironBuilder
    from werkzeug.wrappers import Request

    from helpdesk import chatwoot_sso
    from helpdesk.api.chatwoot_sso import login

    builder = EnvironBuilder(
        path=chatwoot_sso.LOGIN_PATH,
        base_url="http://localhost",
        headers={"Referer": referer} if referer else None,
        query_string=query or None,
    )
    previous = (getattr(frappe.local, "request", None), frappe.local.form_dict)
    frappe.local.request = Request(builder.get_environ())
    frappe.local.response = frappe._dict({"docs": []})
    frappe.set_user(user)
    # after set_user, which empties form_dict
    frappe.local.form_dict = frappe._dict(query)
    try:
        login()
    finally:
        frappe.set_user("Administrator")
        frappe.local.request, frappe.local.form_dict = previous
    return dict(frappe.local.response)


def reset_chat_sign_in_limit(user: str):
    """Forgets `user`'s recent TBO Chat sign-ins, so the per-user limit and the
    signed-out check start afresh."""
    from helpdesk import chatwoot_sso

    frappe.cache.delete(frappe.cache.make_key(f"chatwoot-sso:{user}"))
    frappe.cache.delete_value(chatwoot_sso.opened_key(user))


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


def ai_description_answer(description: str) -> dict:
    """What call_haiku returns for a task description draft."""
    return {"response": {"description": description}, "usage": {}, "cost": 0}


# test-only keys: never real ones
OPENAI_TEST_KEY = "sk-proj-not-a-real-key"
ANTHROPIC_TEST_KEY = "sk-not-a-real-kimi-key"


def make_ai_provider(slot: str = "OpenAI", **values):
    """An ai_engine.AIProvider for one settings section (OpenAI or
    Anthropic-compatible) with test keys, without touching HDS Hub Settings."""
    from helpdesk.ai_engine import AIProvider

    defaults = {
        "OpenAI": {
            "kind": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-test-model",
            "api_key": OPENAI_TEST_KEY,
        },
        "Anthropic-compatible": {
            "kind": "Anthropic Compatible",
            "base_url": "https://api.moonshot.ai/anthropic",
            "model": "kimi-k2.6",
            "api_key": ANTHROPIC_TEST_KEY,
        },
    }[slot]
    return AIProvider(slot=slot, **{**defaults, **values})


def set_ai_providers(**values):
    """Sets the AI part of HDS Hub Settings: OpenAI primary with failover, both
    sections set up with test keys, plus any overrides (None clears a field).
    Forgets every pause and failure so each test starts clean."""
    from helpdesk.ai_engine import reset_provider_state

    doc = frappe.get_doc("HDS Hub Settings")
    doc.update(
        {
            "primary_ai_provider": "OpenAI",
            "ai_failover": 1,
            "openai_base_url": "https://api.openai.com/v1",
            "openai_model": "gpt-test-model",
            "openai_api_key": OPENAI_TEST_KEY,
            "ai_provider": "Anthropic Compatible",
            "ai_base_url": "https://api.moonshot.ai/anthropic",
            "default_triage_model": "kimi-k2.6",
            "anthropic_api_key": ANTHROPIC_TEST_KEY,
            **values,
        }
    )
    doc.save(ignore_permissions=True)
    reset_provider_state()
    clear_ai_alerts()
    return doc


def clear_ai_alerts():
    """Forgets which providers were alerted about and the outage mark."""
    from helpdesk.ai_engine import ALERT_KEY, OUTAGE_KEY, SLOTS

    frappe.cache.delete_value([OUTAGE_KEY, *(ALERT_KEY.format(slot) for slot in SLOTS)])


def openai_http_response(status: int = 200, body: dict | None = None, text=""):
    """A requests.Response stand-in for the OpenAI API: `body` as its JSON, or
    an answer with `text` and token counts when no body is given."""
    from unittest.mock import MagicMock

    if body is None:
        body = {
            "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 78, "completion_tokens": 40},
        }
    return MagicMock(
        ok=status < 400,
        status_code=status,
        reason="Error" if status >= 400 else "OK",
        json=MagicMock(return_value=body),
    )


def anthropic_status_error(status: int, body: dict | None = None):
    """The Anthropic SDK's APIStatusError for an HTTP `status` with an error
    `body`, built without an HTTP response (the SDK's HTTP client varies by version)."""
    import anthropic

    error = anthropic.APIStatusError.__new__(anthropic.APIStatusError)
    Exception.__init__(error, f"Error code: {status}")
    error.status_code = status
    error.body = body
    error.message = f"Error code: {status}"
    return error


def patch_anthropic_sdk(test_case, *answers):
    """Patches the Anthropic SDK client in helpdesk.ai_engine for `test_case`;
    each Messages call returns (or raises) the next of `answers`. Returns the
    patched client class."""
    from helpdesk import ai_engine

    sdk = patch.object(ai_engine.anthropic, "Anthropic")
    client_cls = sdk.start()
    test_case.addCleanup(sdk.stop)
    client_cls.return_value.messages.create.side_effect = list(answers)
    return client_cls


def anthropic_answer(text: str, stop_reason: str = "end_turn"):
    """A Messages API response with one text block and token counts."""
    from unittest.mock import MagicMock

    response = MagicMock(stop_reason=stop_reason)
    response.content = [MagicMock(type="text", text=text)]
    response.usage = MagicMock(
        input_tokens=10,
        output_tokens=5,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return response


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


def make_timesheet(
    project: str | None,
    hours: float,
    from_time,
    task: str | None = None,
    billable: int = 1,
    notes: str | None = None,
):
    """Creates a draft Timesheet with one time log of `hours` on `project` (and `task`).

    `billable=0` logs internal time that doesn't use up a customer's support hours;
    `notes` is the log's work note.
    """
    return frappe.get_doc(
        {
            "doctype": "Timesheet",
            "time_logs": [
                {
                    "project": project,
                    "task": task,
                    "hours": hours,
                    "from_time": from_time,
                    "custom_billable": billable,
                    "description": notes,
                }
            ],
        }
    ).insert(ignore_permissions=True)


def make_support_contract(customer: str, start_date, end_date, **kwargs):
    """Creates an Active HD Support Contract for `customer`: 10 hours a month,
    alert at 80%, no roll-over, unless overridden."""
    return frappe.get_doc(
        {
            "doctype": "HD Support Contract",
            "contract_name": f"{customer} AMC",
            "customer": customer,
            "contract_type": "AMC",
            "status": "Active",
            "start_date": start_date,
            "end_date": end_date,
            "billing_period": "Monthly",
            "hours_per_period": 10,
            "alert_threshold": 80,
            **kwargs,
        }
    ).insert(ignore_permissions=True)


class FakeCRM:
    """In-memory stand-in for the TBO CRM site's REST API (helpdesk.integrations.crm.client)."""

    def __init__(
        self,
        users: list[dict] | None = None,
        failing: tuple = (),
        organizations: list[str] | None = None,
        erp_customers: list[str] | None = None,
    ):
        self.users = {u["name"]: {"roles": [], "enabled": 1, **u} for u in users or []}
        self.failing = set(failing)
        # (email, role) for each sales role given on the CRM site
        self.role_calls: list[tuple[str, str]] = []
        # False: Frappe CRM is gone from the CRM site, so there's no CRM Organization
        self.has_crm_organizations = True
        # an Exception reading ERPNext Customers raises, as the CRM site would
        self.customers_error: Exception | None = None
        self.orgs = [{"name": o, "organization_name": o} for o in organizations or []]
        self.erp = list(erp_customers or [])
        # (ERPNext Customer name, its Account Manager), for filling empty ticket owners
        self.account_managers: list[tuple[str, str]] = []
        # ERPNext on the CRM site, for invoicing: one company and its records
        self.company_rows = [{"name": FAKE_COMPANY, "default_currency": "INR"}]
        self.item_rows = [{"name": FAKE_ITEM, "item_name": "Support hours"}]
        self.company_records = {
            "taxes_templates": [{"name": FAKE_TAXES, "title": "GST 18%"}],
            "income_accounts": [{"name": "Service Income - TBO"}],
            "cost_centers": [{"name": "Main - TBO"}],
        }
        self.invoices: dict[str, dict] = {}
        self.fail_invoices = False
        # ERPNext on the CRM site, for holidays and leave
        self.company_rows[0]["default_holiday_list"] = FAKE_HOLIDAY_LIST
        self.holiday_rows: dict[str, list[dict]] = {FAKE_HOLIDAY_LIST: []}
        self.leave_rows: list[dict] = []
        self.employee_rows: list[dict] = []
        # an Exception the holiday or leave reads raise, as the CRM site would
        self.holidays_error: Exception | None = None
        self.leave_error: Exception | None = None
        # TBO Smart's hub leads API: what each method answers (an Exception: that
        # method raises it), the calls made as (method, post, params), and an
        # Exception every call raises
        self.base = "https://erp.example"
        self.lead_answers: dict[str, object] = {}
        self.lead_calls: list[tuple[str, bool, dict]] = []
        # the full method path of each call, e.g. tbo_smart.api.hub_proposals.get_proposal
        self.lead_paths: list[str] = []
        self.lead_error: Exception | None = None

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
            if u.get("enabled")
            and {r.get("role") for r in u.get("roles") or []}
            & {"Sales User", "Sales Manager"}
        ]

    def organizations(self):
        return list(self.orgs)

    def erp_customers(self, strict=False):
        if self.customers_error:
            if strict:
                raise self.customers_error
            return []
        return [{"name": c, "organization_name": c} for c in self.erp]

    def create_organization(self, name, website=None):
        self.orgs.append({"name": name, "organization_name": name, "website": website})
        return self.orgs[-1]

    def add_role(self, email, role):
        self.role_calls.append((email, role))
        self.users[email]["roles"].append({"role": role})

    def has_doctype(self, doctype):
        return doctype != "CRM Organization" or self.has_crm_organizations

    def call(self, method, post=False, **params):
        name = method.rsplit(".", 1)[-1]
        self.lead_calls.append((name, post, params))
        self.lead_paths.append(method)
        if self.lead_error:
            raise self.lead_error
        answer = self.lead_answers.get(name)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def download(self, method, **params):
        """A file method (a call's recording): `lead_answers[name]` is its
        (bytes, content type); recorded as a GET call."""
        name = method.rsplit(".", 1)[-1]
        self.lead_calls.append((name, False, params))
        self.lead_paths.append(method)
        if self.lead_error:
            raise self.lead_error
        return self.lead_answers.get(name) or (b"", "")

    def customers(self):
        return [{"name": c, "customer_name": c} for c in self.erp]

    def customer_account_managers(self):
        return [
            {"name": c, "customer_name": c, "account_manager": manager}
            for c, manager in self.account_managers
        ]

    def companies(self):
        return list(self.company_rows)

    def service_items(self):
        return list(self.item_rows)

    def taxes_templates(self, company):
        return (
            self.company_records["taxes_templates"] if company == FAKE_COMPANY else []
        )

    def income_accounts(self, company):
        return (
            self.company_records["income_accounts"] if company == FAKE_COMPANY else []
        )

    def cost_centers(self, company):
        return self.company_records["cost_centers"] if company == FAKE_COMPANY else []

    def template_taxes(self, template):
        return [
            {"charge_type": "On Net Total", "account_head": "GST - TBO", "rate": 18}
        ]

    def create_sales_invoice(self, invoice):
        from helpdesk.integrations.crm.client import CRMError

        if self.fail_invoices:
            raise CRMError("CRM said no")
        name = f"ACC-SINV-2026-{len(self.invoices) + 1:05d}"
        self.invoices[name] = {**invoice, "name": name, "docstatus": 0}
        return dict(self.invoices[name])

    def delete_sales_invoice(self, name):
        self.invoices.pop(name, None)

    def get_doc(self, doctype, name):
        return self.invoices.get(name) if doctype == "Sales Invoice" else None

    def sales_invoices(self, names):
        return [
            {"status": "Draft", **self.invoices[n]} for n in names if n in self.invoices
        ]

    def holiday_lists(self):
        return [{"name": name} for name in self.holiday_rows]

    def company_holiday_lists(self):
        return [
            {"name": c["name"], "default_holiday_list": c.get("default_holiday_list")}
            for c in self.company_rows
        ]

    def holidays(self, holiday_list):
        from helpdesk.integrations.crm.client import CRMError

        if self.holidays_error:
            raise self.holidays_error
        if holiday_list not in self.holiday_rows:
            raise CRMError(f"No holiday list {holiday_list}")
        return [dict(row) for row in self.holiday_rows[holiday_list]]

    def approved_leave(self, start, end):
        if self.leave_error:
            raise self.leave_error
        return [
            dict(row)
            for row in self.leave_rows
            if str(row["to_date"]) >= str(start) and str(row["from_date"]) <= str(end)
        ]

    def employees(self, names):
        if self.leave_error:
            raise self.leave_error
        return [dict(e) for e in self.employee_rows if e["name"] in names]


FAKE_COMPANY = "TBO India Pvt Ltd"
FAKE_ITEM = "Support Hours"
FAKE_TAXES = "GST 18% - TBO"
FAKE_HOLIDAY_LIST = "TBO India 2026"


def erp_holiday(day, description: str, weekly_off: int = 0) -> dict:
    """A row of an ERPNext Holiday List as the CRM site returns it (for FakeCRM.holiday_rows)."""
    return {
        "holiday_date": str(day),
        "description": description,
        "weekly_off": weekly_off,
    }


def erp_leave_application(
    name: str, employee: str, from_date: str, to_date: str, **values
) -> dict:
    """An approved ERPNext Leave Application as the CRM site returns it (for
    FakeCRM.leave_rows)."""
    return {
        "name": name,
        "employee": employee,
        "employee_name": employee,
        "from_date": from_date,
        "to_date": to_date,
        "leave_type": "Casual Leave",
        "half_day": 0,
        **values,
    }


def get_doc_refusing_agents(get_doc):
    """Wraps frappe.get_doc so building an HD Agent fails like a validation error would
    (for patching the CRM user sync); every other document is built as usual."""

    def wrapped(*args, **kwargs):
        if args and isinstance(args[0], dict) and args[0].get("doctype") == "HD Agent":
            raise frappe.ValidationError("agent refused")
        return get_doc(*args, **kwargs)

    return wrapped


def enable_leads(teams: tuple[str, ...] = ()):
    """Turns on the CRM connection and the Leads page, for `teams` (every agent when
    none). The connection itself is faked with FakeCRM in the tests. Clears the Leads
    page's cached reads (Redis outlives a test) so each test asks the fake CRM afresh."""
    frappe.db.set_single_value(
        "HD CRM Settings",
        {"enabled": 1, "enable_leads": 1, "leads_teams": "\n".join(teams)},
    )
    frappe.cache.delete_keys("hd_leads:")


def make_sales_manager(email: str, first_name: str = "Manager") -> str:
    """An agent with the Sales Manager role (created when the hub doesn't have it yet),
    who may use Leads and gets the 6 pm Daily Sales Report."""
    create_agent(email, first_name, "Sales")
    if not frappe.db.exists("Role", "Sales Manager"):
        frappe.get_doc({"doctype": "Role", "role_name": "Sales Manager"}).insert(
            ignore_permissions=True
        )
    frappe.get_doc("User", email).add_roles("Sales Manager")
    return email


def daily_report_person(user: str, full_name: str, **fields) -> dict:
    """One salesperson's row as TBO Smart's get_daily_report answers it: every count 0
    and every list empty unless given."""
    return {
        "user": user,
        "full_name": full_name,
        "calls_total": 0,
        "calls_connected": 0,
        "fresh_leads": 0,
        "follow_up_leads": 0,
        "positive_leads": [],
        "new_quotations": {"count": 0, "value": 0, "items": []},
        "meetings_held": 0,
        "follow_ups_done": 0,
        "follow_ups_overdue": 0,
        "new_leads": [],
        "week_to_date": {"leads": 0, "meetings": 0, "proposals": 0, "follow_ups": 0},
        **fields,
    }


def daily_report(people: list[dict], date: str = "2026-10-26") -> dict:
    """A get_daily_report answer for `people` (daily_report_person rows) on `date`."""
    return {
        "date": date,
        "week_from": "2026-10-26",
        "currency": "INR",
        "people": people,
    }


def lead_intake(people: list[dict], by_owner: list[dict]) -> dict:
    """A get_lead_intake answer: today's `by_owner` rows ({user, full_name, count}) with
    yesterday empty, and the scope's `people` ({user, full_name})."""
    total = sum(row["count"] for row in by_owner)
    return {
        "days": [
            {"date": "2026-10-26", "total": total, "by_owner": by_owner},
            {"date": "2026-10-25", "total": 0, "by_owner": []},
        ],
        "people": people,
    }


def sales_person(user: str, **counts) -> dict:
    """One salesperson's row as TBO Smart's get_sales_activity answers it: every
    count 0 unless given (contacted, moms_submitted, quotations_sent, won, …)."""
    row = {
        field: 0
        for field in (
            "contacted",
            "meetings_held",
            "moms_submitted",
            "mom_pending",
            "quotations_sent",
            "follow_ups_done",
            "follow_ups_on_time",
            "follow_ups_overdue",
            "new",
            "won",
            "won_value",
            "calls",
        )
    }
    return {"user": user, "full_name": user, **row, **counts}


def make_hd_leave(
    user: str, from_date, to_date, half_day: int = 0, leave_application=None
):
    """An approved leave of `user` in HD Leave, as the CRM holiday sync stores it."""
    return frappe.get_doc(
        {
            "doctype": "HD Leave",
            "leave_application": leave_application or f"HR-LAP-TEST-{user}-{from_date}",
            "user": user,
            "from_date": from_date,
            "to_date": to_date,
            "half_day": half_day,
        }
    ).insert(ignore_permissions=True)


def set_standup_settings(**values):
    """Saves HD Standup Settings (the async stand-up) with `values`, on by default."""
    doc = frappe.get_doc("HD Standup Settings")
    doc.update({"enabled": 1, **values})
    doc.save(ignore_permissions=True)
    frappe.clear_document_cache("HD Standup Settings", "HD Standup Settings")
    return doc


def standup_calendar(today, holidays=()):
    """A follow-ups WorkCalendar at `today` on a Monday-to-Saturday week with Sundays
    and `holidays` off and no SLA hours: what the stand-up counts working days with."""
    from helpdesk import follow_ups

    holidays = {getdate(day) for day in holidays}
    with patch.object(
        follow_ups,
        "working_day_checker",
        return_value=lambda day: day.weekday() != 6 and day not in holidays,
    ):
        calendar = follow_ups.WorkCalendar(getdate(today))
    calendar.sla = None
    return calendar


def make_standup(user: str, day, department: str | None = None, **values):
    """Creates `user`'s HD Standup for `day` directly, a Draft unless `values` says
    otherwise; `values` may hold the yesterday, today and blockers rows (dicts with
    kind and title, and reference_doctype, reference_name and project for linked work)."""
    return frappe.get_doc(
        {
            "doctype": "HD Standup",
            "user": user,
            "date": getdate(day),
            "department": department,
            "status": "Draft",
            **values,
        }
    ).insert(ignore_permissions=True)


def get_standup_notices(user: str, standup: str) -> list[str]:
    """The messages of the HD Notifications `user` got about a stand-up, oldest first."""
    return frappe.get_all(
        "HD Notification",
        filters={
            "user_to": user,
            "reference_doctype": "HD Standup",
            "reference_name": standup,
        },
        order_by="creation asc",
        pluck="message",
    )


def make_content_post_at(
    title: str, customer: str, publish_on, team: dict | None = None, **values
) -> str:
    """Creates a Drafting HD Content Post going live at `publish_on` with `team` (e.g.
    {"writer": user, "designer": user}), so its role tasks are made and given out, then
    sets `values` (a later status such as Client Review or Changes Requested,
    client_review_since, head_feedback …) straight in the database, past the post's
    approval guards. Returns the post's name."""
    post = make_content_post(
        title,
        customer,
        status="Drafting",
        publish_on=str(publish_on),
        **(team or {}),
    ).name
    if values:
        frappe.db.set_value("HD Content Post", post, values, update_modified=False)
    return post


def log_post_move(post: str, user: str, day, old: str, new: str) -> str:
    """Records in the post's history (a Version) that `user` changed its status from
    `old` to `new` on `day` at 11:00, as the stand-up's "moved yesterday" reads it."""
    version = frappe.get_doc(
        {
            "doctype": "Version",
            "ref_doctype": "HD Content Post",
            "docname": post,
            "data": json.dumps({"changed": [["status", old, new]]}),
        }
    ).insert(ignore_permissions=True)
    frappe.db.set_value(
        "Version",
        version.name,
        {"owner": user, "creation": f"{getdate(day)} 11:00:00"},
        update_modified=False,
    )
    return version.name


def complete_task_on(task: str, day) -> None:
    """Marks a Task Completed on `day` straight in the database, as if its assignee
    finished it that day (its ToDos stay as they are)."""
    frappe.db.set_value("Task", task, {"status": "Completed", "completed_on": day})


def enable_invoicing(**values):
    """Turns invoicing on in HD CRM Settings with FakeCRM's company and item and a
    default rate of 1000 INR an hour, without checking them (pair with a patched FakeCRM).
    Adds the INR Currency when the test site has none."""
    if not frappe.db.exists("Currency", "INR"):
        frappe.get_doc(
            {"doctype": "Currency", "currency_name": "INR", "enabled": 1, "symbol": "₹"}
        ).insert(ignore_permissions=True)
    frappe.db.set_single_value(
        "HD CRM Settings",
        {
            "site_url": "https://crm.example",
            "api_key": "test-key",
            "invoice_company": FAKE_COMPANY,
            "invoice_item": FAKE_ITEM,
            "invoice_taxes_template": None,
            "invoice_income_account": None,
            "invoice_cost_center": None,
            "invoice_hourly_rate": 1000,
            "invoice_currency": "INR",
            **values,
        },
    )
    frappe.clear_document_cache("HD CRM Settings", "HD CRM Settings")


def get_billed_invoices(names: list[str]) -> dict[str, str | None]:
    """{time log: the HD Customer Invoice it is billed on} for Timesheet Detail names."""
    return dict(
        frappe.get_all(
            "Timesheet Detail",
            filters={"name": ("in", names)},
            fields=["name", "custom_billed_invoice"],
            as_list=True,
            limit_page_length=0,
        )
    )


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


def make_signoff_template(template_name: str, questions: list[tuple[str, str]]):
    """An active HD Signoff Template; `questions` is a list of (section, question)."""
    if frappe.db.exists("HD Signoff Template", template_name):
        frappe.delete_doc("HD Signoff Template", template_name, force=True)
    return frappe.get_doc(
        {
            "doctype": "HD Signoff Template",
            "template_name": template_name,
            "module": template_name,
            "is_active": 1,
            "items": [{"section": s, "question": q} for s, q in questions],
        }
    ).insert(ignore_permissions=True)


def make_signoff(
    project: str, contact: str, trainer: str, template: str | None = None, **values
):
    """A Draft HD Project Signoff for `project`, signed by the customer contact `contact`.

    Without a template, pass the questions as `items`.
    """
    return frappe.get_doc(
        {
            "doctype": "HD Project Signoff",
            "project": project,
            "template": template,
            "module_title": values.pop("module_title", template or "Accounts"),
            "trainer": trainer,
            "signatory_contact": contact,
            **values,
        }
    ).insert(ignore_permissions=True)


def open_signoff_link(signoff) -> str:
    """Issues and saves a customer link for the sign-off; returns the raw token the email would carry."""
    token = signoff.issue_link()
    signoff.save(ignore_permissions=True)
    return token


def signoff_session(signoff, email: str | None = None):
    """Patches the sign-off page so its calls run in a verified session for `signoff`.

    The session's email is the signatory's unless `email` says otherwise.
    """
    from helpdesk.api import signoff_portal

    session = {
        "signoff": signoff.name,
        "token_hash": signoff.link_token_hash,
        "email": email or signoff.signatory_email,
    }
    return patch.object(signoff_portal, "get_session", return_value=session)


def fake_request(test_case, cookies: dict | None = None):
    """Gives frappe.local a request carrying `cookies`, put back after the test."""
    from types import SimpleNamespace

    previous = getattr(frappe.local, "request", None)
    frappe.local.request = SimpleNamespace(cookies=cookies or {}, headers={})
    test_case.addCleanup(setattr, frappe.local, "request", previous)


def fake_pdf_renderer():
    """Patches PDF rendering so signing works without wkhtmltopdf; use it as a context manager."""
    import io
    from contextlib import ExitStack

    from pypdf import PdfWriter

    stack = ExitStack()
    stack.enter_context(
        patch(
            "helpdesk.helpdesk.doctype.hd_project_signoff.hd_project_signoff.shutil.which",
            return_value="/usr/bin/wkhtmltopdf",
        )
    )
    # File parses uploaded PDFs, so the fake must be a real one
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    pdf = io.BytesIO()
    writer.write(pdf)
    stack.enter_context(patch("frappe.utils.pdf.get_pdf", return_value=pdf.getvalue()))
    return stack


def recurrence_rule(**values):
    """A recurring-task rule as plain values, for the date math in helpdesk.recurrence:
    monthly on the start date's day from 1 Jan 2026, never ending, no lead time and
    no moving off non-working days unless overridden."""
    return frappe._dict(
        {
            "frequency": "Monthly",
            "interval": 1,
            "weekdays": None,
            "month_day": None,
            "last_day_of_month": 0,
            "start_date": "2026-01-01",
            "ends": "Never",
            "end_date": None,
            "max_occurrences": None,
            "lead_days": 0,
            "due_time": None,
            "skip_non_working_days": 0,
            **values,
        }
    )


def make_recurring_task(project: str, subject: str, **values):
    """Creates an active HD Recurring Task in `project`: monthly on the 1st from today,
    unassigned, unless overridden."""
    from frappe.utils import nowdate

    doc = frappe.new_doc("HD Recurring Task")
    doc.update(
        {
            "project": project,
            "subject": subject,
            "frequency": "Monthly",
            "month_day": 1,
            "start_date": nowdate(),
            # new_doc would fill the Time field with the current time
            "due_time": None,
            **values,
        }
    )
    return doc.insert(ignore_permissions=True)


def add_company_holiday(holiday_date, description: str = "Company holiday (test)"):
    """Adds a holiday to the default SLA's holiday list, the hub calendar recurring
    tasks move their due dates off (widening the list's dates to fit it)."""
    holiday_list = frappe.db.get_value(
        "HD Service Level Agreement",
        {"default_sla": 1, "enabled": 1},
        "holiday_list",
    )
    doc = frappe.get_doc("HD Service Holiday List", holiday_list)
    day = getdate(holiday_date)
    doc.from_date = min(getdate(doc.from_date), day)
    doc.to_date = max(getdate(doc.to_date), day)
    doc.append("holidays", {"holiday_date": day, "description": description})
    doc.save(ignore_permissions=True)


def get_recurring_tasks_created(recurring_task: str) -> list[dict]:
    """The Tasks a recurring task created, oldest occurrence first."""
    return frappe.get_all(
        "Task",
        filters={"custom_recurring_task": recurring_task},
        fields=["name", "subject", "exp_end_date", "custom_recurrence_date", "_assign"],
        order_by="custom_recurrence_date asc",
    )


def make_copilot_settings(templates: dict[str, str] | None = None, **values):
    """Saves HDS Copilot Settings with `values`; `templates` maps a stage to its message text.

    Shadow mode is off and customers default to the Correct level unless asked for, so a
    test sees what a live customer would.
    """
    values.setdefault("shadow_mode", 0)
    values.setdefault("default_copilot_level", "Correct")
    settings = frappe.get_single("HDS Copilot Settings")
    settings.update(values)
    for stage, message in (templates or {}).items():
        row = next((r for r in settings.message_templates if r.stage == stage), None)
        if row:
            row.message = message
        else:
            settings.append("message_templates", {"stage": stage, "message": message})
    settings.save(ignore_permissions=True)
    # the cached settings outlive the test's rollback and would steer the site afterwards
    frappe.db.after_rollback.add(
        lambda: frappe.clear_document_cache(
            "HDS Copilot Settings", "HDS Copilot Settings"
        )
    )
    return settings


def make_site_registry(
    customer: str,
    connection: str | None = None,
    environment: str = "Production",
    apps: list[dict] | None = None,
    **kwargs,
):
    """Creates an HDS Site Registry row for `customer`; `apps` rows are `{app, repository, branch, deployed_commit}`."""
    return frappe.get_doc(
        {
            "doctype": "HDS Site Registry",
            "customer_name": customer,
            "connection": connection,
            "environment": environment,
            "apps": apps or [],
            **kwargs,
        }
    ).insert(ignore_permissions=True)


def make_copilot_run(ticket: str, state: str = "Queued", **values):
    """Creates an HDS Copilot Run for `ticket` directly in `state` (no events, no stage push)."""
    return frappe.get_doc(
        {
            "doctype": "HDS Copilot Run",
            "ticket": ticket,
            "customer": frappe.db.get_value("HD Ticket", ticket, "customer"),
            "kind": "investigate",
            "state": state,
            "queued_at": frappe.utils.now_datetime(),
            **values,
        }
    ).insert(ignore_permissions=True)


# what the fake worker reports for each root cause (demo text, not AI)
FAKE_INVESTIGATIONS = {
    "question": {
        "summary": "A how-to question about printing a Delivery Note in two languages.",
        "customer_message": 'You can print the Delivery Note in Arabic and English: open it, choose Print, and pick the format "Delivery Note (AR/EN)". If it is not in the list, tell us and we will enable it for you.',
        "proposal": {"type": "answer"},
    },
    "not_allowed_request": {
        "summary": "The customer asks to delete a submitted invoice; ERPNext keeps submitted accounting documents.",
        "customer_message": "A submitted invoice cannot be deleted, because the books must keep every posted entry. The right way is Cancel, then Amend: the cancelled invoice stays in the history and the amended copy carries the corrections.",
        "proposal": {"type": "answer"},
    },
    "customer_mistake": {
        "summary": "The total is right: a 10% discount was typed on the item row (Version history shows the user's change).",
        "customer_message": "The total is correct for what was entered: the item row has a 10% discount, added on the day the invoice was made. If the discount was not meant, cancel and amend the invoice and remove it. We can add a warning when a discount is entered, if you like.",
        "proposal": {"type": "answer"},
    },
    "wrong_setting": {
        "summary": "The notification's email account is disabled, so invoice emails are never queued.",
        "customer_message": "",
        "proposal": {
            "type": "config",
            "text": "Enable outgoing on the email account used by the Sales Invoice notification",
        },
    },
    "bug": {
        "summary": "The custom app's Sales Invoice validate hook reads tax_id[0] and fails when the customer has no tax ID.",
        "customer_message": "",
        "proposal": {
            "type": "code",
            "text": "Guard the tax_id read in sales_invoice.py and add a regression test",
        },
    },
    "data_damaged_by_bug": {
        "summary": "Stock for HT-PUMP-200 is wrong since the update: the repost after the custom valuation hook was skipped.",
        "customer_message": "",
        "proposal": {
            "type": "code+data",
            "text": "Fix the hook, then repost the item's ledger entries since the update",
        },
    },
    "core_issue": {
        "summary": "The Accounts Receivable report times out on a large party ledger: a known ERPNext limit, not the custom app.",
        "customer_message": "",
        "proposal": {
            "type": "handover",
            "text": "A person decides between a report workaround and an upstream fix",
        },
    },
    "customization_request": {
        "summary": "A new column for the salesperson's region on the Sales Register: nothing is broken, it is a change.",
        "customer_message": "The Sales Register shows what it was built to show; adding the salesperson's region is a new column in the report.",
        "proposal": {"type": "customization", "estimate_hours": 4},
    },
    "unclear": {
        "summary": "Not enough to go on: no page, time or record is named.",
        "customer_message": "To find the cause we need a little more: which page is slow, at what time of day, and does it happen for one user or everyone?",
        "proposal": {"type": "question"},
        "questions": [
            "Which page is slow?",
            "At what time of day?",
            "One user or everyone?",
        ],
    },
}


def fake_investigation(
    category: str = "question", confidence: float = 0.9, **extra
) -> dict:
    """A worker result for `category`, as `submit_result` expects it."""
    canned = FAKE_INVESTIGATIONS[category]
    result = {
        "kind": "investigation",
        "root_cause_category": category,
        "confidence": confidence,
        "summary": canned["summary"],
        "evidence": [
            {
                "type": "error_log",
                "ref": "Error Log/abc123",
                "note": "IndexError in sales_invoice.py",
            }
        ],
        "proposal": canned.get("proposal", {}),
        "customer_message": canned.get("customer_message", ""),
        "questions": canned.get("questions", []),
        "cost": {"tokens": 1200, "usd": 0.01},
    }
    result.update(extra)
    return result


class FakeWorker:
    """Plays the Copilot worker against the worker API, as the current user (who holds the role)."""

    def __init__(self, worker_id: str = "fake-worker"):
        self.worker_id = worker_id
        self.run = None
        self.token = None
        self.context = None

    def claim(self) -> dict:
        from helpdesk.api.copilot_worker import claim_job

        job = claim_job(self.worker_id)
        if job:
            self.run, self.token, self.context = (
                job["run"],
                job["lease_token"],
                job["context"],
            )
        return job

    def heartbeat(self, stage: str = "") -> dict:
        from helpdesk.api.copilot_worker import heartbeat

        return heartbeat(self.run, self.token, stage)

    def events(self, events: list[dict]) -> dict:
        from helpdesk.api.copilot_worker import post_events

        return post_events(self.run, self.token, events)

    def report(
        self, category: str = "question", confidence: float = 0.9, **extra
    ) -> dict:
        from helpdesk.api.copilot_worker import submit_result

        return submit_result(
            self.run, self.token, fake_investigation(category, confidence, **extra)
        )

    def fail(self, reason: str = "the sandbox did not start") -> dict:
        from helpdesk.api.copilot_worker import submit_result

        return submit_result(
            self.run, self.token, {"kind": "failure", "reason": reason}
        )


def run_fake_worker(
    category: str = "question",
    abandon: bool = False,
    ticket: str | None = None,
    change_set: dict | str | None = None,
) -> dict:
    """`bench execute` demo: claims the oldest queued run (or starts one for `ticket`) and reports `category`.

    With `abandon` it claims and stops, so the lease expiry can be watched. With
    `change_set` (an object, or its JSON) it reports that correction too, as the
    worker would for a wrong setting or damaged data, e.g.
    `{'summary': ..., 'customer_note': ..., 'changes': [{'doctype': 'Selling Settings',
    'name': 'Selling Settings', 'values': {'selling_price_list': 'Standard Selling'}}]}`.
    """
    from helpdesk.copilot.runs import AGENT, start_run

    if ticket:
        start_run(str(ticket), actor=AGENT)
    worker = FakeWorker()
    if not worker.claim():
        return {"claimed": None}
    if abandon:
        return {"claimed": worker.run, "abandoned": True}
    worker.events(
        [
            {
                "seq": 1,
                "type": "tool_call",
                "payload": {"tool": "get_error_log", "ms": 120},
            }
        ]
    )
    extra = {"change_set": frappe.parse_json(change_set)} if change_set else {}
    return {"claimed": worker.run, **worker.report(category, **extra)}


def mcp_message(
    method: str, params: dict | None = None, req_id: int | None = 1
) -> dict:
    """A JSON-RPC 2.0 message for the hub's MCP server; `req_id=None` makes it a notification."""
    message = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        message["params"] = params
    if req_id is not None:
        message["id"] = req_id
    return message


def mcp_tool_result(result: dict):
    """The JSON a tools/call result carries in its text block (or the text itself when it isn't JSON)."""
    text = result["content"][0]["text"]
    try:
        return json.loads(text)
    except ValueError:
        return text


def fake_http_request(
    test_case,
    method: str = "POST",
    body: bytes | str = b"",
    headers: dict | None = None,
):
    """Gives frappe.local a request with `method`, `body` and `headers`, put back after the test."""
    from types import SimpleNamespace

    data = body.encode() if isinstance(body, str) else body
    previous = getattr(frappe.local, "request", None)
    frappe.local.request = SimpleNamespace(
        method=method, headers=headers or {}, cookies={}, get_data=lambda *a, **k: data
    )
    test_case.addCleanup(setattr, frappe.local, "request", previous)


def restrict_tickets_to_teams(test_case):
    """Turns on "agents see only their team's tickets" (tickets without a team hidden too) for one test.

    Switched back off on cleanup: the setting is cached, so a rollback alone
    would leave later tests restricted.
    """
    values = {
        "restrict_tickets_by_agent_group": 1,
        "do_not_restrict_tickets_without_an_agent_group": 0,
    }
    frappe.db.set_single_value("HD Settings", values)
    test_case.addCleanup(
        frappe.db.set_single_value,
        "HD Settings",
        {
            "restrict_tickets_by_agent_group": 0,
            "do_not_restrict_tickets_without_an_agent_group": 1,
        },
    )


# --- Copilot fixes (Phase 1d) ---


def github_pull(
    repo: str,
    number: int,
    head_sha: str,
    body: str = "",
    title: str = "Fix the margin rate",
    draft: bool = False,
    state: str = "open",
    merged: bool = False,
    mergeable_state: str = "clean",
    author: str = "dev-login",
    base: str = "main",
) -> dict:
    """A GitHub pull request as the REST API and webhooks give it."""
    return {
        "number": number,
        "title": title,
        "body": body,
        "draft": draft,
        "state": state,
        "merged": merged,
        "merged_at": "2026-10-12T10:00:00Z" if merged else None,
        "closed_at": "2026-10-12T10:00:00Z" if state == "closed" else None,
        "html_url": f"https://github.com/{repo}/pull/{number}",
        "user": {"login": author},
        "head": {"sha": head_sha, "ref": f"fix-{number}"},
        "base": {"ref": base, "repo": {"full_name": repo}},
        "labels": [],
        "mergeable_state": mergeable_state,
        "merge_commit_sha": None,
        "node_id": f"PR_{repo}_{number}",
    }


class FakeGitHub:
    """GitHub's REST API for Copilot fixes, in memory: pull requests, their files and
    checks, labels, comments, search and the merge (which refuses a moved head, 409).

    `install(test_case)` routes helpdesk.copilot.github.request here for one test.
    """

    def __init__(self):
        self.pulls: dict = {}
        self.files: dict = {}
        self.check_runs: dict = {}
        self.statuses: dict = {}
        self.repo_settings: dict = {}
        self.comments: list = []
        self.calls: list = []
        self.search_items: list = []
        self.merge_refusal: tuple | None = None
        self.merged_with: dict | None = None
        self.reverted: list = []
        # a fine-grained personal token may not read check runs: GitHub says 403
        self.check_runs_refused = False
        # releases (Phase 7): each branch's tip, each repository's commits in order, a commit's pull requests
        self.branches: dict = {}
        self.history: dict = {}
        self.commit_pulls_of: dict = {}

    def commit(
        self,
        repo: str,
        sha: str,
        branch: str = "main",
        message: str = "Change",
        author: str = "dev-login",
        pull: int | None = None,
    ):
        """A commit on `branch`, which becomes its tip; `pull`: the merged pull request it came with."""
        self.history.setdefault(repo, []).append(
            {
                "sha": sha,
                "commit": {
                    "message": message,
                    "author": {"email": f"{author}@example.com"},
                },
                "author": {"login": author},
            }
        )
        self.branches[(repo, branch)] = sha
        if pull:
            self.commit_pulls_of.setdefault((repo, sha), []).append(pull)

    def install(self, test_case):
        patcher = patch("helpdesk.copilot.github.request", side_effect=self.request)
        patcher.start()
        test_case.addCleanup(patcher.stop)
        return self

    def add_pull(
        self, repo: str, number: int, head_sha: str, files: list | None = None, **kwargs
    ) -> dict:
        pull = github_pull(repo, number, head_sha, **kwargs)
        self.pulls[(repo, number)] = pull
        self.files[(repo, number)] = (
            files
            if files is not None
            else [
                {
                    "filename": "demo_app/margin.py",
                    "status": "modified",
                    "additions": 3,
                    "deletions": 1,
                    "patch": "+rate = 0",
                },
                {
                    "filename": "tests/test_margin.py",
                    "status": "modified",
                    "additions": 5,
                    "deletions": 0,
                    "patch": "+check",
                },
            ]
        )
        self.set_checks(head_sha, {"tests": "success"})
        return pull

    def push(self, repo: str, number: int, head_sha: str):
        self.pulls[(repo, number)]["head"]["sha"] = head_sha
        self.set_checks(head_sha, {"tests": "success"})

    def set_checks(self, sha: str, conclusions: dict, status: dict | None = None):
        """`{name: conclusion}`; a conclusion of None means still running."""
        self.check_runs[sha] = [
            {
                "name": name,
                "status": "completed" if result else "in_progress",
                "conclusion": result,
            }
            for name, result in conclusions.items()
        ]
        self.statuses[sha] = status or {"state": "pending", "total_count": 0}

    def workflow_runs(self, sha: str) -> list[dict]:
        """The check runs again, as the GitHub Actions workflow runs of `sha`."""
        return [
            dict(run, workflow_id=i, event="pull_request", created_at="2026-10-12")
            for i, run in enumerate(self.check_runs.get(sha, []))
        ]

    def labels(self, repo: str, number: int) -> list[str]:
        return [label["name"] for label in self.pulls[(repo, number)]["labels"]]

    def request(self, method, path, body=None, params=None, owner=None):
        import copy

        from helpdesk.copilot.github import GitHubError

        self.calls.append((method, path, body))
        parts = path.strip("/").split("/")
        if parts[0] == "search":
            return {"items": self.search_items}
        if parts[0] == "graphql":
            # GitHub's revert of a merged pull request: a new pull request that undoes it
            variables = body["variables"]
            original = next(
                (key, pull)
                for key, pull in self.pulls.items()
                if pull.get("node_id") == variables["id"]
            )
            repo, number = original[0][0], 100 + len(self.pulls)
            self.add_pull(
                repo, number, "r" * 40, body=variables["body"], title=variables["title"]
            )
            self.reverted.append(original[0])
            return {
                "data": {
                    "revertPullRequest": {
                        "revertPullRequest": {
                            "number": number,
                            "url": f"https://github.com/{repo}/pull/{number}",
                        }
                    }
                }
            }
        repo, rest = f"{parts[1]}/{parts[2]}", parts[3:]
        if not rest:
            return self.repo_settings.get(
                repo,
                {
                    "allow_merge_commit": True,
                    "allow_squash_merge": True,
                    "allow_rebase_merge": True,
                },
            )
        if rest[0] == "actions":
            return {"workflow_runs": self.workflow_runs((params or {})["head_sha"])}
        if rest[0] == "branches":
            sha = self.branches.get((repo, rest[1]))
            if not sha:
                raise GitHubError(404, "Branch not found")
            return {"name": rest[1], "commit": {"sha": sha}}
        if rest[0] == "compare":
            base, head = rest[1].split("...")
            shas = [c["sha"] for c in self.history.get(repo, [])]
            if base not in shas or head not in shas:
                raise GitHubError(404, "No common ancestor")
            start, end = shas.index(base), shas.index(head)
            commits = self.history[repo][start + 1 : end + 1]
            status = (
                "identical" if start == end else "ahead" if end > start else "behind"
            )
            # the files of the pull requests the commits came with; a push changes push.py
            files = []
            for commit in commits:
                numbers = self.commit_pulls_of.get((repo, commit["sha"]))
                for number in numbers or []:
                    files += self.files.get((repo, number), [])
                if not numbers:
                    files.append(
                        {"filename": "demo_app/push.py", "additions": 1, "deletions": 0}
                    )
            return {
                "status": status,
                "commits": copy.deepcopy(commits),
                "files": copy.deepcopy(files),
            }
        if rest[0] == "commits" and rest[2] == "pulls":
            return [
                copy.deepcopy(self.pulls[(repo, number)])
                for number in self.commit_pulls_of.get((repo, rest[1]), [])
            ]
        if rest[0] == "commits":
            sha = rest[1]
            if rest[2] == "check-runs":
                if self.check_runs_refused:
                    raise GitHubError(
                        403, "Resource not accessible by personal access token"
                    )
                return {"check_runs": self.check_runs.get(sha, [])}
            return self.statuses.get(sha, {"state": "pending", "total_count": 0})
        number = int(rest[1])
        pull = self.pulls.get((repo, number))
        if not pull:
            raise GitHubError(404, "Not Found")
        if rest[0] == "pulls" and len(rest) == 2:
            return copy.deepcopy(pull)
        if rest[0] == "pulls" and rest[2] == "files":
            return (
                self.files[(repo, number)]
                if int((params or {}).get("page", 1)) == 1
                else []
            )
        if rest[0] == "pulls" and rest[2] == "merge":
            if self.merge_refusal:
                raise GitHubError(*self.merge_refusal)
            if body.get("sha") != pull["head"]["sha"]:
                raise GitHubError(
                    409, "Head branch was modified. Review and try the merge again."
                )
            pull.update(
                state="closed",
                merged=True,
                merged_at="2026-10-12T10:00:00Z",
                merge_commit_sha="m" + body["sha"],
            )
            self.merged_with = body
            return {"sha": pull["merge_commit_sha"], "merged": True}
        if rest[0] == "issues" and rest[2] == "labels":
            if method == "POST":
                pull["labels"] += [{"name": name} for name in body["labels"]]
                return []
            name = rest[3]
            if name not in self.labels(repo, number):
                raise GitHubError(404, "Label does not exist")
            pull["labels"] = [
                label for label in pull["labels"] if label["name"] != name
            ]
            return {}
        if rest[0] == "issues" and rest[2] == "comments":
            self.comments.append((repo, number, body["body"]))
            return {"id": len(self.comments)}
        raise GitHubError(404, f"no fake route for {method} {path}")


def make_hd_pull_request(
    task: str,
    repo: str,
    number: int,
    head_sha: str,
    state: str = "Open",
    link_kind: str = "Closes",
):
    """An HD Pull Request row as the GitHub sync makes it, linked to `task`."""
    return frappe.get_doc(
        {
            "doctype": "HD Pull Request",
            "repo": repo,
            "number": number,
            "task": task,
            "link_kind": link_kind,
            "state": state,
            "title": "Fix the margin rate",
            "url": f"https://github.com/{repo}/pull/{number}",
            "head_sha": head_sha,
            "base_branch": "main",
        }
    ).insert(ignore_permissions=True)


def make_started_task(
    project: str,
    subject: str,
    assignee: str,
    status: str = "Working",
    due=None,
    **values,
) -> str:
    """Creates a Task in `project` assigned to `assignee`, due on `due`, and puts it in
    `status` (Working, Pending Review, On Hold…) with any other `values` (e.g.
    escalation_level) straight in the database; returns its name. For In progress tests."""
    task = make_task(project, subject, due).name
    make_assignment("Task", task, assignee)
    frappe.db.set_value("Task", task, {"status": status, **values})
    return task


def record_status_change(task: str, old: str, new: str, at) -> None:
    """Writes a Version row saying `task` moved from `old` to `new` at `at`, as the
    task form's history would, so a task's status age can be read from it."""
    version = frappe.get_doc(
        {
            "doctype": "Version",
            "ref_doctype": "Task",
            "docname": task,
            "data": frappe.as_json({"changed": [["status", old, new]]}),
        }
    ).insert(ignore_permissions=True)
    frappe.db.set_value("Version", version.name, "creation", at, update_modified=False)


def get_in_progress_as(user: str, **filters) -> dict:
    """The In progress page's answer (helpdesk.api.in_progress.get_in_progress) for `user`."""
    return call_as_user(user, "helpdesk.api.in_progress.get_in_progress", **filters)


# --- Copilot deploys through Press (Phase 2) ---


class FakePress:
    """TBO's Press for Copilot deploys, in memory: one bench with its apps and sites,
    the deploys asked for and the site updates they make. `finish(status)` ends them.

    `install(test_case)` routes helpdesk.copilot.press.call here for one test.
    """

    def __init__(
        self,
        group: str = "bench-1",
        sites: tuple = ("site1.example.com",),
        app: str = "demo_app",
        current: str = "o" * 40,
        next_hash: str | None = None,
    ):
        self.group = group
        self.apps = [
            {
                "app": app,
                "source": "SRC-1",
                "release": "REL-1",
                "hash": current,
                "next_release": "REL-2",
                "next_hash": next_hash or current,
                "branch": "main",
            }
        ]
        self.sites = [
            {"name": site, "server": "f1.example.com", "bench": f"{group}-old"}
            for site in sites
        ]
        self.deploy_in_progress = False
        self.deploys: list = []
        self.fetched: list = []
        self.site_updates: list = []
        self.builds: list = []
        self.on_fetch = None

    @staticmethod
    def _as_press(app: dict) -> dict:
        """An app as TBO's Press shows it in deploy_information (release_group.get_app_updates):
        the running commit as `current_hash`, a newer one only as a release."""
        current, following = app.get("hash"), app.get("next_hash") or app.get("hash")
        update = bool(following) and following != current
        return {
            "app": app["app"],
            "name": app["app"],
            "source": app.get("source"),
            "repository_url": app.get("repository_url"),
            "branch": app.get("branch"),
            "current_branch": app.get("branch"),
            "current_hash": current,
            "current_release": app.get("release"),
            "next_release": app.get("next_release") if update else app.get("release"),
            "releases": [
                {"name": app.get("next_release"), "hash": following, "is_yanked": False}
            ]
            if update
            else [],
            "update_available": update,
        }

    def install(self, test_case):
        patcher = patch("helpdesk.copilot.press.call", side_effect=self.call)
        patcher.start()
        test_case.addCleanup(patcher.stop)
        return self

    def fail_build(self):
        """The bench's newest build fails: Press then updates no site."""
        self.builds[0]["status"] = "Failure"
        self.site_updates.clear()

    def finish(self, status: str = "Success"):
        for build in self.builds:
            build["status"] = "Success"
        for update in self.site_updates:
            update["status"] = status
        if status == "Success":
            self.apps[0]["hash"] = self.apps[0]["next_hash"]

    def call(self, method, **args):
        import copy

        from helpdesk.copilot.press import PressError

        name = method.rsplit(".", 1)[-1]
        if name == "deploy_information":
            return {
                "apps": [self._as_press(app) for app in self.apps],
                "sites": copy.deepcopy(self.sites),
                "deploy_in_progress": self.deploy_in_progress,
                "has_running_release_pipeline": False,
            }
        if name == "fetch_latest_app_update":
            self.fetched.append(args["app"])
            if self.on_fetch:
                self.on_fetch()
            return None
        if name == "deploy_and_update":
            self.deploys.append(copy.deepcopy(args))
            self.builds.insert(
                0,
                {
                    "name": f"DCB-{len(self.deploys)}",
                    "group": self.group,
                    "status": "Running",
                    "creation": str(now_datetime()),
                },
            )
            for site in args["sites"]:
                self.site_updates.insert(
                    0,
                    {
                        "name": f"SU-{len(self.site_updates) + 1}",
                        "site": site["name"],
                        "status": "Running",
                        "creation": str(now_datetime()),
                        "site_backup": f"BKP-{len(self.site_updates) + 1}",
                    },
                )
            return f"DC-{len(self.deploys)}"
        if name == "get_list" and args.get("doctype") == "Site Update":
            if "name" in args["filters"]:
                return [
                    dict(update)
                    for update in self.site_updates
                    if update["name"] == args["filters"]["name"]
                ]
            wanted = set(args["filters"]["site"][1])
            return [
                dict(update) for update in self.site_updates if update["site"] in wanted
            ]
        if name == "get_list" and args.get("doctype") == "Deploy Candidate Build":
            return [
                dict(build)
                for build in self.builds
                if build["group"] == args["filters"]["group"]
            ]
        raise PressError(404, f"no fake route for {method}")


def site_tool_replies(replies: dict):
    """A patched MCPClient whose call_tool answers each customer-site tool with `replies[tool]` (JSON), or an error.

    A reply may be a function of the call's arguments; raising LookupError refuses that call.
    """
    import json as _json

    def refused(text):
        return {"content": [{"type": "text", "text": text}], "isError": True}

    def call_tool(tool, arguments=None, session_id=None):
        if tool not in replies:
            return refused(f"{tool} refused")
        value = replies[tool]
        if callable(value):
            try:
                value = value(arguments or {})
            except LookupError as e:
                return refused(str(e))
        return {"content": [{"type": "text", "text": _json.dumps(value)}]}

    return call_tool


class FakeCustomerSite:
    """The customer's site as Copilot's corrections reach it, in memory: its records,
    `check_change` and `apply_change`, and its guard on the hub's signed approval
    (the connection's approval key, the record, its exact values).

    `install(test_case)` routes helpdesk.mcp_client.MCPClient here for one test.
    """

    def __init__(self, key: str = "site-approval-key", environment: str = "Production"):
        self.key = key
        self.environment = environment
        self.records: dict = {}
        self.problems: dict = {}  # (doctype, name) -> what the site's check says
        self.refusals: dict = {}  # (doctype, name) -> why the site refuses to apply
        self.created: list = []
        self.approvals: list = []
        self.calls: list = []
        # other tools the site answers (the deploy's check): {tool: reply or function of the arguments}
        self.replies: dict = {}

    def install(self, test_case):
        patcher = patch("helpdesk.mcp_client.MCPClient")
        mocked = patcher.start()
        test_case.addCleanup(patcher.stop)
        mocked.return_value.call_tool.side_effect = self.call_tool
        return self

    def add(self, doctype: str, name: str, values: dict, docstatus: int = 0, rows=None):
        self.records[(doctype, name)] = {
            "values": dict(values),
            "rows": {row: dict(v) for row, v in (rows or {}).items()},
            "docstatus": docstatus,
        }

    def value(self, doctype: str, name: str, field: str):
        return self.records[(doctype, name)]["values"].get(field)

    def call_tool(self, tool, arguments=None, ticket_id=None, session_id=None):
        import json as _json

        self.calls.append((tool, arguments))
        if tool in self.replies:
            reply = self.replies[tool]
            reply = reply(arguments or {}) if callable(reply) else reply
            return {
                "content": [{"type": "text", "text": _json.dumps(reply, default=str)}]
            }
        try:
            result = getattr(self, tool)(**(arguments or {}))
        except LookupError as e:
            return {
                "content": [{"type": "text", "text": f"Error executing {tool}: {e}"}],
                "isError": True,
            }
        return {"content": [{"type": "text", "text": _json.dumps(result, default=str)}]}

    def _current(self, change: dict) -> dict:
        record = self.records[(change["doctype"], change.get("name") or "")]
        return {
            "values": {f: record["values"].get(f) for f in change.get("values") or {}},
            "rows": {
                row["name"]: {
                    f: record["rows"].get(row["name"], {}).get(f)
                    for f in row.get("values") or {}
                }
                for row in change.get("rows") or []
            },
        }

    def check_change(self, change: dict):
        key = (change["doctype"], change.get("name") or "")
        if (change.get("action") or "update") == "create":
            return {
                "ok": True,
                "problems": [],
                "current": {},
                "docstatus": 0,
                "environment": self.environment,
            }
        if key not in self.records:
            raise LookupError(f"{key[0]} {key[1]} not found")
        problems = [self.problems[key]] if key in self.problems else []
        return {
            "ok": not problems,
            "problems": problems,
            "current": self._current(change),
            "docstatus": self.records[key]["docstatus"],
            "environment": self.environment,
        }

    def _guard(self, change: dict, expect, token):
        import base64
        import hashlib
        import hmac
        import json as _json
        import time

        from helpdesk.copilot.approval_key import change_digest

        if not token:
            if self.environment == "Production":
                raise LookupError(
                    "On a Production site every write from TBO Support needs its signed approval."
                )
            return {}
        body, _sep, signature = token.partition(".")
        expected = (
            base64.urlsafe_b64encode(
                hmac.new(self.key.encode(), body.encode(), hashlib.sha256).digest()
            )
            .decode()
            .rstrip("=")
        )
        if signature != expected:
            raise LookupError("The approval's signature is not valid.")
        payload = _json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if payload["exp"] < time.time():
            raise LookupError("The approval has expired.")
        wanted = (
            change.get("item"),
            change["doctype"],
            change.get("name") or "",
            change.get("action") or "update",
            change_digest(change, expect),
        )
        if not any(
            (
                r.get("item"),
                r["doctype"],
                r.get("name") or "",
                r["action"],
                r.get("digest"),
            )
            == wanted
            for r in payload["records"]
        ):
            raise LookupError("The approval does not cover this record and its values.")
        self.approvals.append(payload)
        return payload

    def apply_change(self, change: dict, expect=None, approval=None):
        self._guard(change, expect, approval)
        key = (change["doctype"], change.get("name") or "")
        if key in self.refusals:
            raise LookupError(self.refusals[key])
        if (change.get("action") or "update") == "create":
            name = f"{change['doctype']}-NEW-{len(self.created) + 1}"
            self.created.append((change["doctype"], name, change.get("values")))
            return {
                "status": "applied",
                "doctype": change["doctype"],
                "name": name,
                "old": {},
                "new": {"values": change.get("values")},
            }
        before = self._current(change)
        if before != {
            "values": (expect or {}).get("values") or {},
            "rows": (expect or {}).get("rows") or {},
        }:
            raise LookupError(
                f"{key[0]} {key[1]} changed since it was checked; it was left as it is."
            )
        record = self.records[key]
        record["values"].update(change.get("values") or {})
        for row in change.get("rows") or []:
            record["rows"].setdefault(row["name"], {}).update(row.get("values") or {})
        return {
            "status": "applied",
            "doctype": key[0],
            "name": key[1],
            "old": before,
            "new": self._current(change),
        }
