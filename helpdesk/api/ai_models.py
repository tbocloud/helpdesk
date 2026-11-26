# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""AI Models (Phase 31): the pages' API. Agent Managers and System Managers read; only System
Managers change which model a job uses (helpdesk.ai_models)."""

import frappe
from frappe import _

from helpdesk import ai_models
from helpdesk.tasky.permissions import is_tasky_admin


def check_manager():
    # only_for is skipped in tests, so check the roles directly
    if not is_tasky_admin():
        frappe.throw(
            _("Only Agent Managers and System Managers see the AI models."),
            frappe.PermissionError,
        )


@frappe.whitelist()
def overview(days: int | str = 30) -> dict:
    """Every model side by side."""
    check_manager()
    return ai_models.overview(days)


@frappe.whitelist()
def detail(model: str, days: int | str = 30) -> dict:
    """One model's performance and errors."""
    check_manager()
    return ai_models.detail(model, days)


@frappe.whitelist()
def job_settings(days: int | str = 30) -> dict:
    """Each job's primary and fallback model."""
    check_manager()
    return ai_models.job_settings(days)


@frappe.whitelist(methods=["POST"])
def save_job(job: str, values: dict | str) -> dict:
    """One job's first section, fallback and models."""
    check_manager()
    values = frappe.parse_json(values) or {}
    if not isinstance(values, dict):
        frappe.throw(_("values must be an object"))
    return ai_models.save_job(job, values)


@frappe.whitelist(methods=["POST"])
def try_job(job: str) -> dict:
    """A tiny test call with the job's first model."""
    check_manager()
    return ai_models.try_job(job)
