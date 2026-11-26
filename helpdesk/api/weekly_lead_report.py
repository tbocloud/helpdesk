"""Sales → Lead report (docs/weekly-lead-report.md): the KSA sheet of the leads each
salesperson owns that were created or updated in a week, read from and written to the leads
on the division's ERP site. A salesperson sees their own; the division's managers everyone's."""

from datetime import timedelta
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cint, formatdate, get_fullname, today

from helpdesk.api.division_overview import send_xlsx
from helpdesk.divisions import DIVISION, MEMBER, division_client, log_activity
from helpdesk.integrations.crm.client import CRMError
from helpdesk.integrations.crm.leads import call
from helpdesk.weekly_lead_report import (
    CONVERSION_FIELD,
    CONVERSIONS,
    DESIGNATION_FIELD,
    FOLLOW_UP_FIELD,
    FOLLOW_UPS,
    MAX_DESIGNATION,
    MAX_REMARKS,
    MAX_VISITS,
    NOT_SET,
    REMARKS_FIELD,
    SEGMENT_FIELD,
    SEGMENT_LABELS,
    VISITS_FIELD,
    filter_rows,
    read_lead,
    read_week,
    remarks_html,
    report_division,
    sees_team,
    week_start,
)


@frappe.whitelist()
def get_week(
    week: str | None = None,
    salesperson: str | None = None,
    search: str | None = None,
    requirement: str | None = None,
    conversion: str | None = None,
    follow_up: str | None = None,
    quoted: str | None = None,
) -> dict:
    """The week's rows: the signed-in salesperson's leads, or (a manager) everyone's or one
    person's, narrowed by the filters (`filter_rows`)."""
    user, division = require_report()
    start = week_start(week)
    team = sees_team(division, user)
    rows = erp(
        lambda: read_week(division, start, (salesperson or None) if team else user)
    )
    for row in rows:
        row["salesperson_name"] = (
            get_fullname(row["salesperson"]) if row["salesperson"] else _("No owner")
        )
    rows.sort(
        key=lambda r: (r["salesperson_name"].casefold(), r["company_name"].casefold())
    )
    return {
        "division": division,
        "division_name": frappe.db.get_value(DIVISION, division, "division_name"),
        "week_start": str(start),
        "week_end": str(start + timedelta(days=6)),
        "this_week": str(week_start()),
        "today": today(),
        "sees_team": team,
        "people": team_people(division, rows) if team else [],
        "rows": filter_rows(
            rows,
            {
                "search": search,
                "requirement": requirement,
                "conversion": conversion,
                "follow_up": follow_up,
                "quoted": quoted,
            },
        ),
    }


@frappe.whitelist()
def get_lead_sheet(lead: str) -> dict:
    """One lead's sheet columns, for the Lead page and the Edit lead dialog."""
    _user, division = require_report()
    check_lead(lead)
    client = division_client(division)
    return erp(lambda: read_lead(client, lead))


@frappe.whitelist(methods=["POST"])
def update_lead(lead: str, values) -> dict:
    """Changes the lead's sheet fields: designation, requirement, conversion possibility,
    visits this week, follow-up plan and remarks (its Comment). Anyone the ERP site shows
    the lead to."""
    _user, division = require_report()
    values = frappe.parse_json(values) or {}
    check_lead(lead)
    changes = sheet_changes(values)
    if changes:
        client = division_client(division)
        erp(lambda: write_lead(client, lead, changes))
    return {"saved": True}


@frappe.whitelist()
def export_week(
    week: str | None = None,
    salesperson: str | None = None,
    search: str | None = None,
    requirement: str | None = None,
    conversion: str | None = None,
    follow_up: str | None = None,
    quoted: str | None = None,
):
    """The week's rows as the page shows them (same filters), as an Excel file in the
    template's columns (with the salesperson first when it holds several people's). Every
    export is in the audit log."""
    data = get_week(
        week, salesperson, search, requirement, conversion, follow_up, quoted
    )
    # a salesperson's file is always their own; a manager's, one person's when they picked one
    person = salesperson if data["sees_team"] else frappe.session.user
    columns = export_columns(with_person=not person)
    period = _("{0} to {1}").format(
        formatdate(data["week_start"]), formatdate(data["week_end"])
    )
    who = get_fullname(person) if person else _("Everyone")
    log_activity(
        _("Exported the lead report ({0}, {1})").format(period, who),
        data["division"],
    )
    send_xlsx(
        {"title": _("Lead report"), "currency": None},
        columns,
        [[export_cell(r, c["key"]) for c in columns] for r in data["rows"]],
        [
            data["division_name"],
            period,
            who,
            *filter_lines(search, requirement, conversion, follow_up, quoted),
        ],
        f"lead-report-{data['week_start']}",
    )


