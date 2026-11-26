# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The AI gateway's usage, for AI models (Phase 31).

The desktop app's AI calls go through TBO's gateway (LiteLLM), not through TBO Support, so
its models are read from the gateway itself: every hour, with a read-only key, the calls of
today and yesterday are fetched and kept as totals per day, model and person. A message's text
is never asked for and never stored: only the model, who called, tokens, cost, time and whether
it failed.
"""

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
DAY = "HDS Gateway Usage Day"
PAGE_SIZE = 500
MAX_PAGES = 200
TIMEOUT = 30
LOGS_PATH = "/spend/logs/v2"


class GatewayError(Exception):
    pass


def configured(settings=None) -> bool:
    settings = settings or frappe.get_cached_doc(SETTINGS)
    return bool(settings.get("gateway_sync") and settings.get("gateway_url"))


def _key() -> str | None:
    from frappe.utils.password import get_decrypted_password

    return get_decrypted_password(
        SETTINGS, SETTINGS, "gateway_viewer_key", raise_exception=False
    )


def fetch_day(url: str, key: str, day) -> list[dict]:
    """Every call the gateway logged on `day`, page by page."""
    rows, page = [], 1
    while page <= MAX_PAGES:
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
            break
        page += 1
    return rows


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


def real_model(row: dict) -> str:
    """The model behind the gateway's name, without the provider's prefix:
    `openai/gpt-5.6-luna` is gpt-5.6-luna, `bedrock/converse/deepseek.v3.2` is deepseek.v3.2."""
    model = str(row.get("model") or "").strip()
    return model.rsplit("/", 1)[-1] if model else ""


def totals(rows: list[dict]) -> dict[tuple, dict]:
    """The day's calls as totals per (real model, the gateway's name for it, its provider,
    person). The desktop app sees only TBO's names (tbo-default, tbo-deepseek); the page shows
    the real model, so its calls add up with TBO Support's own calls to the same model."""
    out: dict[tuple, dict] = {}
    for row in rows:
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
                "day_key": f"{day}|{model}|{alias}|{person}"[:140],
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
    return {
        "on": bool(settings.get("gateway_sync")),
        "url": settings.get("gateway_url") or "",
        "key_set": bool(_key()),
        "synced_at": str(settings.get("gateway_synced_at") or "")[:16],
        "note": settings.get("gateway_sync_note") or "",
    }
