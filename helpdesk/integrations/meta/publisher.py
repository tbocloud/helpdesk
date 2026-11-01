"""Publishing a client-approved content post to the client's Facebook Page and Instagram
(docs/meta-publishing.md).

The post carries one `HD Content Publish` row per target. Queueing writes the rows;
`process_post` (run in the background for "Publish now", and by the five-minute
scheduler for scheduled rows) claims each due row once, posts it, and records the live
link or the error. Transient errors are tried again with a growing wait, three tries in
all; the final failure tells the post's people."""

import html
import re

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, cstr, get_datetime, now_datetime, strip_html

from helpdesk.content_team import head_approvers
from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
    content_project_for,
)
from helpdesk.helpdesk.doctype.hd_content_publish.hd_content_publish import (
    FAILED,
    PUBLISHED,
    PUBLISHING,
    QUEUED,
)
from helpdesk.helpdesk.doctype.hd_meta_connection.hd_meta_connection import (
    CONNECTED,
    EXPIRED,
)
from helpdesk.integrations.meta import signing
from helpdesk.integrations.meta.connect import app
from helpdesk.integrations.meta.flows import (
    CAROUSEL,
    IMAGE,
    STORY,
    TEXT,
    VIDEO,
    FacebookFlow,
    InstagramFlow,
)
from helpdesk.integrations.meta.graph import GraphClient, MetaError
from helpdesk.tasky.permissions import can_handle_credentials
from helpdesk.work_reminders import notify_users

POST = "HD Content Post"
PUBLISH = "HD Content Publish"
CONNECTION = "HD Meta Connection"
FACEBOOK, INSTAGRAM = "Facebook", "Instagram"
TARGETS = (FACEBOOK, INSTAGRAM)
# the client has approved (and the Digital Marketing Head); nothing earlier may go out
PUBLISHABLE = ("Approved", "Scheduled")
MAX_TRIES = 3
# minutes to wait after the first and second failed try
RETRY_MINUTES = (5, 15)
# a row left Publishing this long means its worker died
STALE_MINUTES = 30
IMAGE_TYPES = ("jpg", "jpeg", "png", "webp")
VIDEO_TYPES = ("mp4", "mov")
# Instagram accepts JPEG images only
INSTAGRAM_IMAGE_TYPES = ("jpg", "jpeg")
CAROUSEL_MAX = 10


# --------------------------------------------------------------- what to post --


def extension(file_name: str | None) -> str:
    return (file_name or "").rsplit(".", 1)[-1].lower()


def post_media(post: str) -> list[dict]:
    """The post's images and videos, oldest first. Other attachments (designs, documents)
    are for the team and are never posted."""
    files = frappe.qb.get_query(
        "File",
        fields=["name", "file_name"],
        filters={
            "attached_to_doctype": POST,
            "attached_to_name": post,
            "is_folder": 0,
        },
        order_by="creation asc",
    ).run(as_dict=True)
    media = []
    for f in files:
        ext = extension(f.file_name)
        if ext in IMAGE_TYPES:
            media.append({"file": f.name, "name": f.file_name, "kind": "image"})
        elif ext in VIDEO_TYPES:
            media.append({"file": f.name, "name": f.file_name, "kind": "video"})
    return media


def resolve_kind(media: list[dict], requested: str | None) -> str:
    """Text, Image, Carousel or Video from what is attached; Story only when asked for."""
    if requested == STORY:
        if len(media) != 1:
            frappe.throw(_("A Story is one image or one video. Attach just that one."))
        return STORY
    if not media:
        return TEXT
    if len(media) == 1:
        return IMAGE if media[0]["kind"] == "image" else VIDEO
    if any(m["kind"] == "video" for m in media):
        frappe.throw(_("Attach one video, or 2 to 10 images, not a mix."))
    if len(media) > CAROUSEL_MAX:
        frappe.throw(
            _("A carousel holds at most 10 images; this post has {0}.").format(
                len(media)
            )
        )
    return CAROUSEL


def check_target(target: str, kind: str, media: list[dict], connection):
    """Refuse, in plain words, a target this post can't go to."""
    if target == INSTAGRAM:
        if not connection.instagram_user_id:
            frappe.throw(
                _(
                    "This Page has no Instagram business account linked, so it can't go to Instagram."
                )
            )
        if kind == TEXT:
            frappe.throw(
                _("Instagram needs an image or a video. Attach one to post there.")
            )
        bad = [
            m["name"]
            for m in media
            if m["kind"] == "image"
            and extension(m["name"]) not in INSTAGRAM_IMAGE_TYPES
        ]
        if bad:
            frappe.throw(
                _("Instagram takes JPEG images only. Convert {0} to .jpg.").format(
                    ", ".join(bad)
                )
            )
    elif kind == STORY:
        frappe.throw(_("Stories can only go to Instagram here."))