def filter_lines(search, requirement, conversion, follow_up, quoted) -> list[str]:
    """The filters a file was made with, one line each, so it says what it leaves out."""

    def shown(value):
        return _("Not set") if value == NOT_SET else _(SEGMENT_LABELS.get(value, value))

    lines = []
    if search:
        lines.append(_("Search: {0}").format(search))
    for label, value in (
        (_("Requirement"), requirement),
        (_("Conversion possibility"), conversion),
        (_("Follow-up plan"), follow_up),
        (_("Quoted"), quoted),
    ):
        if value:
            lines.append(f"{label}: {shown(value)}")
    return lines


def require_report() -> tuple[str, str]:
    """(the signed-in user, their division) when the report is open to them; else refused."""
    user = frappe.session.user
    division = report_division(user)
    if not division:
        frappe.throw(
            _("The lead report is for the salespeople of a division that keeps it."),
            frappe.PermissionError,
        )
    return user, division


def check_lead(name: str):
    """Reads the lead on the ERP site as the signed-in person: refused when they can't see
    it. Writes then go with the hub's key, which may change any lead."""
    call("get_lead", name=name)


def sheet_changes(values: dict) -> dict:
    """The Lead fields to write for the sheet `values` given, each checked."""
    changes = {}
    if "designation" in values:
        designation = str(values["designation"] or "").strip()
        if len(designation) > MAX_DESIGNATION:
            frappe.throw(
                _("Keep the designation under {0} characters.").format(MAX_DESIGNATION)
            )
        changes[DESIGNATION_FIELD] = designation
    if "requirement" in values:
        requirement = values["requirement"] or ""
        if requirement not in ("", *SEGMENT_LABELS):
            frappe.throw(_("Pick ERPNext or Digital Marketing."))
        changes[SEGMENT_FIELD] = requirement
    if "conversion" in values:
        conversion = values["conversion"] or ""
        if conversion not in ("", *CONVERSIONS):
            frappe.throw(_("Pick High, Medium, Low or Not Possible."))
        changes[CONVERSION_FIELD] = conversion
    if "visits" in values:
        visits = cint(values["visits"])
        if not 0 <= visits <= MAX_VISITS:
            frappe.throw(_("Visits this week go from 0 to {0}.").format(MAX_VISITS))
        changes[VISITS_FIELD] = visits
    if "follow_up" in values:
        follow_up = values["follow_up"] or ""
        if follow_up not in ("", *FOLLOW_UPS):
            frappe.throw(_("Pick Yes or No for the follow-up plan."))
        changes[FOLLOW_UP_FIELD] = follow_up
    if "remarks" in values:
        remarks = str(values["remarks"] or "").strip()
        if len(remarks) > MAX_REMARKS:
            frappe.throw(
                _("Keep the remarks under {0} characters.").format(MAX_REMARKS)
            )
        changes[REMARKS_FIELD] = remarks_html(remarks)
    return changes


def write_lead(client, name: str, values: dict):
    client.request("PUT", f"/api/resource/Lead/{quote(name)}", json=values)


def erp(work):
    """`work` against the ERP site, its failure as a message the page can show."""
    try:
        return work()
    except CRMError as e:
        frappe.log_error(title="Lead report: the ERP site failed")
        frappe.throw(
            _(
                "The ERP site couldn't be read or changed ({0}). Try again in a minute."
            ).format(e)
        )


def team_people(division: str, rows: list[dict]) -> list[dict]:
    """Whom a manager may pick: the division's people and the owners of the week's leads."""
    users = set(
        frappe.get_all(
            MEMBER, filters={"parent": division, "parenttype": DIVISION}, pluck="user"
        )
    ) | {r["salesperson"] for r in rows if r["salesperson"]}
    people = [{"user": u, "full_name": get_fullname(u)} for u in users]
    return sorted(people, key=lambda p: p["full_name"].casefold())


def export_columns(with_person: bool) -> list[dict]:
    """The KSA template's columns, in its order."""
    columns = [
        ("company_name", _("Name")),
        ("contact_number", _("Contact Number")),
        ("email", _("Email")),
        ("business", _("Nature of Business")),
        ("contact_name", _("Contact Name")),
        ("designation", _("Contact Designation")),
        ("requirement_label", _("Requirement")),
        ("quoted", _("Quoted (Yes/No)")),
        ("quoted_value", _("Quoted (Value)")),
        ("quotation", _("Quotation Number")),
        ("conversion", _("Conversion Possibility (High/Medium/Low/Not Possible)")),
        ("visits", _("Number of Visits This Week")),
        ("follow_up", _("Future Follow-up Plan")),
        ("remarks", _("Remarks")),
    ]
    if with_person:
        columns.insert(0, ("salesperson_name", _("Salesperson")))
    return [{"key": key, "label": label} for key, label in columns]


def export_cell(row: dict, key: str):
    value = row.get(key)
    if key == "quoted":
        return _("Yes") if value else _("No")
    if key == "quoted_value":
        return (
            "" if value is None else f"{value:,.2f} {row.get('currency') or ''}".strip()
        )
    return value if value is not None else ""
