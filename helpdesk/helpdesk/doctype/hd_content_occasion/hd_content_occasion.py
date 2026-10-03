# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""Days worth a post (national days, festivals). The Content Calendar shows them,
and monthly plans put a post on them (see HD Content Package)."""

import frappe
from frappe.model.document import Document
from frappe.utils import getdate

EVERYWHERE = "Everywhere"

# Fixed-date days, added once on install. Festivals that move every year (Diwali,
# Onam, Vishu, Eid, Ramadan, Holi) are added by the team with that year's date.
DEFAULT_OCCASIONS = (
    (
        "New Year's Day",
        "01-01",
        EVERYWHERE,
        "Wish followers a happy new year and share what's coming this year.",
    ),
    (
        "Valentine's Day",
        "02-14",
        EVERYWHERE,
        "A light post or offer around love, care or customer appreciation.",
    ),
    (
        "International Women's Day",
        "03-08",
        EVERYWHERE,
        "Celebrate the women on the team or among customers.",
    ),
    ("World Health Day", "04-07", EVERYWHERE, "A wellbeing tip that fits the brand."),
    (
        "Earth Day",
        "04-22",
        EVERYWHERE,
        "Show one thing the business does for the environment.",
    ),
    ("Labour Day", "05-01", EVERYWHERE, "Thank the people who make the business run."),
    (
        "World Environment Day",
        "06-05",
        EVERYWHERE,
        "A green tip or a sustainability step the brand takes.",
    ),
    ("International Yoga Day", "06-21", EVERYWHERE, "A calm, healthy-living post."),
    (
        "World Tourism Day",
        "09-27",
        EVERYWHERE,
        "Places, travel or hospitality, if it fits the brand.",
    ),
    (
        "World Mental Health Day",
        "10-10",
        EVERYWHERE,
        "A supportive message about balance and wellbeing.",
    ),
    (
        "Christmas",
        "12-25",
        EVERYWHERE,
        "Season's greetings, a year-end offer or a thank-you.",
    ),
    ("New Year's Eve", "12-31", EVERYWHERE, "Look back at the year with customers."),
    (
        "Republic Day",
        "01-26",
        "India",
        "A respectful tribute; no discount-heavy messaging.",
    ),
    ("Independence Day", "08-15", "India", "A tribute post in national colours."),
    (
        "Teachers' Day",
        "09-05",
        "India",
        "Thank the mentors and teachers behind the team.",
    ),
    (
        "Gandhi Jayanti",
        "10-02",
        "India",
        "A quote or value from Gandhi that fits the brand.",
    ),
    ("Children's Day", "11-14", "India", "A warm post for families and children."),
    (
        "Kerala Piravi",
        "11-01",
        "Kerala",
        "Celebrate Kerala's formation day for a Malayali audience.",
    ),
    ("Emirati Women's Day", "08-28", "UAE", "Celebrate Emirati women's achievements."),
    ("UAE Flag Day", "11-03", "UAE", "Show the flag with pride; a respectful post."),
    (
        "Commemoration Day",
        "11-30",
        "UAE",
        "A respectful tribute to the UAE's martyrs; no promotions.",
    ),
    (
        "UAE National Day",
        "12-02",
        "UAE",
        "Celebrate Eid Al Etihad in national colours.",
    ),
)


class HDContentOccasion(Document):
    pass


def occasions_between(start, end, regions: list[str] | None = None) -> list:
    """Occasions from `start` to `end` (repeating ones in every year of the range), by date.

    `regions` limits them to those regions plus Everywhere; None means all regions.
    """
    start, end = getdate(start), getdate(end)
    filters = {}
    if regions is not None:
        filters["region"] = ["in", [EVERYWHERE, *regions]]
    rows = frappe.get_all(
        "HD Content Occasion",
        filters=filters,
        fields=[
            "name",
            "occasion_name",
            "occasion_date",
            "repeats_yearly",
            "region",
            "idea",
        ],
    )
    found = []
    for row in rows:
        for day in occurrences(row, start, end):
            found.append(
                frappe._dict(
                    name=row.name,
                    occasion_name=row.occasion_name,
                    region=row.region,
                    idea=row.idea,
                    date=day,
                )
            )
    return sorted(found, key=lambda o: (o.date, o.occasion_name))


def occurrences(row, start, end) -> list:
    base = getdate(row.occasion_date)
    if not row.repeats_yearly:
        return [base] if start <= base <= end else []
    days = []
    for year in range(start.year, end.year + 1):
        try:
            day = base.replace(year=year)
        except ValueError:  # 29 February in a year without one
            continue
        if start <= day <= end:
            days.append(day)
    return days


def ensure_default_occasions():
    """Add the fixed-date occasions on a site that has none yet."""
    if frappe.db.count("HD Content Occasion"):
        return
    for name, month_day, region, idea in DEFAULT_OCCASIONS:
        frappe.get_doc(
            {
                "doctype": "HD Content Occasion",
                "occasion_name": name,
                "occasion_date": f"2026-{month_day}",
                "repeats_yearly": 1,
                "region": region,
                "idea": idea,
            }
        ).insert(ignore_permissions=True)
