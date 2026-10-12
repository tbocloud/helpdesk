"""Holidays and approved leave, read from ERPNext on the TBO CRM site. Never writes there.

- **Holidays**: the Holiday Lists picked in Settings → CRM (by default the default holiday
  list of the invoicing company), this calendar year and next. They are stored as rows of
  every enabled SLA's holiday list (HD Service Holiday List), marked `synced_from_crm`, so
  the SLA clocks, the follow-ups, capacity and every working-day count use them without
  knowing where they came from. Upserted by date; a synced date that disappears upstream
  is removed; holidays people entered in the hub are never touched.
- **Weekly offs** (`weekly_off` rows): the hub's own weekly-off rule (HD Work Settings'
  Weekly Off and Saturdays Off) already skips the days it covers, so those aren't stored
  again; only weekly offs the rule doesn't cover become dated rows, and the result says
  so, so the rule can be fixed in Work settings.
- **Leave**: approved, submitted Leave Applications from LEAVE_PAST_DAYS ago to
  LEAVE_AHEAD_DAYS ahead, matched to hub users by the Employee's user or company email,
  kept in HD Leave. Without read access to Leave Application or Employee, holidays still
  sync and the settings say what access is missing.

Daily (hooks.py) and with Sync holidays now; docs/tbo-crm-integration.md.
"""

import calendar
from datetime import date
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, now_datetime, nowdate, strip_html

from helpdesk.integrations.crm.client import CRMClient, CRMError, CRMPermissionError
from helpdesk.task_estimates import is_working_day
from helpdesk.work_calendar import (
    ORDINALS,
    nth_weekday_of_month,
    saturday_rule,
    save_holidays,
    sla_holiday_lists,
)

SETTINGS = "HD CRM Settings"
LEAVE_PAST_DAYS = 30
LEAVE_AHEAD_DAYS = 60
# a weekday off at least this many times in the month is off every week
EVERY_WEEK = 4


def sync_window(today) -> tuple[date, date]:
    """This calendar year and next."""
    today = getdate(today)
    return date(today.year, 1, 1), date(today.year + 1, 12, 31)


def sync_holidays_and_leave() -> dict:
    """Holidays, then leave when that's on; records the outcome in HD CRM Settings.
    Problems are returned, not raised, so one never stops the other."""
    settings = frappe.get_single(SETTINGS)
    today = getdate(nowdate())
    result = {
        "ok": True,
        "holidays": None,
        "covered": 0,
        "weekly_off": "",
        "lists": [],
        "leave": None,
        "unmatched": 0,
        "problems": [],
        # set when the API user can't read leave: a setting to fix, not a failure
        "leave_access_problem": None,
    }
    try:
        client = CRMClient.from_settings()
    except CRMError as e:
        result["problems"].append(str(e))
        return finish(result)
    host = urlparse(settings.site_url or "").netloc or _("the CRM site")
    if settings.sync_holidays:
        try:
            sync_holidays(client, settings, today, result)
        except CRMPermissionError:
            result["problems"].append(
                _(
                    "Holiday sync needs read access to Holiday List and Company on {0}."
                ).format(host)
            )
        except CRMError as e:
            result["problems"].append(
                _("Couldn't read the holidays: {0}").format(str(e))
            )
    if settings.sync_leave:
        try:
            sync_leave(client, today, result)
        except CRMPermissionError:
            result["leave_access_problem"] = _(
                "Leave sync needs read access to Leave Application and Employee on {0}."
            ).format(host)
            result["problems"].append(result["leave_access_problem"])
        except CRMError as e:
            result["problems"].append(_("Couldn't read the leave: {0}").format(str(e)))
    return finish(result)


# --- holidays ---


def chosen_lists(client, settings) -> list[str]:
    """The lists picked in settings, else the company's default holiday list."""
    picked = [
        line.strip()
        for line in (settings.holiday_lists or "").splitlines()
        if line.strip()
    ]
    if picked:
        return list(dict.fromkeys(picked))
    companies = client.company_holiday_lists()
    company = settings.invoice_company or (
        companies[0].get("name") if len(companies) == 1 else None
    )
    if not company:
        raise CRMError(
            _(
                "Pick the holiday lists to sync, or set the company under Invoicing to use its default list."
            )
        )
    default = next(
        (c.get("default_holiday_list") for c in companies if c.get("name") == company),
        None,
    )
    if not default:
        raise CRMError(
            _(
                "{0} has no default holiday list on the CRM site; pick the lists to sync."
            ).format(company)
        )
    return [default]


