"""The Timesheets page's export: the time logs on screen as an Excel workbook or a PDF
report, person by person (each with their own logs, then their total) and the total
hours at the end. See docs/workspace-pages.md, Timesheets."""

import io

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate

from helpdesk.tasky.api import (
    _full_name,
    _names_of,
    _plain_note,
    _time_log_filters,
    _visible_timesheets,
)
from helpdesk.utils import report_brand, send_report_pdf

FORMATS = ("xlsx", "pdf")
PDF_TEMPLATE = "helpdesk/templates/timesheet_report_pdf.html"
# a time log row taller than a page runs over the repeated column headings in
# wkhtmltopdf; the PDF cuts longer notes, the Excel keeps them whole
PDF_NOTES_LIMIT = 500

# the TBO theme's brand teal and slate neutrals (desk/src/theme.css)
BRAND = "17657F"
BRAND_SOFT = "E6F0F4"
HEAD_FILL = "F1F5F9"
RULE = "CBD5E1"
# (label, width, a number: right-aligned)
DETAIL_COLUMNS = [
    ("Date", 13, False),
    ("Timesheet", 17, False),
    ("Project", 26, False),
    ("Task", 34, False),
    ("Notes", 48, False),
    ("Billable", 10, False),
    ("Status", 12, False),
    ("Hours", 10, True),
]
SUMMARY_COLUMNS = [
    ("Employee", 30, False),
    ("Email", 34, False),
    ("Days", 9, True),
    ("Time logs", 11, True),
    ("Billable hours", 15, True),
    ("Non-billable hours", 19, True),
    ("Total hours", 13, True),
]


def send(file_format: str, view: bool, team, agent, from_date, to_date, project):
    """Answers the request with the report: an Excel download, or a PDF downloaded or
    (`view`) shown in the browser."""
    if file_format not in FORMATS:
        frappe.throw(_("Export as Excel or PDF."))
    report = build(team, agent, from_date, to_date, project)
    if file_format == "xlsx":
        send_xlsx(report)
    else:
        send_pdf(report, view)


def build(team, agent, from_date, to_date, project) -> dict:
    """The time logs the viewer may see under the filters, grouped by person (name order),
    each person's logs in date order, with their totals and the report's."""
    sheets = _visible_timesheets(
        team, agent, from_date, to_date, ["name", "status", "owner"], project
    )
    logs = (
        frappe.get_all(
            "Timesheet Detail",
            filters=_time_log_filters(sheets, from_date, to_date, project),
            fields=[
                "parent",
                "from_time",
                "hours",
                "project",
                "task",
                "description",
                "custom_billable",
            ],
            order_by="from_time asc, idx asc",
        )
        if sheets
        else []
    )
    projects = _names_of("Project", "project_name", {log.project for log in logs})
    tasks = _names_of("Task", "subject", {log.task for log in logs})

    people = {}
    for log in logs:
        owner = sheets[log.parent].owner
        person = people.setdefault(owner, {"user": owner, "logs": []})
        person["logs"].append(
            {
                "date": getdate(log.from_time) if log.from_time else None,
                "timesheet": log.parent,
                "status": _(sheets[log.parent].status),
                "project": projects.get(log.project, log.project or ""),
                "task": tasks.get(log.task, log.task or ""),
                "notes": _plain_note(log.description),
                "billable": bool(log.custom_billable),
                "hours": round(flt(log.hours), 2),
            }
        )
    for person in people.values():
        person["full_name"] = _full_name(person["user"])
        person.update(_totals(person["logs"]))
        person["days"] = len({log["date"] for log in person["logs"] if log["date"]})

    ordered = sorted(people.values(), key=lambda p: p["full_name"].lower())
    all_logs = [log for p in ordered for log in p["logs"]]
    return {
        "title": _("Timesheet report"),
        "team": bool(frappe.utils.cint(team)),
        "scope": _scope_label(team, agent),
        "period": _period_label(from_date, to_date),
        "project": _names_of("Project", "project_name", {project}).get(project, project)
        if project
        else None,
        "filename": _filename(from_date, to_date),
        "people": ordered,
        **_totals(all_logs),
    }


def _totals(logs: list) -> dict:
    hours = round(sum(log["hours"] for log in logs), 2)
    billable = round(sum(log["hours"] for log in logs if log["billable"]), 2)
    return {
        "hours": hours,
        "billable_hours": billable,
        "non_billable_hours": round(hours - billable, 2),
        "log_count": len(logs),
    }


