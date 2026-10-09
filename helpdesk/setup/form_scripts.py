"""The HD Form Scripts this app ships for the ticket page, installed on install and on every migrate."""

import os

import frappe

FORM_SCRIPTS = {
    "Helpdesk AI Support Actions": "ai_support_actions.js",
    "Helpdesk Copilot Actions": "copilot_actions.js",
}


def install_form_scripts():
    for name, file_name in FORM_SCRIPTS.items():
        _install(name, file_name)
    frappe.db.commit()  # migration step - nosemgrep


def _install(name: str, file_name: str):
    js_path = os.path.join(os.path.dirname(__file__), "..", "hd_form_scripts", file_name)
    if not os.path.exists(js_path):
        frappe.log_error("HD Form Script JS not found", js_path)
        return

    with open(js_path) as f:  # path is this app's own bundled file - nosemgrep
        script_content = f.read()

    if frappe.db.exists("HD Form Script", name):
        doc = frappe.get_doc("HD Form Script", name)
        doc.script = script_content
        doc.enabled = 1
        doc.save(ignore_permissions=True)
        print(f"Updated HD Form Script: {name}")
    else:
        doc = frappe.get_doc(
            {
                "doctype": "HD Form Script",
                "name": name,
                "dt": "HD Ticket",
                "apply_to": "Form",
                "enabled": 1,
                "script": script_content,
            }
        )
        doc.insert(ignore_permissions=True)
        print(f"Created HD Form Script: {name}")
