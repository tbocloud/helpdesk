"""Reading a client's reach from Meta into the hub, for the Reach report
(docs/meta-insights.md).

Two kinds of rows are kept: one per day per platform (HD Meta Daily Insight) and one per
post (HD Meta Post Insight). Nights sync the last few days, since Meta can be up to 48
hours late; a new connection or "Sync now" fills in the last 90 days. Instagram Stories
are read every hour, because their numbers are gone 24 hours after posting.

Meta renames insight metrics now and then, so every name is in one of the maps below. A
metric Meta no longer knows is skipped and named in the connection's insights error,
instead of stopping the rest of the sync."""

from datetime import datetime, time

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, getdate, now_datetime, today
from frappe.utils.data import convert_utc_to_system_timezone

from helpdesk.helpdesk.doctype.hd_meta_connection.hd_meta_connection import (
    CONNECTED,
    EXPIRED,
)
from helpdesk.helpdesk.doctype.hd_meta_daily_insight.hd_meta_daily_insight import (
    HDMetaDailyInsight,
)
from helpdesk.helpdesk.doctype.hd_meta_post_insight.hd_meta_post_insight import (
    HDMetaPostInsight,
)
from helpdesk.integrations.meta import connect
from helpdesk.integrations.meta.graph import GraphClient, MetaError

DAILY = "HD Meta Daily Insight"
POSTS = "HD Meta Post Insight"
PUBLISH = "HD Content Publish"
FACEBOOK, INSTAGRAM = "Facebook", "Instagram"

# days a nightly sync reads again (Meta's numbers can be up to 48 hours late)
NIGHTLY_DAYS = 3
# days a new connection or "Sync now" fills in; Facebook allows 90 days a request
BACKFILL_DAYS = 90
# posts younger than this get their numbers refreshed each night
POST_REFRESH_DAYS = 30
PAGE_SIZE = 50
# Graph's "invalid parameter" code: what a retired or misspelt metric gets
INVALID_METRIC = 100
# a Story with fewer than 5 viewers has no numbers ("Not enough viewers")
TOO_FEW_VIEWERS = 10

# Page insights, period=day: our field -> Meta's metric
PAGE_METRICS = {
    "reach": "page_total_media_view_unique",
    "views": "page_media_view",
    "engagements": "page_post_engagements",
    "follows": "page_daily_follows_unique",
    "unfollows": "page_daily_unfollows_unique",
}
# Instagram account insights, metric_type=total_value, asked one day at a time
INSTAGRAM_METRICS = {
    "reach": "reach",
    "views": "views",
    "engaged_accounts": "accounts_engaged",
    "engagements": "total_interactions",
}
# follows_and_unfollows by follow_type: who followed, and who unfollowed
FOLLOW_TYPES = {"FOLLOWER": "follows", "NON_FOLLOWER": "unfollows"}
# a Facebook post's lifetime numbers; reactions come by type and are added up
FACEBOOK_POST_METRICS = {
    "reach": "post_total_media_view_unique",
    "views": "post_media_view",
    "clicks": "post_clicks",
    "reactions": "post_reactions_by_type_total",
}
# an Instagram post's lifetime numbers; Stories have no likes, comments or saves
INSTAGRAM_POST_METRICS = {
    "reach": "reach",
    "views": "views",
    "reactions": "likes",
    "comments": "comments",
    "shares": "shares",
    "saves": "saved",
    "interactions": "total_interactions",
}
STORY_METRICS = ("reach", "views", "shares", "interactions")


# --------------------------------------------------------------- who and when --


def can_sync(connection) -> bool:
    return bool(
        connection
        and connection.status == CONNECTED
        and connection.insights_allowed
        and connection.page_token()
    )


def graph_for(connection) -> GraphClient:
    _app_id, secret = connect.app()
    return GraphClient(connection.page_token(), secret)


def sync_all():
    """Scheduler, every night: the last few days and recent posts of every client who
    allowed insights. One client failing doesn't stop the others."""
    if not connect.insights_enabled():
        return
    for project in syncable_projects():
        try:
            sync_connection(project, NIGHTLY_DAYS)
        except Exception:  # noqa: BLE001 - one bad connection must not stop the others
            frappe.log_error(title=f"Meta insights sync failed for {project}")


