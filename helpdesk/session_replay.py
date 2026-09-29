# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Session replays recorded by helpdesk_client when a customer raises a ticket.

The client attaches two private files to its Support Ticket, which the ticket
puller copies onto the HD Ticket:

- ``session-replay.json.gz``: gzip of ``{"version", "minutes", "privacy",
  "started_at", "ended_at", "events": [rrweb events]}``
- ``session-diagnostics.json``: browser, page, app versions and recent errors

This module reads them back and turns the rrweb events into a short plain-text
timeline that agents and the triage model can read.
"""

import gzip
import json
import re
import zlib
from datetime import datetime, timezone
from urllib.parse import urlsplit

import frappe

REPLAY_PREFIX = "session-replay"
DIAGNOSTICS_PREFIX = "session-diagnostics"
REPLAY_FILE_NAME = re.compile(r"^session-replay\.json[0-9a-zA-Z]{0,16}\.gz$")
DIAGNOSTICS_FILE_NAME = re.compile(r"^session-diagnostics[0-9a-zA-Z]{0,16}\.json$")

# a stored replay is compressed; anything bigger than the puller would accept is not ours
MAX_REPLAY_FILE_BYTES = 100 * 1024 * 1024
# gzip bomb guard: refuse to inflate further than this
MAX_REPLAY_BYTES = 50 * 1024 * 1024
MAX_DIAGNOSTICS_BYTES = 1024 * 1024

MAX_TIMELINE_LINES = 150
MAX_LINE_CHARS = 200
MAX_LABEL_CHARS = 60
MAX_SUMMARY_ERRORS = 5
# a failed request this close to a frappe-call-error for the same method is the same failure
CALL_ERROR_MATCH_MS = 10_000
# how far up the DOM a click is traced looking for a button, link or field
MAX_ANCESTOR_HOPS = 12
TIMELINE_CACHE_SECONDS = 24 * 60 * 60

TIMELINE_HEADING = "What the customer did before raising the ticket (session timeline):"
DIAGNOSTICS_HEADING = "Customer's browser and app diagnostics:"

# rrweb EventType
FULL_SNAPSHOT = 2
INCREMENTAL_SNAPSHOT = 3
META = 4
CUSTOM = 5
PLUGIN = 6

# rrweb IncrementalSource
SOURCE_MUTATION = 0
SOURCE_MOUSE_INTERACTION = 2
SOURCE_INPUT = 5

# rrweb MouseInteractions
CLICK = 2
DOUBLE_CLICK = 4

# rrweb serialized NodeType
ELEMENT_NODE = 2
TEXT_NODE = 3

INTERACTIVE_TAGS = {"button", "a", "select", "option", "summary", "label"}
FORM_TAGS = {"input", "textarea", "select"}
INTERACTIVE_ROLES = {
    "button",
    "link",
    "menuitem",
    "tab",
    "option",
    "checkbox",
    "radio",
    "switch",
    "treeitem",
}
CONSOLE_ERROR_LEVELS = {"error", "assert"}
GZIP_MAGIC = b"\x1f\x8b"


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def is_replay_file(file_name: str | None) -> bool:
    """True for ``session-replay.json.gz``, also when Frappe suffixed it to keep
    the stored path unique (``session-replay.json3f2a1b.gz``)."""
    return bool(REPLAY_FILE_NAME.match(file_name or ""))


def is_diagnostics_file(file_name: str | None) -> bool:
    return bool(DIAGNOSTICS_FILE_NAME.match(file_name or ""))


def is_session_file(file_name: str | None) -> bool:
    return is_replay_file(file_name) or is_diagnostics_file(file_name)


def get_session_file(ticket: str, kind: str) -> dict | None:
    """The newest replay (kind="replay") or diagnostics file attached to `ticket`."""
    prefix, matches = (
        (REPLAY_PREFIX, is_replay_file)
        if kind == "replay"
        else (DIAGNOSTICS_PREFIX, is_diagnostics_file)
    )
    File = frappe.qb.DocType("File")
    rows = (
        frappe.qb.from_(File)
        .select(File.name, File.file_name, File.file_url, File.file_size)
        .where(File.attached_to_doctype == "HD Ticket")
        .where(File.attached_to_name == str(ticket))
        .where(File.file_name.like(f"{prefix}%"))
        .orderby(File.creation, order=frappe.qb.desc)
        .limit(10)
        .run(as_dict=True)
    )
    return next((row for row in rows if matches(row.file_name)), None)


def load_replay(ticket: str) -> dict | None:
    """The customer's recorded session for `ticket`, or None if absent or unreadable."""
    row = get_session_file(ticket, "replay")
    return read_replay_file(row) if row else None


