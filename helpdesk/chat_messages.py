# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The Messages section (TBO Copilot phase 32): every TBO Chat message kept in TBO Support.

A message is one HD Chat Message row per Chatwoot message id. The row is written:
- by the webhook, for every message: customers', the AI's, people's (also those typed in Chatwoot's
  own screens), templates, private notes and Chatwoot's activity lines; delivery receipts update it;
- or the moment TBO Support posts a person's reply, so the person who sent it is known. The webhook's
  copy of that message then only adds what is missing: the first writer's sender stays.

Files are copied into private Files by a background job (`copy_files`), because a webhook must answer
quickly. Story mentions keep no media (Meta's rule), only a note.

Each new message also updates its conversation's list fields: the last message and its time, who
it waits on, unread, and when the 24-hour reply window of WhatsApp, Instagram and Facebook closes.
"""

from datetime import datetime, timezone
from urllib.parse import unquote, urlparse

import frappe
import requests
from frappe import _
from frappe.query_builder.functions import Max
from frappe.utils import (
    add_to_date,
    cint,
    convert_utc_to_system_timezone,
    get_datetime,
    now_datetime,
)

MESSAGE = "HD Chat Message"
CONVERSATION = "HD Chat Conversation"
SETTINGS = "HD Chatwoot Settings"

# channels whose free-form replies are allowed only within 24 hours of the customer's last message
WINDOW_CHANNELS = ("Channel::Whatsapp", "Channel::FacebookPage", "Channel::Instagram")
WINDOW_HOURS = 24
SENDERS = {"contact": "Customer", "user": "Staff", "agent_bot": "AI"}
# Chatwoot's delivery statuses, in the order they happen; Failed can follow any of them
STATUSES = {
    "sent": "Sent",
    "delivered": "Delivered",
    "read": "Read",
    "failed": "Failed",
}
STATUS_ORDER = ("", "Sent", "Delivered", "Read")
FILE_TYPES = {
    "image": "Image",
    "audio": "Audio",
    "video": "Video",
    "file": "File",
    "location": "Location",
    "contact": "Contact",
    "share": "Share",
    "fallback": "Share",
    "ig_reel": "Share",
    "ig_post": "Share",
    "ig_story": "Story",
    "story_mention": "Story",
}
COPY_TYPES = ("Image", "Audio", "Video", "File")
PREVIEW_CHARS = 140
DOWNLOAD_TIMEOUT = 60
CHUNK = 64 * 1024
MB = 1024 * 1024
TICKET = "HD Ticket"
MESSAGES, SUPPORT = "Messages", "Support"
# HD Ticket's "Came In By" for each Chatwoot channel
CAME_IN_BY = {
    "Channel::Whatsapp": "WhatsApp",
    "Channel::Instagram": "Instagram",
    "Channel::FacebookPage": "Facebook",
    "Channel::WebWidget": "Website chat",
    "Channel::Telegram": "Telegram",
    "Channel::Sms": "SMS",
    "Channel::TwilioSms": "SMS",
    "Channel::Email": "Email",
}


def enabled(settings=None) -> bool:
    settings = settings or frappe.get_cached_doc(SETTINGS)
    return bool(
        cint(settings.get("enabled")) and cint(settings.get("messages_section"))
    )


def is_manager(user: str | None = None) -> bool:
    user = user or frappe.session.user
    roles = frappe.get_roles(user)
    return (
        user == "Administrator" or "System Manager" in roles or "Agent Manager" in roles
    )


def can_use(user: str | None = None) -> bool:
    """The Messages screen is open to managers and the front-desk team's members, while the
    Messages section is on (the teams per purpose come with phase 34)."""
    settings = frappe.get_cached_doc(SETTINGS)
    if not enabled(settings):
        return False
    user = user or frappe.session.user
    if is_manager(user):
        return True
    team = settings.get("messages_team")
    return bool(team) and bool(
        frappe.db.exists("HD Team Member", {"parent": team, "user": user})
    )


def tickets_for_all(settings=None) -> bool:
    """Every conversation gets a ticket in the Messages section (docs/messages.md, step 2)."""
    settings = settings or frappe.get_cached_doc(SETTINGS)
    return enabled(settings) and bool(cint(settings.get("ticket_every_conversation")))


def in_messages(ticket) -> bool:
    """Whether a ticket is a Messages ticket (its section), not a Support one."""
    if not ticket:
        return False
    section = ticket.get("custom_section") if hasattr(ticket, "get") else None
    if section is None:
        section = frappe.db.get_value(TICKET, str(ticket), "custom_section")
    return section == MESSAGES


def came_in_by(channel: str | None) -> str:
    return CAME_IN_BY.get(channel or "", "Other chat")


def support_only(filters):
    """Support's ticket lists leave out Messages tickets, unless the filter already asks for a
    section (a manager looking at Messages tickets there). `filters` is a dict or a list of
    [field, op, value] / [doctype, field, op, value]; it is changed in place and returned."""
    if isinstance(filters, dict):
        filters.setdefault("custom_section", ("!=", MESSAGES))
        return filters
    names_section = any(
        isinstance(row, (list, tuple))
        and "custom_section" in [str(part) for part in row[:2]]
        for row in filters
    )
    if not names_section:
        filters.append(["custom_section", "!=", MESSAGES])
    return filters


# --- reading a Chatwoot message -------------------------------------------------------------------


def message_type(message: dict) -> str:
    from helpdesk.chatwoot_bridge import message_type_of

    return message_type_of(message)


def sender_of(message: dict) -> str:
    """Customer, AI, Staff or System."""
    from helpdesk.chatwoot_bridge import sender_type_of

    if message_type(message) == "activity":
        return "System"
    return SENDERS.get(sender_type_of(message), "Staff")


def kind_of(message: dict) -> str:
    kind = message_type(message)
    if kind == "activity":
        return "Activity"
    if message.get("private"):
        return "Note"
    if kind == "template":
        return "Template"
    return "Text"


def direction_of(message: dict) -> str:
    return "In" if message_type(message) == "incoming" else "Out"


def staff_member(message: dict) -> str | None:
    """The TBO Support user a Chatwoot agent is, matched by email; staff sign in with Microsoft."""
    from helpdesk.chatwoot_bridge import sender_type_of

    if sender_type_of(message) != "user":
        return None
    email = str((message.get("sender") or {}).get("email") or "").strip().lower()
    if not email:
        return None
    return frappe.db.get_value("User", {"name": email, "enabled": 1}) or None


def sent_at(message: dict):
    """Chatwoot sends created_at as epoch seconds or as an ISO time in UTC."""
    stamp = message.get("created_at")
    try:
        if (
            isinstance(stamp, int | float)
            or str(stamp or "").replace(".", "", 1).isdigit()
        ):
            moment = datetime.fromtimestamp(float(stamp), tz=timezone.utc)
        elif stamp:
            moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
        else:
            return now_datetime()
    except (TypeError, ValueError, OverflowError):
        return now_datetime()
    utc = moment.astimezone(timezone.utc).replace(tzinfo=None)
    # Datetime fields hold the site's local time, without a zone
    return convert_utc_to_system_timezone(utc).replace(tzinfo=None)


def delivery(message: dict) -> tuple[str, str]:
    """(status, why it failed)."""
    status = STATUSES.get(str(message.get("status") or "").lower(), "")
    error = ""
    if status == "Failed":
        error = str(
            (message.get("content_attributes") or {}).get("external_error") or ""
        )
    return status, error[:1000]


def reply_to(message: dict) -> int:
    return cint((message.get("content_attributes") or {}).get("in_reply_to"))


def file_rows(message: dict) -> list[dict]:
    rows = []
    for attachment in message.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        file_type = FILE_TYPES.get(
            str(attachment.get("file_type") or "").lower(), "Other"
        )
        url = str(attachment.get("data_url") or attachment.get("external_url") or "")
        row = {"file_type": file_type, "source_url": url[:1000], "note": ""}
        if file_type == "Story":
            # Meta does not allow keeping a story's media: only that the customer mentioned us
            row["source_url"] = ""
            row["note"] = _(
                "A story mentioning us. Its media isn't kept (Meta's rule)."
            )
        elif file_type == "Location":
            lat, lng = attachment.get("coordinates_lat"), attachment.get(
                "coordinates_long"
            )
            if lat is not None and lng is not None:
                row["note"] = _("Location: {0}, {1}").format(lat, lng)
                row["source_url"] = f"https://maps.google.com/?q={lat},{lng}"
        elif file_type in ("Contact", "Share", "Other"):
            row["note"] = str(attachment.get("fallback_title") or "")[:500]
        rows.append(row)
    return rows


def preview(text: str, files: list[dict]) -> str:
    text = " ".join(str(text or "").split())
    if not text and files:
        text = "[" + ", ".join(_(row["file_type"]) for row in files) + "]"
    return text[:PREVIEW_CHARS]


# --- keeping a message ----------------------------------------------------------------------------


def keep(
    conversation,
    message: dict,
    author: str | None = None,
    sender_type: str | None = None,
    kind: str | None = None,
    files: list[dict] | None = None,
):
    """The message's row, written or brought up to date; None when the message has no id.

    `conversation` is the bridge's ChatConversation. `author`, `sender_type` and `kind` are given
    when TBO Support itself sent the message (a person's reply, note or template): they win over
    what the webhook says, also when its copy got here first. `files` are the rows of files TBO
    Support sent, already stored here."""
    mid = cint(message.get("id"))
    if not mid or not conversation.row.name:
        return None
    status, error = delivery(message)
    existing = frappe.db.get_value(
        MESSAGE,
        {"chatwoot_message_id": mid},
        ["name", "status", "content", "author", "sender_type", "kind", "direction"],
        as_dict=True,
    )
    if existing:
        ours = {"author": author, "sender_type": sender_type, "kind": kind}
        update_known(existing, message, status, error, ours)
        notify(conversation.row.name, existing.direction)
        return existing.name

    files = files if files is not None else file_rows(message)
    doc = frappe.get_doc(
        {
            "doctype": MESSAGE,
            "conversation": conversation.row.name,
            "hd_ticket": conversation.row.hd_ticket or None,
            "chatwoot_message_id": mid,
            "direction": direction_of(message),
            "sender_type": sender_type or sender_of(message),
            "author": author or staff_member(message),
            "kind": kind or kind_of(message),
            "content": str(message.get("content") or "").strip(),
            "reply_to": reply_to(message) or None,
            "sent_at": sent_at(message),
            "status": status,
            "error": error,
            "files": files,
        }
    )
    # a duplicate id (the other webhook's copy, a moment earlier) raises; the bridge retries
    # the event in a new transaction, which then finds the row
    doc.insert(ignore_permissions=True)
    touch(conversation, doc, files)
    if any(row["file_type"] in COPY_TYPES and row["source_url"] for row in files):
        frappe.enqueue(
            "helpdesk.chat_messages.copy_files",
            queue="short",
            message=doc.name,
            enqueue_after_commit=True,
            now=frappe.flags.in_test,
        )
    notify(conversation.row.name, doc.direction)
    return doc.name


def update_known(
    existing, message: dict, status: str, error: str, ours: dict | None = None
):
    """A message seen before: delivery moves forward only, text that arrived later fills in, and
    what TBO Support knows about its own message (who sent it, its kind) wins."""
    values = {
        field: value
        for field, value in (ours or {}).items()
        if value and existing.get(field) != value
    }
    if status and moves_forward(existing.status or "", status):
        values["status"] = status
        if status == "Failed":
            values["error"] = error
    content = str(message.get("content") or "").strip()
    if content and not existing.content:
        values["content"] = content
    if values:
        frappe.db.set_value(MESSAGE, existing.name, values, update_modified=False)


def notify(conversation: str, direction: str):
    """Live update: the Messages screens reload this conversation. It goes to the room of
    HD Chat Conversation, which only people who may read conversations can join (the page joins it
    while open); only the conversation's name and whether the customer wrote travel."""
    from frappe.realtime import get_doctype_room

    frappe.publish_realtime(
        "helpdesk:chat-message",
        {"conversation": conversation, "direction": direction},
        room=get_doctype_room(CONVERSATION),
        after_commit=True,
    )


def moves_forward(current: str, new: str) -> bool:
    if new == current:
        return False
    if new == "Failed":
        return current != "Read"
    if current == "Failed":
        return False
    return STATUS_ORDER.index(new) > STATUS_ORDER.index(current or "")


def touch(conversation, doc, files: list[dict]):
    """The conversation's list fields after a new message; an older message arriving late
    changes nothing."""
    if doc.kind in ("Note", "Activity"):
        return
    row = conversation.row
    when = get_datetime(doc.sent_at)
    last = (
        get_datetime(row.get("last_message_at")) if row.get("last_message_at") else None
    )
    if last and when < last:
        return
    values = {"last_message_at": when, "last_message": preview(doc.content, files)}
    if doc.direction == "In":
        values.update(
            customer_last_message_at=when,
            waiting_on="Us",
            unread=1,
            window_closes_at=(
                add_to_date(when, hours=WINDOW_HOURS)
                if (row.get("channel") or "") in WINDOW_CHANNELS
                else None
            ),
        )
    else:
        values["waiting_on"] = "Customer"
    conversation.set_values(values)


# --- files ----------------------------------------------------------------------------------------


def copy_files(message: str):
    """Background job: a private copy of each file of the message, within the size limit."""
    doc = frappe.get_doc(MESSAGE, message)
    settings = frappe.get_cached_doc(SETTINGS)
    limit = max(cint(settings.get("max_file_mb")) or 25, 1) * MB
    host = urlparse(settings.get("base_url") or "").hostname
    changed = False
    for row in doc.files:
        if row.file or row.file_type not in COPY_TYPES or not row.source_url:
            continue
        row.note, saved = copy_one(doc, row, host, limit)
        if saved:
            row.file, row.file_name, row.size = saved
        changed = True
    if changed:
        doc.save(ignore_permissions=True)


def copy_one(doc, row, host: str | None, limit: int) -> tuple[str, tuple | None]:
    """(note, (file url, name, size) or None)."""
    url = row.source_url
    if not host or urlparse(url).hostname != host:
        # only files TBO Chat itself serves; never an address a message could point anywhere
        return _("Not copied: the file isn't served by TBO Chat."), None
    try:
        data = download(url, limit)
    except FileTooBig:
        return (
            _("Not copied: bigger than {0} MB. Open it in TBO Chat.").format(
                limit // MB
            ),
            None,
        )
    except requests.RequestException as e:
        return _("Not copied yet: {0}").format(str(e)[:200]), None
    name = file_name(url, row.file_type, doc.chatwoot_message_id)
    try:
        saved = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": name,
                "is_private": 1,
                "content": data,
                "attached_to_doctype": MESSAGE,
                "attached_to_name": doc.name,
            }
        ).insert(ignore_permissions=True)
    except frappe.ValidationError as e:
        frappe.clear_last_message()
        return _("Not copied: {0}").format(str(e)[:200]), None
    return "", (saved.file_url, name, len(data))


