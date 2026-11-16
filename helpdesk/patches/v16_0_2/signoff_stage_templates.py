"""TBO's Sign-off requirements' templates (docs/project-signoff.md, Templates shipped): the ten
are added where missing; the ones a site already has get their stage, declaration and print
format; and a template still carrying the earlier seeded mail (which asked the customer to sign
on the page) gets the requirements' mail, which asks them to reply. A mail a site changed is
left alone."""

import frappe

from helpdesk.helpdesk.doctype.hd_signoff_template.hd_signoff_template import (
    DECLARATIONS,
    TRAINING_MAIL,
    TRAINING_STAGE,
    UAT_GO_LIVE_MAIL,
    UAT_MAIL,
    ensure_default_signoff_templates,
    print_format_for,
)

# the earlier seeded mails, as they were
OLD_SIGNATURE = "<p>Regards,<br>{{ sender_name }}<br>{{ sender_designation }}<br>{{ company_name }}</p>"
OLD_TRAINING_MAIL = {
    "subject": "Training Sign-off – {{ modules }} – {{ project_name }}",
    "body": "<p>Dear {{ contact_salutation }} {{ contact_name }},</p>"
    "<p>I hope you are doing well.</p>"
    "<p>We have completed the training on the {{ modules }} module(s) on {{ training_date }}, "
    "conducted by {{ trainer_name }}.</p>"
    "<p>We kindly request you to confirm that the training has been completed to your "
    "satisfaction by completing the short sign-off form here: {{ sign_off_link }}</p>"
    "<p>If any topic needs to be covered again, please let us know and we will arrange a "
    "session.</p>" + OLD_SIGNATURE,
}

OLD_UAT_MAIL = {
    "subject": "UAT Sign-off Request – {{ project_name }}",
    "body": "<p>Dear {{ contact_salutation }} {{ contact_name }},</p>"
    "<p>I hope you are doing well.</p>"
    "<p>As agreed, we have completed the {{ project_name }} implementation on the UAT site, "
    "covering the following modules: {{ modules }}.</p>"
    "<p>This email serves as the official request for UAT sign-off. We kindly request you to "
    "run each test on the sign-off page and confirm your acceptance there: {{ sign_off_link }}</p>"
    "<p>Once we receive your confirmation, we will share the plan for the Go-Live.</p>"
    "<p>If you have any questions or require further clarification, please feel free to "
    "contact us.</p>" + OLD_SIGNATURE,
}
OLD_UAT_GO_LIVE_MAIL = {
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
    + OLD_SIGNATURE,
}

STAGES_OF_EARLIER_SEEDS = {
    "Accounts": TRAINING_STAGE,
    "Stock / Inventory": TRAINING_STAGE,
    "HR & Payroll": TRAINING_STAGE,
    "UAT Sign-off": "UAT Sign-off",
    "UAT Sign-off and Go-Live": "UAT Sign-off and Go-Live",
}
NEW_MAILS = (
    (OLD_TRAINING_MAIL, TRAINING_MAIL),
    (OLD_UAT_MAIL, UAT_MAIL),
    (OLD_UAT_GO_LIVE_MAIL, UAT_GO_LIVE_MAIL),
)


def execute():
    frappe.reload_doc("helpdesk", "doctype", "hd_signoff_template")
    for name, stage in STAGES_OF_EARLIER_SEEDS.items():
        if not frappe.db.exists("HD Signoff Template", name):
            continue
        doc = frappe.get_doc("HD Signoff Template", name)
        doc.stage = doc.stage or stage
        doc.declaration_text = doc.declaration_text or DECLARATIONS.get(doc.stage)
        doc.print_format = doc.print_format or print_format_for(doc.stage)
        for old, new in NEW_MAILS:
            if (doc.email_subject, doc.email_body) == (old["subject"], old["body"]):
                doc.email_subject, doc.email_body = new["subject"], new["body"]
        doc.save(ignore_permissions=True)
    ensure_default_signoff_templates()
