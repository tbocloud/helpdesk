from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime
from frappe.utils.password import get_decrypted_password

from helpdesk.api import meta as meta_api
from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
    content_project_for,
)
from helpdesk.integrations.meta import connect, publisher, signing
from helpdesk.test_utils import (
    FakeGraph,
    attach_media,
    create_customer,
    enable_meta,
    hold_commits,
    make_approved_post,
    make_department,
    make_dm_head,
    make_meta_connection,
    make_sales_employee,
    make_tasky_user,
    run_as_user,
)

CUSTOMER = "Meta Publish Client"
MANAGER = "meta.manager@meta.example"
MEMBER = "meta.member@meta.example"
SALES = "meta.sales@meta.example"
HEAD = "meta.head@meta.example"
SLEEP = "helpdesk.integrations.meta.flows.time.sleep"
ENQUEUE = "helpdesk.integrations.meta.publisher.frappe.enqueue"
NOTIFY = "helpdesk.integrations.meta.publisher.notify_users"

OAUTH = {
    "POST oauth/access_token": {},
    "GET oauth/access_token": [
        {"access_token": "short"},
        {"access_token": "long-lived"},
    ],
    "GET me/permissions": {
        "data": [{"permission": s, "status": "granted"} for s in connect.SCOPES]
    },
    "GET me/accounts": {
        "data": [
            {
                "id": "page-1",
                "name": "Client Page",
                "access_token": "page-token",
                "tasks": ["CREATE_CONTENT"],
                "instagram_business_account": {"id": "ig-1", "username": "client_ig"},
            },
            {
                "id": "page-2",
                "name": "Viewer Only",
                "access_token": "x",
                "tasks": ["ANALYZE"],
            },
        ]
    },
}


class MetaCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        enable_meta()
        create_customer(CUSTOMER)
        make_tasky_user(MANAGER, "Meta Manager")
        make_tasky_user(MEMBER, "Meta Member")
        make_sales_employee(SALES, "Meta Sales")
        make_dm_head(HEAD, "Meta Head")
        digital = make_department("Digital")
        self.post = make_approved_post("Monday offer", CUSTOMER)
        self.project = content_project_for(CUSTOMER)
        project = frappe.get_doc("Project", self.project)
        project.custom_department = digital.name
        project.append("users", {"user": MANAGER, "custom_role": "Project Manager"})
        project.save(ignore_permissions=True)
        patcher = patch(ENQUEUE)
        self.enqueue = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch(SLEEP)
        patcher.start()
        self.addCleanup(patcher.stop)

    def connect(self, **values):
        return make_meta_connection(self.project, **values)

    def attach(self, *names):
        for name in names:
            attach_media(self.post.name, name)

    def rows(self):
        return {
            r.target: r
            for r in frappe.get_doc("HD Content Post", self.post.name).meta_publishes
        }

    def publish(self, targets, **kwargs):
        publisher.queue(self.post.name, targets, **kwargs)
        publisher.process_post(self.post.name)


class TestMetaSigning(MetaCase):
    def test_state_round_trips_and_names_the_person_and_project(self):
        state = signing.make_state(MANAGER, self.project)
        self.assertEqual(signing.read_state(state), (MANAGER, self.project))

    def test_a_tampered_state_is_refused(self):
        body, _dot, sig = signing.make_state(MANAGER, self.project).partition(".")
        other = signing.b64(b'{"u":"Administrator","p":"x","exp":9999999999}')
        for bad in (f"{other}.{sig}", f"{body}.AAAA", "nonsense"):
            with self.assertRaises(frappe.ValidationError):
                signing.read_state(bad)

    def test_a_state_expires(self):
        state = signing.make_state(MANAGER, self.project)
        later = signing.now_seconds() + signing.STATE_SECONDS + 5
        with patch.object(signing, "now_seconds", return_value=later):
            with self.assertRaises(frappe.ValidationError):
                signing.read_state(state)

    def test_a_media_link_names_one_file_and_expires_in_an_hour(self):
        url = signing.media_url("FILE-1")
        token = url.split("token=")[1]
        self.assertEqual(signing.read_media_token(token), "FILE-1")
        with patch.object(
            signing, "now_seconds", return_value=signing.now_seconds() + 3700
        ):
            with self.assertRaises(frappe.ValidationError):
                signing.read_media_token(token)
        # a state is not a media token
        with self.assertRaises(frappe.ValidationError):
            signing.read_media_token(signing.make_state(MANAGER, self.project))

    def test_the_media_endpoint_serves_only_post_attachments(self):
        self.attach("a.jpg")
        file_name = frappe.db.get_value(
            "File", {"attached_to_name": self.post.name}, "name"
        )
        frappe.set_user("Guest")
        meta_api.media(signing.media_url(file_name).split("token=")[1])
        self.assertEqual(frappe.local.response.type, "download")
        other = frappe.get_doc(
            {"doctype": "File", "file_name": "x.txt", "content": b"x", "is_private": 1}
        ).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            meta_api.media(signing.media_url(other.name).split("token=")[1])


