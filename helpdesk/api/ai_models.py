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


@frappe.whitelist()
def quality(model: str, days: int | str = 30) -> dict:
    """One model's quality: outcomes and the hallucination checks."""
    check_manager()
    return ai_models.quality(model, days)


@frappe.whitelist()
def benchmarks(model: str, against: str | None = None) -> dict:
    """One model's test-set runs, head to head, and public benchmarks."""
    check_manager()
    return ai_models.benchmarks(model, against or None)


@frappe.whitelist(methods=["POST"])
def add_public_benchmark(model: str, values: dict | str) -> dict:
    check_manager()
    values = frappe.parse_json(values) or {}
    if not isinstance(values, dict):
        frappe.throw(_("values must be an object"))
    return ai_models.add_public_benchmark(model, values)


@frappe.whitelist(methods=["POST"])
def remove_public_benchmark(name: str) -> dict:
    check_manager()
    return ai_models.remove_public_benchmark(name)


@frappe.whitelist(methods=["POST"])
def request_eval(model: str, job: str = "investigate") -> dict:
    """Queue a run of the test set on a model."""
    check_manager()
    return ai_models.request_eval(model, job)


@frappe.whitelist(methods=["POST"])
def import_eval(model: str, report: list | str, ran_on: str | None = None) -> dict:
    """A test-set report from the worker's `eval` command, brought in by a System Manager.
    Only case numbers and scores are kept."""
    check_manager()
    if not ai_models.can_change():
        frappe.throw(
            _("Only System Managers bring in a test-set report."),
            frappe.PermissionError,
        )
    report = frappe.parse_json(report)
    run = ai_models.store_eval(model, report, source="Imported", ran_on=ran_on)
    ai_models.close_requests(model, run)
    return ai_models.benchmarks(model)


@frappe.whitelist(methods=["POST"])
def withdraw_eval_request(name: str) -> dict:
    """Take back a request for a run nobody has done yet."""
    check_manager()
    return ai_models.withdraw_eval_request(name)


@frappe.whitelist(methods=["POST"])
def guard(job: str, values: dict | str) -> dict:
    """Before saving a Copilot job's model: its test-set score beside the current model's."""
    check_manager()
    values = frappe.parse_json(values) or {}
    if not isinstance(values, dict):
        frappe.throw(_("values must be an object"))
    return ai_models.guard(job, values)


def _values(values) -> dict:
    values = frappe.parse_json(values) or {}
    if not isinstance(values, dict):
        frappe.throw(_("values must be an object"))
    return values


@frappe.whitelist(methods=["POST"])
def save_provider(values: dict | str) -> dict:
    """A provider account (or one of today's sections): address, key, on/off."""
    check_manager()
    return ai_models.save_provider(_values(values))


@frappe.whitelist(methods=["POST"])
def remove_provider(name: str) -> dict:
    check_manager()
    return ai_models.remove_provider(name)


@frappe.whitelist(methods=["POST"])
def test_provider(name: str, model: str | None = None) -> dict:
    """A tiny test call through a provider account."""
    check_manager()
    return ai_models.test_provider(name, model)


@frappe.whitelist(methods=["POST"])
def save_model(values: dict | str) -> dict:
    """A model of the list: added, or its provider, prices, tick or monthly limit changed."""
    check_manager()
    return ai_models.save_model(_values(values))


@frappe.whitelist(methods=["POST"])
def remove_model(model: str) -> dict:
    check_manager()
    return ai_models.remove_model(model)


@frappe.whitelist(methods=["POST"])
def save_alerts(values: dict | str) -> dict:
    """The error-rate and fallback-rate limits that alert the managers."""
    check_manager()
    values = frappe.parse_json(values) or {}
    if not isinstance(values, dict):
        frappe.throw(_("values must be an object"))
    return ai_models.save_alerts(values)


@frappe.whitelist(methods=["POST"])
def save_gateway(values: dict | str) -> dict:
    """The AI gateway's address, read-only key and on/off."""
    check_manager()
    values = frappe.parse_json(values) or {}
    if not isinstance(values, dict):
        frappe.throw(_("values must be an object"))
    return ai_models.save_gateway(values)


@frappe.whitelist(methods=["POST"])
def sync_gateway() -> dict:
    """Read the gateway's usage now."""
    check_manager()
    return ai_models.sync_gateway()