def _scope_label(team, agent) -> str:
    if not frappe.utils.cint(team):
        return _("My timesheets: {0}").format(_full_name(frappe.session.user))
    if agent:
        return _("Team timesheets: {0}").format(_full_name(agent))
    return _("Team timesheets: everyone")


def _period_label(from_date, to_date) -> str:
    if from_date and to_date:
        return _("{0} to {1}").format(formatdate(from_date), formatdate(to_date))
    if from_date:
        return _("Since {0}").format(formatdate(from_date))
    if to_date:
        return _("Up to {0}").format(formatdate(to_date))
    return _("All time")


def _filename(from_date, to_date) -> str:
    period = "-to-".join(str(getdate(d)) for d in (from_date, to_date) if d) or "all"
    return f"timesheets-{period}"


def hours_text(hours: float) -> str:
    """20.5 → "20.5", 8.0 → "8", as the Timesheets page shows hours."""
    return f"{flt(hours):.2f}".rstrip("0").rstrip(".")


# --- PDF ---


def send_pdf(report: dict, view: bool):
    """A4 portrait: the letterhead, the totals, a summary by person for the team, then
    each person on a page of their own with their total; a footer on every page."""
    brand = report_brand()
    send_report_pdf(
        PDF_TEMPLATE,
        {
            **report,
            "brand": brand,
            "hours_text": hours_text,
            "notes_limit": PDF_NOTES_LIMIT,
        },
        report["filename"],
        orientation="Portrait",
        inline=view,
        # room for the footer on every page; a Letter Head footer is a page-wide band
        pdf_options={
            "margin-top": "12mm",
            "margin-bottom": "48mm" if brand["letter_head_footer"] else "22mm",
        },
    )


# --- Excel ---


def send_xlsx(report: dict):
    """A Summary sheet (hours by person and the total) and a Time logs sheet: each person's
    name band, their logs and their total, then the grand total."""
    from openpyxl import Workbook

    book = Workbook()
    summary = book.active
    summary.title = _("Summary")
    _write_summary(summary, report)
    _write_logs(book.create_sheet(_("Time logs")), report)

    out = io.BytesIO()
    book.save(out)
    frappe.response.filename = f"{report['filename']}.xlsx"
    frappe.response.filecontent = out.getvalue()
    frappe.response.type = "binary"


def _write_header(sheet, report: dict, width: int) -> int:
    """The title and what the report covers; returns the next free row."""
    from openpyxl.styles import Font

    brand = report_brand()["name"]
    _text(sheet, 1, 1, f"{brand} · {report['title']}").font = Font(
        bold=True, size=15, color=BRAND
    )
    lines = [report["scope"], _("Period: {0}").format(report["period"])]
    if report["project"]:
        lines.append(_("Project: {0}").format(report["project"]))
    lines.append(
        _("Generated by {0} on {1}").format(
            frappe.utils.get_fullname(frappe.session.user),
            frappe.utils.format_datetime(frappe.utils.now_datetime()),
        )
    )
    for i, line in enumerate(lines, start=2):
        _text(sheet, i, 1, line).font = Font(color="475569")
    for row in range(1, len(lines) + 2):
        sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=width)
    return len(lines) + 3


def _write_summary(sheet, report: dict):
    row = _write_header(sheet, report, len(SUMMARY_COLUMNS))
    _column_heads(sheet, row, SUMMARY_COLUMNS)
    for person in report["people"]:
        row += 1
        _text(sheet, row, 1, person["full_name"])
        _text(sheet, row, 2, person["user"])
        sheet.cell(row, 3, person["days"])
        sheet.cell(row, 4, person["log_count"])
        for col, key in (
            (5, "billable_hours"),
            (6, "non_billable_hours"),
            (7, "hours"),
        ):
            sheet.cell(row, col, person[key]).number_format = "0.00"
        _rule(sheet, row, len(SUMMARY_COLUMNS))
    row += 1
    _total_row(
        sheet,
        row,
        len(SUMMARY_COLUMNS),
        _("Total"),
        {
            4: report["log_count"],
            5: report["billable_hours"],
            6: report["non_billable_hours"],
            7: report["hours"],
        },
        grand=True,
    )
    _widths(sheet, SUMMARY_COLUMNS)
    _print_setup(sheet)


