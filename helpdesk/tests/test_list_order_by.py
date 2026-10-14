"""Browser lists that join another table order by a column named with its table.

A field like "user.user_image", or a filter on a child table, joins a second table
with its own `creation` and `modified`; an unqualified order_by on those is then
"(1052) Column 'creation' in ORDER BY is ambiguous". These are the desk's calls,
with the arguments it sends (desk/src/stores/agent.ts, pages/content/ContentCalendar.vue).
"""

from frappe.client import get_list
from frappe.tests.utils import FrappeTestCase

PERSON = "writer.order@list-order.example"
TEAM_ROLES = ("writer", "designer", "video_editor", "marketer")


def my_posts_query() -> dict:
    """ContentCalendar's personQuery(): the post's roles or its member table."""
    return {
        "or_filters": [
            *([role, "=", PERSON] for role in TEAM_ROLES),
            ["HD Content Post Member", "user", "=", PERSON],
        ],
        "group_by": "`tabHD Content Post`.`name`",
    }


class TestListOrderBy(FrappeTestCase):
    def test_the_agent_list_with_user_images(self):
        get_list(
            "HD Agent",
            fields=["name", "agent_name", "user", "user.user_image"],
            filters={"is_active": 1},
            order_by="`tabHD Agent`.`modified` desc",
            limit_page_length=5,
        )

    def test_my_posts_without_a_posting_date(self):
        get_list(
            "HD Content Post",
            fields=["name", "title", "customer"],
            filters={"status": ["!=", "Cancelled"], "publish_on": ["is", "not set"]},
            order_by="`tabHD Content Post`.`creation` desc",
            limit_page_length=100,
            **my_posts_query(),
        )

    def test_my_posts_in_a_month(self):
        get_list(
            "HD Content Post",
            fields=["name", "title", "status", "publish_on"],
            filters={
                "status": ["!=", "Cancelled"],
                "publish_on": ["between", ["2026-10-01", "2026-10-31 23:59:59"]],
            },
            order_by="`tabHD Content Post`.`publish_on` asc",
            limit_page_length=1000,
            **my_posts_query(),
        )