def sync_holidays(client, settings, today, result: dict):
    start, end = sync_window(today)
    lists = chosen_lists(client, settings)
    wanted, weekly_offs = read_holidays(client, lists, start, end)
    rule = saturday_rule()
    # the hub's own weekly-off rule already skips these; storing them again is noise
    uncovered = [day for day in weekly_offs if is_working_day(day, rule)]
    for day in uncovered:
        wanted.setdefault(day, weekly_offs[day])
    targets = sla_holiday_lists()
    if not targets:
        raise CRMError(
            _(
                "No SLA policy has a holiday list to put them in. Add one in Settings → SLA policies, then sync again."
            )
        )
    for name in targets:
        # saving re-saves the SLA's open tickets; one list failing mustn't stop the rest
        frappe.db.savepoint("crm_holiday_list")
        try:
            doc = frappe.get_doc("HD Service Holiday List", name)
            rows, changed = merge_synced(doc.holidays, wanted, start, end)
            if changed:
                save_holidays(doc, rows)
        except Exception as e:  # noqa: BLE001 - recorded, and the next list goes on
            frappe.db.rollback(save_point="crm_holiday_list")
            result["problems"].append(
                _("Couldn't update the holiday list {0}: {1}").format(name, str(e))
            )
    result["lists"] = lists
    result["holidays"] = len(wanted)
    result["covered"] = len(weekly_offs) - len(uncovered)
    result["uncovered"] = len(uncovered)
    result["weekly_off"] = describe_weekly_offs(list(weekly_offs))


def read_holidays(client, lists: list[str], start, end) -> tuple[dict, dict]:
    """({date: holiday row}, {date: weekly-off row}) of the lists between start and end.
    A date in two lists keeps its first description; a holiday wins over a weekly off."""
    holidays, weekly_offs = {}, {}
    for name in lists:
        for row in client.holidays(name):
            if not row.get("holiday_date"):
                continue
            day = getdate(row["holiday_date"])
            if not start <= day <= end:
                continue
            weekly = bool(cint(row.get("weekly_off")))
            entry = frappe._dict(
                holiday_date=day,
                description=strip_html(row.get("description") or "").strip()
                or (_("Weekly off") if weekly else _("Holiday")),
                weekly_off=1 if weekly else 0,
                synced_from_crm=1,
            )
            (weekly_offs if weekly else holidays).setdefault(day, entry)
    for day in holidays:
        weekly_offs.pop(day, None)
    return holidays, weekly_offs


def merge_synced(rows, wanted: dict, start, end) -> tuple[list, bool]:
    """A holiday list's rows with the synced ones matching `wanted` ({date: row}):
    synced rows are updated or, inside the window, dropped when no longer wanted; dates
    the list doesn't have yet are added. Rows people entered are kept as they are, and a
    date they already have isn't added again. Returns (rows, whether anything changed)."""
    keep, present, changed = [], set(), False
    for row in rows:
        day = getdate(row.holiday_date)
        if cint(row.get("synced_from_crm")):
            if day not in wanted:
                if start <= day <= end:
                    changed = True
                    continue
            else:
                new = wanted[day]
                description = strip_html(row.description or "").strip()
                if (description, cint(row.weekly_off)) != (
                    new.description,
                    new.weekly_off,
                ):
                    row.description, row.weekly_off = new.description, new.weekly_off
                    changed = True
        keep.append(row)
        present.add(day)
    for day in sorted(set(wanted) - present):
        keep.append(wanted[day])
        changed = True
    return keep, changed


def describe_weekly_offs(days: list) -> str:
    """ "Sunday, 2nd and 4th Saturday" from weekly-off dates."""
    by_weekday = {}
    for day in days:
        by_weekday.setdefault(day.weekday(), set()).add(nth_weekday_of_month(day))
    parts = []
    for weekday in sorted(by_weekday, key=lambda w: (w + 1) % 7):
        nths = sorted(by_weekday[weekday])
        name = _(calendar.day_name[weekday])
        if len(nths) >= EVERY_WEEK:
            parts.append(name)
        else:
            parts.append(f"{' and '.join(ORDINALS[n] for n in nths)} {name}")
    return ", ".join(parts)


# --- leave ---


def sync_leave(client, today, result: dict):
    """Approved leave around today into HD Leave, matched by the employee's user or
    company email; leave cancelled or gone upstream is removed."""
    start = add_days(today, -LEAVE_PAST_DAYS)
    end = add_days(today, LEAVE_AHEAD_DAYS)
    applications = client.approved_leave(start, end)
    employee_ids = sorted(
        {a.get("employee") for a in applications if a.get("employee")}
    )
    employees = (
        {e.get("name"): e for e in client.employees(employee_ids)}
        if employee_ids
        else {}
    )
    users = hub_users()
    existing = {
        row.name: row
        for row in frappe.get_all(
            "HD Leave",
            fields=["name", *LEAVE_FIELDS],
        )
    }
    # still approved upstream: kept even when it can't be stored or matched this time
    upstream = {a.get("name") for a in applications if a.get("name")}
    synced, unmatched = set(), 0
    for application in applications:
        name = application.get("name")
        user = match_user(employees.get(application.get("employee")) or {}, users)
        if not user or not name:
            unmatched += 1
            continue
        frappe.db.savepoint("crm_leave")
        try:
            store_leave(name, leave_values(application, user), existing.get(name))
            synced.add(name)
        except Exception as e:  # noqa: BLE001 - recorded, and the next leave goes on
            frappe.db.rollback(save_point="crm_leave")
            result["problems"].append(
                _("Couldn't store leave {0}: {1}").format(name, str(e))
            )
    for name in set(existing) - upstream:
        frappe.delete_doc("HD Leave", name, ignore_permissions=True, force=True)
    result["leave"] = len(synced)
    result["unmatched"] = unmatched