def load_diagnostics(ticket: str) -> dict | None:
    """The browser/app diagnostics captured with the ticket, or None."""
    row = get_session_file(ticket, "diagnostics")
    return read_diagnostics_file(row) if row else None


def read_replay_file(row: dict) -> dict | None:
    try:
        if (row.get("file_size") or 0) > MAX_REPLAY_FILE_BYTES:
            raise ValueError(
                f"{row.get('file_name')} is larger than {MAX_REPLAY_FILE_BYTES} bytes"
            )
        replay = json.loads(inflate(read_file_bytes(row["name"]), MAX_REPLAY_BYTES))
        if not isinstance(replay, dict) or not isinstance(replay.get("events"), list):
            raise ValueError(f"{row.get('file_name')} has no events list")
        return replay
    except Exception:  # noqa: BLE001 - a bad replay must never break the ticket view or triage
        frappe.log_error(
            title=f"Unreadable session replay {row.get('name')}",
            message=frappe.get_traceback(),
        )
        return None


def read_diagnostics_file(row: dict) -> dict | None:
    try:
        if (row.get("file_size") or 0) > MAX_DIAGNOSTICS_BYTES:
            raise ValueError(
                f"{row.get('file_name')} is larger than {MAX_DIAGNOSTICS_BYTES} bytes"
            )
        diagnostics = json.loads(
            inflate(read_file_bytes(row["name"]), MAX_DIAGNOSTICS_BYTES)
        )
        if not isinstance(diagnostics, dict):
            raise ValueError(f"{row.get('file_name')} is not a JSON object")
        return diagnostics
    except Exception:  # noqa: BLE001 - diagnostics are optional context
        frappe.log_error(
            title=f"Unreadable session diagnostics {row.get('name')}",
            message=frappe.get_traceback(),
        )
        return None


def read_file_bytes(file_name: str) -> bytes:
    content = frappe.get_doc("File", file_name).get_content()
    return content.encode() if isinstance(content, str) else content


def inflate(content: bytes, limit: int) -> bytes:
    """Gunzip `content`, refusing to produce more than `limit` bytes.

    Content that is not gzip is returned as is: a proxy that set
    Content-Encoding on the download may already have inflated it.
    """
    if not content.startswith(GZIP_MAGIC):
        if len(content) > limit:
            raise ValueError(f"replay is larger than {limit} bytes")
        return content

    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    data = inflater.decompress(content, limit + 1)
    if len(data) > limit or inflater.unconsumed_tail:
        raise ValueError(f"replay inflates to more than {limit} bytes")
    if not inflater.eof:
        raise gzip.BadGzipFile("replay is truncated")
    return data


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


def get_timeline(ticket: str) -> str:
    """Timeline for `ticket`, cached per replay file (files never change once attached)."""
    replay_row = get_session_file(ticket, "replay")
    diagnostics_row = get_session_file(ticket, "diagnostics")
    if not replay_row and not diagnostics_row:
        return ""

    cache_key = "helpdesk:session_timeline:%s:%s" % (
        replay_row.name if replay_row else "",
        diagnostics_row.name if diagnostics_row else "",
    )
    cached = frappe.cache.get_value(cache_key)
    if cached is not None:
        return cached

    timeline = build_timeline(
        read_replay_file(replay_row) if replay_row else None,
        read_diagnostics_file(diagnostics_row) if diagnostics_row else None,
    )
    frappe.cache.set_value(cache_key, timeline, expires_in_sec=TIMELINE_CACHE_SECONDS)
    return timeline


