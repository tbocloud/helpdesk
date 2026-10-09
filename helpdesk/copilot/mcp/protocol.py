# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""JSON-RPC 2.0 and MCP constants for the hub's MCP server (adapted from helpdesk_client/mcp/protocol.py)."""

JSONRPC_VERSION = "2.0"
# newest first: a client asking for one of these gets it back, anything else gets the newest
SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
SERVER_NAME = "tbo-support-hub"
SERVER_TITLE = "TBO Support"
SERVER_VERSION = "1.0.0"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
AUTH_REQUIRED = -32001
FORBIDDEN = -32003


def make_response(req_id, result: dict) -> dict:
    return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": result}


def make_error(req_id, code: int, message: str, data=None) -> dict:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "error": error}


def negotiate_version(requested) -> str:
    return requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
