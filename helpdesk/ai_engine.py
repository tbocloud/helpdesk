# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The hub's AI calls: OpenAI and Anthropic-compatible providers with failover,
prompt caching and token tracking (docs/ai-providers.md)."""

import contextlib
import json
import re
from dataclasses import dataclass, field, replace
from time import monotonic, perf_counter
from types import SimpleNamespace

import anthropic
import frappe
from frappe import _
from frappe.utils import (
    cint,
    flt,
    format_datetime,
    get_first_day,
    now_datetime,
    nowdate,
)

# Default model constants (can be overridden in HDS Hub Settings)
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"
OPUS_MODEL = "claude-opus-4-7"

# Fallback prices (USD per 1M tokens) used if HDS Model Pricing record is missing.
# The authoritative source is the HDS Model Pricing DocType - update prices there, not here.
FALLBACK_MODEL_COSTS = {
    HAIKU_MODEL: {
        "input": 1.00,
        "output": 5.00,
        "cache_read": 0.10,
        "cache_write": 1.25,
    },
    SONNET_MODEL: {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_write": 3.75,
    },
    OPUS_MODEL: {
        "input": 5.00,
        "output": 25.00,
        "cache_read": 0.50,
        "cache_write": 6.25,
    },
    # Legacy / deprecated (retires 2026-06-15) - kept so old logs still price correctly
    "claude-sonnet-4-20250514": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_write": 3.75,
    },
}


def get_model_cost(model: str) -> dict:
    """Return per-1M-token costs for a model.

    Order of precedence:
    1. HDS Model Pricing DocType record for this model_id (the UI-editable source of truth)
    2. FALLBACK_MODEL_COSTS constant (ships with the code so pricing works before seeding)
    3. Zeros (unknown model - cost will be 0)
    """
    try:
        row = frappe.db.get_value(
            "HDS Model Pricing",
            model,
            [
                "input_cost_per_1m",
                "output_cost_per_1m",
                "cache_read_cost_per_1m",
                "cache_write_cost_per_1m",
            ],
            as_dict=True,
        )
        if row:
            return {
                "input": row.input_cost_per_1m or 0,
                "output": row.output_cost_per_1m or 0,
                "cache_read": row.cache_read_cost_per_1m or 0,
                "cache_write": row.cache_write_cost_per_1m or 0,
            }
    except Exception:
        pass

    return FALLBACK_MODEL_COSTS.get(
        model, {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    )


def ensure_model_pricing(model: str | None, provider: str):
    """An HDS Model Pricing row for a newly configured model, so cost reports list it.

    Priced 0 until a System Manager enters the real price: OpenAI publishes no
    machine-readable list, and the weekly sync_model_pricing reminder flags the
    row because it was never reviewed.
    """
    model = (model or "").strip()
    if not model or frappe.db.exists("HDS Model Pricing", model):
        return
    frappe.get_doc(
        {
            "doctype": "HDS Model Pricing",
            "model_id": model,
            "display_name": model,
            "provider": provider,
            "is_active": 1,
            "notes": "TODO: enter the input and output price per 1M tokens from the provider's pricing page. 0 until then, so cost reports show $0 for this model.",
        }
    ).insert(ignore_permissions=True)


def get_hub_settings():
    """Get HDS Hub Settings singleton."""
    return frappe.get_single("HDS Hub Settings")


def get_models():
    """Get configured model IDs from Hub Settings."""
    try:
        settings = get_hub_settings()
        haiku = settings.default_triage_model or HAIKU_MODEL
        sonnet = settings.default_investigation_model or SONNET_MODEL
    except Exception:
        haiku = HAIKU_MODEL
        sonnet = SONNET_MODEL
    return haiku, sonnet


def get_provider_config(layer="triage"):
    """Return (provider, base_url, api_key) from HDS Hub Settings.

    provider is one of: "Anthropic", "Anthropic Compatible", "OpenAI Compatible".
    The key lives ONLY on the Hub — customer sites never hold an AI credential.
    """
    from frappe.utils.password import get_decrypted_password

    settings = get_hub_settings()
    provider = getattr(settings, "ai_provider", None) or "Anthropic"
    base_url = (getattr(settings, "ai_base_url", None) or "").rstrip("/") or None
    key_field = "anthropic_api_key"

    # Split providers: investigation may run on a different (tool-use capable)
    # provider than the cheap always-on triage layer.
    if layer == "investigation" and getattr(settings, "investigation_provider", None):
        provider = settings.investigation_provider
        base_url = (getattr(settings, "investigation_base_url", None) or "").rstrip(
            "/"
        ) or None
        if get_decrypted_password(
            "HDS Hub Settings",
            "HDS Hub Settings",
            "investigation_api_key",
            raise_exception=False,
        ):
            key_field = "investigation_api_key"

    api_key = get_decrypted_password(
        "HDS Hub Settings", "HDS Hub Settings", key_field, raise_exception=False
    )
    # Fallback to site_config for backward compatibility
    if not api_key:
        api_key = frappe.conf.get("anthropic_api_key")

    if not api_key:
        frappe.throw(_("AI API key not configured. Go to HDS Hub Settings to set it."))
    if provider != "Anthropic" and not base_url:
        frappe.throw(
            "Base URL is required for %s providers. Go to HDS Hub Settings." % provider
        )

    return provider, base_url, api_key


def get_client(layer="investigation"):
    """Get an Anthropic-SDK client (native or a compatible endpoint) for a layer.

    Anthropic-compatible providers (Kimi/Moonshot, GLM/Zhipu) accept the same
    API shape, so the only difference is base_url. OpenAI-compatible providers
    cannot be driven through this SDK — callers that need tool-use sessions
    get a clear error instead of a confusing HTTP failure.
    """
    provider, base_url, api_key = get_provider_config(layer=layer)

    if provider == "OpenAI Compatible":
        frappe.throw(
            _(
                "Investigation sessions need an Anthropic or Anthropic-Compatible "
                "provider. OpenAI-Compatible providers currently support triage only."
            )
        )

    if base_url:
        return anthropic.Anthropic(api_key=api_key, base_url=base_url)
    return anthropic.Anthropic(api_key=api_key)


# --- providers for call_haiku: the primary, then the fallback (docs/ai-providers.md) ---

# the two provider sections of HDS Hub Settings, and the values of primary_ai_provider
ANTHROPIC_SLOT = "Anthropic-compatible"
OPENAI_SLOT = "OpenAI"
SLOTS = (OPENAI_SLOT, ANTHROPIC_SLOT)
# used when the OpenAI section's Base URL is left empty
OPENAI_BASE_URL = "https://api.openai.com/v1"
# a slow answer counts as a failure, so the fallback can still answer
REQUEST_TIMEOUT = 120
# every attempt of one call_haiku, both providers included, ends by then: under
# triage's 300-second job timeout, so a killed job never hides the failover
CALL_SECONDS = 240
# an attempt with less time left than this isn't started
MIN_ATTEMPT_SECONDS = 5
# failover replaces the SDK's own retries, which would outlast the time left
SDK_MAX_RETRIES = 0
TEST_TOKEN_BUDGET = 64

# a provider is skipped this long after a billing, key or model failure
CIRCUIT_SECONDS = 30 * 60
ALERT_SECONDS = 6 * 60 * 60
# how long a provider shows as failing when nothing calls it again
STATUS_SECONDS = 24 * 60 * 60
CIRCUIT_KEY = "ai_engine:circuit:{}"
DOWN_KEY = "ai_engine:down:{}"
ALERT_KEY = "ai_engine:alerted:{}"
# set while every provider failed; the next answer re-runs the triages that failed meanwhile
OUTAGE_KEY = "ai_engine:outage"
RETRY_TRIAGES_JOB = "ai-retry-pending-triages"

# failures another provider may not have; a request rejected as invalid would fail there too
FAILOVER_KINDS = {"billing", "auth", "config", "rate_limit", "server", "timeout"}
CIRCUIT_KINDS = {"billing", "auth", "config"}
# a rate limit passes in seconds: fail over, but don't alert or show the provider as down
TRANSIENT_KINDS = {"rate_limit"}
REASONS = {
    "billing": "insufficient balance or quota",
    "auth": "the API key was refused",
    "config": "the model or base URL wasn't found",
    "rate_limit": "rate limited",
    "server": "the provider had an error",
    "timeout": "no answer in time",
    "invalid": "the request was rejected",
    "paused": "paused after a failure, tried again within 30 minutes",
}
BILLING_WORDS = (
    "balance",
    "quota",
    "billing",
    "credit",
    "payment",
    "insufficient",
    "suspended",
)
MODEL_MISSING_WORDS = (
    "model_not_found",
    "model not found",
    "does not exist",
    "unknown model",
)
# keys and their masked echoes (OpenAI's 401 repeats part of the key)
SECRET_PATTERN = re.compile(r"\b(sk|pk|key)-[\w*\-]{4,}", re.IGNORECASE)
MAX_ERROR_CHARS = 300


@dataclass
class AIProvider:
    """One provider section of HDS Hub Settings, ready to call."""

    slot: str
    kind: str  # Anthropic, Anthropic Compatible, OpenAI Compatible or OpenAI
    base_url: str | None
    model: str
    api_key: str = field(repr=False)
    # a job's own model (HDS AI Job): paused and reported apart from the section's model
    override: bool = False
    # an OpenAI-compatible provider account that takes a token budget and JSON mode (Phase 31)
    budget_param: str = ""
    json_mode: bool = False

    @property
    def label(self) -> str:
        return f"{self.slot} ({self.model})"

    @property
    def key(self) -> str:
        """What a pause, a failing status or an alert is kept under."""
        return f"{self.slot}|{self.model}" if self.override else self.slot

    @property
    def speaks_openai(self) -> bool:
        return self.kind in ("OpenAI", "OpenAI Compatible")


class AIProviderError(Exception):
    """A provider's failure. `kind` (a REASONS key) decides whether to fail over;
    `detail` is the provider's own message with any key masked."""

    def __init__(
        self, provider: AIProvider, kind: str, detail: str, status: int | None = None
    ):
        self.provider = provider
        self.kind = kind
        self.status = status
        self.detail = redact(detail, provider.api_key)
        super().__init__(f"{provider.label}: {self.summary}")

    @property
    def fails_over(self) -> bool:
        return self.kind in FAILOVER_KINDS

    @property
    def summary(self) -> str:
        """What happened, with the provider's words, for people: never the key."""
        status = f"HTTP {self.status}: " if self.status else ""
        reason = _(REASONS.get(self.kind, self.kind))
        return f"{reason} ({status}{self.detail})" if self.detail else reason


