# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The TBO AI gateway (LiteLLM): its usage for AI models (Phase 31), and every AI call (Phase 37).

- Usage: every hour, with a read-only key, the desktop app's calls of today and yesterday are
  fetched and kept as totals per day, model and person. A message's text is never asked for and
  never stored: only the model, who called, tokens, cost, time and whether it failed.
- Every call (Phase 37, "Use the gateway for every AI call"): TBO Support's calls go to the
  gateway with TBO Support's own gateway key, and the AI models page writes the providers'
  keys (as gateway credentials) and the models into the gateway through its admin API. When
  the gateway doesn't answer, TBO Support answers with its emergency key and the managers are
  told (helpdesk.ai_engine).
"""

import contextlib
import hashlib
import json

import frappe
import requests
from frappe import _
from frappe.utils import (
    add_days,
    cint,
    flt,
    get_datetime,
    getdate,
    now_datetime,
    nowdate,
)

SETTINGS = "HDS Hub Settings"
DESKTOP_SETTINGS = "TBO Desktop Settings"
DAY = "HDS Gateway Usage Day"
# how TBO Support's calls name the gateway in the usage log and the provider list
SLOT = "TBO AI gateway"
ALIVE_PATH = "/health/liveliness"
ALIVE_KEY = "ai_gateway:alive"
ALIVE_SECONDS = 60
DOWN_KEY = "ai_gateway:down_since"
DOWN_ALERT_KEY = "ai_gateway:down_alerted"
DOWN_ALERT_SECONDS = 6 * 60 * 60
# the desktop app's keys (tbo_desktop makes them as "desktop:<sign-in>"); the others are TBO
# Support's and the worker's, whose calls TBO Support logs itself
DESKTOP_ALIAS = "desktop:"
MODEL_ID_PREFIX = "tbo-support:"
PAGE_SIZE = 500
MAX_PAGES = 200
TIMEOUT = 30
LOGS_PATH = "/spend/logs/v2"


class GatewayError(Exception):
    def __init__(self, message: str = "", status: int | None = None):
        super().__init__(message)
        # the gateway's HTTP status, when it answered at all
        self.status = status


def configured(settings=None) -> bool:
    settings = settings or frappe.get_cached_doc(SETTINGS)
    return bool(settings.get("gateway_sync") and settings.get("gateway_url"))


def _key() -> str | None:
    from frappe.utils.password import get_decrypted_password

    return get_decrypted_password(
        SETTINGS, SETTINGS, "gateway_viewer_key", raise_exception=False
    )


def _password(doctype: str, field: str) -> str:
    from frappe.utils.password import get_decrypted_password

    try:
        return (
            get_decrypted_password(doctype, doctype, field, raise_exception=False) or ""
        )
    except Exception:
        return ""


def base_url(settings=None) -> str:
    settings = settings or frappe.get_cached_doc(SETTINGS)
    return (settings.get("gateway_url") or "").strip().rstrip("/")


def call_key() -> str:
    """TBO Support's own gateway key, for its calls."""
    return _password(SETTINGS, "gateway_key")


def admin_key() -> str:
    """The key that may write providers and models: TBO Support's own, else the one TBO Desktop
    Settings holds on the same site."""
    key = _password(SETTINGS, "gateway_admin_key")
    if key or not frappe.db.exists("DocType", DESKTOP_SETTINGS):
        return key
    return _password(DESKTOP_SETTINGS, "gateway_admin_key")


def for_all(settings=None) -> bool:
    """Every TBO Support call goes through the gateway (Phase 37)."""
    settings = settings or frappe.get_cached_doc(SETTINGS)
    return bool(settings.get("gateway_for_all") and base_url(settings) and call_key())


def remember(key: str, value, seconds: int) -> None:
    """A short-lived flag, kept in Redis only. Frappe 15 keeps a request's own copy of a cached value
    and doesn't update it when a value with an expiry is written; that copy is dropped here, and the
    flag is read with `expires=True`, so a call sees a change made earlier in the same request."""
    frappe.cache.set_value(key, value, expires_in_sec=seconds)
    frappe.local.cache.pop(frappe.cache.make_key(key), None)