LEAVE_FIELDS = (
    "user",
    "employee_name",
    "leave_type",
    "from_date",
    "to_date",
    "half_day",
    "half_day_date",
)


def leave_values(application: dict, user: str) -> dict:
    return {
        "user": user,
        "employee_name": application.get("employee_name"),
        "leave_type": application.get("leave_type"),
        "from_date": getdate(application.get("from_date")),
        "to_date": getdate(application.get("to_date")),
        "half_day": cint(application.get("half_day")),
        "half_day_date": getdate(application["half_day_date"])
        if application.get("half_day_date")
        else None,
    }


def store_leave(name: str, values: dict, existing=None):
    if existing is None:
        frappe.get_doc(
            {"doctype": "HD Leave", "leave_application": name, **values}
        ).insert(ignore_permissions=True)
        return
    # an empty Data field reads back as None or ""; both mean nothing
    changed = {
        field: value
        for field, value in values.items()
        if (existing[field] or None) != (value or None)
    }
    if changed:
        frappe.db.set_value("HD Leave", name, changed)


def hub_users() -> dict[str, str]:
    """{lower-cased name or email: user} of the hub's desk users."""
    found = {}
    for user in frappe.get_all(
        "User", filters={"user_type": "System User"}, fields=["name", "email"]
    ):
        for key in (user.name, user.email):
            if key:
                found.setdefault(key.strip().lower(), user.name)
    return found


def match_user(employee: dict, users: dict) -> str | None:
    """The hub user of an ERPNext Employee: its user, else its company or preferred email."""
    for field in ("user_id", "company_email", "prefered_email"):
        email = (employee.get(field) or "").strip().lower()
        if email in users:
            return users[email]
    return None


# --- recording ---


def finish(result: dict) -> dict:
    """Write the outcome to HD CRM Settings and return it."""
    result["ok"] = not result["problems"]
    values = {
        "holiday_sync_error": "\n".join(result["problems"]),
        "holiday_sync_result": summary(result),
    }
    # when either part synced; each count changes only when its part did
    if result["holidays"] is not None or result["leave"] is not None:
        values["holidays_synced_on"] = now_datetime()
    if result["holidays"] is not None:
        values["holidays_synced_count"] = result["holidays"]
    if result["leave"] is not None:
        values["leave_synced_count"] = result["leave"]
    frappe.db.set_single_value(SETTINGS, values)
    return result


def summary(result: dict) -> str:
    parts = []
    if result["holidays"] is not None:
        parts.append(
            _("{0} holidays from {1}.").format(
                result["holidays"], ", ".join(result["lists"])
            )
        )
        if result["weekly_off"] and result.get("uncovered"):
            parts.append(
                _(
                    "Weekly offs on the CRM site ({0}): {1} of them aren't in Work settings' weekly off, so they're kept as dated holidays. Set the same weekly off in Work settings to drop them."
                ).format(result["weekly_off"], result["uncovered"])
            )
        elif result["weekly_off"]:
            parts.append(
                _("Weekly offs on the CRM site ({0}) match Work settings.").format(
                    result["weekly_off"]
                )
            )
    if result["leave"] is not None:
        parts.append(_("{0} approved leave.").format(result["leave"]))
        if result["unmatched"]:
            parts.append(
                _(
                    "{0} couldn't be matched to a person here: set the employee's user or company email on the CRM site."
                ).format(result["unmatched"])
            )
    return " ".join(parts)


def is_on() -> bool:
    settings = frappe.get_cached_doc(SETTINGS)
    return bool(settings.enabled and (settings.sync_holidays or settings.sync_leave))


def sync_holidays_job():
    """Daily (hooks.py). Never raises: a timeout or a refused key is logged briefly,
    shown in Settings → CRM and tried again on the next run."""
    if not is_on():
        return
    result = sync_holidays_and_leave()
    failures = [p for p in result["problems"] if p != result["leave_access_problem"]]
    if failures:
        frappe.log_error(
            title="CRM holiday sync failed", message="\n".join(failures)[:1000]
        )