class _Usage:
    """Duck-typed usage object so OpenAI-shaped counts flow through the same
    estimate_cost/log_usage plumbing as the Anthropic SDK's."""

    def __init__(self, input_tokens=0, output_tokens=0):
        self.input_tokens = input_tokens or 0
        self.output_tokens = output_tokens or 0


def redact(text: str, key: str | None = None) -> str:
    text = str(text or "")
    if key:
        text = text.replace(key, "…")
    return SECRET_PATTERN.sub(lambda m: f"{m.group(1)}-…", text)[:MAX_ERROR_CHARS]


def _hub_password(field_name: str) -> str | None:
    from frappe.utils.password import get_decrypted_password

    return get_decrypted_password(
        "HDS Hub Settings", "HDS Hub Settings", field_name, raise_exception=False
    )


def configured_providers(settings=None) -> dict[str, AIProvider | None]:
    """Each provider section, or None where it lacks a key or model."""
    settings = settings or get_hub_settings()
    providers: dict[str, AIProvider | None] = {}

    key = _hub_password("anthropic_api_key") or frappe.conf.get("anthropic_api_key")
    kind = settings.get("ai_provider") or "Anthropic"
    base_url = (settings.get("ai_base_url") or "").strip().rstrip("/") or None
    providers[ANTHROPIC_SLOT] = (
        AIProvider(
            ANTHROPIC_SLOT,
            kind,
            base_url,
            settings.get("default_triage_model") or HAIKU_MODEL,
            key,
        )
        if key and (base_url or kind == "Anthropic")
        else None
    )

    key = _hub_password("openai_api_key")
    model = (settings.get("openai_model") or "").strip()
    base_url = (settings.get("openai_base_url") or "").strip().rstrip("/")
    providers[OPENAI_SLOT] = (
        AIProvider(OPENAI_SLOT, "OpenAI", base_url or OPENAI_BASE_URL, model, key)
        if key and model
        else None
    )
    return providers


