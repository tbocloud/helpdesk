# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""A sign-off template: the stage of a project it is for (TBO's Sign-off requirements: an SRS,
a module's training, UAT, go-live, handover, a month of digital marketing...), the mail that
asks the customer to accept it, the declaration printed on the document, and (optionally) the
questions the customer answers on the questions page.

The stage decides which details a sign-off shows and needs (STAGES). Everything is copied into
a sign-off when it is created, so editing a template never changes a sign-off already sent. See
docs/project-signoff.md.
"""

import frappe
from frappe import _
from frappe.model.document import Document

ERPNEXT = "ERP Implementation"
DIGITAL_MARKETING = "Digital Marketing"
TRAINING_STAGE = "Module Training Sign-off"
UAT_STAGES = ("UAT Sign-off", "UAT Sign-off and Go-Live")

# The parts of a sign-off's details and document, and the fields each holds (a table's field is
# a child table). Shared by the controller, the API and the forms (get_signoff_form sends them).
SECTIONS = {
    "environment": ("uat_site_url", "live_site_url", "erpnext_version"),
    "requirement": ("srs_reference", "srs_version", "srs_date"),
    "modules": ("modules",),
    "uat": ("uat_start_date", "uat_end_date", "issues_raised", "issues_resolved"),
    "open_items": ("open_items",),
    "training": ("training_date", "trainer", "attendees"),
    "migration": ("masters_migrated", "opening_balances_migrated", "migration_remarks"),
    "go_live": ("go_live_date",),
    "support": ("support_start_date", "support_end_date", "support_channel"),
    "engagement": ("services", "platforms"),
    "period": ("period_from", "period_to"),
    "deliverables": ("deliverables",),
    "performance": (
        "reach",
        "impressions",
        "engagement_rate",
        "followers_gained",
        "website_visits",
        "leads",
        "performance_summary",
    ),
    "ad_spend": ("approved_budget", "actual_spend", "billed_through"),
    "carry_forward": ("carry_forward",),
    "next_plan": ("next_period_plan",),
    "website": ("live_site_url", "go_live_date", "pages_delivered"),
    "attachments": ("delivery_report",),
}

# Each stage of TBO's Sign-off requirements (Template list, the documents' "Shown for"):
# the project type it belongs to, the sections it shows, what must be filled before it is sent,
# and the details the New sign-off dialog asks for (the rest are on the full page).
STAGES = {
    "SRS / Requirement Sign-off": {
        "project_type": ERPNEXT,
        "sections": ("requirement",),
        "required": ("srs_version", "srs_date"),
        "dialog": ("srs_version", "srs_date"),
    },
    TRAINING_STAGE: {
        "project_type": ERPNEXT,
        "sections": ("modules", "training"),
        "required": ("modules", "training_date", "trainer"),
        "dialog": ("modules", "training_date", "trainer"),
    },
    "UAT Sign-off": {
        "project_type": ERPNEXT,
        "sections": ("environment", "requirement", "modules", "uat", "open_items"),
        "required": ("modules", "uat_site_url"),
        "dialog": ("modules", "uat_site_url"),
    },
    "UAT Sign-off and Go-Live": {
        "project_type": ERPNEXT,
        "sections": (
            "environment",
            "requirement",
            "modules",
            "uat",
            "open_items",
            "go_live",
            "support",
        ),
        "required": ("modules", "uat_site_url", "go_live_date"),
        "dialog": ("modules", "go_live_date"),
    },
    "Go-Live Confirmation": {
        "project_type": ERPNEXT,
        "sections": ("environment", "migration", "go_live", "support"),
        "required": (
            "go_live_date",
            "live_site_url",
            "support_start_date",
            "support_end_date",
        ),
        "dialog": ("go_live_date", "live_site_url"),
    },
    "Project Completion / Handover": {
        "project_type": ERPNEXT,
        "sections": ("modules", "open_items", "support"),
        "required": ("support_end_date",),
        "dialog": ("support_end_date",),
    },
    "Content Calendar / Strategy Approval": {
        "project_type": DIGITAL_MARKETING,
        "sections": ("engagement", "period", "next_plan"),
        "required": ("services", "period_from", "period_to"),
        "dialog": ("services", "period_from", "period_to"),
    },
    "Monthly Deliverables Sign-off": {
        "project_type": DIGITAL_MARKETING,
        # ad spend only when Paid Ads is one of the services (HDProjectSignoff.shown_sections)
        "sections": (
            "engagement",
            "period",
            "deliverables",
            "performance",
            "ad_spend",
            "carry_forward",
            "next_plan",
            "attachments",
        ),
        "required": ("services", "period_from", "period_to"),
        "dialog": ("services", "period_from", "period_to"),
    },
    "Campaign Completion Sign-off": {
        "project_type": DIGITAL_MARKETING,
        "sections": (
            "engagement",
            "period",
            "deliverables",
            "performance",
            "ad_spend",
            "attachments",
        ),
        "required": ("period_from", "period_to"),
        "dialog": ("services", "period_from", "period_to"),
    },
    "Website / Landing Page Go-Live": {
        "project_type": DIGITAL_MARKETING,
        "sections": ("engagement", "website"),
        "required": ("live_site_url", "go_live_date"),
        "dialog": ("live_site_url", "go_live_date"),
    },
}
# a stage-less sign-off (made before stages): a training's questions, or a UAT's tests
LEGACY_SECTIONS = ("training",)

# ERPNext's modules, for "Modules covered" (the requirements: a multi-select of ERPNext modules)
ERPNEXT_MODULES = (
    "Accounts",
    "Selling",
    "Buying",
    "Stock",
    "Manufacturing",
    "Projects",
    "CRM",
    "Assets",
    "Quality",
    "Support",
    "HR",
    "Payroll",
    "Website",
    "Setup",
)

# Services and platforms a digital marketing sign-off picks from (the requirements)
SERVICES = ("Social Media", "SEO", "Paid Ads", "Content", "Website", "Email Marketing")
PLATFORMS = ("Instagram", "Facebook", "LinkedIn", "YouTube", "Google")
PAID_ADS = "Paid Ads"


class HDSignoffTemplate(Document):
    def validate(self):
        self.clean_items()
        self.validate_stage()
        self.validate_default_cc()

    def clean_items(self):
        """Blank rows are dropped; text is trimmed. Questions are optional: a sign-off is
        accepted by replying to its mail."""
        rows = []
        for row in self.items:
            row.section = (row.section or "").strip()
            row.question = (row.question or "").strip()
            row.help_text = (row.help_text or "").strip()
            if row.question:
                rows.append(row)
        self.items = rows

    def validate_stage(self):
        """A UAT template (its tests from the SRS) is for a UAT stage."""
        if self.signoff_type == "UAT" and self.stage and self.stage not in UAT_STAGES:
            frappe.throw(_("A UAT template is for a UAT stage."))

    def validate_default_cc(self):
        from helpdesk.helpdesk.doctype.hd_project_signoff.hd_project_signoff import (
            HDProjectSignoff,
        )

        self.default_cc = ", ".join(HDProjectSignoff.clean_emails(self.default_cc))


# The mails of TBO's Sign-off requirements (Seed template content): the customer accepts by
# replying. Data, like a template's own mail, so not translated.
SIGNATURE = "<p>Regards,<br>{{ sender_name }}<br>{{ sender_designation }}<br>{{ company_name }}</p>"
GREETING = "<p>Dear {{ contact_salutation }} {{ contact_name }},</p><p>I hope you are doing well.</p>"
QUESTIONS = (
    "If you have any questions or require further clarification, please feel free to "
    "contact us."
)


def _mail(subject: str, *paragraphs: str) -> dict:
    return {
        "subject": subject,
        "body": GREETING + "".join(f"<p>{p}</p>" for p in paragraphs) + SIGNATURE,
    }


SRS_MAIL = _mail(
    "SRS Sign-off – {{ project_name }}",
    "As discussed, please find attached the Software Requirements Specification for "
    "{{ project_name }}, which captures the scope agreed with your team.",
    "This email serves as the official request for SRS sign-off. We kindly request you to "
    "review the document and confirm by replying to this email with your formal sign-off, so "
    "that the scope is frozen and we can begin development.",
    "Any change after sign-off will be handled as a change request.",
    QUESTIONS,
)
TRAINING_MAIL = _mail(
    "Training Sign-off – {{ modules }} – {{ project_name }}",
    "We have completed the training on the {{ modules }} module(s) on {{ training_date }}, "
    "conducted by {{ trainer_name }}.",
    "We kindly request you to confirm that the training has been completed to your "
    "satisfaction, either by replying to this email or by completing the short sign-off form "
    "here: {{ sign_off_link }}",
    "If any topic needs to be covered again, please let us know and we will arrange a session.",
)
UAT_MAIL = _mail(
    "UAT Sign-off Request – {{ project_name }}",
    "As agreed, we have completed the {{ project_name }} ERPNext {{ erpnext_version }} "
    "implementation on the UAT site ({{ uat_site_url }}), covering the following modules: "
    "{{ modules }}.",
    "This email serves as the official request for UAT sign-off. We kindly request you to "
    "review the completed implementation and confirm your acceptance by replying to this email "
    "with your formal sign-off. The sign-off document is attached for your reference.",
    "Once we receive your confirmation, we will share the plan for the Go-Live.",
    QUESTIONS,
)
UAT_GO_LIVE_MAIL = _mail(
    "UAT Sign-off and Go-Live Confirmation – {{ project_name }}",
    "As agreed, we have completed the {{ project_name }} ERPNext {{ erpnext_version }} "
    "implementation on the UAT site, covering the requirements outlined in the SRS and the "
    "concerns raised by your team.",
    "This email serves as the official request for UAT sign-off and confirmation to proceed "
    "with the Go-Live process. We kindly request you to review and confirm your acceptance of "
    "the completed implementation by replying to this email with your formal sign-off.",
    "As agreed, we will continue to provide support throughout the agreed support period. Upon "
    "receiving your confirmation, we will proceed with the necessary activities to deploy the "
    "completed setup to your live server at the earliest.",
    QUESTIONS,
    "We look forward to receiving your confirmation and proceeding with the Go-Live.",
)
GO_LIVE_MAIL = _mail(
    "Go-Live Confirmation – {{ project_name }}",
    "We are pleased to inform you that the {{ project_name }} setup has been deployed to your "
    "live server ({{ live_site_url }}) on {{ go_live_date }}.",
    "We kindly request you to confirm that the live system is working as expected by replying "
    "to this email with your formal confirmation.",
    "As agreed, our support period runs from {{ support_start_date }} to "
    "{{ support_end_date }}. Please reach out to us for any issues during this period.",
)
COMPLETION_MAIL = _mail(
    "Project Completion and Handover – {{ project_name }}",
    "The agreed support period for {{ project_name }} ended on {{ support_end_date }}. Please "
    "find attached the handover document with the modules delivered and any pending items.",
    "We kindly request you to confirm the completion and handover of the project by replying "
    "to this email with your formal sign-off.",
    "Thank you for your trust in us. We look forward to supporting you in the future.",
)
CONTENT_CALENDAR_MAIL = _mail(
    "Content Calendar Approval – {{ project_name }} – {{ period_from }} to {{ period_to }}",
    "Please find attached the content calendar and strategy for {{ period_from }} to "
    "{{ period_to }}, covering the {{ services }} services agreed with your team.",
    "We kindly request you to review the plan and approve it by replying to this email, so we "
    "can start the work on time. Any changes you share will be reflected in the calendar.",
    QUESTIONS,
)
MONTHLY_MAIL = {
    "subject": "Monthly Deliverables Sign-off – {{ project_name }} – {{ period_from }} to "
    "{{ period_to }}",
    "body": GREETING
    + "<p>Please find attached the delivery report for {{ period_from }} to {{ period_to }}, "
    "covering the {{ services }} deliverables agreed in the content calendar.</p>"
    "<p>We kindly request you to review the report and confirm your acceptance of the listed "
    "deliverables by replying to this email. Any feedback you share will be taken up in the "
    "next cycle.</p>"
    "<p>If you have any questions, please feel free to contact us.</p>" + SIGNATURE,
}
CAMPAIGN_MAIL = _mail(
    "Campaign Completion Sign-off – {{ project_name }} – {{ period_from }} to {{ period_to }}",
    "The campaign that ran from {{ period_from }} to {{ period_to }} has ended. Please find "
    "attached the completion report with the deliverables, the budget and spend, and the "
    "results.",
    "We kindly request you to review the report and confirm your acceptance by replying to "
    "this email.",
    QUESTIONS,
)
WEBSITE_MAIL = _mail(
    "Website Go-Live Confirmation – {{ project_name }}",
    "We are pleased to inform you that the website / landing page for {{ project_name }} went "
    "live at {{ live_site_url }} on {{ go_live_date }}.",
    "We kindly request you to review it and confirm by replying to this email with your formal "
    "sign-off.",
    QUESTIONS,
)
DEFAULT_MAILS = {"Training": TRAINING_MAIL, "UAT": UAT_MAIL}

# What the customer declares on the document (TBO's Sign-off requirements, Declaration)
DECLARATIONS = {
    "SRS / Requirement Sign-off": "We confirm that the requirements in the SRS referenced "
    "above are complete and correct, and we approve them as the scope of the project.",
    TRAINING_STAGE: "We confirm that the training on the modules listed above has been "
    "completed to our satisfaction.",
    "UAT Sign-off": "We confirm that the ERPNext implementation for the modules listed above "
    "has been reviewed on the UAT site and meets the requirements in the SRS, subject to the "
    "open items listed.",
    "UAT Sign-off and Go-Live": "We confirm that the ERPNext implementation for the modules "
    "listed above has been reviewed on the UAT site and meets the requirements in the SRS, "
    "subject to the open items listed. We approve proceeding to Go-Live.",
    "Go-Live Confirmation": "We confirm that the system has been deployed to the live server "
    "stated above and is working as expected.",
    "Project Completion / Handover": "We confirm that the project has been completed and "
    "handed over to us, subject to the pending items listed.",
    "Content Calendar / Strategy Approval": "We approve the content calendar and strategy for "
    "the period stated above.",
    "Monthly Deliverables Sign-off": "We confirm receipt and acceptance of the deliverables "
    "listed above for the period stated, subject to the carry-forward items noted.",
    "Campaign Completion Sign-off": "We confirm that the campaign stated above has been "
    "completed and accept the deliverables, the spend and the results reported.",
    "Website / Landing Page Go-Live": "We confirm that the website / landing page stated above "
    "has gone live and is accepted.",
}


def _stage_template(name: str, mail: dict, description: str, **extra) -> dict:
    """One of the ten templates of TBO's Sign-off requirements: its stage is its name."""
    return {
        "template_name": name,
        "module": "",
        "stage": name,
        "project_type": STAGES[name]["project_type"],
        "description": description,
        "mail": mail,
        "sections": (),
        **extra,
    }