def build_timeline(replay: dict | None, diagnostics: dict | None = None) -> str:
    """What the customer did, one step per line: ``t+12s clicked "Save"``.

    Timestamps are relative to the first recorded event. Long sessions keep
    their last steps, because what led up to raising the ticket matters most.
    """
    events = [
        e
        for e in (replay or {}).get("events") or []
        if isinstance(e, dict) and isinstance(e.get("timestamp"), (int, float))
    ]
    steps = TimelineBuilder(events).build()
    steps = merge_diagnostic_errors(steps, events, diagnostics)
    if not steps:
        return ""

    start = min(e["timestamp"] for e in events) if events else steps[0][0]
    lines = collapse_repeats(
        [f"{format_offset(ts - start)} {text}" for ts, text in steps]
    )
    if len(lines) > MAX_TIMELINE_LINES:
        omitted = len(lines) - (MAX_TIMELINE_LINES - 1)
        lines = [f"… {omitted} earlier steps omitted"] + lines[
            -(MAX_TIMELINE_LINES - 1) :
        ]
    return "\n".join(clip(line, MAX_LINE_CHARS) for line in lines)


class TimelineBuilder:
    """Walks rrweb events in order, keeping a node map so clicks resolve to labels."""

    def __init__(self, events: list[dict]):
        self.events = events
        self.nodes: dict[int, dict] = {}
        self.steps: list[tuple[float, str]] = []
        self.last_path = None
        self.last_input_label = None
        # (timestamp, method) of frappe-call-error events, and failed network
        # entries as (timestamp, text, url path) until they are checked against them
        self.call_errors: list[tuple[float, str]] = []
        self.failed_requests: list[tuple[float, str, str]] = []

    def build(self) -> list[tuple[float, str]]:
        for event in self.events:
            try:
                self.handle(event)
            except Exception:  # noqa: BLE001 - skip an odd event, keep the rest of the story
                continue
        self.add_uncovered_request_failures()
        return self.steps

    def add_uncovered_request_failures(self):
        """Network failures only where no frappe-call-error already tells the story."""
        added = False
        for ts, text, path in self.failed_requests:
            covered = any(
                abs(ts - error_ts) <= CALL_ERROR_MATCH_MS
                and method
                and path.endswith(f"/api/method/{method}")
                for error_ts, method in self.call_errors
            )
            if not covered:
                self.steps.append((ts, text))
                added = True
        if added:
            self.steps.sort(key=lambda step: step[0])

    def handle(self, event: dict):
        kind = event.get("type")
        data = event.get("data") or {}
        ts = event["timestamp"]
        if kind == FULL_SNAPSHOT:
            # a snapshot holds every live node; each recording segment starts
            # with one and may number its nodes afresh
            self.nodes = {}
            self.index_node(data.get("node"), None)
        elif kind == META:
            self.opened(ts, data.get("href"))
        elif kind == INCREMENTAL_SNAPSHOT:
            self.handle_incremental(ts, data)
        elif kind == CUSTOM:
            self.handle_custom(ts, data.get("tag"), data.get("payload") or {})
        elif kind == PLUGIN:
            self.handle_plugin(ts, data.get("plugin") or "", data.get("payload") or {})

    def add(self, ts: float, text: str, is_input: bool = False):
        self.steps.append((ts, text))
        if not is_input:
            self.last_input_label = None

    # -- DOM ----------------------------------------------------------------

    def index_node(self, root: dict | None, root_parent: int | None):
        # iterative: real pages nest deeper than Python's recursion limit allows
        stack = [(root, root_parent)]
        while stack:
            node, parent_id = stack.pop()
            if not isinstance(node, dict) or node.get("id") is None:
                continue
            node_id = node["id"]
            self.nodes[node_id] = {
                "type": node.get("type"),
                "tag": (node.get("tagName") or "").lower(),
                "attrs": dict(node.get("attributes") or {}),
                "text": node.get("textContent") or "",
                "parent": parent_id,
                "children": [],
            }
            parent = self.nodes.get(parent_id)
            if parent and node_id not in parent["children"]:
                parent["children"].append(node_id)
            # reversed so children pop, and so are listed, in document order
            stack.extend(
                (child, node_id) for child in reversed(node.get("childNodes") or [])
            )

    def apply_mutation(self, data: dict):
        for removed in data.get("removes") or []:
            parent = self.nodes.get(removed.get("parentId"))
            if parent and removed.get("id") in parent["children"]:
                parent["children"].remove(removed["id"])
        for added in data.get("adds") or []:
            self.index_node(added.get("node"), added.get("parentId"))
        for change in data.get("texts") or []:
            if change.get("id") in self.nodes:
                self.nodes[change["id"]]["text"] = change.get("value") or ""
        for change in data.get("attributes") or []:
            if change.get("id") in self.nodes:
                attrs = self.nodes[change["id"]]["attrs"]
                for key, value in (change.get("attributes") or {}).items():
                    if value is None:
                        attrs.pop(key, None)
                    else:
                        attrs[key] = value

    def ancestors(self, node_id):
        hops = 0
        while node_id in self.nodes and hops <= MAX_ANCESTOR_HOPS:
            yield node_id, self.nodes[node_id]
            node_id = self.nodes[node_id]["parent"]
            hops += 1

    def text_of(self, node_id, depth: int = 0) -> str:
        node = self.nodes.get(node_id)
        if not node or depth > 8:
            return ""
        if node["type"] == TEXT_NODE:
            return node["text"]
        if node["tag"] in ("script", "style", "svg"):
            return ""
        return " ".join(self.text_of(child, depth + 1) for child in node["children"])

    def field_label(self, node_id) -> str:
        """Label of the Frappe form field (``.frappe-control``) enclosing a node."""
        for _id, node in self.ancestors(node_id):
            attrs = node["attrs"]
            fieldname = attrs.get("data-fieldname")
            if not fieldname:
                continue
            label_id = self.find_descendant(_id, "control-label")
            label = tidy(self.text_of(label_id)) if label_id else ""
            return label or tidy(attrs.get("data-label") or "") or humanize(fieldname)
        return ""

    def find_descendant(self, node_id, css_class: str, depth: int = 0):
        node = self.nodes.get(node_id)
        if not node or depth > 6:
            return None
        if css_class in (node["attrs"].get("class") or "").split():
            return node_id
        for child in node["children"]:
            found = self.find_descendant(child, css_class, depth + 1)
            if found:
                return found
        return None

    def element_label(self, node_id) -> str:
        """The words a user would use for the thing they clicked or typed in."""
        target = None
        for _id, node in self.ancestors(node_id):
            if node["type"] != ELEMENT_NODE:
                continue
            attrs = node["attrs"]
            if (
                node["tag"] in INTERACTIVE_TAGS
                or node["tag"] in FORM_TAGS
                or attrs.get("role") in INTERACTIVE_ROLES
                or attrs.get("data-label")
            ):
                target = _id
                break
        target = target if target is not None else node_id
        node = self.nodes.get(target)
        if not node:
            return ""
        attrs = node["attrs"]

        if node["tag"] in FORM_TAGS:
            label = (
                self.field_label(target)
                or attrs.get("aria-label")
                or attrs.get("placeholder")
                or attrs.get("name")
            )
            return clip(tidy(label or ""), MAX_LABEL_CHARS)

        for candidate in (
            attrs.get("aria-label"),
            attrs.get("data-label"),
            self.text_of(target),
            attrs.get("title"),
            attrs.get("placeholder"),
        ):
            if candidate and tidy(candidate):
                return clip(tidy(candidate), MAX_LABEL_CHARS)
        return self.field_label(target) or (f"<{node['tag']}>" if node["tag"] else "")

    # -- events -------------------------------------------------------------

    def handle_incremental(self, ts: float, data: dict):
        source = data.get("source")
        if source == SOURCE_MUTATION:
            self.apply_mutation(data)
        elif source == SOURCE_MOUSE_INTERACTION and data.get("type") in (
            CLICK,
            DOUBLE_CLICK,
        ):
            label = self.element_label(data.get("id"))
            verb = "double-clicked" if data.get("type") == DOUBLE_CLICK else "clicked"
            self.add(ts, f'{verb} "{label}"' if label else f"{verb} on the page")
        elif source == SOURCE_INPUT:
            self.typed(ts, data)

    def typed(self, ts: float, data: dict):
        node = self.nodes.get(data.get("id")) or {"attrs": {}}
        label = self.element_label(data.get("id")) or "a field"
        input_type = (node["attrs"].get("type") or "").lower()
        if isinstance(data.get("isChecked"), bool) and input_type in (
            "checkbox",
            "radio",
        ):
            verb = "ticked" if data["isChecked"] else "unticked"
            self.add(ts, f'{verb} "{label}"')
            return
        # one line per field, however many keystrokes it took
        if label == self.last_input_label:
            return
        self.add(ts, f'typed in "{label}"', is_input=True)
        self.last_input_label = label

    def opened(self, ts: float, url: str | None):
        path = url_path(url)
        if not path or path == self.last_path:
            return
        self.last_path = path
        self.add(ts, f"opened {path}")

    def handle_custom(self, ts: float, tag: str | None, payload: dict):
        if not isinstance(payload, dict):
            payload = {}
        if tag == "frappe-route":
            route = payload.get("route")
            path = payload.get("url") or (
                "/app/" + "/".join(str(p) for p in route)
                if isinstance(route, list) and route
                else None
            )
            self.opened(ts, path)
        elif tag == "frappe-msgprint":
            title = tidy(strip_html(payload.get("title")))
            message = tidy(strip_html(payload.get("message")))
            shown = ": ".join(part for part in (title, message) if part)
            self.add(ts, f"message shown: {shown}" if shown else "message shown")
        elif tag == "frappe-call-error":
            self.call_errors.append((ts, str(payload.get("method") or "")))
            self.add(ts, "server error: " + describe_call_error(payload))
        elif tag == "raise-ticket":
            self.add(ts, "raised the ticket")

    def handle_plugin(self, ts: float, plugin: str, payload: dict):
        if not isinstance(payload, dict):
            return
        if "console" in plugin:
            level = (payload.get("level") or "").lower()
            if level in CONSOLE_ERROR_LEVELS:
                message = " ".join(unquote(p) for p in payload.get("payload") or [])
                self.add(ts, f"console error: {tidy(message)}")
        elif "network" in plugin:
            for request in payload.get("requests") or []:
                failure = describe_failed_request(request)
                if failure:
                    self.failed_requests.append((ts, *failure))