def provider_order(settings=None, job: str | None = None) -> list[str]:
    """The primary section, then the other one when failover is on. A job's row in Models per
    job may choose its own first section and switch its own fallback on or off (Phase 31)."""
    settings = settings or get_hub_settings()
    primary = settings.get("primary_ai_provider") or ANTHROPIC_SLOT
    failover = bool(settings.get("ai_failover"))
    row = job_row(job, settings)
    if row:
        if row.get("primary_section") in SLOTS:
            primary = row.primary_section
        if row.get("allow_fallback") in ("On", "Off"):
            failover = row.allow_fallback == "On"
    if not failover:
        return [primary]
    return [primary, *(slot for slot in SLOTS if slot != primary)]


def job_row(job: str | None, settings=None):
    """The job's row in Models per job, if it has one."""
    if not job:
        return None
    settings = settings or get_hub_settings()
    return next((r for r in settings.get("ai_jobs") or [] if r.job == job), None)


# Every application that uses AI, with its purposes (docs/ai-models.md). Each purpose gets a model
# and a backup on the AI models page; a new application or purpose is one entry here.
APPLICATIONS = (
    {
        "name": "TBO Support",
        "note": "TBO Support's own AI: triage, drafts, summaries, tasks and chat.",
        "purposes": ("triage", "draft", "summary", "task", "chat"),
    },
    {
        "name": "Copilot worker",
        "note": "Copilot's investigations, fixes and reviews, on the worker server.",
        "purposes": ("investigate", "fix", "review"),
    },
    {
        "name": "Desktop app",
        "note": "The desktop assistant's levels. Each is written to the TBO AI gateway as tbo-simple … tbo-very-hard, its model first and its backup second; the desktop app shows them as TBO AI · Simple … Very hard once its update is installed.",
        "purposes": (
            "desktop_simple",
            "desktop_medium",
            "desktop_hard",
            "desktop_very_hard",
        ),
        # a level has its own model or none: no sections and no fallback order
        "own_models_only": True,
    },
    {
        "name": "Inbox",
        "note": "Facebook, Instagram, WhatsApp and email (phases 32 to 35): these purposes arrive with those phases.",
        "purposes": ("inbox_reply", "inbox_purpose", "inbox_voice", "inbox_files"),
        "coming": True,
    },
)
# a desktop level's name on the gateway, the one the desktop app asks for
DESKTOP_GATEWAY_NAMES = {
    "desktop_simple": "tbo-simple",
    "desktop_medium": "tbo-medium",
    "desktop_hard": "tbo-hard",
    "desktop_very_hard": "tbo-very-hard",
}
PURPOSE_LABELS = {
    "desktop_simple": "Simple",
    "desktop_medium": "Medium",
    "desktop_hard": "Hard",
    "desktop_very_hard": "Very hard",
    "inbox_reply": "Auto reply",
    "inbox_purpose": "Purpose of a message",
    "inbox_voice": "Voice notes",
    "inbox_files": "Pictures and files",
}
# every purpose (the Models per job rows); TBO Support's own, then the Copilot worker's, then the rest
JOBS = tuple(job for app in APPLICATIONS for job in app["purposes"])
WORKER_JOBS = ("investigate", "fix", "review")
OWN_MODEL_JOBS = tuple(
    job for app in APPLICATIONS if app.get("own_models_only") for job in app["purposes"]
)
# shown on the page before their phase builds them; no model can be chosen yet
COMING_JOBS = tuple(
    job for app in APPLICATIONS if app.get("coming") for job in app["purposes"]
)


def application_of(job: str | None) -> str:
    return next((a["name"] for a in APPLICATIONS if job in a["purposes"]), "")


def purpose_label(job: str) -> str:
    return PURPOSE_LABELS.get(job, job)


def job_models(job: str | None, settings=None) -> dict[str, str]:
    """A job's own model per section, from its row in Models per job; empty without one."""
    if not job:
        return {}
    settings = settings or get_hub_settings()
    for row in settings.get("ai_jobs") or []:
        if row.job == job:
            models = {
                OPENAI_SLOT: row.openai_model,
                ANTHROPIC_SLOT: row.anthropic_model,
            }
            return {
                slot: model.strip()
                for slot, model in models.items()
                if (model or "").strip()
            }
    return {}


def get_providers(job: str | None = None) -> list[AIProvider]:
    """The providers call_haiku tries, in order (`job_chain`), less the models past their
    monthly token limit (`within_limits`)."""
    return within_limits(job_chain(job), own_model(job))


def own_model(job: str | None, settings=None) -> str:
    """The job's own model as set in Models per job, even when its provider is off; '' without
    one."""
    if job in COMING_JOBS:
        return ""
    row = job_row(job, settings)
    return row.model if row and row.get("model") else ""


def job_chain(job: str | None = None, settings=None) -> list[AIProvider]:
    """A job with its own model (Phase 31) tries it, then its backup, each through its provider
    account; a model whose provider is off or has no key is left out. Any other job tries the
    sections in its order (`provider_order`), each with the job's model for that section,
    leaving out sections without a key. A purpose with its own models only (a desktop level)
    has nothing without one, and a coming purpose has nothing yet."""
    settings = settings or get_hub_settings()
    if job in COMING_JOBS:
        return []
    from helpdesk import ai_gateway

    if ai_gateway.for_all(settings):
        return [gateway_provider(m, settings) for m in chain_models(job, settings)]
    row = job_row(job, settings)
    if row and row.get("model"):
        chosen = (row.model, row.get("backup_model"))
        return [p for p in (model_provider(m, settings) for m in chosen if m) if p]
    if job in OWN_MODEL_JOBS:
        return []
    return section_chain(job, settings)


def section_chain(job: str | None, settings=None) -> list[AIProvider]:
    """The sections in the job's order, each with the job's model for it; sections without a
    key are left out. Also the emergency path when the gateway can't be used (Phase 37)."""
    settings = settings or get_hub_settings()
    providers = configured_providers(settings)
    models = job_models(job, settings)
    return [
        replace(providers[slot], model=models[slot], override=True)
        if models.get(slot) and models[slot] != providers[slot].model
        else providers[slot]
        for slot in provider_order(settings, job)
        if providers[slot]
    ]


def chain_models(job: str | None, settings=None) -> list[str]:
    """The models a purpose tries, in order, by name: its own model and backup (allowed ones),
    else its sections' models in its order (sections with a key)."""
    settings = settings or get_hub_settings()
    if job in COMING_JOBS:
        return []
    row = job_row(job, settings)
    if row and row.get("model"):
        return [
            m for m in (row.model, row.get("backup_model")) if m and listed_and_on(m)
        ]
    if job in OWN_MODEL_JOBS:
        return []
    return list(dict.fromkeys(p.model for p in section_chain(job, settings)))


