"""Monthly plans and occasions for the Content Calendar's Monthly plans page."""

import json

import frappe
from frappe import _
from frappe.utils import add_months, cint, get_first_day, getdate, nowdate

from helpdesk.helpdesk.doctype.hd_content_occasion.hd_content_occasion import (
    occasions_between,
)
from helpdesk.helpdesk.doctype.hd_content_package.hd_content_package import (
    DEFAULT_PLAN_DAY,
)

PACKAGE = "HD Content Package"
OCCASION = "HD Content Occasion"
# what the page may set on a package; the rest (totals, last planned) is computed
PACKAGE_FIELDS = (
    "enabled",
    "posting_days",
    "publish_time",
    "task_mode",
    "writer",
    "designer",
    "marketer",
    "include_occasions",
    "occasions_india",
    "occasions_kerala",
    "occasions_uae",
    "ai_topics",
    "about_brand",
)
OCCASION_FIELDS = ("occasion_name", "occasion_date", "repeats_yearly", "region", "idea")


@frappe.whitelist()
def get_plans() -> dict:
    """Every customer's monthly plan, with when the next month gets planned."""
    frappe.has_permission(PACKAGE, "read", throw=True)
    today = getdate(nowdate())
    next_month = get_first_day(add_months(today, 1))
    plan_day = (
        cint(frappe.db.get_single_value("HD Content Settings", "plan_day"))
        or DEFAULT_PLAN_DAY
    )
    plans = []
    for name in frappe.get_list(PACKAGE, pluck="name", order_by="customer asc"):
        doc = frappe.get_doc(PACKAGE, name)
        plan = {
            field: doc.get(field) for field in ("name", "customer", *PACKAGE_FIELDS)
        }
        plan["posts_per_month"] = doc.posts_per_month
        plan["last_planned_month"] = doc.last_planned_month
        plan["next_month_planned"] = bool(
            doc.last_planned_month and getdate(doc.last_planned_month) >= next_month
        )
        plan["items"] = [
            {
                "channel": row.channel,
                "format": row.format,
                "posts_per_month": row.posts_per_month,
            }
            for row in doc.items
        ]
        plan["team"] = {
            field: frappe.utils.get_fullname(doc.get(field))
            for field in ("writer", "designer", "marketer")
            if doc.get(field)
        }
        plans.append(plan)
    return {
        "plans": plans,
        "plan_day": plan_day,
        "next_month": str(next_month),
        "can_edit": bool(frappe.has_permission(PACKAGE, "write")),
    }


@frappe.whitelist(methods=["POST"])
def save_plan(values: str | dict, name: str | None = None) -> str:
    """Create a customer's plan, or update it when `name` is given."""
    values = json.loads(values) if isinstance(values, str) else values
    if name:
        doc = frappe.get_doc(PACKAGE, name)
        doc.check_permission("write")
    else:
        frappe.has_permission(PACKAGE, "create", throw=True)
        doc = frappe.new_doc(PACKAGE)
        doc.customer = values.get("customer")
    doc.update(
        {field: values.get(field) for field in PACKAGE_FIELDS if field in values}
    )
    doc.set(
        "items",
        [
            {
                "channel": row.get("channel"),
                "format": row.get("format"),
                "posts_per_month": cint(row.get("posts_per_month")),
            }
            for row in values.get("items") or []
        ],
    )
    doc.save()
    return doc.name


@frappe.whitelist(methods=["POST"])
def plan_now(name: str, which: str = "next") -> int:
    """Create this or next month's posts for one customer now; returns how many."""
    if which not in ("this", "next"):
        frappe.throw(_("Plan this month or next month."))
    doc = frappe.get_doc(PACKAGE, name)
    doc.check_permission("write")
    return doc.plan(which)


@frappe.whitelist(methods=["POST"])
def delete_plan(name: str):
    """Stop planning for a customer; posts already planned stay on the calendar."""
    frappe.get_doc(PACKAGE, name).check_permission("delete")
    # the posts keep their place on the calendar, just no longer tied to a plan
    for post in frappe.get_all(
        "HD Content Post", filters={"content_package": name}, pluck="name"
    ):
        frappe.db.set_value(
            "HD Content Post", post, "content_package", None, update_modified=False
        )
    frappe.delete_doc(PACKAGE, name)


@frappe.whitelist()
def get_occasions_for_year(year: int | str) -> dict:
    """The year's occasions by date (repeating ones placed in that year)."""
    frappe.has_permission(OCCASION, "read", throw=True)
    year = cint(year)
    rows = occasions_between(f"{year}-01-01", f"{year}-12-31")
    details = {
        r.name: r
        for r in frappe.get_all(
            OCCASION, fields=["name", "repeats_yearly", "occasion_date"]
        )
    }
    return {
        "occasions": [
            {
                "name": o.name,
                "occasion_name": o.occasion_name,
                "date": str(o.date),
                "region": o.region,
                "idea": o.idea,
                "repeats_yearly": bool(details[o.name].repeats_yearly),
                "occasion_date": str(details[o.name].occasion_date),
            }
            for o in rows
        ],
        "can_edit": bool(frappe.has_permission(OCCASION, "write")),
    }


@frappe.whitelist(methods=["POST"])
def save_occasion(values: str | dict, name: str | None = None) -> str:
    values = json.loads(values) if isinstance(values, str) else values
    if name:
        doc = frappe.get_doc(OCCASION, name)
        doc.check_permission("write")
    else:
        frappe.has_permission(OCCASION, "create", throw=True)
        doc = frappe.new_doc(OCCASION)
    doc.update(
        {field: values.get(field) for field in OCCASION_FIELDS if field in values}
    )
    doc.save()
    return doc.name


@frappe.whitelist(methods=["POST"])
def delete_occasion(name: str):
    frappe.get_doc(OCCASION, name).check_permission("delete")
    frappe.delete_doc(OCCASION, name)