def alive(fresh: bool = False) -> bool:
    """Whether the gateway answers its health check; asked again at most once a minute."""
    if not fresh:
        cached = frappe.cache.get_value(ALIVE_KEY, expires=True)
        if cached is not None:
            return bool(cint(cached))
    try:
        ok = requests.get(base_url() + ALIVE_PATH, timeout=5).ok
    except requests.RequestException:
        ok = False
    remember(ALIVE_KEY, 1 if ok else 0, ALIVE_SECONDS)
    return ok


KEY_WORKS_KEY = "ai_gateway:key_works"


def key_works() -> bool:
    """Whether the gateway takes TBO Support's own key (its model list answers); asked again
    at most once a minute."""
    cached = frappe.cache.get_value(KEY_WORKS_KEY, expires=True)
    if cached is not None:
        return bool(cint(cached))
    try:
        ok = requests.get(
            base_url() + "/v1/models",
            headers={"Authorization": f"Bearer {call_key()}"},
            timeout=10,
        ).ok
    except requests.RequestException:
        ok = False
    remember(KEY_WORKS_KEY, 1 if ok else 0, ALIVE_SECONDS)
    return ok


def mark_down(emergency: bool | None = None) -> None:
    """The gateway can't be used: remember since when, and tell the managers once in 6 hours,
    saying whether TBO Support's emergency key answers meanwhile."""
    since = frappe.cache.get_value(DOWN_KEY)
    if not since:
        since = str(now_datetime())[:16]
        frappe.cache.set_value(DOWN_KEY, since)
    if frappe.cache.get_value(DOWN_ALERT_KEY, expires=True):
        return
    frappe.cache.set_value(DOWN_ALERT_KEY, 1, expires_in_sec=DOWN_ALERT_SECONDS)
    if emergency is None:
        from helpdesk.ai_engine import configured_providers

        emergency = any(configured_providers().values())
    if emergency:
        subject = _(
            "The TBO AI gateway is not answering since {0}. TBO Support answers with its emergency key; the Copilot worker and the desktop app wait until the gateway answers."
        ).format(since)
    else:
        subject = _(
            "The TBO AI gateway is not answering since {0}, and TBO Support has no emergency key: its AI waits too, like the Copilot worker's and the desktop app's."
        ).format(since)
    _alert(subject)


