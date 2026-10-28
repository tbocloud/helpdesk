# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""HDS Copilot Settings: the knobs every Copilot module reads."""

import frappe
from frappe import _

DEFAULT_MCP_CALLS_PER_MINUTE = 120

# the stages a customer sees on their own ticket, in the order they usually happen
STAGES = (
    "Received",
    "Working on it",
    "Fix scheduled",
    "Resolved",
    "With our team",
    "Waiting for you",
)

# used when the settings have no row (or an empty one) for a stage
DEFAULT_TEMPLATES = {
    "Received": "We have received your ticket and are looking at it.",
    "Working on it": "We found what is happening and are working on it. We will update you here.",
    "Fix scheduled": "A fix is ready and will go live on {date}.",
    "Resolved": "{resolution} Please confirm this solved it, or reopen the ticket if not.",
    "With our team": "A TBO engineer is looking at this personally.",
    "Waiting for you": "We need some information from you; please see our reply.",
}

# a build of an approved customization (Phase 8) tells the customer about their change
BUILD_TEMPLATES = {
    "Working on it": "We are building the change you approved. We will update you here.",
    "Fix scheduled": "Your change is ready and will go live on {date}.",
    "Resolved": "Your change is live. {resolution} Please check it, then confirm, or reopen the ticket if it is not what you approved.",
}

# a chat with an Arabic-speaking customer (Phase 5): the same stages in Arabic, unless a settings row says otherwise
ARABIC_TEMPLATES = {
    "Received": "استلمنا طلبك ونعمل على دراسته.",
    "Working on it": "وجدنا سبب المشكلة ونعمل على حلها. سنوافيك بالتحديثات هنا.",
    "Fix scheduled": "الإصلاح جاهز وسيتم تفعيله في {date}.",
    "Resolved": "{resolution} يرجى تأكيد أن المشكلة قد حُلّت، أو إعادة فتح التذكرة إن لم تُحل.",
    "With our team": "أحد مهندسي TBO يتابع طلبك شخصيًا.",
    "Waiting for you": "نحتاج بعض المعلومات منك؛ يرجى الاطلاع على ردنا.",
}
ARABIC_BUILD_TEMPLATES = {
    "Working on it": "نعمل على تنفيذ التعديل الذي وافقت عليه. سنوافيك بالتحديثات هنا.",
    "Fix scheduled": "التعديل جاهز وسيتم تفعيله في {date}.",
    "Resolved": "أصبح التعديل متاحًا. {resolution} يرجى التحقق منه ثم التأكيد، أو إعادة فتح التذكرة إن لم يكن كما وافقت عليه.",
}
LANGUAGE_ROWS = {"en": ("", None), "ar": ("Arabic",)}


def get_settings():
    return frappe.get_cached_doc("HDS Copilot Settings")


def is_enabled() -> bool:
    return bool(get_settings().enabled)


def is_shadow() -> bool:
    """Shadow mode: Copilot's findings stay with the team; the customer hears nothing from Copilot."""
    return bool(get_settings().shadow_mode)


# a customer's Copilot level (HD Customer), each one allowing what the ones before it do
DIAGNOSE, EXPLAIN, FIX, CORRECT = LEVELS = (
    "Diagnose only",
    "Explain",
    "Fix",
    "Correct",
)


def level_of(customer: str | None) -> str:
    """How far Copilot may go for the customer: their level, else the default; shadow mode
    holds everyone at Diagnose only, and so does a ticket with no customer."""
    if is_shadow() or not customer:
        return DIAGNOSE
    level = frappe.db.get_value("HD Customer", customer, "custom_copilot_level")
    if level not in LEVELS:
        level = get_settings().get("default_copilot_level")
    return level if level in LEVELS else DIAGNOSE


def allows(customer: str | None, level: str) -> bool:
    """Whether the customer's level reaches `level`."""
    return LEVELS.index(level_of(customer)) >= LEVELS.index(level)


def template_for(stage: str, build: bool = False, language: str = "en") -> str:
    """The message text for a stage: a build's own text, else the configured row in the language,
    else the built-in text (English, or Arabic for an Arabic-speaking customer's chat)."""
    if stage not in STAGES:
        raise ValueError(f"Unknown Copilot stage: {stage}")
    arabic = language == "ar"
    if build and stage in BUILD_TEMPLATES:
        return (ARABIC_BUILD_TEMPLATES if arabic else BUILD_TEMPLATES)[stage]
    for row in get_settings().message_templates:
        if (
            row.stage == stage
            and (row.get("language") or "") in LANGUAGE_ROWS["ar" if arabic else "en"]
            and (row.message or "").strip()
        ):
            return row.message.strip()
    return (ARABIC_TEMPLATES if arabic else DEFAULT_TEMPLATES)[stage]


def seed_default_templates(settings) -> None:
    """Appends a row with the built-in text for every stage the settings don't have yet."""
    present = {
        row.stage for row in settings.message_templates if not row.get("language")
    }
    for stage in STAGES:
        if stage not in present:
            settings.append(
                "message_templates",
                {"stage": stage, "message": DEFAULT_TEMPLATES[stage]},
            )


def validate_limits(settings) -> None:
    if (settings.lease_minutes or 0) < 1:
        frappe.throw(_("Lease minutes must be at least 1"))
    if (settings.max_lease_losses or 0) < 1:
        frappe.throw(_("Max lease losses must be at least 1"))
    if not 0 <= (settings.min_confidence or 0) <= 1:
        frappe.throw(_("Min confidence must be between 0 and 1"))
    if not settings.mcp_calls_per_minute:
        settings.mcp_calls_per_minute = DEFAULT_MCP_CALLS_PER_MINUTE
    if settings.mcp_calls_per_minute < 1:
        frappe.throw(_("MCP calls per minute must be at least 1"))
