"""One-off import of the standalone content_calendar app into the Content Calendar.

DM Client -> HD Customer (+ a Contact for its email so it can use the portal)
Content Calendar Item -> one HD Content Post per platform
Content Calendar Settings -> HD Content Settings

Safe to run more than once: customers, contacts and posts that already exist are
reused or skipped. Nothing is written unless dry_run is False:

    bench --site <site> execute helpdesk.content_calendar_import.run
    bench --site <site> execute helpdesk.content_calendar_import.run --kwargs "{'dry_run': False}"
"""

import re

import frappe
from frappe.utils import escape_html, get_datetime

from helpdesk.api.content_portal import add_portal_contact
from helpdesk.helpdesk.doctype.hd_content_settings.hd_content_settings import (
    PLACEHOLDER,
    TEMPLATES,
)

CHANNELS = {
    "instagram": "Instagram",
    "facebook": "Facebook",
    "linkedin": "LinkedIn",
    "x": "X",
    "twitter": "X",
    "youtube": "YouTube",
    "blog": "Blog",
    "email": "Email",
    "whatsapp": "WhatsApp",
}
DEFAULT_CHANNEL = "Instagram"
FORMATS = {"Ad": "Post", "Blog": "Article"}
STATUSES = {
    "Draft": "Drafting",
    "In Progress": "Drafting",
    "Overdue": "Drafting",
    "Postponed": "Drafting",
    "Internal Review": "Internal Review",
    "Submitted to Client": "Client Review",
    "Client Review": "Client Review",
    "Resubmitted": "Client Review",
    "Correction Required": "Changes Requested",
    "Client Approved": "Approved",
    "Published": "Published",
    "Cancelled": "Cancelled",
}
# calendar-level states that mean the whole month is in front of the client
CLIENT_CALENDAR_STATES = ("Submitted to Client", "Client Review", "Resubmitted")
OLD_PLACEHOLDERS = {
    "campaign_name": "title",
    "client_name": "customer",
    "client_display_name": "customer",
    "calendar_link": "post_link",
}
FEEDBACK = re.compile(
    r"\[Client Feedback\]:\s*(.*?)(?=\n\n\[Client Feedback\]:|\Z)", re.S
)


def run(dry_run: bool = True) -> dict:
    if not frappe.db.table_exists("Content Calendar Item"):
        print("content_calendar is not installed on this site; nothing to import.")
        return {}

    summary = {"customers": {}, "contacts": 0, "posts": 0, "skipped": [], "notes": []}
    customers = import_clients(summary, dry_run)
    import_items(customers, summary, dry_run)
    import_settings(summary, dry_run)

    if dry_run:
        frappe.db.rollback()
    else:
        frappe.db.commit()
    print(("DRY RUN (nothing saved) " if dry_run else "") + frappe.as_json(summary))
    return summary


# ---------------------------------------------------------------- clients --


def import_clients(summary: dict, dry_run: bool) -> dict[str, str]:
    """DM Client name -> HD Customer name."""
    mapping = {}
    for client in frappe.get_all(
        "DM Client", fields=["name", "client_name", "client_display_name", "email"]
    ):
        label = (
            client.client_display_name or client.client_name or client.name
        ).strip()
        customer = frappe.db.exists("HD Customer", label)
        if not customer:
            customer = (
                frappe.get_doc({"doctype": "HD Customer", "customer_name": label})
                .insert(ignore_permissions=True)
                .name
            )
        mapping[client.name] = customer
        summary["customers"][client.name] = customer
        if client.email:
            if add_portal_contact(customer, client.email.strip().lower()):
                summary["contacts"] += 1
    return mapping


# ------------------------------------------------------------------ items --


def import_items(customers: dict[str, str], summary: dict, dry_run: bool):
    calendars = {
        c.name: c
        for c in frappe.get_all(
            "Content Calendar", fields=["name", "client", "workflow_status"]
        )
    }
    items = frappe.get_all(
        "Content Calendar Item",
        fields=[
            "name",
            "parent",
            "planned_date",
            "posting_date",
            "posting_time",
            "campaign_name",
            "deliverable",
            "status",
            "platforms",
            "main_copy",
            "description",
            "assigned_writer",
            "assigned_creative",
            "published",
            "actual_posting_date",
            "published_url",
            "postponed",
            "new_posting_date",
            "new_posting_time",
            "attachment",
            "missed_notification_sent",
        ],
        order_by="planned_date asc",
    )
    for item in items:
        calendar = calendars.get(item.parent)
        if not calendar or calendar.client not in customers:
            summary["skipped"].append(f"{item.name}: calendar {item.parent} not found")
            continue
        for channel in item_channels(item.platforms, summary):
            if import_item(item, calendar, customers[calendar.client], channel):
                summary["posts"] += 1
            else:
                summary["skipped"].append(f"{item.name} ({channel}): already imported")


