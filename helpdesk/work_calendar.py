"""Which Saturdays the team takes off, for SLAs and for working-day counts.

TBO works Monday to Saturday with the 2nd and 4th Saturdays off. HD Work Settings holds the
rule (Saturdays Off); task and customization dates skip those Saturdays, and every enabled
SLA's holiday list carries them as holidays for the coming year so the SLA clock skips
them too. The list is kept up to date daily and whenever the setting changes.
"""

import frappe
from frappe.utils import add_days, getdate, nowdate

SATURDAY = 5
RULES = {
    "2nd and 4th": {2, 4},
    "1st and 3rd": {1, 3},
    "All": {1, 2, 3, 4, 5},
}
ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th"}
# rows this module adds end with this, so it never touches holidays people entered
MARK = "Saturday off"
DAYS_AHEAD = 366


def saturday_rule() -> set[int]:
    value = frappe.db.get_single_value("HD Work Settings", "saturdays_off")
    return RULES.get(value or "", set())


def nth_weekday_of_month(day) -> int:
    return (getdate(day).day - 1) // 7 + 1


def is_saturday_off(day, rule: set[int] | None = None) -> bool:
    day = getdate(day)
    if day.weekday() != SATURDAY:
        return False
    return nth_weekday_of_month(day) in (saturday_rule() if rule is None else rule)


def saturdays_off_between(start, end, rule: set[int] | None = None) -> list:
    rule = saturday_rule() if rule is None else rule
    day = getdate(start)
    # the first Saturday on or after start
    day = add_days(day, (SATURDAY - day.weekday()) % 7)
    found = []
    while day <= getdate(end):
        if nth_weekday_of_month(day) in rule:
            found.append(day)
        day = add_days(day, 7)
    return found


def sync_saturdays_off():
    """Daily and on settings change: the next year's Saturdays off in every SLA holiday list."""
    today = getdate(nowdate())
    wanted = saturdays_off_between(today, add_days(today, DAYS_AHEAD))
    holiday_lists = set(
        frappe.get_all(
            "HD Service Level Agreement",
            filters={"enabled": 1, "holiday_list": ("is", "set")},
            pluck="holiday_list",
        )
    )
    for name in sorted(holiday_lists):
        sync_holiday_list(name, wanted, today)


def sync_holiday_list(name: str, wanted: list, today) -> bool:
    """Add the wanted Saturdays and drop future ones a changed rule no longer wants."""
    doc = frappe.get_doc("HD Service Holiday List", name)
    wanted = set(wanted)
    keep = []
    changed = False
    for row in doc.holidays:
        day = getdate(row.holiday_date)
        ours = (row.description or "").strip().endswith(MARK)
        if ours and day >= today and day not in wanted:
            changed = True
            continue
        keep.append(row)
    present = {getdate(row.holiday_date) for row in keep}
    for day in sorted(wanted - present):
        keep.append(
            frappe._dict(
                holiday_date=day,
                description=f"{ORDINALS[nth_weekday_of_month(day)]} {MARK}",
                weekly_off=1,
            )
        )
        changed = True
    if not changed:
        return False
    doc.set("holidays", [])
    for row in sorted(keep, key=lambda r: getdate(r.holiday_date)):
        doc.append(
            "holidays",
            {
                "holiday_date": row.holiday_date,
                "description": row.description,
                "weekly_off": row.weekly_off,
            },
        )
    dates = [getdate(r.holiday_date) for r in doc.holidays]
    if dates:
        doc.from_date = min([getdate(doc.from_date or dates[0]), *dates])
        doc.to_date = max([getdate(doc.to_date or dates[-1]), *dates])
    doc.save(ignore_permissions=True)
    return True