class FileTooBig(Exception):
    pass


def download(url: str, limit: int) -> bytes:
    with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()
        if cint(response.headers.get("Content-Length")) > limit:
            raise FileTooBig
        parts, size = [], 0
        for chunk in response.iter_content(CHUNK):
            size += len(chunk)
            if size > limit:
                raise FileTooBig
            parts.append(chunk)
    return b"".join(parts)


def file_name(url: str, file_type: str, message_id) -> str:
    name = unquote(urlparse(url).path.rsplit("/", 1)[-1]).strip()
    name = "".join(ch for ch in name if ch.isalnum() or ch in "._- ")[:120].strip(" .")
    return name or f"{file_type.lower()}-{message_id}"


# --- Move to Support ------------------------------------------------------------------------------


def move_to_support(ticket: str) -> str:
    """A Messages ticket that is really a customer's ERP problem becomes a Support ticket.

    What a Support ticket gets when it arrives, and a Messages ticket skipped, runs now: the
    customer's own people (ticket owner or project team), triage, Copilot and the coordinators'
    notice. The chat stays the ticket's channel: the customer's next messages become replies on the
    ticket, as for any chat ticket, and replies go back on the same channel."""
    from helpdesk import triage
    from helpdesk.chatwoot_bridge import ChatConversation
    from helpdesk.copilot import conversation as copilot_chat
    from helpdesk.copilot import people, runs

    doc = frappe.get_doc(TICKET, str(ticket))
    if doc.get("custom_section") != MESSAGES:
        frappe.throw(_("Ticket {0} is not in Messages.").format(doc.name))
    doc.db_set("custom_section", SUPPORT)
    chat = ChatConversation.for_ticket(doc.name)
    if chat:
        # only messages from now on become replies on the ticket: the earlier ones are in Messages
        message = frappe.qb.DocType(MESSAGE)
        last = (
            frappe.qb.from_(message)
            .select(Max(message.chatwoot_message_id))
            .where(message.conversation == chat.row.name)
            .run()
        )
        chat.set_values({"last_synced_message_id": cint(last[0][0] if last else 0)})
        # Copilot's stage lines reach the chat, as for a ticket the AI raised
        copilot_chat.tbo_chat_ticket(chat.row.name, doc.name)
    doc.assign_customer_owner()
    triage.auto_triage_ticket(doc, None)
    runs.on_ticket_insert(doc)
    people.on_ticket_insert(doc)
    doc.add_comment(
        "Info", _("Moved from Messages to Support by {0}.").format(frappe.session.user)
    )
    return doc.name