# Seeded on install and by patches, only when a template of that name is missing, so a site's
# own edits are never overwritten. The ten of the requirements, then the training question sets.
DEFAULT_TEMPLATES = (
    _stage_template(
        "SRS / Requirement Sign-off",
        SRS_MAIL,
        "The SRS is final and the scope must be frozen before development.",
    ),
    _stage_template(
        TRAINING_STAGE,
        TRAINING_MAIL,
        "Training on one or more modules is done.",
    ),
    _stage_template(
        "UAT Sign-off",
        UAT_MAIL,
        "UAT is complete; only acceptance is requested. Its tests come from the SRS.",
        signoff_type="UAT",
    ),
    _stage_template(
        "UAT Sign-off and Go-Live",
        UAT_GO_LIVE_MAIL,
        "UAT is accepted and approval to move to live is requested.",
        signoff_type="UAT",
    ),
    _stage_template(
        "Go-Live Confirmation",
        GO_LIVE_MAIL,
        "The setup is deployed on the live server.",
    ),
    _stage_template(
        "Project Completion / Handover",
        COMPLETION_MAIL,
        "The support period has ended; final closure.",
    ),
    _stage_template(
        "Content Calendar / Strategy Approval",
        CONTENT_CALENDAR_MAIL,
        "Before a month or a campaign starts.",
    ),
    _stage_template(
        "Monthly Deliverables Sign-off",
        MONTHLY_MAIL,
        "Month end: the deliverables and the report to be accepted.",
    ),
    _stage_template(
        "Campaign Completion Sign-off",
        CAMPAIGN_MAIL,
        "A paid or seasonal campaign has ended.",
    ),
    _stage_template(
        "Website / Landing Page Go-Live",
        WEBSITE_MAIL,
        "A site or landing page has been launched.",
    ),
    {
        "template_name": "Accounts",
        "module": "Accounts",
        "project_type": "ERP Implementation",
        "mail": TRAINING_MAIL,
        "stage": TRAINING_STAGE,
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
        "stage": TRAINING_STAGE,
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
        "stage": TRAINING_STAGE,
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
        stage = template.get("stage")
        frappe.get_doc(
            {
                "doctype": "HD Signoff Template",
                "template_name": template["template_name"],
                "module": template["module"],
                "description": template["description"],
                "signoff_type": template.get("signoff_type", "Training"),
                "stage": stage,
                "project_type": template.get("project_type"),
                "email_subject": template["mail"]["subject"],
                "email_body": template["mail"]["body"],
                "declaration_text": DECLARATIONS.get(stage),
                "attach_pdf_default": 1,
                "print_format": print_format_for(stage),
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


def print_format_for(stage: str | None) -> str | None:
    """The requirements' print format for a stage's project type, when the site has it."""
    from helpdesk.helpdesk.doctype.hd_project_signoff.hd_project_signoff import (
        PRINT_FORMATS,
    )

    kind = STAGES.get(stage or "", {}).get("project_type", ERPNEXT)
    name = PRINT_FORMATS[kind]
    return name if frappe.db.exists("Print Format", name) else None


def seed_question(question: str | tuple[str, str]) -> dict:
    """A seed question is its text, or (text, help text)."""
    text, help_text = (question, "") if isinstance(question, str) else question
    return {"question": text, "help_text": help_text}
