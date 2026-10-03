"""Client approval follow-up: a reminder to the client, then an alert to the team.

Runs daily. A post waits for the client from when it entered Client Review (older
posts: from when it was sent to the client's ERP). After `client_reminder_days`
(HD Content Settings) the client's contacts get one email listing what's waiting;
after `client_escalate_days` the post's marketer, its creator and the project lead
are told. Each happens once per round of review.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import (
    cint,
    escape_html,
    format_datetime,
    get_datetime,
    get_url,
    now_datetime,
)

from helpdesk.work_reminders import notify_users


def send_client_follow_ups():
    settings = frappe.get_cached_doc("HD Content Settings")
    remind_after = cint(settings.client_reminder_days)
    alert_after = cint(settings.client_escalate_days)
    if not (remind_after or alert_after):
        return

    now = now_datetime()
    to_remind = defaultdict(list)
    for post in waiting_posts():
        since = post.client_review_since or post.sent_for_approval_on
        if not since:
            continue
        days = (now - get_datetime(since)).total_seconds() / 86400
        if (
            remind_after
            and days >= remind_after
            and not post.client_reminded_on
            and post.customer
        ):
            to_remind[post.customer].append(post)
        if alert_after and days >= alert_after and not post.client_escalated_on:
            alert_team(post, int(days))

    for customer, posts in to_remind.items():
        remind_client(customer, posts)


def waiting_posts() -> list:
    return frappe.get_all(
        "HD Content Post",
        filters={"status": "Client Review"},
        fields=[
            "name",
            "title",
            "customer",
            "publish_on",
            "marketer",
            "owner",
            "client_connection",
            "client_review_since",
            "sent_for_approval_on",
            "client_reminded_on",
            "client_escalated_on",
        ],
        order_by="publish_on asc",
    )


def remind_client(customer: str, posts: list):
    """One email to the customer's contacts listing every post waiting for them."""
    from helpdesk.api.content_portal import portal_emails, portal_enabled

    emails = portal_emails(customer)
    in_erp = any(p.client_connection for p in posts)
    # without the portal or a connected ERP the client has nowhere to approve
    if not emails or not (portal_enabled() or in_erp):
        return

    items = "".join(
        f"<li>{escape_html(p.title)} · {format_datetime(p.publish_on, 'd MMM, h:mm a')}</li>"
        for p in posts
    )
    if portal_enabled():
        url = get_url("/content-portal")
        where = _("Review them in the content portal: {0}").format(
            f'<a href="{url}">{url}</a>'
        )
    else:
        where = _("Review them under Content Approval in your ERP.")
    frappe.sendmail(
        recipients=emails,
        subject=_("{0} posts are waiting for your approval").format(len(posts))
        if len(posts) > 1
        else _("A post is waiting for your approval"),
        message=f"<p>{_('Hello,')}</p>"
        f"<p>{_('These posts are ready for your review before they go live:')}</p>"
        f"<ul>{items}</ul><p>{where}</p>",
        reference_doctype="HD Customer",
        reference_name=customer,
    )
    now = now_datetime()
    for post in posts:
        # update_modified=False: the ERP sync compares `modified` to decide what to resend
        frappe.db.set_value(
            "HD Content Post",
            post.name,
            "client_reminded_on",
            now,
            update_modified=False,
        )


def alert_team(post, days: int):
    """Tell the people who can chase the client: the marketer, the creator, the project lead."""
    doc = frappe.get_doc("HD Content Post", post.name)
    project = doc.content_project()
    lead = frappe.db.get_value("Project", project, "project_lead") if project else None
    notify_users(
        [post.marketer, post.owner, lead],
        "HD Content Post",
        post.name,
        _(
            "{0} ({1}) has waited {2} days for the client's approval and publishes {3}."
        ).format(
            post.title,
            post.customer,
            days,
            format_datetime(post.publish_on, "d MMM, h:mm a"),
        ),
        link=doc.board_path(),
    )
    frappe.db.set_value(
        "HD Content Post",
        post.name,
        "client_escalated_on",
        now_datetime(),
        update_modified=False,
    )
