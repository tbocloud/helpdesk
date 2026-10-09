# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The MCP server's tools: who sees which, and how one call runs, is logged and is limited."""

import importlib
import json
import time

import frappe
from frappe import _
from frappe.utils import strip_html

from helpdesk.copilot import audit
from helpdesk.copilot.mcp.auth import WORKER

READ, WRITE, WORKER_TOOL = "read", "write", "worker"
TOOLS: dict[str, dict] = {}
# imported on first use, so every entry point (endpoint, tests, bench execute) sees all tools
TOOL_MODULES = (
    "helpdesk.copilot.mcp.tools_read",
    "helpdesk.copilot.mcp.tools_write",
    "helpdesk.copilot.mcp.tools_worker",
)
MAX_RESULT_CHARS = 100_000
SAVEPOINT = "copilot_mcp_tool"

# refusals the caller caused: a tool error the model can read, never an Error Log entry
EXPECTED_ERRORS = (
    frappe.PermissionError,
    frappe.ValidationError,
    frappe.DoesNotExistError,
    frappe.AuthenticationError,
)
JSON_TYPES = {
    "string": str,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def register_tool(
    name: str,
    *,
    kind: str,
    description: str,
    handler,
    properties: dict | None = None,
    required: list[str] | None = None,
    read_only: bool | None = None,
    open_world: bool = False,
):
    """Adds a tool; `kind` read and write are for people, worker for a Copilot run."""
    if kind not in (READ, WRITE, WORKER_TOOL):
        raise ValueError(f"Unknown tool kind: {kind}")
    TOOLS[name] = {
        "name": name,
        "kind": kind,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
            "additionalProperties": False,
        },
        "handler": handler,
        "read_only": kind == READ if read_only is None else read_only,
        "open_world": open_world,
    }


def visible(caller, tool: dict) -> bool:
    """People get read and write tools; a worker's run token gets worker tools only."""
    return (tool["kind"] == WORKER_TOOL) == (caller.kind == WORKER)


def load_tools() -> None:
    for module in TOOL_MODULES:
        importlib.import_module(module)


def definitions_for(caller) -> list[dict]:
    load_tools()
    return [
        {
            "name": tool["name"],
            "description": tool["description"],
            "inputSchema": tool["input_schema"],
            "annotations": {
                "readOnlyHint": tool["read_only"],
                "destructiveHint": False,
                "openWorldHint": tool["open_world"],
            },
        }
        for tool in TOOLS.values()
        if visible(caller, tool)
    ]


def call(caller, name: str, arguments) -> dict:
    """Runs one tool call as the caller and logs it; every outcome is an MCP tool result."""
    started = time.monotonic()
    load_tools()
    tool = TOOLS.get(name)
    status, is_error = "OK", False
    try:
        if not tool or not visible(caller, tool):
            frappe.throw(_("Unknown tool: {0}").format(name), frappe.ValidationError)
        audit.check_rate_limit(caller.user)
        arguments = check_arguments(tool["input_schema"], arguments)
        frappe.db.savepoint(SAVEPOINT)
        text = to_text(tool["handler"](caller, **arguments))
    except frappe.RateLimitExceededError as e:
        status, is_error, text = "Limited", True, message_of(e)
    except EXPECTED_ERRORS as e:
        _undo()
        status, is_error, text = "Refused", True, message_of(e)
    except Exception as e:
        _undo()
        frappe.log_error(title=f"Copilot MCP tool failed: {name}", message=frappe.get_traceback())
        status, is_error, text = "Error", True, f"{name} failed: {message_of(e)}"
    finally:
        frappe.local.message_log = []
    audit.log_call(
        caller,
        name,
        arguments if isinstance(arguments, dict) else {},
        status,
        round((time.monotonic() - started) * 1000),
        text,
    )
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _undo():
    try:
        frappe.db.rollback(save_point=SAVEPOINT)
    except Exception:
        pass  # a tool that called a customer site committed already (MCPClient), nothing to undo


def check_arguments(schema: dict, arguments) -> dict:
    """The arguments if they fit the tool's schema; a ValidationError naming the problem otherwise."""
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        frappe.throw(_("The arguments must be an object."), frappe.ValidationError)
    properties = schema["properties"]
    unknown = sorted(set(arguments) - set(properties))
    if unknown:
        frappe.throw(_("Unknown argument: {0}").format(", ".join(unknown)), frappe.ValidationError)
    missing = [key for key in schema["required"] if arguments.get(key) in (None, "")]
    if missing:
        frappe.throw(_("Missing argument: {0}").format(", ".join(missing)), frappe.ValidationError)
    checked = {}
    for key, value in arguments.items():
        if value is None:
            continue
        checked[key] = _check_value(key, properties[key], value)
    return checked


def _check_value(key: str, spec: dict, value):
    kind = spec.get("type")
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int | float) or int(value) != value:
            frappe.throw(_("{0} must be a whole number").format(key), frappe.ValidationError)
        value = int(value)
        low, high = spec.get("minimum"), spec.get("maximum")
        if (low is not None and value < low) or (high is not None and value > high):
            frappe.throw(_("{0} must be between {1} and {2}").format(key, low, high), frappe.ValidationError)
        return value
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, int | float):
            frappe.throw(_("{0} must be a number").format(key), frappe.ValidationError)
        return value
    expected = JSON_TYPES.get(kind)
    if expected and not isinstance(value, expected):
        frappe.throw(_("{0} must be a {1}").format(key, kind), frappe.ValidationError)
    if kind == "string":
        value = value.strip()
        if spec.get("maxLength") and len(value) > spec["maxLength"]:
            frappe.throw(
                _("{0} is longer than {1} characters").format(key, spec["maxLength"]),
                frappe.ValidationError,
            )
    if spec.get("enum") and value not in spec["enum"]:
        frappe.throw(_("{0} must be one of: {1}").format(key, ", ".join(spec["enum"])), frappe.ValidationError)
    return value


def to_text(result) -> str:
    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + f"... (cut at {MAX_RESULT_CHARS} characters)"
    return text


def message_of(error: Exception) -> str:
    """A short, plain message for the model: the error's text, else Frappe's last message."""
    text = str(error).strip()
    if not text and frappe.local.message_log:
        last = frappe.local.message_log[-1]
        if isinstance(last, str):
            try:
                last = json.loads(last)
            except ValueError:
                last = {"message": last}
        text = str((last or {}).get("message") or "")
    return strip_html(text).strip()[:480] or type(error).__name__
