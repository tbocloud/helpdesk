# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""A sign-off template: a training questionnaire for one module (Accounts, Stock, HR...), or a
UAT's mail (its tests come from the project's SRS), with the mail that asks the customer to sign.

Each question is copied into a sign-off when it is created, so editing a template never changes
a sign-off already sent; the mail is copied too, its placeholders filled in. See
docs/project-signoff.md.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class HDSignoffTemplate(Document):
    def validate(self):
        self.clean_items()
        self.validate_items()
        self.validate_default_cc()

    def clean_items(self):
        """Blank rows are dropped; text is trimmed."""
        rows = []
        for row in self.items:
            row.section = (row.section or "").strip()
            row.question = (row.question or "").strip()
            row.help_text = (row.help_text or "").strip()
            if row.question:
                rows.append(row)
        self.items = rows

    def validate_items(self):
        # a UAT's tests come from the project's SRS: its template is only the mail
        if self.is_active and not self.items and self.signoff_type != "UAT":
            frappe.throw(_("Add at least one question, or make the template inactive."))

    def validate_default_cc(self):
        from helpdesk.helpdesk.doctype.hd_project_signoff.hd_project_signoff import (
            HDProjectSignoff,
        )

        self.default_cc = ", ".join(HDProjectSignoff.clean_emails(self.default_cc))


# The mail each kind of sign-off sends when its template has none (and the seeds' mail): the
# wording of TBO's Sign-off requirements, with the customer signing on the page the link opens
# rather than by replying. Data, like a template's own mail, so not translated.
SIGNATURE = "<p>Regards,<br>{{ sender_name }}<br>{{ sender_designation }}<br>{{ company_name }}</p>"
TRAINING_MAIL = {
    "subject": "Training Sign-off – {{ modules }} – {{ project_name }}",
    "body": "<p>Dear {{ contact_salutation }} {{ contact_name }},</p>"
    "<p>I hope you are doing well.</p>"
    "<p>We have completed the training on the {{ modules }} module(s) on {{ training_date }}, "
    "conducted by {{ trainer_name }}.</p>"
    "<p>We kindly request you to confirm that the training has been completed to your "
    "satisfaction by completing the short sign-off form here: {{ sign_off_link }}</p>"
    "<p>If any topic needs to be covered again, please let us know and we will arrange a "
    "session.</p>" + SIGNATURE,
}
UAT_MAIL = {
    "subject": "UAT Sign-off Request – {{ project_name }}",
    "body": "<p>Dear {{ contact_salutation }} {{ contact_name }},</p>"
    "<p>I hope you are doing well.</p>"
    "<p>As agreed, we have completed the {{ project_name }} implementation on the UAT site, "
    "covering the following modules: {{ modules }}.</p>"
    "<p>This email serves as the official request for UAT sign-off. We kindly request you to "
    "run each test on the sign-off page and confirm your acceptance there: {{ sign_off_link }}</p>"
    "<p>Once we receive your confirmation, we will share the plan for the Go-Live.</p>"
    "<p>If you have any questions or require further clarification, please feel free to "
    "contact us.</p>" + SIGNATURE,
}
UAT_GO_LIVE_MAIL = {
    "subject": "UAT Sign-off and Go-Live Confirmation – {{ project_name }}",
    "body": "<p>Dear {{ contact_salutation }} {{ contact_name }},</p>"
    "<p>I hope you are doing well.</p>"
    "<p>As agreed, we have completed the {{ project_name }} implementation on the UAT site, "
    "covering the requirements outlined in the SRS and the concerns raised by your team.</p>"
    "<p>This email serves as the official request for UAT sign-off and confirmation to proceed "
    "with the Go-Live process. We kindly request you to review the completed implementation and "
    "confirm your acceptance on the sign-off page: {{ sign_off_link }}</p>"
    "<p>As agreed, we will continue to provide support throughout the agreed support period. "
    "Upon receiving your confirmation, we will proceed with the necessary activities to deploy "
    "the completed setup to your live server at the earliest.</p>"
    "<p>If you have any questions or require further clarification, please feel free to "
    "contact us.</p>"
    "<p>We look forward to receiving your confirmation and proceeding with the Go-Live.</p>"
    + SIGNATURE,
}
DEFAULT_MAILS = {"Training": TRAINING_MAIL, "UAT": UAT_MAIL}

