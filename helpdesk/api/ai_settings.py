"""Settings → AI providers: the AI part of HDS Hub Settings, for System and Agent Managers.

The API keys never go back to the browser once saved: the page gets a masked
value and whether each is set, and sends a key only to replace or remove it (as
Settings → GitHub does). docs/ai-providers.md describes the page.
"""

import frappe
from frappe import _

from helpdesk import ai_engine
from helpdesk.tasky.permissions import is_tasky_admin

SETTINGS = "HDS Hub Settings"
PLAIN_FIELDS = (
    "primary_ai_provider",
    "ai_failover",
    "ai_base_url",
    "default_triage_model",
    "openai_base_url",
    "openai_model",
)
SECRET_FIELDS = ("openai_api_key", "anthropic_api_key")
JOB_FIELDS = ("openai_model", "anthropic_model")
# enough of a key to tell which kind is saved, nothing of the key itself
KEY_PREFIXES = ("sk-proj-", "sk-ant-", "sk-")
# the Messages API kinds of the Anthropic-compatible section; "OpenAI Compatible",
# an older choice for that section, is kept as it is
ANTHROPIC = "Anthropic"
ANTHROPIC_COMPATIBLE = "Anthropic Compatible"


def check_admin():
    # only_for is skipped in tests, so check the roles directly
    if not is_tasky_admin():
        frappe.throw(
            _("Only System Managers and Agent Managers can change the AI providers."),
            frappe.PermissionError,
        )


def mask(value: str) -> str:
    return next((f"{p}…" for p in KEY_PREFIXES if value.startswith(p)), "…")


def settings_payload(doc) -> dict:
    secrets = {}
    for fieldname in SECRET_FIELDS:
        value = doc.get_password(fieldname, raise_exception=False)
        secrets[fieldname] = {
            "set": bool(value),
            "masked": mask(value) if value else "",
        }
    return {
        "settings": {
            **{f: doc.get(f) for f in PLAIN_FIELDS},
            "ai_jobs": [
                {"job": row.job, **{f: row.get(f) or "" for f in JOB_FIELDS}}
                for row in doc.get("ai_jobs") or []
            ],
        },
        "secrets": secrets,
        "status": ai_engine.provider_status(),
    }


def job_rows(rows: list) -> list[dict]:
    """Models per job as the page sends them: known jobs with at least one model, trimmed."""
    out = []
    for row in rows:
        if not isinstance(row, dict) or row.get("job") not in ai_engine.JOBS:
            continue
        models = {f: str(row.get(f) or "").strip() for f in JOB_FIELDS}
        if any(models.values()):
            out.append({"job": row["job"], **models})
    return out


@frappe.whitelist()
def get_settings() -> dict:
    check_admin()
    return settings_payload(frappe.get_doc(SETTINGS))


@frappe.whitelist(methods=["POST"])
def save_settings(values: dict | str) -> dict:
    """Plain fields as sent. A key only when it is sent: a value replaces it, an
    empty string removes it; HDSHubSettings.validate checks the base URLs.
    `ai_jobs`, when sent, replaces Models per job; a job with no model is left out.

    Saving forgets the providers' pauses and failures, so a fixed key or model is
    tried at once."""
    check_admin()
    values = frappe.parse_json(values) or {}
    doc = frappe.get_doc(SETTINGS)
    doc.update({k: v for k, v in values.items() if k in PLAIN_FIELDS})
    for fieldname in SECRET_FIELDS:
        if values.get(fieldname) is not None:
            doc.set(fieldname, str(values[fieldname]).strip())
    if isinstance(values.get("ai_jobs"), list):
        doc.set("ai_jobs", job_rows(values["ai_jobs"]))
    if doc.ai_provider in (ANTHROPIC, ANTHROPIC_COMPATIBLE, None, ""):
        # a base URL is what makes the Messages API endpoint Anthropic-compatible
        doc.ai_provider = ANTHROPIC_COMPATIBLE if doc.ai_base_url else ANTHROPIC
    doc.save(ignore_permissions=True)
    for model in {doc.openai_model, *(row.openai_model for row in doc.ai_jobs)}:
        ai_engine.ensure_model_pricing(model, ai_engine.OPENAI_SLOT)
    ai_engine.reset_provider_state()
    return settings_payload(frappe.get_doc(SETTINGS))


@frappe.whitelist(methods=["POST"])
def test_connection(provider: str) -> dict:
    """One tiny call with the saved settings of `provider` (OpenAI or
    Anthropic-compatible): {ok, message, details}, never the key."""
    check_admin()
    if provider not in ai_engine.SLOTS:
        frappe.throw(_("Choose a provider to test: OpenAI or Anthropic-compatible."))
    return ai_engine.test_provider(provider)
