import frappe

from helpdesk.ai_engine import OPENAI_SLOT, ensure_model_pricing

SETTINGS = "HDS Hub Settings"
FIELDS = ("primary_ai_provider", "ai_failover", "openai_base_url", "openai_model")


def execute():
    """OpenAI as the primary provider with failover (docs/ai-providers.md).

    A Single's field defaults only apply to new sites, so the new fields get their
    doctype defaults here where they were never saved. Keys are never touched: until
    an OpenAI key is entered, the Anthropic-compatible provider keeps answering.
    """
    meta = frappe.get_meta(SETTINGS)
    Singles = frappe.qb.DocType("Singles")
    saved = dict(
        frappe.qb.from_(Singles)
        .select(Singles.field, Singles.value)
        .where(Singles.doctype == SETTINGS)
        .where(Singles.field.isin(FIELDS))
        .run()
    )
    for fieldname in FIELDS:
        if saved.get(fieldname) in (None, ""):
            frappe.db.set_single_value(
                SETTINGS, fieldname, meta.get_field(fieldname).default
            )
    ensure_model_pricing(
        frappe.db.get_single_value(SETTINGS, "openai_model"), OPENAI_SLOT
    )