def listed_and_on(model: str) -> bool:
    """The model is allowed for jobs and its provider account isn't switched off: the gateway
    path skips an account that is off, as `account_provider` does. A section is always on."""
    row = frappe.db.get_value(
        PRICING_DOCTYPE, model, ["listed", "ai_provider"], as_dict=True
    )
    if not row or not row.listed:
        return False
    if not row.ai_provider or row.ai_provider in SLOTS:
        return True
    return bool(frappe.db.get_value(PROVIDER_DOCTYPE, row.ai_provider, "enabled"))


def gateway_provider(model: str, settings=None) -> AIProvider:
    """`model` as the TBO AI gateway serves it, with TBO Support's own gateway key. The gateway
    speaks OpenAI's chat completions for every model and passes on the providers' errors."""
    from helpdesk import ai_gateway

    return AIProvider(
        ai_gateway.SLOT,
        "OpenAI Compatible",
        ai_gateway.base_url(settings) + "/v1",
        model,
        ai_gateway.call_key(),
        override=True,
        budget_param="max_tokens",
        json_mode=True,
    )


def gateway_unusable(error: "AIProviderError") -> bool:
    """Whether a failed call through the gateway means the gateway itself can't be used: it
    doesn't answer its health check, or it refused TBO Support's own key."""
    from helpdesk import ai_gateway

    if error.provider.slot != ai_gateway.SLOT:
        return False
    if error.kind in ("timeout", "server"):
        return not ai_gateway.alive(fresh=True)
    if error.kind == "auth":
        return not ai_gateway.key_works()
    return False


def within_limits(chain: list[AIProvider], first: str = "") -> list[AIProvider]:
    """A model past its monthly token limit isn't called. When it is the first model, the job
    stops: the backup is there for outages, not for spending past a limit. `first` is the job's
    own model (`own_model`): its limit counts even when its provider is off and the chain left
    it out."""
    first = first or (chain[0].model if chain else "")
    if first and over_limit(first):
        return []
    return [p for p in chain if not over_limit(p.model)]


def limit_reached(job: str | None = None) -> str:
    """The job's first model when its monthly token limit is used up, else ''."""
    first = own_model(job) or next((p.model for p in job_chain(job)), "")
    return first if first and over_limit(first) else ""


# --- the model list and the provider accounts (Phase 31, docs/ai-models.md) ---

PRICING_DOCTYPE = "HDS Model Pricing"
PROVIDER_DOCTYPE = "HDS AI Provider"
# a provider account's API style, as the request it gets
STYLE_KINDS = {
    "OpenAI": "OpenAI",
    "OpenAI-compatible": "OpenAI Compatible",
    "Anthropic": "Anthropic",
    "Anthropic-compatible": "Anthropic Compatible",
}
MONTH_TOKENS_KEY = "ai_engine:month_tokens:{}"
MONTH_TOKENS_SECONDS = 5 * 60


def model_provider(model: str, settings=None) -> AIProvider | None:
    """A model of the list (HDS Model Pricing), ready to call through its provider account;
    None when it isn't allowed for jobs, or its provider is off or has no key."""
    row = frappe.db.get_value(
        PRICING_DOCTYPE, model, ["name", "ai_provider", "listed"], as_dict=True
    )
    if not row or not row.listed or not row.ai_provider:
        return None
    return account_provider(row.ai_provider, row.name, settings)


def account_provider(account: str, model: str, settings=None) -> AIProvider | None:
    """`model` through a provider account: one of today's sections, or an HDS AI Provider.
    None when the account is off or has no key."""
    if account in SLOTS:
        section = configured_providers(settings)[account]
        if not section:
            return None
        if model == section.model:
            return section
        return replace(section, model=model, override=True)
    doc = frappe.db.get_value(
        PROVIDER_DOCTYPE,
        account,
        ["name", "api_style", "base_url", "enabled", "json_mode"],
        as_dict=True,
    )
    if not doc or not doc.enabled:
        return None
    from frappe.utils.password import get_decrypted_password

    key = get_decrypted_password(
        PROVIDER_DOCTYPE, doc.name, "api_key", raise_exception=False
    )
    if not key:
        return None
    compatible = doc.api_style == "OpenAI-compatible" and bool(doc.json_mode)
    return AIProvider(
        doc.name,
        STYLE_KINDS.get(doc.api_style, "OpenAI Compatible"),
        doc.base_url or (OPENAI_BASE_URL if doc.api_style == "OpenAI" else None),
        model,
        key,
        override=True,
        budget_param="max_tokens" if compatible else "",
        json_mode=compatible,
    )


def jobs_using(model: str, settings=None) -> list[str]:
    """The jobs whose own model or backup is `model`."""
    if not model:
        return []
    settings = settings or get_hub_settings()
    return [
        row.job
        for row in settings.get("ai_jobs") or []
        if model in (row.get("model"), row.get("backup_model"))
    ]


def in_use_message(model: str, settings=None) -> str:
    """Why `model` must stay allowed: the jobs that use it; '' when none does."""
    jobs = jobs_using(model, settings)
    if not jobs:
        return ""
    if len(jobs) == 1:
        return _("{0} uses {1}. Choose another model for it first.").format(
            jobs[0], model
        )
    return _("{0} use {1}. Choose another model for them first.").format(
        ", ".join(jobs), model
    )


def month_tokens(model: str) -> int:
    """Input (cached input too) plus output tokens of `model` this calendar month, TBO Support's
    and the Copilot worker's (the usage log), counted again at most every 5 minutes."""
    key = MONTH_TOKENS_KEY.format(model)
    cached = frappe.cache.get_value(key, expires=True)
    if cached is not None:
        return cint(cached)
    from frappe.query_builder.functions import Coalesce, Sum

    log = frappe.qb.DocType("HDS AI Usage Log")
    total = (
        frappe.qb.from_(log)
        .select(
            # Anthropic and the worker log cached input apart from input_tokens
            Sum(
                Coalesce(log.input_tokens, 0)
                + Coalesce(log.cache_read_tokens, 0)
                + Coalesce(log.cache_write_tokens, 0)
                + Coalesce(log.output_tokens, 0)
            )
        )
        .where(log.model == model)
        .where(log.creation >= get_first_day(nowdate()))
    ).run()[0][0]
    total = cint(total)
    from helpdesk.ai_gateway import remember

    remember(key, total, MONTH_TOKENS_SECONDS)
    return total


