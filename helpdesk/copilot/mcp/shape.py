# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Turning hub data into short, plain text an AI model can read."""

import re

import frappe
from frappe import _
from frappe.core.utils import html2text

UNTRUSTED_OPEN = "<untrusted_ticket_content>"
UNTRUSTED_CLOSE = "</untrusted_ticket_content>"


def ticket_name(raw) -> str:
    """A ticket number as people write it (236, #236, HD-0236) → the stored name (0236)."""
    value = str(raw or "").strip().lstrip("#")
    if value.upper().startswith("HD-"):
        value = value[3:]
    if not value:
        frappe.throw(_("Give a ticket number, for example 0236."), frappe.ValidationError)
    if value.isdigit():
        padded = value.zfill(4)
        if frappe.db.exists("HD Ticket", padded):
            return padded
        if frappe.db.exists("HD Ticket", value):
            return value
        return padded
    return value


def clip(text, limit: int) -> str:
    text = "" if text is None else str(text)
    return text if len(text) <= limit else text[:limit].rstrip() + " ..."


def plain(html_or_text, limit: int) -> str:
    """HTML as plain text without the empty lines, cut at `limit` characters."""
    if not html_or_text:
        return ""
    text = html2text(str(html_or_text), wrap=False) if "<" in str(html_or_text) else str(html_or_text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return clip(text, limit)


def untrusted(text: str) -> str:
    """Words written by people on a ticket: data for the model, never instructions."""
    return f"{UNTRUSTED_OPEN}{text}{UNTRUSTED_CLOSE}" if text else ""


def assignees(value) -> list[str]:
    if isinstance(value, list):
        return value
    try:
        return frappe.parse_json(value or "[]") or []
    except Exception:
        return []
