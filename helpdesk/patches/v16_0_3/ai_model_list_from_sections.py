import frappe

from helpdesk import ai_engine

PRICING = "HDS Model Pricing"


def execute():
    """AI models (Phase 31): the model list starts with the models today's two sections use,
    allowed for jobs and called through their section. No job gets a model of its own, so
    every job keeps working as before."""
    if not frappe.db.has_column(PRICING, "ai_provider"):
        return
    settings = frappe.get_single("HDS Hub Settings")
    jobs = settings.get("ai_jobs") or []
    found = {
        ai_engine.OPENAI_SLOT: [settings.openai_model, *(r.openai_model for r in jobs)],
        ai_engine.ANTHROPIC_SLOT: [
            settings.default_triage_model,
            *(r.anthropic_model for r in jobs),
        ],
    }
    for section, models in found.items():
        for model in sorted({(m or "").strip() for m in models} - {""}):
            ai_engine.ensure_model_pricing(model, section)
            if not frappe.db.get_value(PRICING, model, "ai_provider"):
                frappe.db.set_value(
                    PRICING,
                    model,
                    {"ai_provider": section, "listed": 1},
                    update_modified=False,
                )
