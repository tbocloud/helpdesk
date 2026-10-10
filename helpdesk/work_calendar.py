"""The hub's calendar: days off, holidays and who is on leave.

TBO works Monday to Saturday with the 2nd and 4th Saturdays off. HD Work Settings holds the
rule (Saturdays Off); task and customization dates skip those Saturdays, and every enabled
SLA's holiday list carries them as holidays for the coming year so the SLA clock skips
them too. The list is kept up to date daily and whenever the setting changes.

Holidays and approved leave synced from ERPNext on the CRM site
(helpdesk.integrations.crm.holidays) land in the same holiday lists and in HD Leave; the
readers below are what the calendar, Home, capacity and the follow-ups use.
"""

import frappe
from frappe.utils import add_days, cint, getdate, nowdate

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


def default_holiday_list() -> str | None:
    """The default SLA's holiday list: the hub's calendar."""
    return frappe.db.get_value(
        "HD Service Level Agreement",
        {"default_sla": 1, "enabled": 1},
        "holiday_list",
    )


def sla_holiday_lists() -> list[str]:
    """Every enabled SLA's holiday list, each once."""
    return sorted(
        set(
            frappe.get_all(
                "HD Service Level Agreement",
                filters={"enabled": 1, "holiday_list": ("is", "set")},
                pluck="holiday_list",
            )
        )
    )


def holidays_between(start, end, weekly_off: bool = True) -> list[dict]:
    """Rows of the default SLA's holiday list between `start` and `end`, by date:
    date, description and whether it came from the CRM site. Without `weekly_off`,
    only the named holidays (no Saturdays off or other weekly offs)."""
    holiday_list = default_holiday_list()
    if not holiday_list:
        return []
    holiday = frappe.qb.DocType("HD Holiday")
    query = (
        frappe.qb.from_(holiday)
        .select(
            holiday.holiday_date,
            holiday.description,
            holiday.synced_from_crm,
        )
        .where(
            (holiday.parenttype == "HD Service Holiday List")
            & (holiday.parent == holiday_list)
            & holiday.holiday_date.between(getdate(start), getdate(end))
        )
        .orderby(holiday.holiday_date)
    )
    if not weekly_off:
        query = query.where(holiday.weekly_off == 0)
    return [
        {
            "date": getdate(row.holiday_date),
            "description": frappe.utils.strip_html(row.description or "").strip(),
            "synced": bool(row.synced_from_crm),
        }
        for row in query.run(as_dict=True)
    ]


def company_holidays(start, end) -> set:
    """Holidays between `start` and `end` on the default SLA's holiday list, the hub's
    calendar (it also carries the Saturdays off, see sync_saturdays_off, and the
    holidays synced from the CRM site)."""
    return {row["date"] for row in holidays_between(start, end)}


def next_holiday(today=None) -> dict | None:
    """The next named holiday from `today` on (today included), within a year."""
    today = getdate(today or nowdate())
    found = holidays_between(today, add_days(today, DAYS_AHEAD), weekly_off=False)
    return found[0] if found else None


# --- leave (HD Leave, synced from the CRM site) ---


def is_half_day(leave, day) -> bool:
    """Whether `day` of a leave is a half day (ERPNext's half_day and half_day_date)."""
    if not cint(leave.half_day):
        return False
    if leave.half_day_date:
        return getdate(leave.half_day_date) == getdate(day)
    return getdate(leave.from_date) == getdate(leave.to_date)


def leave_between(start, end, users=None) -> list:
    """HD Leave rows overlapping `start` to `end`, of `users` (everyone when None)."""
    filters = {
        "from_date": ("<=", getdate(end)),
        "to_date": (">=", getdate(start)),
    }
    if users is not None:
        filters["user"] = ("in", list(users) or [""])
    return frappe.get_all(
        "HD Leave",
        filters=filters,
        fields=["user", "from_date", "to_date", "half_day", "half_day_date"],
        order_by="from_date asc",
    )


def on_leave(day=None, users=None, half_days: bool = False) -> dict:
    """{user: the last day of their leave} for people on leave on `day` (today).
    A half day only counts with `half_days`; they still work part of it."""
    day = getdate(day or nowdate())
    away = {}
    for leave in leave_between(day, day, users):
        if half_days or not is_half_day(leave, day):
            away[leave.user] = max(getdate(leave.to_date), away.get(leave.user, day))
    return away


def leave_today(day=None) -> dict:
    """{user: {"to_date", "half_day"}} for everyone on leave on `day` (today), half
    days included: what the pickers, the team views and Home show."""
    day = getdate(day or nowdate())
    full_day = on_leave(day)
    return {
        user: {"to_date": str(to_date), "half_day": user not in full_day}
        for user, to_date in on_leave(day, half_days=True).items()
    }


def leave_fractions(users, start, end) -> dict:
    """{user: {day: 1, or 0.5 for a half day}} of leave between `start` and `end`."""
    start, end = getdate(start), getdate(end)
    found = {}
    for leave in leave_between(start, end, users):
        day = max(getdate(leave.from_date), start)
        last = min(getdate(leave.to_date), end)
        while day <= last:
            found.setdefault(leave.user, {})[day] = (
                0.5 if is_half_day(leave, day) else 1
            )
            day = add_days(day, 1)
    return found


def sync_saturdays_off():
    """Daily and on settings change: the next year's Saturdays off in every SLA holiday list."""
    today = getdate(nowdate())
    wanted = saturdays_off_between(today, add_days(today, DAYS_AHEAD))
    for name in sla_holiday_lists():
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
    save_holidays(doc, keep)
    return True


def save_holidays(doc, rows: list):
    """Replace a holiday list's rows with `rows` (sorted by date), widening its dates to
    fit them, and save it."""
    doc.set("holidays", [])
    for row in sorted(rows, key=lambda r: getdate(r.holiday_date)):
        doc.append(
            "holidays",
            {
                "holiday_date": row.holiday_date,
                "description": row.description,
                "weekly_off": row.weekly_off,
                "synced_from_crm": row.get("synced_from_crm") or 0,
            },
        )
    dates = [getdate(r.holiday_date) for r in doc.holidays]
    if dates:
        doc.from_date = min([getdate(doc.from_date or dates[0]), *dates])
        doc.to_date = max([getdate(doc.to_date or dates[-1]), *dates])
    doc.save(ignore_permissions=True)
