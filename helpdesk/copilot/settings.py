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


def get_settings():
    return frappe.get_cached_doc("HDS Copilot Settings")


def is_enabled() -> bool:
    return bool(get_settings().enabled)


def template_for(stage: str) -> str:
    """The message text for a stage: the configured row, else the built-in text."""
    if stage not in STAGES:
        raise ValueError(f"Unknown Copilot stage: {stage}")
    for row in get_settings().message_templates:
        if row.stage == stage and (row.message or "").strip():
            return row.message.strip()
    return DEFAULT_TEMPLATES[stage]


def seed_default_templates(settings) -> None:
    """Appends a row with the built-in text for every stage the settings don't have yet."""
    present = {row.stage for row in settings.message_templates}
    for stage in STAGES:
        if stage not in present:
            settings.append(
                "message_templates", {"stage": stage, "message": DEFAULT_TEMPLATES[stage]}
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