def sync_stories():
    """Scheduler, every hour: Instagram Stories still up, before their numbers expire."""
    if not connect.insights_enabled():
        return
    for project in syncable_projects(instagram=True):
        connection = frappe.get_doc(connect.CONNECTION, project)
        try:
            InsightsSync(connection).sync_stories()
        except MetaError as e:
            if e.token_expired:
                connection.mark(EXPIRED, e.user_message)
        except Exception:  # noqa: BLE001 - one bad connection must not stop the others
            frappe.log_error(title=f"Meta Stories sync failed for {project}")


def syncable_projects(instagram: bool = False) -> list[str]:
    filters = {"status": CONNECTED, "insights_allowed": 1}
    if instagram:
        filters["instagram_user_id"] = ["is", "set"]
    return frappe.get_all(connect.CONNECTION, filters=filters, pluck="name")


def queue_sync(project: str, days: int = BACKFILL_DAYS):
    """Fill in the last `days` in the background (a new connection, "Sync now")."""
    frappe.enqueue(
        "helpdesk.integrations.meta.insights.sync_connection",
        queue="long",
        project=project,
        days=days,
        job_id=f"meta-insights-{project}",
        deduplicate=True,
    )


def sync_connection(project: str, days: int = NIGHTLY_DAYS):
    """Read the last `days` days and the posts of that time (or the last 30 days, if
    longer) for one client. What went wrong is kept on the connection for the report."""
    connection = frappe.get_doc(connect.CONNECTION, project)
    if not can_sync(connection):
        return
    sync = InsightsSync(connection)
    error = None
    try:
        sync.run(days)
    except MetaError as e:
        if e.token_expired:
            connection.mark(EXPIRED, e.user_message)
        error = e.user_message
    if sync.skipped and not error:
        error = _("Meta no longer gives these numbers: {0}").format(
            ", ".join(sorted(sync.skipped))
        )
    connection.db_set(
        {"insights_synced_on": now_datetime(), "insights_error": error},
        update_modified=False,
    )


# --------------------------------------------------------------------- the sync --