def describe_call_error(payload: dict) -> str:
    method = payload.get("method") or "request"
    verb = payload.get("http_method") or payload.get("verb")
    target = f"{verb} {method}" if verb else method
    exc = " ".join(
        str(part) for part in (payload.get("status"), payload.get("exc_type")) if part
    )
    message = tidy(strip_html(payload.get("message")))
    detail = ": ".join(part for part in (exc, message) if part)
    return f"{target} → {detail}" if detail else target


def describe_failed_request(request) -> tuple[str, str] | None:
    """(timeline text, url path) for a network entry that failed with an HTTP error.

    Entries without a status are common (resource timing hides it) and are skipped.
    """
    if not isinstance(request, dict):
        return None
    status = request.get("status", request.get("responseStatus"))
    try:
        status = int(status)
    except (TypeError, ValueError):
        return None
    if status < 400:
        return None
    path = url_path(request.get("name") or request.get("url")) or "request"
    method = (request.get("method") or "").upper()
    target = f"{method} {path}" if method else path
    return f"request failed: {target} → {status}", path


def merge_diagnostic_errors(
    steps: list[tuple[float, str]], events: list[dict], diagnostics: dict | None
) -> list[tuple[float, str]]:
    """Add errors that the diagnostics saw during the recording but the replay missed."""
    errors = (diagnostics or {}).get("recent_errors") or []
    if not isinstance(errors, list) or not errors:
        return steps

    stamps = [e["timestamp"] for e in events]
    window = (min(stamps), max(stamps)) if stamps else None
    seen_texts = {text for _ts, text in steps}
    seen = " ".join(seen_texts)
    extra = []
    for error in errors:
        if not isinstance(error, dict) or not isinstance(
            error.get("time"), (int, float)
        ):
            continue
        if window and not window[0] <= error["time"] <= window[1]:
            continue
        text = describe_diagnostic_error(error)
        message = tidy(strip_html(error.get("message")))
        if text in seen_texts or (message and message[:80] in seen):
            continue
        extra.append((error["time"], text))
    return sorted(steps + extra, key=lambda step: step[0])


