import frappe

# the statuses before TBO's Sign-off requirements, and what each is now
# (docs/project-signoff.md, Statuses)
NEW_STATUS = {
    "Signed": "Signed Off",
    "Reopened": "Changes Requested",
    "In progress": "Sent",
    "Needs clarification": "Sent",
    "Ready to sign": "Sent",
}


def execute():
    for old, new in NEW_STATUS.items():
        frappe.db.set_value(
            "HD Project Signoff",
            {"status": old},
            "status",
            new,
            update_modified=False,
        )