class InsightsSync:
    def __init__(self, connection):
        self.connection = connection
        self.graph = graph_for(connection)
        # metric names Meta refused, for the connection's insights error
        self.skipped: set[str] = set()
        self._published: dict[str, dict[str, str]] | None = None

    def run(self, days: int):
        last = getdate(add_days(today(), -1))
        first = getdate(add_days(last, -(days - 1)))
        since = getdate(add_days(today(), -max(days, POST_REFRESH_DAYS)))
        self.sync_page_days(first, last)
        self.sync_facebook_posts(since)
        if self.connection.instagram_user_id:
            self.sync_instagram_days(first, last)
            self.sync_instagram_posts(since)
        self.record_followers(last)

    # -- days

    def sync_page_days(self, first, last):
        rows = self.metrics(
            f"{self.connection.facebook_page_id}/insights",
            PAGE_METRICS,
            period="day",
            since=unix(first),
            until=unix(add_days(last, 1)),
        )
        days: dict = {}
        for field, item in rows.items():
            for point in item.get("values") or []:
                # each value's end_time is the end of its day, i.e. the next midnight
                day = getdate(add_days(getdate(point["end_time"][:10]), -1))
                if first <= day <= last:
                    days.setdefault(day, {})[field] = number(point.get("value"))
        for day, values in days.items():
            self.save_day(FACEBOOK, day, values)

    def sync_instagram_days(self, first, last):
        day = first
        while day <= last:
            rows = self.metrics(
                f"{self.connection.instagram_user_id}/insights",
                INSTAGRAM_METRICS,
                period="day",
                metric_type="total_value",
                since=unix(day),
                until=unix(add_days(day, 1)),
            )
            values = {
                field: number((item.get("total_value") or {}).get("value"))
                for field, item in rows.items()
            }
            values.update(self.instagram_follows(day))
            if values:
                self.save_day(INSTAGRAM, day, values)
            day = getdate(add_days(day, 1))

    def instagram_follows(self, day) -> dict:
        """follows_and_unfollows split by follow_type; asked alone, since a breakdown
        Meta can't apply to every metric of a request fails the whole request. Accounts
        under 100 followers get nothing back."""
        try:
            data = self.graph.get(
                f"{self.connection.instagram_user_id}/insights",
                metric="follows_and_unfollows",
                period="day",
                metric_type="total_value",
                breakdown="follow_type",
                since=unix(day),
                until=unix(add_days(day, 1)),
            ).get("data")
        except MetaError as e:
            if e.transient or e.token_expired:
                raise
            return {}
        item = next(
            (i for i in data or [] if i.get("name") == "follows_and_unfollows"), {}
        )
        values = {}
        for breakdown in (item.get("total_value") or {}).get("breakdowns") or []:
            for result in breakdown.get("results") or []:
                kind = (result.get("dimension_values") or [None])[0]
                if kind in FOLLOW_TYPES:
                    values[FOLLOW_TYPES[kind]] = cint(result.get("value"))
        return values

    def record_followers(self, day):
        """Meta only tells today's follower total, so each sync writes it on the last day
        it read; the report draws the follower line from these."""
        page = self.graph.get(
            self.connection.facebook_page_id, fields="followers_count"
        )
        self.save_day(FACEBOOK, day, {"followers": cint(page.get("followers_count"))})
        if self.connection.instagram_user_id:
            account = self.graph.get(
                self.connection.instagram_user_id, fields="followers_count"
            )
            self.save_day(
                INSTAGRAM, day, {"followers": cint(account.get("followers_count"))}
            )

    def save_day(self, platform: str, day, values: dict):
        name = HDMetaDailyInsight.key(self.connection.project, platform, day)
        if frappe.db.exists(DAILY, name):
            frappe.db.set_value(DAILY, name, values)
            return
        frappe.get_doc(
            {
                "doctype": DAILY,
                "project": self.connection.project,
                "customer": self.connection.customer,
                "platform": platform,
                "day": day,
                **values,
            }
        ).insert(ignore_permissions=True)

    # -- posts

    def sync_facebook_posts(self, since):
        posts = self.pages(
            f"{self.connection.facebook_page_id}/published_posts",
            stop=lambda post: getdate(post["created_time"][:10]) < since,
            fields="id,message,created_time,permalink_url,full_picture,"
            "attachments{media_type},shares,comments.summary(true).limit(0)",
            since=unix(since),
        )
        for post in posts:
            rows = self.metrics(f"{post['id']}/insights", FACEBOOK_POST_METRICS)
            values = {
                field: number((item.get("values") or [{}])[0].get("value"))
                for field, item in rows.items()
            }
            values["comments"] = cint(
                ((post.get("comments") or {}).get("summary") or {}).get("total_count")
            )
            values["shares"] = cint((post.get("shares") or {}).get("count"))
            values["interactions"] = (
                values.get("reactions", 0) + values["comments"] + values["shares"]
            )
            self.save_post(
                FACEBOOK,
                post["id"],
                {
                    "kind": facebook_kind(post),
                    "posted_on": meta_datetime(post["created_time"]),
                    "caption": (post.get("message") or "")[:500],
                    "permalink": post.get("permalink_url"),
                    "thumbnail_url": post.get("full_picture"),
                    **values,
                },
            )

    def sync_instagram_posts(self, since):
        posts = self.pages(
            f"{self.connection.instagram_user_id}/media",
            stop=lambda media: getdate(media["timestamp"][:10]) < since,
            fields="id,caption,media_type,media_product_type,permalink,timestamp,"
            "thumbnail_url,media_url",
        )
        for media in posts:
            self.save_instagram_media(media)

    def sync_stories(self):
        for story in self.pages(
            f"{self.connection.instagram_user_id}/stories",
            fields="id,caption,media_type,media_product_type,permalink,timestamp,"
            "thumbnail_url,media_url",
        ):
            self.save_instagram_media(story)

    def save_instagram_media(self, media: dict):
        kind = instagram_kind(media)
        wanted = {
            field: metric
            for field, metric in INSTAGRAM_POST_METRICS.items()
            if kind != "Story" or field in STORY_METRICS
        }
        note = None
        try:
            rows = self.metrics(f"{media['id']}/insights", wanted)
        except MetaError as e:
            if e.code != TOO_FEW_VIEWERS:
                raise
            rows, note = {}, _(
                "Fewer than 5 people viewed it, so Meta shows no numbers."
            )
        values = {
            field: number((item.get("values") or [{}])[0].get("value"))
            for field, item in rows.items()
        }
        self.save_post(
            INSTAGRAM,
            media["id"],
            {
                "kind": kind,
                "posted_on": meta_datetime(media["timestamp"]),
                "caption": (media.get("caption") or "")[:500],
                "permalink": media.get("permalink"),
                "thumbnail_url": media.get("thumbnail_url") or media.get("media_url"),
                "insights_note": note,
                **values,
            },
        )

    def save_post(self, platform: str, media_id: str, values: dict):
        values["last_synced"] = now_datetime()
        values["content_post"] = self.content_post(platform, media_id)
        name = HDMetaPostInsight.key(platform, media_id)
        if frappe.db.exists(POSTS, name):
            frappe.db.set_value(POSTS, name, values, update_modified=False)
            return
        frappe.get_doc(
            {
                "doctype": POSTS,
                "project": self.connection.project,
                "customer": self.connection.customer,
                "platform": platform,
                "media_id": media_id,
                **values,
            }
        ).insert(ignore_permissions=True)

    def content_post(self, platform: str, media_id: str) -> str | None:
        """The content calendar post the hub published as this one. A Facebook video
        is kept by its video id, while Meta lists it as "<page>_<video id>"."""
        if self._published is None:
            self._published = {FACEBOOK: {}, INSTAGRAM: {}}
            rows = frappe.get_all(
                PUBLISH,
                filters={"status": "Published", "meta_post_id": ["is", "set"]},
                fields=["parent", "target", "meta_post_id"],
            )
            for row in rows:
                if row.target in self._published:
                    self._published[row.target][row.meta_post_id] = row.parent
        found = self._published[platform]
        return found.get(media_id) or found.get(media_id.split("_", 1)[-1])

    # -- Graph helpers

    def metrics(self, path: str, wanted: dict, **params) -> dict:
        """{our field: Meta's insight row} for the metrics Meta knows. All are asked at
        once; when Meta refuses the request for a bad metric, each is asked alone and the
        refused ones are skipped (and remembered)."""
        by_metric = {metric: field for field, metric in wanted.items()}
        try:
            data = self.graph.get(path, metric=",".join(by_metric), **params)
        except MetaError as e:
            if not refused_metric(e):
                raise
            if len(by_metric) == 1:
                self.skipped.update(by_metric)
                return {}
            rows = {}
            for field, metric in wanted.items():
                rows.update(self.metrics(path, {field: metric}, **params))
            return rows
        return {
            by_metric[item["name"]]: item
            for item in data.get("data") or []
            if item.get("name") in by_metric
        }

    def pages(self, path: str, stop=None, **params) -> list[dict]:
        """Every item of a paged Graph list, newest first, until `stop(item)` is true."""
        items, after = [], None
        while True:
            body = self.graph.get(path, limit=PAGE_SIZE, after=after, **params)
            for item in body.get("data") or []:
                if stop and stop(item):
                    return items
                items.append(item)
            paging = body.get("paging") or {}
            after = (paging.get("cursors") or {}).get("after")
            if not (paging.get("next") and after):
                return items