def import_item(item, calendar, customer: str, channel: str) -> bool:
    title = (item.campaign_name or "Untitled").strip()
    publish_on = item_publish_on(item)
    if frappe.db.exists(
        "HD Content Post",
        {
            "customer": customer,
            "title": title,
            "channel": channel,
            "publish_on": publish_on,
        },
    ):
        return False

    status = item_status(item, calendar)
    if not publish_on and status != "Cancelled":
        status = "Idea"
    post = frappe.get_doc(
        {
            "doctype": "HD Content Post",
            "title": title,
            "customer": customer,
            "channel": channel,
            "format": FORMATS.get(item.deliverable, item.deliverable or "Post"),
            # Published is set afterwards: old items often have no URL, which a save would refuse
            "status": "Scheduled" if status == "Published" else status,
            "publish_on": publish_on,
            "caption": text_to_html(item.main_copy),
            "writer": existing_user(item.assigned_writer),
            "designer": existing_user(item.assigned_creative),
            "client_feedback": latest_feedback(item.description),
        }
    ).insert(ignore_permissions=True)

    updates = {"missed_alert_sent": item.missed_notification_sent or 0}
    if status == "Published":
        updates.update(
            status="Published",
            published_url=item.published_url,
            published_on=get_datetime(item.actual_posting_date or publish_on),
        )
    post.db_set(updates, update_modified=False)

    if item.attachment:
        frappe.get_doc(
            {
                "doctype": "File",
                "file_url": item.attachment,
                "attached_to_doctype": "HD Content Post",
                "attached_to_name": post.name,
                "is_private": int(item.attachment.startswith("/private/")),
            }
        ).insert(ignore_permissions=True)

    brief = FEEDBACK.sub("", item.description or "").strip()
    note = f"Imported from content calendar {calendar.name} (item {item.name})."
    if brief:
        note += f"<br><br><b>Brief:</b> {escape_html(brief)}"
    post.add_comment("Info", note)
    return True


def item_channels(platforms: str | None, summary: dict) -> list[str]:
    channels = []
    for raw in (platforms or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        channel = CHANNELS.get(raw.lower())
        if not channel:
            summary["notes"].append(
                f"Unknown platform {raw!r} imported as {DEFAULT_CHANNEL}"
            )
            channel = DEFAULT_CHANNEL
        if channel not in channels:
            channels.append(channel)
    return channels or [DEFAULT_CHANNEL]


def item_publish_on(item):
    if item.postponed and item.new_posting_date:
        return get_datetime(
            f"{item.new_posting_date} {item.new_posting_time or item.posting_time or '00:00:00'}"
        )
    day = item.posting_date or item.planned_date
    return get_datetime(f"{day} {item.posting_time or '00:00:00'}") if day else None


def item_status(item, calendar) -> str:
    if item.published:
        return "Published"
    status = STATUSES.get(item.status, "Drafting")
    if status == "Drafting" and calendar.workflow_status in CLIENT_CALENDAR_STATES:
        return "Client Review"
    return status


def latest_feedback(description: str | None) -> str | None:
    found = FEEDBACK.findall(description or "")
    return found[-1].strip() if found else None


def existing_user(user: str | None) -> str | None:
    return user if user and frappe.db.exists("User", user) else None


def text_to_html(text: str | None) -> str:
    if not text:
        return ""
    return "".join(
        f"<p>{escape_html(line)}</p>" for line in text.splitlines() if line.strip()
    )


# --------------------------------------------------------------- settings --


def import_settings(summary: dict, dry_run: bool):
    old = frappe.get_single("Content Calendar Settings")
    new = frappe.get_single("HD Content Settings")
    new.enable_missed_post_alerts = old.enable_missed_post_notifications
    new.grace_period_minutes = old.grace_period_minutes or 0
    new.notify_post_team = old.notify_assigned_marketer

    emails = set(new.get_alert_emails())
    users = {row.user for row in new.alert_recipients}
    for row in old.additional_recipients:
        if row.recipient_type == "User" and frappe.db.exists("User", row.recipient):
            users.add(row.recipient)
        elif email := recipient_email(row.recipient_type, row.recipient):
            emails.add(email)
    raw = (old.additional_email_recipients or "").replace(",", "\n")
    emails |= {e.strip() for e in raw.splitlines() if e.strip()}
    new.set("alert_recipients", [{"user": u} for u in sorted(users)])
    new.alert_emails = "\n".join(sorted(emails))

    for (old_subject, old_message), kind in (
        (("email_subject_template", "email_message_template"), "missed_post"),
        (
            ("client_otp_email_subject_template", "client_otp_email_message_template"),
            "portal_code",
        ),
    ):
        subject_field, message_field, *_rest, allowed = TEMPLATES[kind]
        for old_field, new_field in (
            (old_subject, subject_field),
            (old_message, message_field),
        ):
            template = convert_template(old.get(old_field), allowed)
            if template is None:
                summary["notes"].append(
                    f"{old_field} uses placeholders with no match; kept the default"
                )
            new.set(new_field, template or "")
    new.save(ignore_permissions=True)


def convert_template(template: str | None, allowed) -> str | None:
    """Rename old placeholders; None when some placeholder has no equivalent."""
    if not template:
        return ""
    converted = PLACEHOLDER.sub(
        lambda m: "{" + OLD_PLACEHOLDERS.get(m.group(1), m.group(1)) + "}", template
    )
    if set(PLACEHOLDER.findall(converted)) - set(allowed):
        return None
    return converted.strip()


def recipient_email(recipient_type: str, recipient: str | None) -> str | None:
    if not recipient:
        return None
    if recipient_type == "Employee" and frappe.db.table_exists("Employee"):
        emp = frappe.db.get_value(
            "Employee",
            recipient,
            ["prefered_email", "company_email", "personal_email", "user_id"],
            as_dict=True,
        )
        return emp and (
            emp.prefered_email or emp.company_email or emp.personal_email or emp.user_id
        )
    return frappe.db.get_value("User", recipient, "email")