def describe_diagnostic_error(error: dict) -> str:
    kind = error.get("kind")
    message = tidy(strip_html(error.get("message")))
    if kind == "call":
        return "server error: " + describe_call_error(error)
    if kind == "msgprint":
        return f"message shown: {message}"
    return f"console error: {message}"


def collapse_repeats(lines: list[str]) -> list[str]:
    """``t+3s clicked "Save"`` three times in a row becomes one line with ``(×3)``."""
    collapsed: list[list] = []
    for line in lines:
        text = line.split(" ", 1)[-1]
        if collapsed and collapsed[-1][1] == text:
            collapsed[-1][2] += 1
            continue
        collapsed.append([line, text, 1])
    return [
        line if count == 1 else f"{line} (×{count})" for line, _text, count in collapsed
    ]


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def summarize_diagnostics(diagnostics: dict | None) -> str:
    """A few lines on the customer's browser, page, versions and last errors."""
    if not isinstance(diagnostics, dict):
        return ""
    lines = []

    browser = describe_value(diagnostics.get("browser"))
    os_name = describe_value(diagnostics.get("os"))
    env = " on ".join(part for part in (browser, os_name) if part)
    for key, label in (("viewport", "viewport"), ("screen", "screen")):
        size = describe_size(diagnostics.get(key))
        if size:
            env = f"{env}, {label} {size}" if env else f"{label} {size}"
    if env:
        lines.append(f"Browser: {env}")

    page = tidy(diagnostics.get("title") or "")
    path = url_path(diagnostics.get("url"))
    if not path and isinstance(diagnostics.get("route"), list):
        path = "/app/" + "/".join(str(p) for p in diagnostics["route"])
    if page or path:
        lines.append("Page: " + (f"{page} ({path})" if page and path else page or path))

    versions = describe_versions(diagnostics.get("versions"))
    if versions:
        lines.append(f"Versions: {versions}")

    site = " · ".join(
        str(diagnostics[key])
        for key in ("site", "timezone", "language")
        if diagnostics.get(key)
    )
    if site:
        lines.append(f"Site: {site}")

    errors = [e for e in diagnostics.get("recent_errors") or [] if isinstance(e, dict)]
    if errors:
        lines.append("Recent errors:")
        for error in errors[-MAX_SUMMARY_ERRORS:]:
            when = format_clock(error.get("time"))
            text = describe_diagnostic_error(error)
            lines.append(
                clip(f"- {when} {text}" if when else f"- {text}", MAX_LINE_CHARS)
            )

    return "\n".join(clip(line, MAX_LINE_CHARS * 2) for line in lines)