def _write_logs(sheet, report: dict):
    from openpyxl.styles import Alignment, Font, PatternFill

    width = len(DETAIL_COLUMNS)
    row = _write_header(sheet, report, width)
    if not report["people"]:
        _text(sheet, row, 1, _("No time logged in these dates."))
    for person in report["people"]:
        # the person's band: name and email, then their hours on the right
        band = PatternFill("solid", fgColor=BRAND)
        for col in range(1, width + 1):
            sheet.cell(row, col).fill = band
        name = person["full_name"]
        if person["user"] != name:
            name = f"{name}  ·  {person['user']}"
        _text(sheet, row, 1, name).font = Font(bold=True, color="FFFFFF", size=12)
        sheet.merge_cells(
            start_row=row, start_column=1, end_row=row, end_column=width - 2
        )
        _text(
            sheet,
            row,
            width - 1,
            _("{0} days").format(person["days"]) if person["days"] != 1 else _("1 day"),
        ).font = Font(color="FFFFFF")
        hours = sheet.cell(row, width, person["hours"])
        hours.font = Font(bold=True, color="FFFFFF", size=12)
        hours.number_format = "0.00"
        sheet.row_dimensions[row].height = 22

        row += 1
        _column_heads(sheet, row, DETAIL_COLUMNS)
        for log in person["logs"]:
            row += 1
            date = sheet.cell(row, 1, log["date"])
            date.number_format = "DD MMM YYYY"
            _text(sheet, row, 2, log["timesheet"])
            _text(sheet, row, 3, log["project"])
            _text(sheet, row, 4, log["task"])
            _text(sheet, row, 5, log["notes"])
            _text(sheet, row, 6, _("Yes") if log["billable"] else _("No"))
            _text(sheet, row, 7, log["status"])
            sheet.cell(row, 8, log["hours"]).number_format = "0.00"
            for col in range(1, width + 1):
                sheet.cell(row, col).alignment = Alignment(
                    vertical="top", wrap_text=col in (3, 4, 5)
                )
            _rule(sheet, row, width)
        row += 1
        _total_row(
            sheet,
            row,
            width,
            _("Total for {0}").format(person["full_name"]),
            {width: person["hours"]},
        )
        row += 2
    if report["people"]:
        _total_row(
            sheet,
            row,
            width,
            _("Total hours, all employees ({0} h billable)").format(
                hours_text(report["billable_hours"])
            )
            if report["team"]
            else _("Total hours ({0} h billable)").format(
                hours_text(report["billable_hours"])
            ),
            {width: report["hours"]},
            grand=True,
        )
    _widths(sheet, DETAIL_COLUMNS)
    _print_setup(sheet)


def _text(sheet, row: int, col: int, value):
    """A text cell; text that starts like a formula stays text, never runs."""
    cell = sheet.cell(row, col, value or "")
    if isinstance(value, str) and value:
        cell.data_type = "s"
    return cell


def _column_heads(sheet, row: int, columns: list):
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    for col, (label, _width, numeric) in enumerate(columns, start=1):
        cell = _text(sheet, row, col, _(label))
        cell.font = Font(bold=True, color="334155")
        cell.fill = PatternFill("solid", fgColor=HEAD_FILL)
        cell.border = Border(bottom=Side(style="medium", color=RULE))
        if numeric:
            cell.alignment = Alignment(horizontal="right")


def _total_row(sheet, row: int, width: int, label: str, values: dict, grand=False):
    from openpyxl.styles import Border, Font, PatternFill, Side

    fill = PatternFill("solid", fgColor=BRAND if grand else BRAND_SOFT)
    color = "FFFFFF" if grand else BRAND
    for col in range(1, width + 1):
        cell = sheet.cell(row, col)
        cell.fill = fill
        cell.border = Border(top=Side(style="medium", color=BRAND))
    first_value = min(values)
    _text(sheet, row, 1, label).font = Font(bold=True, color=color)
    if first_value > 2:
        sheet.merge_cells(
            start_row=row, start_column=1, end_row=row, end_column=first_value - 1
        )
    for col, value in values.items():
        cell = sheet.cell(row, col, value)
        cell.font = Font(bold=True, color=color)
        if isinstance(value, float):
            cell.number_format = "0.00"
    sheet.row_dimensions[row].height = 20


def _rule(sheet, row: int, width: int):
    from openpyxl.styles import Border, Side

    for col in range(1, width + 1):
        sheet.cell(row, col).border = Border(bottom=Side(style="thin", color="E2E8F0"))


def _widths(sheet, columns: list):
    from openpyxl.utils import get_column_letter

    for col, (_label, width, _numeric) in enumerate(columns, start=1):
        sheet.column_dimensions[get_column_letter(col)].width = width


def _print_setup(sheet):
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.sheet_view.showGridLines = False
