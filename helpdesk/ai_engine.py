# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The hub's AI calls: OpenAI and Anthropic-compatible providers with failover,
prompt caching and token tracking (docs/ai-providers.md)."""

import json
import re
import time
from dataclasses import dataclass, field

import anthropic
import frappe
from frappe import _
from frappe.utils import format_datetime, now_datetime

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
# a slow answer counts as a failure, so the fallback still answers inside a job's time
REQUEST_TIMEOUT = 120
# the Anthropic SDK retries a 429 or 5xx itself; once is enough when a fallback waits
SDK_MAX_RETRIES = 1
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

    @property
    def label(self) -> str:
        return f"{self.slot} ({self.model})"

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


def provider_order(settings=None) -> list[str]:
    """The primary section, then the other one when failover is on."""
    settings = settings or get_hub_settings()
    primary = settings.get("primary_ai_provider") or ANTHROPIC_SLOT
    if not settings.get("ai_failover"):
        return [primary]
    return [primary, *(slot for slot in SLOTS if slot != primary)]


def get_providers() -> list[AIProvider]:
    """The providers call_haiku tries, in order; sections without a key are left out."""
    settings = get_hub_settings()
    providers = configured_providers(settings)
    return [providers[slot] for slot in provider_order(settings) if providers[slot]]


def wants_json(system_prompt: str) -> bool:
    """The caller asks for JSON. OpenAI's JSON mode also needs the word in the prompt."""
    return "json" in (system_prompt or "").lower()


def classify(status: int, detail: str) -> str:
    """The kind of failure behind an HTTP status and the provider's message."""
    text = (detail or "").lower()
    if status == 402 or (
        status in (403, 429) and any(word in text for word in BILLING_WORDS)
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
    provider: AIProvider, system_prompt: str, user_message: str, max_tokens: int
):
    """One /chat/completions call, through requests so there is no openai SDK
    to depend on. Returns (text, _Usage, ran_out_of_tokens).

    Only the OpenAI section gets a token budget and JSON mode; other
    OpenAI-compatible endpoints may not know them. No temperature is sent:
    newer OpenAI models refuse anything but the default.
    """
    import requests

    body = {
        "model": provider.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    }
    if provider.kind == "OpenAI":
        # reasoning models count their thinking in this budget too
        body["max_completion_tokens"] = max_tokens
        if wants_json(system_prompt):
            body["response_format"] = {"type": "json_object"}
    try:
        response = requests.post(
            f"{provider.base_url}/chat/completions",
            json=body,
            headers={
                "Authorization": f"Bearer {provider.api_key}",
                "Content-Type": "application/json",
            },
            timeout=REQUEST_TIMEOUT,
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

    data = response.json()
    choice = (data.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content") or ""
    usage = data.get("usage") or {}
    return (
        text,
        _Usage(usage.get("prompt_tokens"), usage.get("completion_tokens")),
        choice.get("finish_reason") == "length",
    )


def _anthropic_messages(
    provider: AIProvider, system_prompt: str, user_message: str, max_tokens: int
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
            messages=[{"role": "user", "content": user_message}],
            timeout=REQUEST_TIMEOUT,
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
):
    """One answer from one provider, each attempt logged; AIProviderError if it fails.

    Thinking models (Kimi, OpenAI's reasoning models) spend part of the budget
    thinking and can run out before writing the answer: they get room, then more once.
    """
    call = _openai_chat if provider.speaks_openai else _anthropic_messages
    for max_tokens in budgets or TRIAGE_TOKEN_BUDGETS:
        text, usage, ran_out = call(provider, system_prompt, user_message, max_tokens)
        log_usage(
            provider.model, usage, ticket_name=ticket_name, provider=provider.slot
        )
        if text.strip() or not ran_out:
            break
    return text, usage


# --- failover state: circuit breaker, status and alerts (Redis, site-prefixed) ---


def circuit_open(provider: AIProvider) -> bool:
    return bool(frappe.cache.get_value(CIRCUIT_KEY.format(provider.slot), expires=True))


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
            CIRCUIT_KEY.format(provider.slot),
            error.kind,
            expires_in_sec=CIRCUIT_SECONDS,
        )
    if error.kind in TRANSIENT_KINDS:
        return
    since = (provider_down(provider.slot) or {}).get("since") or str(now_datetime())
    frappe.cache.set_value(
        DOWN_KEY.format(provider.slot),
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
        frappe.cache.make_key(ALERT_KEY.format(provider.slot)),
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
        [CIRCUIT_KEY.format(provider.slot), DOWN_KEY.format(provider.slot)]
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
    started = time.monotonic()
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
                "value": f"{round((time.monotonic() - started) * 1000)} ms",
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
):
    """Log API usage to HDS AI Usage Log. Without `provider` it is an
    investigation's call: those always run on an Anthropic-compatible provider."""
    try:
        frappe.get_doc(
            {
                "doctype": "HDS AI Usage Log",
                "session": session_name,
                "ticket": ticket_name,
                "model": model,
                "provider": provider or ANTHROPIC_SLOT,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0),
                "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0),
                "estimated_cost_usd": estimate_cost(model, usage),
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error("Failed to log AI usage")


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


def call_haiku(system_prompt, user_message, ticket_name=None):
    """The cheap, always-on AI call behind triage, drafts and summaries.

    Tries the primary provider, then the fallback (docs/ai-providers.md), and
    skips one paused after a billing, key or model failure.

    Args:
            system_prompt: The instructions; mentioning JSON turns on OpenAI's JSON mode
            user_message: The content to work on
            ticket_name: Optional ticket name for usage logging

    Returns:
            dict with keys: response (parsed JSON), usage (token counts), cost (USD)
    """
    providers = get_providers()
    if not providers:
        frappe.throw(_("AI isn't set up. Add an API key in Settings → AI providers."))
    ready = [provider for provider in providers if not circuit_open(provider)]
    if not ready:
        frappe.cache.set_value(OUTAGE_KEY, 1, expires_in_sec=STATUS_SECONDS)
        raise AIProviderError(providers[0], "paused", "")

    error = None
    for index, provider in enumerate(ready):
        try:
            text, usage = complete(provider, system_prompt, user_message, ticket_name)
        except AIProviderError as e:
            error = e
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
        }

    frappe.cache.set_value(OUTAGE_KEY, 1, expires_in_sec=STATUS_SECONDS)
    raise error


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
