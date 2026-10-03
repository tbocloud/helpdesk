# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""A customer's monthly content package: what goes out each month and who does it.

On the planning day (HD Content Settings), next month's posts are created as Ideas,
spread over the posting days, with the team and tasks already set. Occasions in the
month (HD Content Occasion) pull the nearest planned post onto their day.
"""

from collections import Counter
from datetime import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
    add_days,
    add_months,
    cint,
    get_first_day,
    get_last_day,
    get_time,
    getdate,
    nowdate,
)

from helpdesk.helpdesk.doctype.hd_content_occasion.hd_content_occasion import (
    occasions_between,
)

# weekday() numbers left out of the plan
SKIPPED_WEEKDAYS = {
    "Monday to Saturday": (6,),
    "Monday to Friday": (5, 6),
    "Every day": (),
}
REGION_FIELDS = {
    "occasions_india": "India",
    "occasions_kerala": "Kerala",
    "occasions_uae": "UAE",
}
DEFAULT_PLAN_DAY = 20


class HDContentPackage(Document):
    def validate(self):
        self.validate_items()
        self.set_posts_per_month()

    def validate_items(self):
        if not self.items:
            frappe.throw(_("Add what goes out each month, e.g. 8 Instagram posts."))
        for row in self.items:
            if cint(row.posts_per_month) < 1:
                frappe.throw(
                    _("Row {0}: posts per month must be at least 1.").format(row.idx)
                )

    def set_posts_per_month(self):
        self.posts_per_month = sum(cint(row.posts_per_month) for row in self.items)

    @frappe.whitelist()
    def plan(self, which: str = "next") -> int:
        """Plan this month or next month now; returns how many posts were created."""
        self.check_permission("write")
        today = getdate(nowdate())
        month = get_first_day(today if which == "this" else add_months(today, 1))
        if self.is_planned(month):
            frappe.throw(
                _("{0} is already planned for {1}.").format(
                    self.customer, month.strftime("%B %Y")
                )
            )
        count = self.plan_month(month)
        self.save()
        return count

    def is_planned(self, month) -> bool:
        start, end = month_bounds(month)
        return bool(
            frappe.db.exists(
                "HD Content Post",
                {
                    "content_package": self.name,
                    "publish_on": ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]],
                },
            )
        )

    def plan_month(self, month) -> int:
        """Create the month's posts and tell the team once; the caller saves the package."""
        slots = self.slots(month)
        for slot in slots:
            self.make_post(slot, month)
        if slots:
            self.notify_team(month, len(slots))
        self.last_planned_month = month
        return len(slots)

    def slots(self, month) -> list:
        """One slot per post: its item and day, spread evenly over the posting days."""
        days = self.posting_days_in(month)
        sequence = self.interleaved_items()
        if not days or not sequence:
            return []
        numbers = Counter()
        slots = []
        for k, item in enumerate(sequence):
            numbers[item.name] += 1
            day = days[min(int((k + 0.5) * len(days) / len(sequence)), len(days) - 1)]
            slots.append(
                frappe._dict(
                    item=item, number=numbers[item.name], date=day, occasion=None
                )
            )
        self.place_occasions(slots, days[0], days[-1])
        return slots

    def posting_days_in(self, month) -> list:
        """The month's posting days from tomorrow on (a plan never lands in the past)."""
        start, end = month_bounds(month)
        start = max(start, add_days(getdate(nowdate()), 1))
        skipped = SKIPPED_WEEKDAYS.get(
            self.posting_days, SKIPPED_WEEKDAYS["Monday to Saturday"]
        )
        days = []
        day = start
        while day <= end:
            if day.weekday() not in skipped:
                days.append(day)
            day = add_days(day, 1)
        return days

    def interleaved_items(self) -> list:
        """Items in turn (post, reel, post, reel...) so formats are spread out, not bunched."""
        queues = [[row] * cint(row.posts_per_month) for row in self.items]
        sequence = []
        while any(queues):
            for queue in queues:
                if queue:
                    sequence.append(queue.pop())
        return sequence

    def place_occasions(self, slots: list, first, last):
        """Move the nearest free slot onto each occasion day in the plan's range."""
        if not self.include_occasions:
            return
        for occasion in occasions_between(first, last, self.occasion_regions()):
            free = [s for s in slots if not s.occasion]
            if not free:
                return
            nearest = min(free, key=lambda s: abs((s.date - occasion.date).days))
            nearest.date = occasion.date
            nearest.occasion = occasion

    def occasion_regions(self) -> list[str]:
        return [region for field, region in REGION_FIELDS.items() if self.get(field)]

    def make_post(self, slot, month):
        item = slot.item
        if slot.occasion:
            title = f"{slot.occasion.occasion_name} · {item.channel} {item.format}"
            brief = slot.occasion.idea or _("A post for {0}.").format(
                slot.occasion.occasion_name
            )
        else:
            title = f"{item.channel} {item.format} {slot.number}/{item.posts_per_month} · {month.strftime('%b %Y')}"
            brief = _(
                "Planned from the monthly package. Replace the title with the topic and add a brief."
            )
        post = frappe.get_doc(
            {
                "doctype": "HD Content Post",
                "title": title,
                "customer": self.customer,
                "channel": item.channel,
                "format": item.format,
                "status": "Idea",
                "publish_on": datetime.combine(
                    slot.date, get_time(self.publish_time or "10:00")
                ),
                "writer": self.writer,
                "designer": self.designer,
                "marketer": self.marketer,
                "brief": brief,
                "task_mode": self.task_mode or None,
                "content_package": self.name,
            }
        )
        # one summary per person (notify_team) instead of a notice per task
        post.flags.quiet_tasks = True
        post.insert(ignore_permissions=True)

    def notify_team(self, month, count: int):
        from helpdesk.work_reminders import notify_users

        notify_users(
            [self.writer, self.designer, self.marketer],
            "HD Content Package",
            self.name,
            _("{0}: {1} posts planned for {2}. Your parts are in My Work.").format(
                self.customer, count, month.strftime("%B %Y")
            ),
            link="/content",
        )


def month_bounds(month) -> tuple:
    month = getdate(month)
    return get_first_day(month), get_last_day(month)


def plan_upcoming_months():
    """Daily: from the planning day on, plan next month for every package not yet planned."""
    today = getdate(nowdate())
    plan_day = (
        cint(frappe.db.get_single_value("HD Content Settings", "plan_day"))
        or DEFAULT_PLAN_DAY
    )
    if today.day < plan_day:
        return
    month = get_first_day(add_months(today, 1))
    for name in frappe.get_all(
        "HD Content Package", filters={"enabled": 1}, pluck="name"
    ):
        package = frappe.get_doc("HD Content Package", name)
        if package.last_planned_month and getdate(package.last_planned_month) >= month:
            continue
        try:
            if not package.is_planned(month):
                package.plan_month(month)
            else:  # planned by hand already
                package.last_planned_month = month
            package.save(ignore_permissions=True)
            frappe.db.commit()  # nosemgrep - one customer's plan must not undo another's
        except Exception:  # noqa: BLE001 - one bad package must not stop the others
            frappe.db.rollback()
            frappe.log_error(
                title=f"Content plan failed for {name}", message=frappe.get_traceback()
            )
