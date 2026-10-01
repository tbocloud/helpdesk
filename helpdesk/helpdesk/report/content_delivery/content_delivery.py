# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""Per-client delivery of planned content: what shipped, what shipped on time,
what is late, and how long clients take to approve."""

import frappe
from frappe import _
from frappe.utils import get_datetime, getdate, now_datetime


def execute(filters=None):
    filters = frappe._dict(filters or {})
    rows = get_rows(filters)
    return get_columns(), rows, None, get_chart(rows)


def get_columns():
    return [
        {
            "fieldname": "customer",
            "label": _("Customer"),
            "fieldtype": "Link",
            "options": "HD Customer",
            "width": 220,
        },
        {
            "fieldname": "planned",
            "label": _("Planned"),
            "fieldtype": "Int",
            "width": 100,
        },
        {
            "fieldname": "published",
            "label": _("Published"),
            "fieldtype": "Int",
            "width": 100,
        },
        {
            "fieldname": "on_time",
            "label": _("On Time"),
            "fieldtype": "Int",
            "width": 100,
        },
        {
            "fieldname": "on_time_pct",
            "label": _("On Time %"),
            "fieldtype": "Percent",
            "width": 110,
        },
        {
            "fieldname": "overdue",
            "label": _("Overdue"),
            "fieldtype": "Int",
            "width": 100,
        },
        {
            "fieldname": "awaiting_client",
            "label": _("Awaiting Client"),
            "fieldtype": "Int",
            "width": 130,
        },
        {
            "fieldname": "avg_approval_hours",
            "label": _("Avg Approval (hrs)"),
            "fieldtype": "Float",
            "precision": 1,
            "width": 150,
        },
    ]


def get_rows(filters) -> list[dict]:
    post_filters = {
        "publish_on": [
            "between",
            [f"{filters.from_date} 00:00:00", f"{filters.to_date} 23:59:59"],
        ],
        # a cancelled post was never going to be delivered
        "status": ["!=", "Cancelled"],
    }
    if filters.customer:
        post_filters["customer"] = filters.customer

    # get_list applies the content visibility rules for the viewer
    posts = frappe.get_list(
        "HD Content Post",
        filters=post_filters,
        fields=[
            "customer",
            "status",
            "publish_on",
            "published_on",
            "sent_for_approval_on",
            "client_decided_on",
        ],
        limit_page_length=0,
    )

    now = now_datetime()
    by_customer: dict[str, dict] = {}
    for post in posts:
        row = by_customer.setdefault(
            post.customer,
            {
                "customer": post.customer,
                "planned": 0,
                "published": 0,
                "on_time": 0,
                "overdue": 0,
                "awaiting_client": 0,
                "_approval_hours": [],
            },
        )
        row["planned"] += 1
        if post.status == "Published":
            row["published"] += 1
            if post.published_on and getdate(post.published_on) <= getdate(
                post.publish_on
            ):
                row["on_time"] += 1
        elif get_datetime(post.publish_on) < now:
            row["overdue"] += 1
        if post.status == "Client Review":
            row["awaiting_client"] += 1
        if post.sent_for_approval_on and post.client_decided_on:
            hours = (
                get_datetime(post.client_decided_on)
                - get_datetime(post.sent_for_approval_on)
            ).total_seconds() / 3600
            row["_approval_hours"].append(max(hours, 0))

    rows = []
    for row in sorted(by_customer.values(), key=lambda r: r["customer"] or ""):
        hours = row.pop("_approval_hours")
        row["on_time_pct"] = (
            round(row["on_time"] / row["published"] * 100, 1) if row["published"] else 0
        )
        row["avg_approval_hours"] = round(sum(hours) / len(hours), 1) if hours else None
        rows.append(row)
    return rows


def get_chart(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    return {
        "data": {
            "labels": [r["customer"] for r in rows],
            "datasets": [
                {"name": _("Planned"), "values": [r["planned"] for r in rows]},
                {"name": _("Published"), "values": [r["published"] for r in rows]},
            ],
        },
        "type": "bar",
        "barOptions": {"spaceRatio": 0.4},
    }


@frappe.whitelist()
def export_xlsx(from_date: str, to_date: str, customer: str | None = None):
    """The delivery report as an Excel file, with a total row; same rows the page shows."""
    from frappe.utils.xlsxutils import make_xlsx

    frappe.has_permission("HD Content Post", "read", throw=True)
    filters = frappe._dict(from_date=from_date, to_date=to_date, customer=customer)
    columns = get_columns()
    rows = get_rows(filters)

    data = [[c["label"] for c in columns]]
    data += [[row.get(c["fieldname"]) for c in columns] for row in rows]
    data.append(total_row(columns, rows))

    sheet = f"Delivery {from_date} to {to_date}"
    xlsx = make_xlsx(data, sheet, column_widths=[c["width"] // 7 for c in columns])
    suffix = f"-{frappe.scrub(customer)}" if customer else ""
    frappe.response.filename = f"content-delivery-{from_date}-to-{to_date}{suffix}.xlsx"
    frappe.response.filecontent = xlsx.getvalue()
    frappe.response.type = "binary"


def total_row(columns: list[dict], rows: list[dict]) -> list:
    totals = {
        key: sum(r[key] for r in rows)
        for key in ("planned", "published", "on_time", "overdue", "awaiting_client")
    }
    totals["customer"] = _("Total")
    totals["on_time_pct"] = (
        round(totals["on_time"] / totals["published"] * 100, 1)
        if totals["published"]
        else 0
    )
    # averaging the per-customer averages would overweight small customers
    totals["avg_approval_hours"] = None
    return [totals.get(c["fieldname"]) for c in columns]