def monthly_limit(model: str) -> float:
    """The model's monthly token limit in millions; 0 means none."""
    if not model:
        return 0.0
    return flt(frappe.db.get_value(PRICING_DOCTYPE, model, "monthly_token_limit"))


def over_limit(model: str) -> bool:
    limit = monthly_limit(model)
    return bool(limit) and month_tokens(model) >= limit * 1_000_000


def forget_provider(account: str):
    """Forget a provider account's pauses and failures, e.g. after its key changed."""
    for key in (CIRCUIT_KEY, DOWN_KEY):
        frappe.cache.delete_keys(key.format(f"{account}|"))


def check_job_rows(settings):
    """HDS Hub Settings: one row per job; a job's own model and backup are two different
    models allowed for jobs (Phase 31)."""
    seen = set()
    for row in settings.get("ai_jobs") or []:
        if row.job in seen:
            frappe.throw(
                _("Models per job: {0} has more than one row.").format(row.job)
            )
        seen.add(row.job)
        if row.get("backup_model") and not row.get("model"):
            frappe.throw(
                _("Models per job: {0} has a backup but no model.").format(row.job)
            )
        if row.get("model") and row.get("model") == row.get("backup_model"):
            frappe.throw(
                _("Models per job: the backup of {0} must be another model.").format(
                    row.job
                )
            )
        for model in (row.get("model"), row.get("backup_model")):
            if model and not frappe.db.get_value(PRICING_DOCTYPE, model, "listed"):
                frappe.throw(
                    _(
                        "Models per job: {0} isn't allowed for jobs. Tick it under AI models → Models first."
                    ).format(model)
                )


def worker_models() -> dict[str, list[dict]]:
    """For the Copilot worker's run context: each worker job's providers in order (its own
    model and backup, or the sections), with the model and its price per million tokens.
    Never a key: the worker holds its own and finds it by the provider's name (`section`)."""
    out = {}
    for job in WORKER_JOBS:
        out[job] = []
        for provider in get_providers(job):
            cost = get_model_cost(provider.model)
            out[job].append(
                {
                    "section": provider.slot,
                    "model": provider.model,
                    "price_in": cost["input"],
                    "price_out": cost["output"],
                    "price_cached": cost["cache_read"],
                }
            )
    return out


def wants_json(system_prompt: str) -> bool:
    """The caller asks for JSON. OpenAI's JSON mode also needs the word in the prompt."""
    return "json" in (system_prompt or "").lower()


def classify(status: int, detail: str) -> str:
    """The kind of failure behind an HTTP status and the provider's message."""
    text = (detail or "").lower()
    if status == 402 or (
        # Anthropic answers "credit balance is too low" with a 400
        status in (400, 403, 429)
        and any(word in text for word in BILLING_WORDS)
    ):
        return "billing"
    if status in (401, 403):
        return "auth"
    if status == 404 or (
        status == 400 and any(word in text for word in MODEL_MISSING_WORDS)
    ):
        return "config"
    if status == 429:
        return "rate_limit"
    if status in (408, 504):
        return "timeout"
    if status >= 500:
        return "server"
    return "invalid"


def error_detail(body) -> str:
    """The message (and type or code) in an OpenAI- or Anthropic-shaped error body."""
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        message = str(error.get("message") or "")
        code = error.get("code") or error.get("type")
        if message and code:
            return f"{message} ({code})"
        return message or str(code or "")
    if isinstance(error, str):
        return error
    if isinstance(body, dict):
        return str(body.get("message") or "")
    return ""


def _openai_chat(
    provider: AIProvider,
    system_prompt: str,
    user_message: str,
    max_tokens: int,
    timeout: float,
    images: list[dict] | None = None,
):
    """One /chat/completions call, through requests so there is no openai SDK
    to depend on. Returns (text, _Usage, ran_out_of_tokens).

    Only OpenAI itself gets a token budget and JSON mode, and an OpenAI-compatible
    provider account that says it supports them (DeepSeek, Qwen); other endpoints
    may not know them. No temperature is sent: newer OpenAI models refuse anything
    but the default.
    """
    import requests

    body = {
        "model": provider.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _openai_content(user_message, images)},
        ],
    }
    if provider.kind == "OpenAI":
        # reasoning models count their thinking in this budget too
        body["max_completion_tokens"] = max_tokens
        if wants_json(system_prompt):
            body["response_format"] = {"type": "json_object"}
    elif provider.budget_param:
        body[provider.budget_param] = max_tokens
        if provider.json_mode and wants_json(system_prompt):
            body["response_format"] = {"type": "json_object"}
    try:
        response = requests.post(
            f"{provider.base_url}/chat/completions",
            json=body,
            headers={
                "Authorization": f"Bearer {provider.api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
    except requests.RequestException as e:
        # only the kind: the text can hold the request
        raise AIProviderError(provider, "timeout", type(e).__name__) from None
    if not response.ok:
        try:
            detail = error_detail(response.json())
        except ValueError:
            detail = ""
        status = response.status_code
        raise AIProviderError(
            provider, classify(status, detail), detail or response.reason, status
        )

    try:
        data = response.json()
        choice = data["choices"][0]
        text = choice["message"].get("content") or ""
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        # a 200 that isn't an answer is the provider's fault: let the other one try
        raise AIProviderError(
            provider, "server", "the answer had no choices or message"
        ) from None
    usage = data.get("usage") or {}
    return (
        text,
        _Usage(usage.get("prompt_tokens"), usage.get("completion_tokens")),
        choice.get("finish_reason") == "length",
    )


def _openai_content(user_message: str, images: list[dict] | None):
    """The user message, with `images` ([{media_type, data (base64)}]) as data URLs."""
    if not images:
        return user_message
    return [
        {"type": "text", "text": user_message},
        *(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image['media_type']};base64,{image['data']}"
                },
            }
            for image in images
        ),
    ]


def _anthropic_content(user_message: str, images: list[dict] | None):
    if not images:
        return user_message
    return [
        *(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image["media_type"],
                    "data": image["data"],
                },
            }
            for image in images
        ),
        {"type": "text", "text": user_message},
    ]


