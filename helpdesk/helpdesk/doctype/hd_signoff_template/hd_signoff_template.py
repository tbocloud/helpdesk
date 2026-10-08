# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""A training sign-off questionnaire for one module (Accounts, Stock, HR...).

Each question is copied into a sign-off when it is created, so editing a
template never changes a sign-off already sent. See docs/project-signoff.md.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class HDSignoffTemplate(Document):
    def validate(self):
        self.clean_items()
        self.validate_items()

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
        if self.is_active and not self.items:
            frappe.throw(_("Add at least one question, or make the template inactive."))


# Seeded on install and by a patch, only when a template of that name is missing,
# so a site's own edits are never overwritten.
DEFAULT_TEMPLATES = (
    {
        "template_name": "Accounts",
        "module": "Accounts",
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
