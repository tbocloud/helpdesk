"""Client approval for content posts over MCP.

Posts in "Client Review" are pushed to the customer's ERP as a `Content Approval`
(helpdesk_client). The customer approves or requests changes there, and the
decision is pulled back onto the post. Like the ticket sync, every call starts
here; the customer site holds no credentials.
"""

import base64

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from helpdesk.mcp_client import MCPClient
from helpdesk.ticket_puller import _unwrap

APPROVAL_DOCTYPE = "Content Approval"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
MAX_IMAGES = 6
MAX_IMAGE_BYTES = 8 * 1024 * 1024
# the client's approval goes to the Digital Marketing Head before the post is Approved
DECISION_TO_STATUS = {
    "Approved": "Head Review",
    "Changes Requested": "Changes Requested",
}


def get_client_connection(customer: str | None) -> str | None:
    """The connected ERP for a customer, if any."""
    if not customer:
        return None
    return frappe.db.get_value(
        "HDS Support Connection",
        {"customer_name": customer, "connection_status": "Connected"},
        "name",
    )


def sync_content_approvals():
    """Scheduled: pull decisions first so a re-push never overwrites an unseen decision."""
    pull_approval_decisions()
    push_posts_for_approval()


def pull_approval_decisions() -> int:
    posts = frappe.get_all(
        "HD Content Post",
        filters={"status": "Client Review", "client_approval_ref": ("is", "set")},
        fields=["name", "client_approval_ref", "client_connection"],
    )
    by_connection: dict[str, dict[str, str]] = {}
    for post in posts:
        by_connection.setdefault(post.client_connection, {})[
            post.client_approval_ref
        ] = post.name

    applied = 0
    for connection, ref_to_post in by_connection.items():
        try:
            decisions = (
                _unwrap(
                    MCPClient(connection).call_tool(
                        "get_list",
                        {
                            "doctype": APPROVAL_DOCTYPE,
                            "filters": {
                                "name": ["in", list(ref_to_post)],
                                "status": ["!=", "Pending"],
                            },
                            "fields": [
                                "name",
                                "status",
                                "client_comment",
                                "decided_by",
                                "decided_on",
                            ],
                            "limit": len(ref_to_post),
                        },
                    )
                )
                or []
            )
        except Exception:  # noqa: BLE001 - one failing site must not stop the sync
            frappe.log_error(
                title=f"Content approval pull failed for {connection}",
                message=frappe.get_traceback(),
            )
            continue

        for decision in decisions:
            try:
                apply_decision(ref_to_post[decision["name"]], decision)
                frappe.db.commit()
                applied += 1
            except Exception:  # noqa: BLE001 - one bad record must not stop the sync
                frappe.db.rollback()
                frappe.log_error(
                    title=f"Applying content decision failed for {decision.get('name')}",
                    message=frappe.get_traceback(),
                )
    return applied


def apply_decision(post_name: str, decision: dict):
    status = DECISION_TO_STATUS.get(decision.get("status"))
    if not status:
        return
    post = frappe.get_doc("HD Content Post", post_name)
    post.status = status
    post.client_feedback = decision.get("client_comment") or post.client_feedback
    post.client_decided_on = decision.get("decided_on") or now_datetime()
    post.save(ignore_permissions=True)
    verb = (
        _("approved")
        if decision.get("status") == "Approved"
        else _("requested changes")
    )
    note = f": {decision['client_comment']}" if decision.get("client_comment") else ""
    post.add_comment(
        "Info",
        _("Client {0} in their ERP ({1}){2}").format(
            verb, decision.get("decided_by") or "", note
        ),
    )


def push_posts_for_approval() -> int:
    posts = frappe.get_all(
        "HD Content Post",
        filters={"status": "Client Review"},
        fields=[
            "name",
            "customer",
            "client_approval_ref",
            "client_connection",
            "sent_for_approval_on",
            "modified",
        ],
    )
    pushed = 0
    for post in posts:
        if not needs_push(post):
            continue
        connection = post.client_connection or get_client_connection(post.customer)
        if not connection:
            continue
        try:
            send_for_approval(frappe.get_doc("HD Content Post", post.name), connection)
            frappe.db.commit()
            pushed += 1
        except Exception:  # noqa: BLE001 - one failing site must not stop the sync
            frappe.db.rollback()
            frappe.log_error(
                title=f"Content approval push failed for {post.name}",
                message=frappe.get_traceback(),
            )
    return pushed