def describe_versions(versions) -> str:
    if not isinstance(versions, dict) or not versions:
        return ""
    # the two versions support asks about first
    order = sorted(
        versions,
        key=lambda app: (app not in ("erpnext", "frappe"), app != "erpnext", app),
    )
    return ", ".join(f"{app} {versions[app]}" for app in order[:8])


def describe_value(value) -> str:
    if isinstance(value, dict):
        return tidy(
            " ".join(str(v) for v in (value.get("name"), value.get("version")) if v)
        )
    return tidy(str(value)) if value else ""


def describe_size(size) -> str:
    if isinstance(size, dict) and size.get("w") and size.get("h"):
        return f"{size['w']}×{size['h']}"
    return ""


# ---------------------------------------------------------------------------
# Triage + API
# ---------------------------------------------------------------------------


def get_session_replay_info(ticket: str) -> dict:
    """Everything the agent UI shows for a ticket's session replay. Caller checks permission."""
    replay_row = get_session_file(ticket, "replay")
    diagnostics_row = get_session_file(ticket, "diagnostics")
    diagnostics = read_diagnostics_file(diagnostics_row) if diagnostics_row else None
    available = bool(replay_row or diagnostics)
    return {
        "available": available,
        "replay_url": replay_row.file_url if replay_row else None,
        "diagnostics": diagnostics,
        "summary": summarize_diagnostics(diagnostics),
        "timeline": get_timeline(ticket) if available else "",
    }