class TestMetaConnect(MetaCase):
    def sign_in(self, user=MANAGER):
        state = signing.make_state(user, self.project)
        with FakeGraph(OAUTH).patch():
            return connect.finish_login("code", state, user)

    def test_the_login_url_has_the_scopes_and_a_signed_state(self):
        url = connect.login_url(self.project, MANAGER)
        self.assertIn("pages_manage_posts", url)
        self.assertIn("instagram_content_publish", url)
        state = url.split("state=")[1].split("&")[0]
        from urllib.parse import unquote

        self.assertEqual(signing.read_state(unquote(state)), (MANAGER, self.project))

    def test_the_callback_stores_the_token_encrypted_and_never_returns_it(self):
        self.sign_in()
        raw = frappe.db.sql(
            "select password from `__Auth` where doctype='HD Meta Connection' and name=%s and fieldname='user_access_token'",
            self.project,
        )[0][0]
        self.assertNotIn("long-lived", raw)
        self.assertEqual(
            get_decrypted_password(
                "HD Meta Connection", self.project, "user_access_token"
            ),
            "long-lived",
        )
        pages = run_as_user(MANAGER, lambda: self.list_pages())
        self.assertEqual([p["id"] for p in pages], ["page-1"])
        self.assertNotIn("token", str(pages))

    def list_pages(self):
        with FakeGraph(OAUTH).patch():
            return meta_api.list_pages(self.project)

    def test_picking_a_page_keeps_its_token_and_drops_the_sign_in_token(self):
        self.sign_in()
        with FakeGraph(OAUTH).patch():
            summary = run_as_user(
                MANAGER, lambda: meta_api.select_page(self.project, "page-1")
            )
        self.assertEqual(summary["status"], "Connected")
        self.assertEqual(summary["instagram_username"], "client_ig")
        self.assertNotIn("token", str(summary))
        self.assertEqual(
            get_decrypted_password(
                "HD Meta Connection", self.project, "page_access_token"
            ),
            "page-token",
        )
        self.assertFalse(
            get_decrypted_password(
                "HD Meta Connection",
                self.project,
                "user_access_token",
                raise_exception=False,
            )
        )

    def test_a_page_the_person_cannot_post_to_is_refused(self):
        self.sign_in()
        with FakeGraph(OAUTH).patch():
            with self.assertRaises(frappe.ValidationError):
                run_as_user(
                    MANAGER, lambda: meta_api.select_page(self.project, "page-2")
                )

    def test_someone_else_cannot_finish_a_sign_in(self):
        state = signing.make_state(MANAGER, self.project)
        with FakeGraph(OAUTH).patch(), self.assertRaises(frappe.PermissionError):
            connect.finish_login("code", state, HEAD)

    def test_missing_permissions_are_named(self):
        routes = {
            **OAUTH,
            "GET me/permissions": {
                "data": [{"permission": "pages_show_list", "status": "granted"}]
            },
        }
        state = signing.make_state(MANAGER, self.project)
        with FakeGraph(routes).patch(), self.assertRaises(
            frappe.ValidationError
        ) as ctx:
            connect.finish_login("code", state, MANAGER)
        self.assertIn("pages_manage_posts", str(ctx.exception))

    def test_only_those_who_handle_the_accounts_may_connect(self):
        for user in (MANAGER, HEAD, "Administrator"):
            result = run_as_user(user, lambda: meta_api.start_connect(self.project))
            self.assertIn("facebook.com", result["url"])
        for user in (MEMBER, SALES):
            with self.assertRaises(frappe.PermissionError):
                run_as_user(user, lambda: meta_api.start_connect(self.project))
            with self.assertRaises(frappe.PermissionError):
                run_as_user(user, lambda: meta_api.disconnect(self.project))

    def test_disconnect_deletes_the_connection_and_its_tokens(self):
        self.connect()
        run_as_user(MANAGER, lambda: meta_api.disconnect(self.project))
        self.assertFalse(frappe.db.exists("HD Meta Connection", self.project))
        self.assertFalse(
            get_decrypted_password(
                "HD Meta Connection",
                self.project,
                "page_access_token",
                raise_exception=False,
            )
        )

    def test_only_a_system_manager_changes_the_settings(self):
        with self.assertRaises(frappe.PermissionError):
            run_as_user(MANAGER, meta_api.get_settings)
        data = meta_api.get_settings()
        self.assertEqual(data["secrets"]["app_secret"]["set"], True)
        self.assertNotIn("app-secret", str(data))
        self.assertEqual(data["graph_api_version"], "v25.0")