def _anthropic_messages(
    provider: AIProvider,
    system_prompt: str,
    user_message: str,
    max_tokens: int,
    timeout: float,
    images: list[dict] | None = None,
):
    """One Messages API call (Anthropic or a compatible endpoint such as Kimi).
    Returns (text, usage, ran_out_of_tokens)."""
    client_args = {"api_key": provider.api_key, "max_retries": SDK_MAX_RETRIES}
    if provider.base_url:
        client_args["base_url"] = provider.base_url
    try:
        response = anthropic.Anthropic(**client_args).messages.create(
            model=provider.model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {"role": "user", "content": _anthropic_content(user_message, images)}
            ],
            timeout=timeout,
        )
    except anthropic.APIStatusError as e:
        detail = error_detail(e.body) or e.message
        raise AIProviderError(
            provider, classify(e.status_code, detail), detail, e.status_code
        ) from None
    except anthropic.APIConnectionError as e:  # a timeout is one too
        raise AIProviderError(provider, "timeout", type(e).__name__) from None

    # thinking-capable models may put a thinking block first
    text = "".join(
        block.text
        for block in response.content
        if getattr(block, "type", "text") == "text"
    )
    return text, response.usage, getattr(response, "stop_reason", None) == "max_tokens"


def complete(
    provider: AIProvider,
    system_prompt: str,
    user_message: str,
    ticket_name: str | None = None,
    budgets: tuple[int, ...] | None = None,
    deadline: float | None = None,
    job: str | None = None,
    fallback: bool = False,
    images: list[dict] | None = None,
):
    """One answer from one provider, each attempt logged; AIProviderError if it fails.
    `images` ([{media_type, data (base64)}]) are shown to the model with the message; the
    model must read images (docs/lead-bank.md).

    Thinking models (Kimi, OpenAI's reasoning models) spend part of the budget
    thinking and can run out before writing the answer: they get room, then more once.
    No attempt runs past `deadline` (a monotonic() value).
    """
    call = _openai_chat if provider.speaks_openai else _anthropic_messages
    if deadline is None:
        deadline = monotonic() + CALL_SECONDS
    for max_tokens in budgets or TRIAGE_TOKEN_BUDGETS:
        timeout = min(REQUEST_TIMEOUT, deadline - monotonic())
        if timeout < MIN_ATTEMPT_SECONDS:
            raise AIProviderError(provider, "timeout", "no time left for this call")
        # its own clock: the deadline's monotonic() is counted by the tests
        started = perf_counter()
        try:
            text, usage, ran_out = call(
                provider, system_prompt, user_message, max_tokens, timeout, images
            )
        except AIProviderError as e:
            # a failed attempt is a row too: errors and speed are counted per model (Phase 31)
            keep_failed_attempt(
                provider,
                e,
                ticket_name=ticket_name,
                job=job,
                fallback=fallback,
                duration_ms=round((perf_counter() - started) * 1000),
            )
            raise
        log_usage(
            provider.model,
            usage,
            ticket_name=ticket_name,
            provider=provider.slot,
            job=job,
            fallback=fallback,
            duration_ms=round((perf_counter() - started) * 1000),
        )
        if text.strip() or not ran_out:
            break
    return text, usage


# --- failover state: circuit breaker, status and alerts (Redis, site-prefixed) ---


def circuit_open(provider: AIProvider) -> bool:
    return bool(frappe.cache.get_value(CIRCUIT_KEY.format(provider.key), expires=True))


def provider_down(slot: str) -> dict | None:
    """{kind, reason, since, model} while a section is failing, else None."""
    return frappe.cache.get_value(DOWN_KEY.format(slot), expires=True)


def record_failure(error: AIProviderError, fallback: AIProvider | None):
    """Pause a provider whose bill, key or model is wrong, show it as failing and
    alert the managers once; a rejected request is only logged."""
    provider = error.provider
    if not error.fails_over:
        frappe.log_error(
            title=f"AI request rejected by {provider.label}", message=str(error)
        )
        return
    if error.kind in CIRCUIT_KINDS:
        frappe.cache.set_value(
            CIRCUIT_KEY.format(provider.key),
            error.kind,
            expires_in_sec=CIRCUIT_SECONDS,
        )
    if error.kind in TRANSIENT_KINDS:
        return
    since = (provider_down(provider.key) or {}).get("since") or str(now_datetime())
    frappe.cache.set_value(
        DOWN_KEY.format(provider.key),
        {
            "kind": error.kind,
            "reason": error.summary,
            "since": since,
            "model": provider.model,
        },
        expires_in_sec=STATUS_SECONDS,
    )
    alert_once(error, fallback, since)


def alert_once(error: AIProviderError, fallback: AIProvider | None, since: str):
    """One alert per provider in ALERT_SECONDS, sent from a job so a request
    that rolls back after the failure doesn't take the alert with it."""
    provider = error.provider
    first = frappe.cache.set(  # site-prefixed via make_key; set_value can't do NX - nosemgrep
        frappe.cache.make_key(ALERT_KEY.format(provider.key)),
        1,
        nx=True,
        ex=ALERT_SECONDS,
    )
    if not first:
        return
    # the time keeps each incident's text unique: chat posts are sent once per text
    since = format_datetime(since, "d MMM, HH:mm")
    reason = _(REASONS[error.kind])
    if fallback:
        subject = _("AI provider {0} failing since {1}: {2}. Using {3}.").format(
            provider.label, since, reason, fallback.label
        )
    else:
        subject = _(
            "AI provider {0} failing since {1}: {2}. No other provider is set up, so AI features are paused until it's fixed in Settings → AI providers."
        ).format(provider.label, since, reason)
    frappe.enqueue(
        "helpdesk.ai_engine.send_provider_alert",
        subject=subject,
        queue="short",
        now=frappe.flags.in_test,
    )


def send_provider_alert(subject: str):
    """To the System and Agent Managers, in the app and in the team's chat channel."""
    from helpdesk.github_sync import admin_users
    from helpdesk.work_reminders import notify_users

    notify_users(
        admin_users(),
        "HDS Hub Settings",
        "HDS Hub Settings",
        subject,
        escalate=True,
        link="/home",
        once=False,
    )


def record_success(provider: AIProvider):
    """The provider works: unpause it, and re-run triages that failed while none did."""
    frappe.cache.delete_value(
        [CIRCUIT_KEY.format(provider.key), DOWN_KEY.format(provider.key)]
    )
    if frappe.cache.get_value(OUTAGE_KEY, expires=True):
        frappe.cache.delete_value(OUTAGE_KEY)
        retry_failed_triages()


def reset_provider_state():
    """Forget pauses and failures, e.g. after the settings changed."""
    frappe.cache.delete_value(
        [key.format(slot) for slot in SLOTS for key in (CIRCUIT_KEY, DOWN_KEY)]
    )