def html_to_text(text: str | None) -> str:
    text = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", text or "")
    lines = [line.strip() for line in html.unescape(strip_html(text)).splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def caption_for(post) -> str:
    """The post's sub copy (its title when that is empty), then its hashtags."""
    text = html_to_text(post.caption) or cstr(post.title).strip()
    tags = " ".join(
        t if t.startswith("#") else f"#{t}"
        for t in re.split(r"[,\s]+", post.hashtags or "")
        if t
    )
    return "\n\n".join(part for part in (text, tags) if part)


def default_targets(post) -> list[str]:
    """The targets named in the post's platforms."""
    platforms = (post.platforms or post.channel or "").lower()
    return [t for t in TARGETS if t.lower() in platforms]


# ------------------------------------------------------------- who and which --


def connection_for(post):
    """The connection of the post's project, else a connected one for the same customer."""
    project = content_project_for(post.customer)
    name = project if project and frappe.db.exists(CONNECTION, project) else None
    if not name and post.customer:
        name = frappe.db.get_value(
            CONNECTION, {"customer": post.customer, "status": CONNECTED}
        )
    return frappe.get_doc(CONNECTION, name) if name else None


def require_publisher(post, connection=None):
    """Who may publish: whoever may handle the project's client accounts (its managers
    and lead, the Digital Marketing Head, System Managers), never a Sales Employee."""
    project = connection.project if connection else content_project_for(post.customer)
    post.check_permission("read")
    if not can_handle_credentials(project):
        frappe.throw(
            _(
                "Only the project's managers and the Digital Marketing Head can publish to Meta."
            ),
            frappe.PermissionError,
        )


def blocked_reason(post, connection) -> str | None:
    """Why this post can't be published to Meta right now, or None."""
    if not frappe.db.get_single_value("HD Meta Settings", "enabled"):
        return _(
            "Meta publishing is switched off. A System Manager turns it on in Settings → Meta."
        )
    if not connection or connection.status == "Pending":
        return _("Connect Meta on the project first.")
    if connection.status != CONNECTED:
        return _(
            "The Meta connection needs attention: connect Meta again on the project."
        )
    if post.status not in PUBLISHABLE:
        return _("Only an approved post can be published. This one is {0}.").format(
            _(post.status)
        )
    return None


# ------------------------------------------------------------------ queueing --


def queue(
    post_name: str, targets: list[str], requested_kind=None, publish_at=None, link=None
):
    """Queue the post for these targets: now, or at `publish_at`. Returns the post."""
    post = frappe.get_doc(POST, post_name)
    connection = connection_for(post)
    require_publisher(post, connection)
    if reason := blocked_reason(post, connection):
        frappe.throw(reason)
    targets = [t for t in TARGETS if t in (targets or [])]
    if not targets:
        frappe.throw(_("Pick Facebook, Instagram or both."))
    media = post_media(post.name)
    kind = resolve_kind(media, requested_kind)
    for target in targets:
        check_target(target, kind, media, connection)
    if kind == TEXT and not caption_for(post):
        frappe.throw(_("There is nothing to post: add copy or an image first."))
    when = get_datetime(publish_at) if publish_at else now_datetime()
    now = now_datetime()
    busy = [
        r.target
        for r in post.meta_publishes
        if r.target in targets and r.status in (PUBLISHING, PUBLISHED)
    ]
    if busy:
        frappe.throw(
            _("{0}: already {1}. It can't be posted twice.").format(
                ", ".join(busy), _("posting or posted")
            )
        )
    post.set(
        "meta_publishes",
        [r for r in post.meta_publishes if r.target not in targets],
    )
    for target in targets:
        post.append(
            "meta_publishes",
            {
                "target": target,
                "status": QUEUED,
                "publish_kind": kind,
                "publish_at": when,
                "queued_by": frappe.session.user,
                "link": link,
                "attempts": 0,
            },
        )
    later = when > add_to_date(now, minutes=1)
    if later:
        post.status = "Scheduled"
    post.meta_publish_on = when if later else None
    post.save(ignore_permissions=True)
    if not later:
        frappe.enqueue(
            "helpdesk.integrations.meta.publisher.process_post",
            post_name=post.name,
            queue="long",
            timeout=1800,
            enqueue_after_commit=True,
        )
    return post


def cancel_queued(post_name: str, target: str | None = None):
    """Take queued targets off the schedule (a post already being sent can't be stopped)."""
    post = frappe.get_doc(POST, post_name)
    require_publisher(post, connection_for(post))
    keep = [
        r
        for r in post.meta_publishes
        if r.status != QUEUED or (target and r.target != target)
    ]
    post.set("meta_publishes", keep)
    post.save(ignore_permissions=True)
    refresh_post(post.name)
    return frappe.get_doc(POST, post_name)


# ---------------------------------------------------------------- publishing --


def process_post(post_name: str):
    """Send every queued target of the post that is due."""
    for row in due_rows(post_name):
        publish_row(row)


def due_rows(post_name: str | None = None) -> list[str]:
    """Names of queued rows whose time (and retry wait) has come."""
    now = now_datetime()
    Row = frappe.qb.DocType(PUBLISH)
    query = (
        frappe.qb.from_(Row)
        .select(Row.name)
        .where(Row.parenttype == POST)
        .where(Row.status == QUEUED)
        .where((Row.publish_at.isnull()) | (Row.publish_at <= now))
        .where((Row.next_try_on.isnull()) | (Row.next_try_on <= now))
        .orderby(Row.publish_at)
    )
    if post_name:
        query = query.where(Row.parent == post_name)
    return query.run(pluck=True)


def publish_due():
    """Scheduler, every five minutes: send what is due, and free rows a dead worker left."""
    free_stale_rows()
    for row in due_rows():
        try:
            publish_row(row)
        except Exception:  # noqa: BLE001 - one bad post must not stop the others
            frappe.log_error(title=f"Meta publish failed for {row}")


def free_stale_rows():
    cutoff = add_to_date(now_datetime(), minutes=-STALE_MINUTES)
    Row = frappe.qb.DocType(PUBLISH)
    stale = (
        frappe.qb.from_(Row)
        .select(Row.name, Row.parent)
        .where(Row.status == PUBLISHING)
        .where(Row.modified < cutoff)
        .run(as_dict=True)
    )
    for row in stale:
        record_failure(
            row.name,
            MetaError(
                _("The post was interrupted. Check the page before trying again.")
            ),
        )


def claim(row_name: str) -> bool:
    """Take a queued row for publishing, once: whoever flips it to Publishing owns it."""
    status = frappe.db.get_value(PUBLISH, row_name, "status", for_update=True)
    if status != QUEUED:
        return False
    frappe.db.set_value(PUBLISH, row_name, "status", PUBLISHING)
    frappe.db.commit()  # the claim must be visible to the next scheduler run at once - nosemgrep
    return True


def publish_row(row_name: str):
    if not claim(row_name):
        return
    row = frappe.get_doc(PUBLISH, row_name)
    post = frappe.get_doc(POST, row.parent)
    connection = connection_for(post)
    try:
        if post.status not in PUBLISHABLE or not connection:
            raise MetaError(
                _("The post is no longer approved, or has no Meta connection.")
            )
        _app_id, secret = app()
        graph = GraphClient(connection.page_token(), secret)
        flow = (
            InstagramFlow(graph, connection.instagram_user_id)
            if row.target == INSTAGRAM
            else FacebookFlow(graph, connection.facebook_page_id)
        )
        media = [
            {"url": signing.media_url(m["file"]), "kind": m["kind"]}
            for m in post_media(post.name)
        ]
        meta_id, permalink = flow.publish(
            row.publish_kind, media, caption_for(post), row.link
        )
    except MetaError as e:
        record_failure(row_name, e)
    else:
        frappe.db.set_value(
            PUBLISH,
            row_name,
            {
                "status": PUBLISHED,
                "meta_post_id": meta_id,
                "permalink": permalink,
                "published_on": now_datetime(),
                "error": None,
                "next_try_on": None,
            },
        )
        frappe.db.commit()  # a post that is live on Meta must be recorded even if a later step fails - nosemgrep
        refresh_post(post.name)


def record_failure(row_name: str, error: MetaError):
    """A failed try: wait and try again if it may pass and tries are left, else Failed
    and tell the people on the post."""
    row = frappe.get_doc(PUBLISH, row_name)
    attempts = cint(row.attempts) + 1
    retry = error.transient and attempts < MAX_TRIES
    frappe.db.set_value(
        PUBLISH,
        row_name,
        {
            "status": QUEUED if retry else FAILED,
            "attempts": attempts,
            "error": error.user_message,
            "next_try_on": (
                add_to_date(now_datetime(), minutes=RETRY_MINUTES[attempts - 1])
                if retry
                else None
            ),
        },
    )
    if error.token_expired:
        connection = connection_for(frappe.get_doc(POST, row.parent))
        if connection:
            connection.mark(EXPIRED, error.user_message)
    frappe.db.commit()  # the failure and its wait must survive the notification step - nosemgrep
    refresh_post(row.parent)
    if not retry:
        tell_failure(row.parent, row.target, error.user_message)


def tell_failure(post_name: str, target: str, message: str):
    post = frappe.get_doc(POST, post_name)
    people = {post.owner, post.marketer, *head_approvers()}
    notify_users(
        sorted(u for u in people if u),
        POST,
        post_name,
        _("Couldn't post {0} to {1}: {2}").format(post.label, _(target), message),
        link=post.board_path(),
    )


def refresh_post(post_name: str):
    """Keep the post in step with its rows: the next auto-publish time, Scheduled while
    something waits, and Published (with the live link) once every target is."""
    post = frappe.get_doc(POST, post_name)
    rows = post.meta_publishes
    queued = [r for r in rows if r.status == QUEUED]
    pending = queued + [r for r in rows if r.status == PUBLISHING]
    upcoming = min(
        (get_datetime(r.next_try_on or r.publish_at) for r in queued if r.publish_at),
        default=None,
    )
    if rows and not pending and all(r.status == PUBLISHED for r in rows):
        links = {r.target: r.permalink for r in rows if r.permalink}
        facebook = next((r for r in rows if r.target == FACEBOOK), None)
        post.meta_publish_on = None
        post.status = "Published"
        # a post can't be Published without a link; a missing permalink falls back to the id
        post.published_url = (
            links.get(FACEBOOK)
            or links.get(INSTAGRAM)
            or (facebook and f"https://www.facebook.com/{facebook.meta_post_id}")
            or f"https://www.instagram.com/{connection_for(post).instagram_username}/"
        )
        post.save(ignore_permissions=True)
        post.add_comment(
            "Info",
            _("Published to {0} by the hub.").format(
                ", ".join(_(r.target) for r in rows)
            ),
        )
        return
    frappe.db.set_value(
        POST, post_name, "meta_publish_on", upcoming, update_modified=False
    )
    if post.status == "Scheduled" and not pending:
        frappe.db.set_value(
            POST, post_name, "status", "Approved", update_modified=False
        )


# --------------------------------------------------------------------- state --


def publish_state(post_name: str) -> dict:
    """Everything the Publish to Meta section shows, with no tokens."""
    post = frappe.get_doc(POST, post_name)
    post.check_permission("read")
    connection = connection_for(post)
    project = connection.project if connection else content_project_for(post.customer)
    media = post_media(post.name)
    try:
        kind = resolve_kind(media, None)
        media_problem = None
    except frappe.ValidationError as e:
        kind, media_problem = None, strip_html(str(e))
    reason = blocked_reason(post, connection)
    return {
        "project": project,
        "can_publish": can_handle_credentials(project),
        "blocked_reason": reason,
        "connection": connection
        and {
            "status": connection.status,
            "page_name": connection.facebook_page_name,
            "instagram_username": connection.instagram_username,
            "last_error": connection.last_error,
        },
        "targets": [
            {
                "name": t,
                "available": t == FACEBOOK
                or bool(connection and connection.instagram_user_id),
            }
            for t in TARGETS
        ],
        "default_targets": default_targets(post),
        "kind": kind,
        "media_problem": media_problem,
        "media": [{"name": m["name"], "kind": m["kind"]} for m in media],
        "caption": caption_for(post),
        "default_publish_at": cstr(post.publish_on) if post.publish_on else None,
        "publishes": [
            {
                "target": r.target,
                "status": r.status,
                "kind": r.publish_kind,
                "publish_at": cstr(r.publish_at) if r.publish_at else None,
                "published_on": cstr(r.published_on) if r.published_on else None,
                "permalink": r.permalink,
                "error": r.error,
                "attempts": r.attempts,
            }
            for r in post.meta_publishes
        ],
    }