class TestMetaPublishing(MetaCase):
    def test_an_instagram_image_goes_through_container_and_publish(self):
        self.connect()
        self.attach("a.jpg")
        graph = FakeGraph(
            {
                "GET ig-1/content_publishing_limit": {
                    "data": [{"quota_usage": 2, "config": {"quota_total": 50}}]
                },
                "POST ig-1/media": {"id": "c1"},
                "GET c1": {"status_code": "FINISHED"},
                "POST ig-1/media_publish": {"id": "m1"},
                "GET m1": {"permalink": "https://www.instagram.com/p/m1/"},
            }
        )
        with graph.patch():
            self.publish(["Instagram"])
        create = next(p for m, path, p in graph.calls if path == "ig-1/media")
        self.assertIn("image_url", create)
        self.assertIn("Fresh Monday offer", create["caption"])
        self.assertIn("#sale #summer", create["caption"])
        row = self.rows()["Instagram"]
        self.assertEqual((row.status, row.meta_post_id), ("Published", "m1"))
        post = frappe.get_doc("HD Content Post", self.post.name)
        self.assertEqual(post.status, "Published")
        self.assertEqual(post.published_url, "https://www.instagram.com/p/m1/")

    def test_an_instagram_carousel_makes_child_containers_first(self):
        self.connect()
        self.attach("a.jpg", "b.jpg", "c.jpg")
        graph = FakeGraph(
            {
                "GET ig-1/content_publishing_limit": {
                    "data": [{"quota_usage": 0, "config": {"quota_total": 50}}]
                },
                "POST ig-1/media": [
                    {"id": "k1"},
                    {"id": "k2"},
                    {"id": "k3"},
                    {"id": "parent"},
                ],
                "GET parent": {"status_code": "FINISHED"},
                "POST ig-1/media_publish": {"id": "m2"},
                "GET m2": {"permalink": "https://www.instagram.com/p/m2/"},
            }
        )
        with graph.patch():
            self.publish(["Instagram"])
        media_calls = [p for m, path, p in graph.calls if path == "ig-1/media"]
        self.assertEqual(len(media_calls), 4)
        self.assertEqual(media_calls[0]["is_carousel_item"], "true")
        self.assertEqual(media_calls[3]["media_type"], "CAROUSEL")
        self.assertEqual(media_calls[3]["children"], "k1,k2,k3")

    def test_an_instagram_video_waits_until_finished(self):
        self.connect()
        self.attach("clip.mp4")
        graph = FakeGraph(
            {
                "GET ig-1/content_publishing_limit": {
                    "data": [{"quota_usage": 0, "config": {"quota_total": 50}}]
                },
                "POST ig-1/media": {"id": "v1"},
                "GET v1": [
                    {"status_code": "IN_PROGRESS"},
                    {"status_code": "IN_PROGRESS"},
                    {"status_code": "FINISHED"},
                ],
                "POST ig-1/media_publish": {"id": "m3"},
                "GET m3": {"permalink": "https://www.instagram.com/reel/m3/"},
            }
        )
        with graph.patch():
            self.publish(["Instagram"])
        statuses = [p for m, p, _ in graph.calls if p == "v1"]
        self.assertEqual(len(statuses), 3)
        publish_at = graph.paths().index("ig-1/media_publish")
        self.assertGreater(publish_at, graph.paths().index("v1"))
        create = next(p for m, path, p in graph.calls if path == "ig-1/media")
        self.assertEqual(create["media_type"], "REELS")

    def test_a_story_is_one_media_and_instagram_only(self):
        self.connect()
        self.attach("a.jpg", "b.jpg")
        with self.assertRaises(frappe.ValidationError):
            publisher.queue(self.post.name, ["Instagram"], requested_kind="Story")
        frappe.get_doc(
            "File", {"attached_to_name": self.post.name, "file_name": "b.jpg"}
        ).delete()
        with self.assertRaises(frappe.ValidationError):
            publisher.queue(self.post.name, ["Facebook"], requested_kind="Story")

    def test_a_facebook_photo_post(self):
        self.connect()
        self.attach("a.jpg")
        graph = FakeGraph(
            {
                "POST page-1/photos": {"id": "ph1", "post_id": "page-1_77"},
                "GET page-1_77": {
                    "permalink_url": "https://www.facebook.com/page-1/posts/77"
                },
            }
        )
        with graph.patch():
            self.publish(["Facebook"])
        self.assertEqual(self.rows()["Facebook"].meta_post_id, "page-1_77")
        self.assertEqual(
            frappe.db.get_value("HD Content Post", self.post.name, "published_url"),
            "https://www.facebook.com/page-1/posts/77",
        )

    def test_facebook_multiple_photos_use_attached_media(self):
        self.connect()
        self.attach("a.jpg", "b.png")
        graph = FakeGraph(
            {
                "POST page-1/photos": [{"id": "p1"}, {"id": "p2"}],
                "POST page-1/feed": {"id": "page-1_88"},
                "GET page-1_88": {
                    "permalink_url": "https://www.facebook.com/page-1/posts/88"
                },
            }
        )
        with graph.patch():
            self.publish(["Facebook"])
        feed = next(p for m, path, p in graph.calls if path == "page-1/feed")
        self.assertIn("p1", feed["attached_media[0]"])
        self.assertIn("p2", feed["attached_media[1]"])

    def test_a_text_post_goes_to_facebook_but_not_instagram(self):
        self.connect()
        with self.assertRaises(frappe.ValidationError):
            publisher.queue(self.post.name, ["Instagram"])
        graph = FakeGraph(
            {
                "POST page-1/feed": {"id": "page-1_99"},
                "GET page-1_99": {
                    "permalink_url": "https://www.facebook.com/page-1/posts/99"
                },
            }
        )
        with graph.patch():
            self.publish(["Facebook"], link="https://client.example/offer")
        feed = next(p for m, path, p in graph.calls if path == "page-1/feed")
        self.assertEqual(feed["link"], "https://client.example/offer")
        self.assertIn("Fresh Monday offer", feed["message"])

    def test_instagram_needs_jpeg(self):
        self.connect()
        self.attach("a.png")
        with self.assertRaises(frappe.ValidationError) as ctx:
            publisher.queue(self.post.name, ["Instagram"])
        self.assertIn("JPEG", str(ctx.exception))

    def test_a_used_up_instagram_limit_is_refused_with_a_clear_message(self):
        self.connect()
        self.attach("a.jpg")
        graph = FakeGraph(
            {
                "GET ig-1/content_publishing_limit": {
                    "data": [{"quota_usage": 50, "config": {"quota_total": 50}}]
                }
            }
        )
        with graph.patch():
            self.publish(["Instagram"])
        row = self.rows()["Instagram"]
        self.assertEqual(row.status, "Failed")
        self.assertIn("daily limit", row.error)
        self.assertNotIn("ig-1/media", graph.paths())

    def test_a_post_that_is_not_approved_is_refused(self):
        self.connect()
        for status in ("Drafting", "Client Review", "Published"):
            frappe.db.set_value("HD Content Post", self.post.name, "status", status)
            with self.assertRaises(frappe.ValidationError):
                publisher.queue(self.post.name, ["Facebook"])
        state = publisher.publish_state(self.post.name)
        self.assertIn("approved", state["blocked_reason"])

    def test_without_a_connection_the_state_says_so(self):
        state = publisher.publish_state(self.post.name)
        self.assertIsNone(state["connection"])
        self.assertIn("Connect Meta", state["blocked_reason"])
        with self.assertRaises(frappe.ValidationError):
            publisher.queue(self.post.name, ["Facebook"])

    def test_only_those_who_handle_the_accounts_may_publish(self):
        self.connect()
        for user in (MEMBER, SALES):
            with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
                run_as_user(user, lambda: publisher.queue(self.post.name, ["Facebook"]))
        run_as_user(HEAD, lambda: publisher.queue(self.post.name, ["Facebook"]))
        self.enqueue.assert_called_once()

    def test_a_later_time_schedules_the_post_for_the_scheduler(self):
        self.connect()
        when = add_to_date(now_datetime(), hours=3)
        publisher.queue(self.post.name, ["Facebook"], publish_at=when)
        self.enqueue.assert_not_called()
        post = frappe.get_doc("HD Content Post", self.post.name)
        self.assertEqual(post.status, "Scheduled")
        self.assertIsNotNone(post.meta_publish_on)
        # not due yet
        self.assertEqual(publisher.due_rows(), [])
        publisher.cancel_queued(self.post.name)
        post.reload()
        self.assertEqual(post.status, "Approved")
        self.assertIsNone(post.meta_publish_on)
        self.assertEqual(len(post.meta_publishes), 0)

    def test_the_scheduler_publishes_a_due_item_once(self):
        self.connect()
        publisher.queue(
            self.post.name,
            ["Facebook"],
            publish_at=add_to_date(now_datetime(), hours=3),
        )
        frappe.db.set_value(
            "HD Content Publish",
            {"parent": self.post.name},
            "publish_at",
            add_to_date(now_datetime(), minutes=-1),
        )
        graph = FakeGraph(
            {
                "POST page-1/feed": {"id": "page-1_5"},
                "GET page-1_5": {
                    "permalink_url": "https://www.facebook.com/page-1/posts/5"
                },
            }
        )
        with graph.patch():
            publisher.publish_due()
            publisher.publish_due()
        self.assertEqual(graph.paths("POST"), ["page-1/feed"])
        self.assertEqual(self.rows()["Facebook"].status, "Published")

    def test_a_transient_error_retries_with_a_wait_then_fails_and_tells_people(self):
        self.connect()
        publisher.queue(self.post.name, ["Facebook"])
        busy = {
            "POST page-1/feed": {
                "_status": 500,
                "error": {"code": 2, "message": "Service temporarily unavailable"},
            }
        }
        with patch(NOTIFY) as notify, FakeGraph(busy).patch():
            publisher.process_post(self.post.name)
            row = self.rows()["Facebook"]
            self.assertEqual((row.status, row.attempts), ("Queued", 1))
            self.assertGreater(row.next_try_on, now_datetime())
            # not due until the wait is over
            publisher.process_post(self.post.name)
            self.assertEqual(self.rows()["Facebook"].attempts, 1)
            for tries in (2, 3):
                frappe.db.set_value(
                    "HD Content Publish",
                    row.name,
                    "next_try_on",
                    add_to_date(now_datetime(), minutes=-1),
                )
                publisher.process_post(self.post.name)
            row = self.rows()["Facebook"]
            self.assertEqual((row.status, row.attempts), ("Failed", 3))
            notify.assert_called_once()
            users = notify.call_args.args[0]
            self.assertIn(HEAD, users)
            self.assertIn(self.post.owner, users)

    def test_a_permanent_error_fails_at_once_and_an_expired_token_marks_the_connection(
        self,
    ):
        connection = self.connect()
        publisher.queue(self.post.name, ["Facebook"])
        expired = {
            "POST page-1/feed": {
                "_status": 400,
                "error": {"code": 190, "message": "token"},
            }
        }
        with patch(NOTIFY) as notify, FakeGraph(expired).patch():
            publisher.process_post(self.post.name)
        self.assertEqual(self.rows()["Facebook"].status, "Failed")
        self.assertEqual(
            frappe.db.get_value("HD Meta Connection", connection.name, "status"),
            "Expired",
        )
        notify.assert_called_once()
        self.assertNotIn(
            "token", self.rows()["Facebook"].error.lower().replace("connection", "")
        )

    def test_a_row_stuck_publishing_is_freed_as_failed(self):
        self.connect()
        publisher.queue(self.post.name, ["Facebook"])
        row = self.rows()["Facebook"]
        frappe.db.set_value(
            "HD Content Publish",
            row.name,
            {"status": "Publishing"},
            update_modified=False,
        )
        frappe.db.set_value(
            "HD Content Publish",
            row.name,
            "modified",
            add_to_date(now_datetime(), hours=-1),
            update_modified=False,
        )
        with patch(NOTIFY):
            publisher.free_stale_rows()
        self.assertEqual(self.rows()["Facebook"].status, "Failed")

    def test_both_targets_publish_the_post_once_each_is_live(self):
        self.connect()
        self.attach("a.jpg")
        graph = FakeGraph(
            {
                "GET ig-1/content_publishing_limit": {
                    "data": [{"quota_usage": 0, "config": {"quota_total": 50}}]
                },
                "POST ig-1/media": {"id": "c1"},
                "GET c1": {"status_code": "FINISHED"},
                "POST ig-1/media_publish": {"id": "m1"},
                "GET m1": {"permalink": "https://www.instagram.com/p/m1/"},
                "POST page-1/photos": {"id": "ph", "post_id": "page-1_1"},
                "GET page-1_1": {
                    "permalink_url": "https://www.facebook.com/page-1/posts/1"
                },
            }
        )
        with graph.patch():
            self.publish(["Facebook", "Instagram"])
        post = frappe.get_doc("HD Content Post", self.post.name)
        self.assertEqual(post.status, "Published")
        # the Facebook link comes first
        self.assertEqual(post.published_url, "https://www.facebook.com/page-1/posts/1")
        with self.assertRaises(frappe.ValidationError):
            publisher.queue(self.post.name, ["Facebook"])