def needs_push(post) -> bool:
    """Never sent, or edited / given new images since it was last sent."""
    if not post.client_approval_ref:
        return True
    if not post.sent_for_approval_on:
        return False
    sent = get_datetime(post.sent_for_approval_on)
    if get_datetime(post.modified) > sent:
        return True
    # attaching an image doesn't touch the post's `modified`
    latest_image = frappe.db.get_value(
        "File",
        {"attached_to_doctype": "HD Content Post", "attached_to_name": post.name},
        "max(creation)",
    )
    return bool(latest_image) and get_datetime(latest_image) > sent


def approval_values(post) -> dict:
    return {
        "title": post.title,
        "channel": post.channel,
        "format": post.format,
        "publish_on": str(post.publish_on) if post.publish_on else None,
        "caption": post.caption,
        "hashtags": post.hashtags,
        "hub_post": post.name,
    }


def send_for_approval(post, connection: str):
    mcp = MCPClient(connection)
    values = approval_values(post)
    if post.client_approval_ref and post.client_connection == connection:
        mcp.call_tool(
            "set_values",
            {
                "doctype": APPROVAL_DOCTYPE,
                "name": post.client_approval_ref,
                "values": {**values, "status": "Pending", "client_comment": ""},
            },
        )
        ref = post.client_approval_ref
    else:
        ref = _unwrap(
            mcp.call_tool("create_doc", {"doctype": APPROVAL_DOCTYPE, "values": values})
        )["name"]
    # update_modified=False keeps `modified` as the content's last edit, which needs_push compares against
    post.db_set(
        {
            "client_approval_ref": ref,
            "client_connection": connection,
            "sent_for_approval_on": now_datetime(),
        },
        update_modified=False,
    )
    send_images(mcp, post.name, ref)


def post_images(post_name: str) -> list:
    files = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": "HD Content Post",
            "attached_to_name": post_name,
            "is_folder": 0,
        },
        fields=["name", "file_name", "file_size"],
        order_by="creation asc",
    )
    images = [
        f
        for f in files
        if (f.file_name or "").lower().endswith(IMAGE_EXTENSIONS)
        and (f.file_size or 0) <= MAX_IMAGE_BYTES
    ]
    return images[:MAX_IMAGES]


def send_images(mcp, post_name: str, ref: str):
    """Attach the post's images to the client's approval; skip ones already there.

    Images help the client decide but are not required, so a failed upload is
    logged and never blocks the approval itself.
    """
    images = post_images(post_name)
    if not images:
        return
    try:
        existing = (
            _unwrap(
                mcp.call_tool(
                    "get_list",
                    {
                        "doctype": "File",
                        "filters": {
                            "attached_to_doctype": APPROVAL_DOCTYPE,
                            "attached_to_name": ref,
                        },
                        "fields": ["file_name"],
                        "limit": 50,
                    },
                )
            )
            or []
        )
    except Exception:  # noqa: BLE001 - images are optional
        frappe.log_error(
            title=f"Listing client images failed for {ref}",
            message=frappe.get_traceback(),
        )
        return
    already_sent = {f.get("file_name") for f in existing}

    for image in images:
        if image.file_name in already_sent:
            continue
        try:
            content = frappe.get_doc("File", image.name).get_content()
            if isinstance(content, str):
                content = content.encode()
            mcp.call_tool(
                "create_doc",
                {
                    "doctype": "File",
                    "values": {
                        "file_name": image.file_name,
                        "attached_to_doctype": APPROVAL_DOCTYPE,
                        "attached_to_name": ref,
                        "is_private": 1,
                        "content": base64.b64encode(content).decode(),
                        "decode": 1,
                    },
                },
            )
        except Exception:  # noqa: BLE001 - images are optional
            frappe.log_error(
                title=f"Sending image {image.file_name} failed",
                message=frappe.get_traceback(),
            )