def retry_failed_triages():
    frappe.enqueue(
        "helpdesk.tasks.retry_pending_triages",
        queue="short",
        job_id=RETRY_TRIAGES_JOB,
        deduplicate=True,
    )


def provider_status() -> dict:
    """What Settings → AI providers and the Home banner show: the order, each
    section's state, and which one answers now. Never a key."""
    settings = get_hub_settings()
    providers = configured_providers(settings)
    order = provider_order(settings)
    sections = {}
    for slot in SLOTS:
        provider = providers[slot]
        sections[slot] = {
            "configured": bool(provider),
            "model": provider.model if provider else None,
            "paused": bool(provider and circuit_open(provider)),
            "down": provider_down(slot),
        }
    in_use = next(
        (
            slot
            for slot in order
            if sections[slot]["configured"] and not sections[slot]["paused"]
        ),
        None,
    )
    return {
        "primary": order[0],
        "failover": bool(settings.get("ai_failover")),
        "order": order,
        "in_use": in_use,
        "providers": sections,
    }


def test_provider(slot: str) -> dict:
    """One tiny call with a section's saved settings: {ok, message, details}.
    A success also unpauses it and re-runs the triages that failed."""
    provider = configured_providers().get(slot)
    if not provider:
        return {
            "ok": False,
            "message": _("Add the API key and model, save, then test again."),
        }
    started = monotonic()
    try:
        complete(
            provider,
            "Reply with the single word OK.",
            "Connection test",
            budgets=(TEST_TOKEN_BUDGET,),
        )
    except AIProviderError as e:
        return {
            "ok": False,
            "message": _("{0} answered: {1}").format(provider.slot, e.summary),
        }
    record_success(provider)
    retry_failed_triages()
    host = (provider.base_url or "https://api.anthropic.com").split("/")[2]
    return {
        "ok": True,
        "message": _("{0} answered. AI features can use it.").format(provider.slot),
        "details": [
            {"label": _("Model"), "value": provider.model},
            {"label": _("Endpoint"), "value": host},
            {
                "label": _("Time"),
                "value": f"{round((monotonic() - started) * 1000)} ms",
            },
        ],
    }


def estimate_cost(model: str, usage) -> float:
    """Estimate cost in USD from API usage object."""
    costs = get_model_cost(model)
    input_cost = (usage.input_tokens / 1_000_000) * costs["input"]
    output_cost = (usage.output_tokens / 1_000_000) * costs["output"]
    cache_read_cost = (
        getattr(usage, "cache_read_input_tokens", 0) / 1_000_000
    ) * costs["cache_read"]
    cache_write_cost = (
        getattr(usage, "cache_creation_input_tokens", 0) / 1_000_000
    ) * costs["cache_write"]
    return round(input_cost + output_cost + cache_read_cost + cache_write_cost, 6)


def log_usage(
    model: str,
    usage,
    session_name: str | None = None,
    ticket_name: str | None = None,
    provider: str | None = None,
    job: str | None = None,
    copilot_run: str | None = None,
    fallback: bool = False,
    duration_ms: int | None = None,
    error: "AIProviderError | None" = None,
    at: str | None = None,
):
    """Log API usage to HDS AI Usage Log. Without `provider` it is an
    investigation's call: those always run on an Anthropic-compatible provider.
    `error` makes it a Failed row with the error's kind and the provider's own words
    (key masked, clipped): never the prompt. `at` is when the call happened, for a row
    written later (a failed attempt's row is written by a job of its own)."""
    try:
        row = frappe.get_doc(
            {
                "doctype": "HDS AI Usage Log",
                "session": session_name,
                "ticket": ticket_name,
                "model": model,
                "provider": provider or ANTHROPIC_SLOT,
                "job": job,
                "copilot_run": copilot_run,
                "fallback": int(bool(fallback)),
                "duration_ms": duration_ms,
                "status": "Failed" if error else "Success",
                "error_class": error.kind if error else None,
                "error_message": (
                    f"HTTP {error.status}: " if error and error.status else ""
                )
                + (error.detail or "")[:MAX_ERROR_CHARS]
                if error
                else None,
                "source": "TBO Support",
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0),
                "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0),
                "estimated_cost_usd": estimate_cost(model, usage),
            }
        ).insert(ignore_permissions=True)
        if at:
            # the call's own time, so a fallback that answered after it still sorts after it,
            # and the day reports count it on the day it happened
            row.db_set({"creation": at, "timestamp": at}, update_modified=False)
    except Exception:
        frappe.log_error("Failed to log AI usage")


def keep_failed_attempt(provider: AIProvider, error: AIProviderError, **row):
    """A failed attempt's usage row, written by a job of its own: a request that fails after it
    (a draft that can't be made) rolls back, and must not take the row with it. The job commits
    only this row. Never raises: the caller is failing over."""
    try:
        frappe.enqueue(
            "helpdesk.ai_engine.log_failed_attempt",
            queue="short",
            now=frappe.flags.in_test,
            attempt={
                **row,
                "at": str(now_datetime()),
                "model": provider.model,
                "provider": provider.slot,
                "kind": error.kind,
                "status": error.status,
                "detail": error.detail,
            },
        )
    except Exception:
        # even the Error Log may be down: the caller fails over whatever happens here
        with contextlib.suppress(Exception):
            frappe.log_error("Failed to log AI usage")


def log_failed_attempt(attempt: dict):
    """The job behind `keep_failed_attempt`. `detail` was masked when the error was made."""
    log_usage(
        attempt["model"],
        _Usage(0, 0),
        ticket_name=attempt.get("ticket_name"),
        provider=attempt.get("provider"),
        job=attempt.get("job"),
        fallback=attempt.get("fallback"),
        duration_ms=attempt.get("duration_ms"),
        error=SimpleNamespace(
            kind=attempt.get("kind"),
            status=attempt.get("status"),
            detail=attempt.get("detail"),
        ),
        at=attempt.get("at"),
    )


