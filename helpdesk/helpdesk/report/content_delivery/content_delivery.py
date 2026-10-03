# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""Per-client delivery of planned content: what shipped, what shipped on time,
what is late, and how long clients take to approve."""

import frappe
from frappe import _
from frappe.utils import (
    add_days,
    format_datetime,
    formatdate,
    get_datetime,
    get_first_day,
    get_last_day,
    getdate,
    now_datetime,
)

# where a post is in the workflow, grouped the way the calendar colours them
STAGES = {
    "Idea": "planning",
    "Drafting": "planning",
    "Design": "planning",
    "Internal Review": "review",
    "Client Review": "review",
    "Changes Requested": "review",
    "Approved": "ready",
    "Scheduled": "ready",
    "Published": "published",
}


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
            "fieldname": "promised",
            "label": _("Promised"),
            "fieldtype": "Int",
            "width": 100,
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
        row = by_customer.setdefault(post.customer, new_row(post.customer))
        row["planned"] += 1
        row["stages"][STAGES.get(post.status, "planning")] += 1
        if post.status == "Published":
            row["published"] += 1
            if post.published_on and getdate(post.published_on) <= getdate(
                post.publish_on
            ):
                row["on_time"] += 1
            else:
                row["late"] += 1
        elif get_datetime(post.publish_on) < now:
            row["overdue"] += 1
        else:
            row["upcoming"] += 1
        if post.status == "Client Review":
            row["awaiting_client"] += 1
        if post.sent_for_approval_on and post.client_decided_on:
            hours = (
                get_datetime(post.client_decided_on)
                - get_datetime(post.sent_for_approval_on)
            ).total_seconds() / 3600
            row["_approval_hours"].append(max(hours, 0))

    for customer, promised in promised_posts(filters, set(by_customer)).items():
        by_customer.setdefault(customer, new_row(customer))["promised"] = promised

    rows = []
    for row in sorted(by_customer.values(), key=lambda r: r["customer"] or ""):
        hours = row.pop("_approval_hours")
        row["on_time_pct"] = (
            round(row["on_time"] / row["published"] * 100, 1) if row["published"] else 0
        )
        row["avg_approval_hours"] = round(sum(hours) / len(hours), 1) if hours else None
        rows.append(row)
    return rows


def new_row(customer: str) -> dict:
    return {
        "customer": customer,
        "promised": None,
        "planned": 0,
        "published": 0,
        "on_time": 0,
        "overdue": 0,
        "awaiting_client": 0,
        "late": 0,
        "upcoming": 0,
        "stages": dict.fromkeys(set(STAGES.values()), 0),
        "_approval_hours": [],
    }


def promised_posts(filters, visible: set) -> dict[str, int]:
    """Posts each customer's monthly package promises over the period (pro rata by day).

    Customers the viewer can't see posts for are left out unless they may read packages.
    """
    package_filters = {"enabled": 1}
    if filters.customer:
        package_filters["customer"] = filters.customer
    packages = frappe.get_all(
        "HD Content Package",
        filters=package_filters,
        fields=["customer", "posts_per_month"],
    )
    sees_all = frappe.has_permission("HD Content Package", "read")
    start, end = getdate(filters.from_date), getdate(filters.to_date)
    return {
        p.customer: prorated(p.posts_per_month or 0, start, end)
        for p in packages
        if sees_all or p.customer in visible
    }


def prorated(per_month: int, start, end) -> int:
    total = 0.0
    month = get_first_day(start)
    while month <= end:
        last = get_last_day(month)
        days = (min(end, last) - max(start, month)).days + 1
        total += per_month * days / last.day
        month = add_days(last, 1)
    return round(total)


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

    # Excel refuses sheet names over 31 characters; the dates are in the file name
    xlsx = make_xlsx(
        data, "Content delivery", column_widths=[c["width"] // 7 for c in columns]
    )
    suffix = f"-{frappe.scrub(customer)}" if customer else ""
    frappe.response.filename = f"content-delivery-{from_date}-to-{to_date}{suffix}.xlsx"
    frappe.response.filecontent = xlsx.getvalue()
    frappe.response.type = "binary"


def total_row(columns: list[dict], rows: list[dict]) -> list:
    totals = {
        key: sum(r[key] for r in rows)
        for key in ("planned", "published", "on_time", "overdue", "awaiting_client")
    }
    totals["promised"] = sum(r["promised"] or 0 for r in rows) or None
    totals["customer"] = _("Total")
    totals["on_time_pct"] = (
        round(totals["on_time"] / totals["published"] * 100, 1)
        if totals["published"]
        else 0
    )
    # averaging the per-customer averages would overweight small customers
    totals["avg_approval_hours"] = None
    return [totals.get(c["fieldname"]) for c in columns]


@frappe.whitelist()
def export_pdf(from_date: str, to_date: str, customer: str | None = None):
    """The delivery report as a PDF download.

    Frappe renders PDFs with wkhtmltopdf. Where it is not installed, the same page is
    returned ready to print, and the browser's print dialog saves it as a PDF.
    """
    import shutil

    frappe.has_permission("HD Content Post", "read", throw=True)
    filters = frappe._dict(from_date=from_date, to_date=to_date, customer=customer)
    columns = get_columns()
    rows = get_rows(filters)
    can_render_pdf = bool(shutil.which("wkhtmltopdf"))
    html = frappe.render_template(  # the app's own fixed template, not user input - nosemgrep
        "helpdesk/helpdesk/report/content_delivery/content_delivery_pdf.html",
        {
            "title": _("Content delivery report"),
            "period": _("{0} to {1}").format(
                formatdate(from_date), formatdate(to_date)
            ),
            "customer": customer,
            "columns": [frappe._dict(c) for c in columns],
            "rows": [[row.get(c["fieldname"]) for c in columns] for row in rows],
            "total": total_row(columns, rows),
            "generated_on": format_datetime(now_datetime()),
            "generated_by": frappe.utils.get_fullname(frappe.session.user),
            "auto_print": not can_render_pdf,
        },
    )
    suffix = f"-{frappe.scrub(customer)}" if customer else ""
    filename = f"content-delivery-{from_date}-to-{to_date}{suffix}"

    if can_render_pdf:
        from frappe.utils.pdf import get_pdf

        frappe.response.filename = f"{filename}.pdf"
        frappe.response.filecontent = get_pdf(
            html, {"orientation": "Landscape", "page-size": "A4"}
        )
        frappe.response.type = "pdf"
        return

    frappe.response.filename = f"{filename}.html"
    frappe.response.filecontent = html
    frappe.response.type = "download"
    frappe.response.display_content_as = "inline"
