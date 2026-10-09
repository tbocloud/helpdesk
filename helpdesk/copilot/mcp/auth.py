# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Who is calling the hub's MCP server.

A person signs in with their own API key (`Authorization: token key:secret`).
Frappe checks the key before the endpoint runs, so here we only decide whether
that user may use the server: an enabled agent, never Administrator. There
are no sessions: every request carries its header and is checked again.
"""

from dataclasses import dataclass

import frappe
from frappe import _

AUTHORIZATION = "Authorization"
RUN_TOKEN_HEADER = "X-Copilot-Run-Token"
PERSON, WORKER = "person", "worker"


@dataclass(frozen=True)
class Caller:
    user: str
    kind: str = PERSON
    run: str | None = None


def identify() -> Caller:
    return identify_from(
        frappe.get_request_header(AUTHORIZATION),
        frappe.get_request_header(RUN_TOKEN_HEADER),
        frappe.session.user,
    )


def identify_from(authorization: str | None, run_token: str | None, session_user: str | None) -> Caller:
    if authorization and run_token:
        frappe.throw(_("Send either an API key or a run token, not both."), frappe.AuthenticationError)
    if run_token:
        return worker_caller(run_token)
    if not authorization:
        # a browser session is not enough: the brief asks for the person's own key
        frappe.throw(
            _("Sign in with your own API key: Authorization: token API_KEY:API_SECRET"),
            frappe.AuthenticationError,
        )
    return person_caller(session_user)


def person_caller(user: str | None) -> Caller:
    if not user or user == "Guest":
        frappe.throw(_("The API key was not accepted."), frappe.AuthenticationError)
    if user == "Administrator":
        frappe.throw(
            _("Administrator may not use the MCP server; sign in with your own key."),
            frappe.PermissionError,
        )
    if not frappe.db.get_value("User", user, "enabled"):
        frappe.throw(_("This user is disabled."), frappe.AuthenticationError)
    if not is_agent_user(user):
        frappe.throw(_("Only TBO Support agents may use the MCP server."), frappe.PermissionError)
    return Caller(user=user)


def is_agent_user(user: str) -> bool:
    """`user` is an agent: helpdesk.utils.is_agent asks about the session user's admin rights instead."""
    roles = set(frappe.get_roles(user))
    return bool(roles & {"Agent", "Agent Manager"}) or bool(frappe.db.exists("HD Agent", {"name": user}))


def worker_caller(run_token: str) -> Caller:
    frappe.throw(_("Run tokens are not accepted by this server yet."), frappe.AuthenticationError)