def build_triage_context(ticket: str, max_chars: int) -> str:
    """Session timeline + diagnostics for the triage prompt, at most `max_chars` long."""
    timeline = get_timeline(ticket)
    summary = summarize_diagnostics(load_diagnostics(ticket))
    if not timeline and not summary:
        return ""

    parts = []
    if timeline:
        budget = max(max_chars - len(summary) - 200, max_chars // 2)
        if len(timeline) > budget:
            # keep whole lines from the end: the steps just before the ticket matter most
            tail = timeline[-budget:]
            timeline = "…\n" + tail.split("\n", 1)[-1]
        parts.append(f"{TIMELINE_HEADING}\n{timeline}")
    if summary:
        parts.append(f"{DIAGNOSTICS_HEADING}\n{summary}")
    return "\n\n".join(parts)[:max_chars]


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def format_offset(ms: float) -> str:
    seconds = max(int(round(ms / 1000)), 0)
    if seconds < 60:
        return f"t+{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    return f"t+{minutes}m{seconds:02d}s"


def format_clock(ms) -> str:
    if not isinstance(ms, (int, float)):
        return ""
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
            "%H:%M:%S UTC"
        )
    except (OverflowError, OSError, ValueError):
        return ""


def url_path(url) -> str:
    """``https://erp.example.com/app/sales-invoice/new?x=1`` → ``/app/sales-invoice/new``."""
    if not url or not isinstance(url, str):
        return ""
    parts = urlsplit(url.strip())
    path = parts.path or "/"
    return path if parts.scheme or url.startswith("/") else url.strip()


def strip_html(value) -> str:
    if not value:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
    return frappe.utils.strip_html_tags(value)


def tidy(value: str) -> str:
    return clip(re.sub(r"\s+", " ", value or "").strip(), MAX_LABEL_CHARS * 3)


def clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def humanize(fieldname: str) -> str:
    return fieldname.replace("_", " ").strip().title()


def unquote(value) -> str:
    """rrweb's console plugin JSON-stringifies each argument; show the plain text."""
    if not isinstance(value, str):
        return str(value)
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return json.loads(value)
        except ValueError:
            return value[1:-1]
    return value
