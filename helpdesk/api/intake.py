"""Settings → Ticket intake: HD Intake Settings plus HD Settings' built-in mail filter,
for System Managers and Agent Managers (docs/ticket-intake.md)."""

import frappe
from frappe import _
from frappe.query_builder.functions import Count

from helpdesk.consts import TRIAGE_CATEGORIES
from helpdesk.intake import LOG, SETTINGS, apply_cleanup, plan_cleanup
from helpdesk.tasky.permissions import is_tasky_admin

FIELDS = (
    "post_alerts_to_channel",
    "apply_triage",
    "default_team",
    "match_customer_by_domain",
    "public_email_domains",
    "feedback_on_close",
)
FILTER_FIELDS = ("ignore_automated_emails", "ignored_email_senders")
RULE_FIELDS = ("enabled", "label", "sender_pattern", "subject_pattern", "action")
ROUTE_FIELDS = ("category", "team", "ticket_type")
RECENT_LOGS = 20


def check_admin():
    # only_for is skipped in tests, so check the roles directly
    if not is_tasky_admin():
        frappe.throw(
            _("Only System Managers and Agent Managers can change ticket intake."),
            frappe.PermissionError,
        )


@frappe.whitelist()
def get_settings() -> dict:
    check_admin()
    return payload()


@frappe.whitelist(methods=["POST"])
def save_settings(values: dict) -> dict:
    check_admin()
    doc = frappe.get_single(SETTINGS)
    doc.update({f: values[f] for f in FIELDS if f in values})
    if "rules" in values:
        doc.set("rules", [pick(r, RULE_FIELDS) for r in values["rules"] or []])
    if "routes" in values:
        doc.set("routes", [pick(r, ROUTE_FIELDS) for r in values["routes"] or []])
    doc.save(ignore_permissions=True)
    filter_values = {f: values[f] for f in FILTER_FIELDS if f in values}
    if filter_values:
        frappe.db.set_single_value("HD Settings", filter_values)
        frappe.clear_document_cache("HD Settings", "HD Settings")
    return payload()


@frappe.whitelist()
def preview_cleanup() -> dict:
    """What Apply rules to open tickets would do; nothing changes."""
    check_admin()
    return {"plan": plan_cleanup()}


@frappe.whitelist(methods=["POST"])
def apply_rules_to_open_tickets() -> dict:
    """Run the cleanup the preview showed. Never runs on its own."""
    check_admin()
    return apply_cleanup()


def pick(row: dict, fields: tuple) -> dict:
    return {f: row.get(f) for f in fields}


def payload() -> dict:
    doc = frappe.get_single(SETTINGS)
    hd_settings = frappe.get_cached_doc("HD Settings")
    return {
        "settings": {
            **{f: doc.get(f) for f in FIELDS},
            **{f: hd_settings.get(f) for f in FILTER_FIELDS},
            "rules": [pick(r.as_dict(), RULE_FIELDS) for r in doc.rules],
            "routes": [pick(r.as_dict(), ROUTE_FIELDS) for r in doc.routes],
        },
        "categories": list(TRIAGE_CATEGORIES),
        "teams": teams(),
        "ticket_types": frappe.get_all(
            "HD Ticket Type", filters={"disabled": 0}, pluck="name", order_by="name"
        ),
        "recent": frappe.get_all(
            LOG,
            fields=["action", "rule", "sender", "subject", "ticket", "creation"],
            order_by="creation desc",
            limit_page_length=RECENT_LOGS,
        ),
    }


def teams() -> list[dict]:
    """Each team with its member count and whether its round robin runs, so the page
    can warn about a team that would leave routed tickets unassigned."""
    team = frappe.qb.DocType("HD Team")
    member = frappe.qb.DocType("HD Team Member")
    rule = frappe.qb.DocType("Assignment Rule")
    rows = (
        frappe.qb.from_(team)
        .left_join(member)
        .on(member.parent == team.name)
        .left_join(rule)
        .on(rule.name == team.assignment_rule)
        .select(
            team.name,
            team.disabled,
            rule.disabled.as_("rule_disabled"),
            team.assignment_rule,
            Count(member.user).as_("members"),
        )
        .groupby(team.name, team.disabled, rule.disabled, team.assignment_rule)
        .orderby(team.name)
        .run(as_dict=True)
    )
    return [
        {
            "name": r.name,
            "members": r.members,
            "disabled": bool(r.disabled),
            "rotation": bool(r.assignment_rule) and not r.rule_disabled,
        }
        for r in rows
    ]
