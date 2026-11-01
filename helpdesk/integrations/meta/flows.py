"""The Graph calls that put one post on Facebook or Instagram.

Each flow takes media as `{"url": <public link>, "kind": "image" | "video"}` and returns
`(meta post id, live link or None)`. Docs: Instagram Platform > Content Publishing, and
Pages API > Photos / Videos / Feed."""

import json
import time

from frappe import _

from helpdesk.integrations.meta.graph import GraphClient, MetaError

IMAGE, CAROUSEL, VIDEO, STORY, TEXT = "Image", "Carousel", "Video", "Story", "Text"
# seconds between checks while Instagram processes a video, and how many checks
POLL_SECONDS = 5
POLL_TRIES = 60


def live_link(graph: GraphClient, object_id: str, field: str) -> str | None:
    """The public link of something just posted; a missing link doesn't undo the post."""
    try:
        return graph.get(object_id, fields=field).get(field)
    except MetaError:
        return None


class InstagramFlow:
    def __init__(self, graph: GraphClient, instagram_user_id: str):
        self.graph = graph
        self.account = instagram_user_id

    def publish(self, kind: str, media: list[dict], caption: str, link=None):
        self.check_quota()
        container = getattr(self, f"make_{kind.lower()}")(media, caption)
        self.wait_until_ready(container)
        done = self.graph.post(
            f"{self.account}/media_publish", safe_to_retry=False, creation_id=container
        )
        media_id = done["id"]
        return media_id, live_link(self.graph, media_id, "permalink")

    def check_quota(self):
        """Instagram allows a fixed number of API posts per rolling day; say so before
        starting, instead of failing halfway."""
        data = self.graph.get(
            f"{self.account}/content_publishing_limit", fields="quota_usage,config"
        ).get("data") or [{}]
        used = data[0].get("quota_usage")
        total = (data[0].get("config") or {}).get("quota_total")
        if used is not None and total and used >= total:
            raise MetaError(
                _(
                    "Instagram's daily limit of {0} posts through the API is used up. Try again tomorrow."
                ).format(total)
            )

    def make_image(self, media, caption):
        return self.graph.post(
            f"{self.account}/media", image_url=media[0]["url"], caption=caption
        )["id"]

    def make_story(self, media, caption):
        key = "image_url" if media[0]["kind"] == "image" else "video_url"
        return self.graph.post(
            f"{self.account}/media", media_type="STORIES", **{key: media[0]["url"]}
        )["id"]

    def make_video(self, media, caption):
        return self.graph.post(
            f"{self.account}/media",
            media_type="REELS",
            video_url=media[0]["url"],
            caption=caption,
        )["id"]

    def make_carousel(self, media, caption):
        children = [
            self.graph.post(
                f"{self.account}/media", image_url=m["url"], is_carousel_item="true"
            )["id"]
            for m in media
        ]
        return self.graph.post(
            f"{self.account}/media",
            media_type="CAROUSEL",
            children=",".join(children),
            caption=caption,
        )["id"]

    def wait_until_ready(self, container: str):
        """Instagram fetches and processes the media first; publish only when FINISHED."""
        for _attempt in range(POLL_TRIES):
            info = self.graph.get(container, fields="status_code,status")
            code = info.get("status_code")
            if code == "FINISHED":
                return
            if code in ("ERROR", "EXPIRED"):
                raise MetaError(
                    _("Instagram couldn't process the media: {0}").format(
                        info.get("status") or code
                    )
                )
            time.sleep(POLL_SECONDS)
        raise MetaError(
            _("Instagram is still processing the media. It will be tried again."),
            transient=True,
        )


class FacebookFlow:
    def __init__(self, graph: GraphClient, page_id: str):
        self.graph = graph
        self.page = page_id

    def publish(self, kind: str, media: list[dict], caption: str, link=None):
        if kind == IMAGE:
            done = self.graph.post(
                f"{self.page}/photos",
                safe_to_retry=False,
                url=media[0]["url"],
                caption=caption,
                published="true",
            )
            post_id = done.get("post_id") or done["id"]
            return post_id, live_link(self.graph, post_id, "permalink_url")
        if kind == CAROUSEL:
            # unpublished photos first, then one feed post that attaches them all
            photos = [
                self.graph.post(f"{self.page}/photos", url=m["url"], published="false")[
                    "id"
                ]
                for m in media
            ]
            attached = {
                f"attached_media[{i}]": json.dumps({"media_fbid": photo})
                for i, photo in enumerate(photos)
            }
            post_id = self.graph.post(
                f"{self.page}/feed", safe_to_retry=False, message=caption, **attached
            )["id"]
            return post_id, live_link(self.graph, post_id, "permalink_url")
        if kind == VIDEO:
            video_id = self.graph.post(
                f"{self.page}/videos",
                safe_to_retry=False,
                file_url=media[0]["url"],
                description=caption,
            )["id"]
            return video_id, live_link(self.graph, video_id, "permalink_url")
        post_id = self.graph.post(
            f"{self.page}/feed", safe_to_retry=False, message=caption, link=link
        )["id"]
        return post_id, live_link(self.graph, post_id, "permalink_url")