def log_worker_usage(run: str, cost: dict | None, job: str, attempt: int = 1):
    """The Copilot worker's spend for a run, one row per stage: `cost` is one stage's
    totals ({tokens_in, tokens_cached, tokens_out, usd, model}) or {"stages": [...]}, each
    with its own `job`. A report sent again adds nothing (one row per run, job, attempt and
    model: a stage that moved to the fallback has a row for each)."""
    stages = (cost or {}).get("stages") if isinstance(cost, dict) else None
    for stage in stages if isinstance(stages, list) else [cost or {}]:
        if not isinstance(stage, dict) or not (
            stage.get("tokens_in") or stage.get("usd")
        ):
            continue
        stage_job = stage.get("job") if stage.get("job") in WORKER_JOBS else job
        key = f"{run}:{stage_job}:{attempt}" + (
            ":fallback" if stage.get("fallback") else ""
        )
        if frappe.db.exists("HDS AI Usage Log", {"stage_key": key}):
            continue
        tokens_in, cached = int(stage.get("tokens_in") or 0), int(
            stage.get("tokens_cached") or 0
        )
        frappe.get_doc(
            {
                "doctype": "HDS AI Usage Log",
                "ticket": frappe.db.get_value("HDS Copilot Run", run, "ticket"),
                "copilot_run": run,
                "job": stage_job,
                "stage_key": key,
                "provider": stage.get("section") or "Copilot worker",
                "model": str(stage.get("model") or "")[:140],
                "fallback": int(bool(stage.get("fallback"))),
                "source": "Copilot worker",
                "duration_ms": int(stage.get("ms") or 0) or None,
                "input_tokens": tokens_in - cached,
                "cache_read_tokens": cached,
                "output_tokens": int(stage.get("tokens_out") or 0),
                "estimated_cost_usd": float(stage.get("usd") or 0),
            }
        ).insert(ignore_permissions=True)


TRIAGE_TOKEN_BUDGETS = (4096, 8192)


def parse_json_answer(text: str) -> dict:
    """The JSON object in a model's answer, which may come in a code fence or with prose around it."""
    candidates = [text]
    if "```" in text:
        fenced = text.split("```")[1]
        candidates.append(fenced[4:] if fenced.startswith("json") else fenced)
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        # models like Kimi sometimes explain before or after the JSON
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return {"raw_response": text, "parse_error": True}


NUMBER = re.compile(r"\d+(?:\.\d+)?")


def fact_numbers(facts) -> set[str]:
    """Every number in the facts given to the model, for `invents_numbers`."""
    return set(NUMBER.findall(json.dumps(facts, default=str)))


def invents_numbers(text: str, known: set[str]) -> bool:
    """The model's text has a number that isn't in its facts, so it can't be trusted."""
    return bool(set(NUMBER.findall(text)) - known)


def call_haiku(system_prompt, user_message, ticket_name=None, job=None, images=None):
    """The cheap, always-on AI call behind triage, drafts and summaries.

    Tries the primary provider, then the fallback (docs/ai-providers.md), and
    skips one paused after a billing, key or model failure.

    Args:
            system_prompt: The instructions; mentioning JSON turns on OpenAI's JSON mode
            user_message: The content to work on
            ticket_name: Optional ticket name for usage logging
            job: The AI job (JOBS): its row in Models per job picks each section's model
            images: Optional [{media_type, data (base64)}] the model looks at too

    Returns:
            dict with keys: response (parsed JSON), usage (token counts), cost (USD)
    """
    providers = get_providers(job)
    if not providers:
        used_up = limit_reached(job)
        if used_up:
            frappe.throw(
                _(
                    "{0} has used its monthly token limit, so this AI job waits until next month, or until a System Manager raises the limit in AI models."
                ).format(used_up)
            )
        frappe.throw(_("AI isn't set up. Add an API key in Settings → AI providers."))
    from helpdesk import ai_gateway

    if providers[0].slot == ai_gateway.SLOT and not ai_gateway.alive():
        return _emergency(system_prompt, user_message, ticket_name, job, images)
    return _answer(providers, system_prompt, user_message, ticket_name, job, images)


def _answer(
    providers, system_prompt, user_message, ticket_name, job, images, emergency=False
):
    """The first provider that answers, in order; each failure is recorded and alerted."""
    ready = [provider for provider in providers if not circuit_open(provider)]
    if not ready:
        frappe.cache.set_value(OUTAGE_KEY, 1, expires_in_sec=STATUS_SECONDS)
        raise AIProviderError(providers[0], "paused", "")

    error = None
    deadline = monotonic() + CALL_SECONDS
    for index, provider in enumerate(ready):
        try:
            text, usage = complete(
                provider,
                system_prompt,
                user_message,
                ticket_name,
                deadline=deadline,
                job=job,
                fallback=provider is not providers[0],
                images=images,
            )
        except AIProviderError as e:
            error = e
            if not emergency and gateway_unusable(e):
                return _emergency(system_prompt, user_message, ticket_name, job, images)
            record_failure(e, ready[index + 1] if index + 1 < len(ready) else None)
            if not e.fails_over:
                raise
            continue
        record_success(provider)
        return {
            "response": parse_json_answer(text),
            "usage": {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0),
                "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0),
            },
            "cost": estimate_cost(provider.model, usage),
            "model": provider.model,
        }

    frappe.cache.set_value(OUTAGE_KEY, 1, expires_in_sec=STATUS_SECONDS)
    raise error


def _emergency(system_prompt, user_message, ticket_name, job, images):
    """The gateway can't be used: TBO Support's sections answer with its own keys (the owner's
    decision for Phase 37), and the managers are told once in 6 hours."""
    from helpdesk import ai_gateway

    chain = within_limits(section_chain(job))
    ai_gateway.mark_down(emergency=bool(chain))
    if not chain:
        frappe.throw(
            _(
                "The TBO AI gateway is not answering, and no emergency key is set in Settings → AI providers."
            )
        )
    return _answer(
        chain, system_prompt, user_message, ticket_name, job, images, emergency=True
    )


def create_investigation_session(
    system_prompt,
    tools,
    initial_messages,
    model=None,
) -> tuple[anthropic.Anthropic, object]:
    """Create an investigation session with Sonnet.

    Args:
            system_prompt: The investigation system prompt
            tools: List of tool definitions for the model
            initial_messages: Initial conversation messages
            model: Model to use (default Sonnet)

    Returns:
            Tuple of (client, initial_response)
    """
    client = get_client()
    if not model:
        _, model = get_models()

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=tools,
        messages=initial_messages,
    )

    return client, response


def continue_investigation(
    client,
    model,
    system_prompt,
    tools,
    messages,
):
    """Continue an investigation with tool results.

    Args:
            client: Anthropic client
            model: Model ID
            system_prompt: System prompt (cached)
            tools: Tool definitions
            messages: Full conversation including tool results

    Returns:
            API response
    """
    return client.messages.create(
        model=model,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=tools,
        messages=messages,
    )
