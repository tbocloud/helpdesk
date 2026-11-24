"""The division overview page and the division reports (docs/divisions.md)."""

import shutil

import frappe
from frappe import _
from frappe.utils import flt, format_datetime, formatdate, now_datetime

from helpdesk import division_overview as overview_data
from helpdesk.divisions import DIVISION, log_activity

EXPORT_FORMATS = ("xlsx", "pdf")


@frappe.whitelist()
def get_overview(
    division: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    return overview_data.overview(division or None, from_date, to_date)


@frappe.whitelist()
def get_lead_status(
    division: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    group: str | None = None,
    status: str | None = None,
    employee: str | None = None,
    lead_source: str | None = None,
) -> dict:
    return overview_data.lead_status(
        division or None,
        from_date,
        to_date,
        group or None,
        status or None,
        employee or None,
        lead_source or None,
    )


@frappe.whitelist()
def get_division_cards(
    from_date: str | None = None, to_date: str | None = None
) -> dict:
    return overview_data.division_cards(from_date, to_date)


@frappe.whitelist()
def get_division_dashboard(
    division: str, from_date: str | None = None, to_date: str | None = None
) -> dict:
    return overview_data.division_dashboard(division, from_date, to_date)


@frappe.whitelist()
def get_reports() -> dict:
    """The reports and the divisions they can be run for."""
    overview_data.scope(None)
    return {
        "reports": overview_data.report_list(),
        "options": overview_data.division_options(),
    }


@frappe.whitelist()
def get_report(
    report: str,
    division: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    return overview_data.report(report, division or None, from_date, to_date)


@frappe.whitelist()
def export_report(
    report: str,
    file_format: str,
    division: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
):
    """The report as an Excel file or a PDF (a page that prints itself where the server
    can't render PDFs). Every export is in the audit log."""
    if file_format not in EXPORT_FORMATS:
        frappe.throw(_("Export as Excel or PDF."))
    result = overview_data.report(report, division or None, from_date, to_date)
    scope = (
        frappe.db.get_value(DIVISION, division, "division_name")
        if division
        else _("All divisions")
    )
    period = _("{0} to {1}").format(
        formatdate(result["from_date"]), formatdate(result["to_date"])
    )
    columns = result["columns"]
    rows = [
        [cell(row.get(c["key"]), c["kind"]) for c in columns] for row in result["rows"]
    ]
    errors = [
        _("{0}: no customers or quotations ({1})").format(e["division"], e["error"])
        for e in result["errors"]
    ]
    filename = (
        f"{frappe.scrub(result['title'])}-{result['from_date']}-to-{result['to_date']}"
    )
    log_activity(
        _("Exported {0} ({1}, {2}) as {3}").format(
            result["title"], scope, period, file_format.upper()
        ),
        division or None,
    )
    if file_format == "xlsx":
        send_xlsx(result, columns, rows, [scope, period, *errors], filename)
    else:
        send_pdf(result, columns, rows, scope, period, errors, filename)


def cell(value, kind: str):
    """A value as the file shows it; unknown stays blank, never 0."""
    if value is None:
        return ""
    if kind == "percent":
        return f"{value}%"
    if kind in ("money", "hours"):
        return round(flt(value), 2)
    return value


def send_xlsx(result: dict, columns: list, rows: list, lines: list, filename: str):
    from frappe.utils.xlsxutils import make_xlsx

    data = [[result["title"]], *[[line] for line in lines]]
    if result["currency"]:
        data.append([_("Money in {0}").format(result["currency"])])
    data += [[], [c["label"] for c in columns], *rows]
    # Excel refuses sheet names over 31 characters
    xlsx = make_xlsx(data, result["title"][:31])
    frappe.response.filename = f"{filename}.xlsx"
    frappe.response.filecontent = xlsx.getvalue()
    frappe.response.type = "binary"


def send_pdf(
    result: dict,
    columns: list,
    rows: list,
    scope: str,
    period: str,
    errors: list,
    filename: str,
):
    can_render_pdf = bool(shutil.which("wkhtmltopdf"))
    html = frappe.render_template(  # the app's own fixed template, not user input - nosemgrep
        "helpdesk/templates/division_report_pdf.html",
        {
            "title": result["title"],
            "scope": scope,
            "period": period,
            "currency": result["currency"],
            "errors": errors,
            "columns": [frappe._dict(c) for c in columns],
            "rows": rows,
            "generated_on": format_datetime(now_datetime()),
            "generated_by": frappe.utils.get_fullname(frappe.session.user),
            "auto_print": not can_render_pdf,
        },
    )
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