# Seeded on install and by a patch, only when a template of that name is missing,
# so a site's own edits are never overwritten.
DEFAULT_TEMPLATES = (
    {
        "template_name": "Accounts",
        "module": "Accounts",
        "project_type": "ERP Implementation",
        "mail": TRAINING_MAIL,
        "description": "Selling, buying, payments and the core accounting reports.",
        "sections": (
            (
                "Sales",
                (
                    "I can create a Quotation, convert it to a Sales Order and then to a Sales Invoice.",
                    "I can create a Sales Invoice directly, with the right customer, items, taxes and due date.",
                    "I can make a Credit Note (sales return) against an invoice.",
                    "I can add a new Customer with its billing address and tax details.",
                    "I can find unpaid sales invoices and see which are overdue.",
                ),
            ),
            (
                "Purchase",
                (
                    "I can create a Purchase Order and convert it to a Purchase Invoice.",
                    "I can record a supplier's bill as a Purchase Invoice with the right taxes.",
                    "I can make a Debit Note (purchase return) against a supplier invoice.",
                    "I can add a new Supplier with its address and tax details.",
                ),
            ),
            (
                "Payments",
                (
                    "I can record a Payment Entry against a sales invoice (money received).",
                    "I can record a Payment Entry against a purchase invoice (money paid).",
                    "I can record an advance payment and allocate it to an invoice later.",
                    "I can make a Journal Entry for expenses, adjustments or bank transfers.",
                    "I can reconcile the bank statement with the payments in the system.",
                ),
            ),
            (
                "Reports",
                (
                    (
                        "I can read the Accounts Receivable and Accounts Payable reports.",
                        "Who owes us, whom we owe, and how old each amount is.",
                    ),
                    "I can open the General Ledger for an account, customer or supplier.",
                    "I can run the Trial Balance, Profit and Loss and Balance Sheet for a period.",
                    "I can run the tax (GST / VAT) report for a month.",
                ),
            ),
        ),
    },
    {
        "template_name": "Stock / Inventory",
        "module": "Stock",
        "project_type": "ERP Implementation",
        "mail": TRAINING_MAIL,
        "description": "Items, warehouses, stock movements and the stock reports.",
        "sections": (
            (
                "Items and warehouses",
                (
                    "I can create a new Item with its unit of measure, item group and prices.",
                    "I can create a Warehouse and know which warehouse each kind of stock is kept in.",
                    "I can set an item's reorder level so the system suggests purchases.",
                    "I can maintain batch or serial numbers for the items that need them.",
                ),
            ),
            (
                "Stock movements",
                (
                    "I can make a Stock Entry to move stock from one warehouse to another.",
                    "I can make a Stock Entry for material issued or received without a purchase or sale.",
                    "I can make a Stock Reconciliation to correct quantities after a physical count.",
                    "I can check the stock of an item in every warehouse before promising it to a customer.",
                ),
            ),
            (
                "Receipts and deliveries",
                (
                    "I can make a Purchase Receipt when goods arrive against a Purchase Order.",
                    "I can make a Delivery Note when goods leave against a Sales Order.",
                    "I can handle a return of goods from a customer or to a supplier.",
                    "I can see which orders are still waiting to be received or delivered.",
                ),
            ),
            (
                "Stock reports",
                (
                    "I can read the Stock Balance report for a warehouse and a date.",
                    "I can read the Stock Ledger to see every movement of an item.",
                    "I can read the Stock Ageing report to find slow-moving stock.",
                    "I can see the stock value as it appears in the accounts.",
                ),
            ),
        ),
    },
    {
        "template_name": "HR & Payroll",
        "module": "HR & Payroll",
        "project_type": "ERP Implementation",
        "mail": TRAINING_MAIL,
        "description": "Employee records, attendance, leave and the monthly payroll.",
        "sections": (
            (
                "Employees",
                (
                    "I can add a new Employee with joining date, department, designation and reporting manager.",
                    "I can update an employee's details, such as a promotion or transfer.",
                    "I can record an employee leaving, with the relieving date.",
                    "I can find any employee's documents and personal details.",
                ),
            ),
            (
                "Attendance and leave",
                (
                    "I can mark attendance for a day, or upload it for a month.",
                    "I can set up Leave Types and allocate leave to employees for the year.",
                    "I can approve or reject a Leave Application.",
                    "I can see an employee's leave balance.",
                    "I can maintain the holiday list for the year.",
                ),
            ),
            (
                "Payroll",
                (
                    "I can create Salary Components (earnings and deductions).",
                    "I can create a Salary Structure and assign it to employees.",
                    "I can run the monthly payroll with a Payroll Entry.",
                    "I can review, correct and submit Salary Slips, and email them to employees.",
                    "I can read the Salary Register and the statutory deduction reports.",
                ),
            ),
        ),
    },
    {
        "template_name": "UAT Sign-off",
        "module": "",
        "description": "Asks the client to accept the UAT; the tests come from the SRS.",
        "signoff_type": "UAT",
        "project_type": "ERP Implementation",
        "sections": (),
        "mail": UAT_MAIL,
    },
    {
        "template_name": "UAT Sign-off and Go-Live",
        "module": "",
        "description": "Asks the client to accept the UAT and approve moving to the live server.",
        "signoff_type": "UAT",
        "project_type": "ERP Implementation",
        "sections": (),
        "mail": UAT_GO_LIVE_MAIL,
    },
)


def ensure_default_signoff_templates() -> list[str]:
    """Add the default templates a site doesn't have yet; returns the ones added."""
    added = []
    for template in DEFAULT_TEMPLATES:
        if frappe.db.exists("HD Signoff Template", template["template_name"]):
            continue
        frappe.get_doc(
            {
                "doctype": "HD Signoff Template",
                "template_name": template["template_name"],
                "module": template["module"],
                "description": template["description"],
                "signoff_type": template.get("signoff_type", "Training"),
                "project_type": template.get("project_type"),
                "email_subject": template["mail"]["subject"],
                "email_body": template["mail"]["body"],
                "is_active": 1,
                "items": [
                    {"section": section, **seed_question(question)}
                    for section, questions in template["sections"]
                    for question in questions
                ],
            }
        ).insert(ignore_permissions=True)
        added.append(template["template_name"])
    return added


def seed_question(question: str | tuple[str, str]) -> dict:
    """A seed question is its text, or (text, help text)."""
    text, help_text = (question, "") if isinstance(question, str) else question
    return {"question": text, "help_text": help_text}