def _admin(
    method: str, path: str, payload: dict | None = None, missing_ok=False
) -> dict:
    """One admin call. A key or a provider's answer never reaches an error message."""
    key = admin_key()
    if not key:
        raise GatewayError(_("No gateway admin key is set."))
    try:
        response = requests.request(
            method,
            base_url() + path,
            json=payload,
            headers={"Authorization": f"Bearer {key}"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise GatewayError(type(e).__name__) from None
    if missing_ok and response.status_code in (400, 404):
        return {}
    if response.status_code in (401, 403):
        raise GatewayError(_("the gateway refused the admin key"))
    if not response.ok:
        raise GatewayError(f"HTTP {response.status_code}", response.status_code)
    try:
        return response.json()
    except ValueError:
        return {}


def make_call_key() -> str:
    """TBO Support's own gateway key, made with the admin key, so nobody copies one by hand. Its
    alias names this site and the time (an alias is unique on the gateway, and any alias but a
    desktop one keeps these calls out of the desktop app's usage)."""
    alias = f"tbo-support:{frappe.local.site}:{now_datetime().strftime('%Y%m%d%H%M%S')}"
    reply = _admin(
        "POST",
        "/key/generate",
        {"key_alias": alias, "metadata": {"made_by": "TBO Support"}},
    )
    key = reply.get("key") if isinstance(reply, dict) else None
    if not key:
        raise GatewayError(_("the gateway made no key"))
    return key


def save_credential(name: str, values: dict) -> None:
    """A provider's key (and address) as a gateway credential its models refer to. Changed in
    place, so a refused change leaves the working credential as it was; written new when there
    is none yet (or the gateway can't change one in place)."""
    body = {
        "credential_name": name,
        "credential_values": values,
        "credential_info": {"written_by": "TBO Support"},
    }
    # the gateway merges a change into what it has: without an address of its own, an earlier
    # address would stay, so that credential is written new instead
    if "api_base" in values:
        try:
            _admin("PATCH", f"/credentials/{name}", body)
            return
        except GatewayError as e:
            if e.status not in (404, 405):
                raise
    _admin("DELETE", f"/credentials/{name}", missing_ok=True)
    _admin("POST", "/credentials", body)


def delete_credential(name: str) -> None:
    _admin("DELETE", f"/credentials/{name}", missing_ok=True)


def model_id(name: str) -> str:
    return MODEL_ID_PREFIX + name


def _deployment(name: str, params: dict, key: str | None) -> dict:
    return {
        "model_name": name,
        "litellm_params": params,
        "model_info": {"id": model_id(key or name), "written_by": "TBO Support"},
    }


def save_model(
    name: str, params: dict, key: str | None = None, previous: dict | None = None
) -> None:
    """A model the gateway serves under `name`; written again from scratch each time. `key`
    tells apart several models under one name (a desktop level: its model and its backup).
    `previous` is what the gateway served under this id until now: the gateway takes no second
    model with the same id, so the old one goes first, and it is written back when the gateway
    refuses the new one, so a failed save doesn't leave the name without its model."""
    delete_model(key or name)
    try:
        _admin("POST", "/model/new", _deployment(name, params, key))
    except GatewayError as e:
        if not previous:
            raise
        # a POST that timed out may still have been stored: take it off, or the write-back
        # would meet the same id
        with contextlib.suppress(GatewayError):
            delete_model(key or name)
        try:
            _admin("POST", "/model/new", _deployment(name, previous, key))
        except GatewayError:
            raise GatewayError(
                _(
                    "{0}; the model it had could not be written back either: use Write all to the gateway once it answers"
                ).format(str(e))
            ) from None
        raise


def delete_model(key: str) -> None:
    _admin("POST", "/model/delete", {"id": model_id(key)}, missing_ok=True)


def watch() -> str:
    """Every 5 minutes while every call goes through the gateway: tells the managers when it
    stops answering (once in 6 hours) and when it answers again. Never raises."""
    try:
        if not for_all():
            return ""
        if alive(fresh=True):
            since = frappe.cache.get_value(DOWN_KEY)
            if not since:
                return "up"
            frappe.cache.delete_value([DOWN_KEY, DOWN_ALERT_KEY])
            _alert(
                _(
                    "The TBO AI gateway answers again (it did not since {0}). TBO Support's calls go through it again."
                ).format(since)
            )
            return "back"
        mark_down()
        return "down"
    except Exception:
        with contextlib.suppress(Exception):
            frappe.log_error(title="TBO AI gateway not checked")
        return ""


def _alert(subject: str) -> None:
    from helpdesk.ai_engine import send_provider_alert

    send_provider_alert(subject)


def fetch_day(url: str, key: str, day) -> list[dict]:
    """Every call the gateway logged on `day`, page by page. A day with more pages than
    MAX_PAGES is refused, so its totals are never replaced with a part of its calls."""
    rows = []
    for page in range(1, MAX_PAGES + 1):
        try:
            response = requests.get(
                url.rstrip("/") + LOGS_PATH,
                params={
                    "start_date": f"{day} 00:00:00",
                    "end_date": f"{day} 23:59:59",
                    "page": page,
                    "page_size": PAGE_SIZE,
                },
                headers={"Authorization": f"Bearer {key}"},
                timeout=TIMEOUT,
            )
        except requests.RequestException as e:
            # only the kind: the text can hold the address and the key
            raise GatewayError(type(e).__name__) from None
        if response.status_code in (401, 403):
            raise GatewayError(_("the gateway refused the key"))
        if not response.ok:
            raise GatewayError(f"HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError:
            raise GatewayError(_("the gateway's answer was not JSON")) from None
        data = body.get("data") if isinstance(body, dict) else body
        if not isinstance(data, list):
            raise GatewayError(_("the gateway's answer had no list of calls"))
        rows += [r for r in data if isinstance(r, dict)]
        pages = cint(body.get("total_pages")) if isinstance(body, dict) else 0
        if len(data) < PAGE_SIZE or (pages and page >= pages):
            return rows
    raise GatewayError(
        _("{0} has more than {1} calls, more than are read at once").format(
            day, MAX_PAGES * PAGE_SIZE
        )
    )


def _percentile(values: list[int], share: float) -> int | None:
    values = sorted(v for v in values if v)
    if not values:
        return None
    return values[min(len(values) - 1, max(0, round(share * (len(values) - 1))))]


def _failed(row: dict) -> str | None:
    """The error's class when the call failed, else None."""
    metadata = row.get("metadata")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except ValueError:
            metadata = {}
    info = (metadata or {}).get("error_information") or {}
    if str(row.get("status") or "").lower() == "failure" or info.get("error_class"):
        return str(info.get("error_class") or info.get("error_code") or "Error")[:60]
    return None


def _duration_ms(row: dict) -> int | None:
    if row.get("request_duration_ms"):
        return cint(row["request_duration_ms"])
    try:
        start, end = get_datetime(row.get("startTime")), get_datetime(
            row.get("endTime")
        )
        return max(0, round((end - start).total_seconds() * 1000))
    except Exception:
        return None


def _key_alias(row: dict) -> str:
    """The alias of the gateway key that made the call, when the log says it."""
    metadata = row.get("metadata")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except ValueError:
            metadata = {}
    alias = (metadata or {}).get("user_api_key_alias") or row.get("key_alias") or ""
    return str(alias).strip()


def real_model(row: dict) -> str:
    """The model behind the gateway's name, without the provider's prefix:
    `openai/gpt-5.6-luna` is gpt-5.6-luna; an older Bedrock row's `bedrock/converse/deepseek.v3.2`
    is deepseek.v3.2."""
    model = str(row.get("model") or "").strip()
    return model.rsplit("/", 1)[-1] if model else ""


def totals(rows: list[dict]) -> dict[tuple, dict]:
    """The day's calls as totals per (real model, the gateway's name for it, its provider,
    person). The desktop app sees only TBO's names (tbo-default, tbo-deepseek); the page shows
    the real model, so its calls add up with TBO Support's own calls to the same model."""
    out: dict[tuple, dict] = {}
    for row in rows:
        key_alias = _key_alias(row)
        if key_alias and not key_alias.startswith(DESKTOP_ALIAS):
            continue
        alias = str(row.get("model_group") or "").strip()
        model = real_model(row) or alias
        if not model:
            continue
        alias = "" if alias == model else alias
        provider = str(row.get("custom_llm_provider") or "").strip()
        person = str(row.get("user") or row.get("end_user") or "").strip()
        t = out.setdefault(
            (model, alias, provider, person),
            {
                "requests": 0,
                "failures": 0,
                "errors": {},
                "input_tokens": 0,
                "output_tokens": 0,
                "spend_usd": 0.0,
                "times": [],
            },
        )
        t["requests"] += 1
        t["input_tokens"] += cint(row.get("prompt_tokens"))
        t["output_tokens"] += cint(row.get("completion_tokens"))
        t["spend_usd"] += flt(row.get("spend"))
        error = _failed(row)
        if error:
            t["failures"] += 1
            t["errors"][error] = t["errors"].get(error, 0) + 1
        else:
            ms = _duration_ms(row)
            if ms:
                t["times"].append(ms)
    return out


def day_key(day: str, model: str, alias: str, provider: str, person: str) -> str:
    """A row's unique key: the day and a digest of everything its totals are grouped by, so
    rows that differ only in the provider, or after the 140 characters a field keeps, never
    share one."""
    identity = json.dumps([model, alias, provider, person])
    return f"{day}|{hashlib.sha256(identity.encode()).hexdigest()}"


def store_day(day, rows: list[dict]) -> int:
    """Replaces `day`'s totals with what the gateway says now, so reading again never doubles."""
    day = str(getdate(day))
    frappe.db.delete(DAY, {"day": day})
    found = totals(rows)
    for (model, alias, provider, person), t in found.items():
        frappe.get_doc(
            {
                "doctype": DAY,
                "day": day,
                "model": model[:140],
                "gateway_alias": alias[:140],
                "gateway_provider": provider[:140],
                "gateway_user": person[:140],
                "day_key": day_key(day, model, alias, provider, person),
                "requests": t["requests"],
                "failures": t["failures"],
                "error_classes": json.dumps(t["errors"]) if t["errors"] else None,
                "input_tokens": t["input_tokens"],
                "output_tokens": t["output_tokens"],
                "spend_usd": round(t["spend_usd"], 4),
                "p50_ms": _percentile(t["times"], 0.5),
                "p95_ms": _percentile(t["times"], 0.95),
            }
        ).insert(ignore_permissions=True)
    return len(found)


def sync(days: int = 2) -> dict:
    """Scheduled hourly: today and yesterday from the gateway. Quiet when it is not set up; a
    failure is noted on the settings and shown on the page, never raised to the scheduler."""
    settings = frappe.get_doc(SETTINGS)
    if not configured(settings):
        return {"ok": False, "note": _("The gateway is not set up.")}
    key = _key()
    if not key:
        return _note(False, _("No read-only key is saved."))
    url = settings.gateway_url
    try:
        calls = 0
        for back in range(max(1, min(cint(days), 31))):
            day = add_days(getdate(nowdate()), -back)
            rows = fetch_day(url, key, day)
            store_day(day, rows)
            calls += len(rows)
    except GatewayError as e:
        return _note(False, _("Not read: {0}").format(str(e)))
    return _note(True, _("{0} calls read.").format(calls))


def _note(ok: bool, note: str) -> dict:
    frappe.db.set_single_value(
        SETTINGS,
        {
            "gateway_sync_note": note[:300],
            **({"gateway_synced_at": now_datetime()} if ok else {}),
        },
        update_modified=False,
    )
    return {"ok": ok, "note": note}


def day_rows(days: int, model: str | None = None) -> list:
    filters = {"day": [">=", add_days(getdate(nowdate()), -(days - 1))]}
    if model:
        filters["model"] = model
    return frappe.get_all(
        DAY,
        filters=filters,
        fields=[
            "day",
            "model",
            "gateway_alias",
            "gateway_provider",
            "gateway_user",
            "requests",
            "failures",
            "error_classes",
            "spend_usd",
            "p50_ms",
            "p95_ms",
        ],
        limit=0,
    )


def status() -> dict:
    settings = frappe.get_cached_doc(SETTINGS)
    everything = bool(settings.get("gateway_for_all"))
    return {
        "on": bool(settings.get("gateway_sync")),
        "url": settings.get("gateway_url") or "",
        "key_set": bool(_key()),
        "synced_at": str(settings.get("gateway_synced_at") or "")[:16],
        "note": settings.get("gateway_sync_note") or "",
        "for_all": everything,
        "call_key_set": bool(call_key()),
        "admin_key_set": bool(_password(SETTINGS, "gateway_admin_key")),
        "admin_key_from_desktop": not _password(SETTINGS, "gateway_admin_key")
        and bool(admin_key()),
        "down_since": (frappe.cache.get_value(DOWN_KEY) or "") if everything else "",
    }
