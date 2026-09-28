import frappe


def execute():
	"""Pin connections that predate `client_app` to the legacy client app.

	The hub used to hardcode `qcs_support_client`; new connections default to
	`helpdesk_client`. This runs once, so every connection that exists now was
	set up against the legacy app and keeps working.
	"""
	frappe.reload_doc("helpdesk", "doctype", "hds_support_connection")
	frappe.db.sql("update `tabHDS Support Connection` set client_app = 'qcs_support_client'")