# -------------------------------------------------------------------- helpers --


def unix(day) -> int:
    return int(datetime.combine(getdate(day), time.min).timestamp())


def meta_datetime(value: str):
    """Meta's "2026-11-20T09:30:00+0000" (UTC) as a naive datetime in the site's time."""
    return convert_utc_to_system_timezone(get_datetime(value[:19])).replace(tzinfo=None)


def number(value) -> int:
    """An insight value as one count: reactions by type are added up."""
    if isinstance(value, dict):
        return sum(cint(v) for v in value.values())
    return cint(value)


def facebook_kind(post: dict) -> str:
    media_type = (((post.get("attachments") or {}).get("data") or [{}])[0]).get(
        "media_type"
    )
    return {"photo": "Image", "album": "Carousel", "video": "Video"}.get(
        media_type, "Text" if not media_type or media_type == "link" else "Other"
    )


def instagram_kind(media: dict) -> str:
    product = media.get("media_product_type")
    if product in ("REELS", "STORY"):
        return {"REELS": "Reel", "STORY": "Story"}[product]
    return {"IMAGE": "Image", "CAROUSEL_ALBUM": "Carousel", "VIDEO": "Video"}.get(
        media.get("media_type"), "Other"
    )


def refused_metric(error: MetaError) -> bool:
    """Meta's "(#100) ... must be a valid insights metric": the same code also means an
    object without insights, which is not a retired metric."""
    return error.code == INVALID_METRIC and "metric" in error.user_message.lower()
