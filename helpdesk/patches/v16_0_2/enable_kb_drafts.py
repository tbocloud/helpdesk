import frappe


def execute():
    """Turn KB drafts from resolved tickets on for existing sites; a new Check
    field's default only applies to new documents."""
    frappe.db.set_single_value("HDS Hub Settings", "draft_kb_articles", 1)
