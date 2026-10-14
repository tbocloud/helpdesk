"""Ticket intake: which incoming mails open a ticket, and how monitoring alerts group.

Half the support mailbox was noise: Grafana alerts (every FIRING and RESOLVED mail its
own ticket), Grafana's own account mail, weekly summaries and vendor newsletters. The
rules in HD Intake Settings (Settings → Ticket intake) decide, first match wins:

- **Ignore**: no ticket; the mail is logged (HD Intake Log).
- **Alert**: a ticket of type Alert, with no SLA and left out of Home and the SLA
  figures. Repeats of an open alert are added to it as a comment, and the monitor's
  RESOLVED mail closes it ("Resolved by monitor").
- **Merge into open alert**: only ever added to an open alert; never opens a ticket.

The built-in filter (helpdesk/email_filter.py: noreply@ senders and HD Settings'
ignored senders) runs after the rules, so a rule can still catch a monitor that
mails from a noreply address. See docs/ticket-intake.md.
"""

import re
from dataclasses import dataclass

import frappe
import requests
from frappe import _
from frappe.utils import escape_html, strip_html_tags

from helpdesk.automation import as_automation_user, automation_user
from helpdesk.consts import ALERT_TICKET_TYPE, MONITOR_RESOLVED_STATUS
from helpdesk.email_filter import is_unwanted_sender, sender_matches

SETTINGS = "HD Intake Settings"
LOG = "HD Intake Log"
IGNORE, ALERT, MERGE = "Ignore", "Alert", "Merge into open alert"
IGNORED, GROUPED, RESOLVED = "Ignored", "Grouped", "Resolved"
OPEN_CATEGORIES = ["Open", "Paused"]
BUILT_IN_FILTER = "Automated or ignored sender"
# "[FIRING:2, RESOLVED:1] DatasourceError tbocloud (critical)": the state, then the
# alert name and group labels, then Grafana's common labels in parentheses
ALERT_SUBJECT = re.compile(r"^\[(?P<state>[^\]]*)\]\s*(?P<rest>.*)$")
RESOLVED_STATES = {"resolved", "ok", "recovered", "up"}
MAX_KEY_LENGTH = 140
COMMENT_EXCERPT_CHARS = 1500
CLEANUP_LIMIT = 500
CLOSED = "Closed"

# seeded on install and by the intake patch; every rule stays editable in Settings
DEFAULT_RULES = (
    {
        "label": "Grafana alerts",
        "sender_pattern": "grafana.net",
        "subject_pattern": r"^\[(FIRING|RESOLVED)",
        "action": ALERT,
    },
    {
        "label": "Other monitoring alerts",
        "subject_pattern": r"^\[(FIRING|RESOLVED)",
        "action": ALERT,
    },
    {
        "label": "Grafana account mail",
        "sender_pattern": "grafana.com",
        "action": IGNORE,
    },
    {
        "label": "Grafana Cloud notices",
        "subject_pattern": r"verify your grafana|grafana stack is active",
        "action": IGNORE,
    },
    {
        "label": "Weekly energy points summary",
        "subject_pattern": r"^weekly energy points summary",
        "action": IGNORE,
    },
    {
        "label": "Vendor newsletters",
        "sender_pattern": "anthropic.com\ncanva.com\nfigma.com\nnotion.so\nlinkedin.com\n"
        "facebookmail.com\nmedium.com\nsubstack.com\nquora.com\nzoom.us",
        "action": IGNORE,
    },
)
PUBLIC_EMAIL_DOMAINS = (
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "yahoo.com",
    "yahoo.co.in",
    "ymail.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "zoho.com",
    "zohomail.com",
    "gmx.com",
    "mail.com",
    "yandex.com",
    "rediffmail.com",
)


@dataclass(frozen=True)
class Decision:
    action: str
    rule: str


@dataclass(frozen=True)
class AlertSubject:
    resolved: bool
    # the alert name and its group labels: the same for the alert's FIRING and RESOLVED mails
    key: str
    # the labels in parentheses, which change as single alerts in a group fire and resolve
    labels: frozenset


def decide(sender: str | None, subject: str | None) -> Decision | None:
    """The first enabled rule the mail matches, else the built-in filter, else None."""
    for rule in frappe.get_cached_doc(SETTINGS).rules:
        if rule.enabled and rule_matches(rule, sender, subject):
            return Decision(rule.action, rule.label)
    if is_unwanted_sender(sender):
        return Decision(IGNORE, _(BUILT_IN_FILTER))
    return None


def rule_matches(rule, sender: str | None, subject: str | None) -> bool:
    """Every pattern the rule has must match; a rule without patterns matches nothing."""
    if not (rule.sender_pattern or rule.subject_pattern):
        return False
    if rule.sender_pattern and not sender_matches(rule.sender_pattern, sender):
        return False
    if rule.subject_pattern:
        try:
            return bool(re.search(rule.subject_pattern, subject or "", re.IGNORECASE))
        except re.error:
            # HDIntakeSettings.validate rejects a bad pattern; one saved some other way
            # must not stop the mailbox
            return False
    return True


def parse_alert(subject: str | None) -> AlertSubject:
    """The alert's state, key and labels from a monitor's subject line.

    A state such as "FIRING:1, RESOLVED:1" still has something firing; only a state
    that is all resolved (RESOLVED, OK, RECOVERED, UP) closes the alert.
    """
    text = " ".join((subject or "").split())
    state, rest = "", text
    if match := ALERT_SUBJECT.match(text):
        state, rest = match["state"], match["rest"]
    parts = [p.split(":")[0].strip().lower() for p in state.split(",") if p.strip()]
    name, _paren, labels = rest.partition(" (")
    return AlertSubject(
        resolved=bool(parts) and all(p in RESOLVED_STATES for p in parts),
        key=name.strip().casefold()[:MAX_KEY_LENGTH],
        labels=frozenset(labels.rstrip(")").casefold().split()),
    )


def open_alert(alert: AlertSubject) -> str | None:
    """The open alert ticket this alert belongs to: same key, then the most labels in
    common, then the newest."""
    if not alert.key:
        return None
    candidates = frappe.get_all(
        "HD Ticket",
        filters={
            "alert_key": alert.key,
            "ticket_type": ALERT_TICKET_TYPE,
            "status_category": ("in", OPEN_CATEGORIES),
            "is_merged": 0,
        },
        fields=["name", "subject"],
        order_by="creation desc",
        limit_page_length=20,
    )
    if not candidates:
        return None
    best = max(
        candidates, key=lambda t: len(parse_alert(t.subject).labels & alert.labels)
    )
    return str(best.name)


def handle_new_mail(sender: str | None, subject: str | None, content: str | None):
    """Apply the rules to a new mail (not a reply). True when it was handled here and
    must not open a ticket; False lets Frappe open one (an Alert gets its type in
    HDTicket.apply_intake_rules)."""
    return handle_mail(decide(sender, subject), sender, subject, content)


def handle_mail(
    decision: Decision | None,
    sender: str | None,
    subject: str | None,
    content: str | None,
) -> bool:
    """`handle_new_mail` for a mail the rules were already applied to."""
    if not decision:
        return False
    if decision.action == IGNORE:
        log(IGNORED, decision.rule, sender, subject)
        return True
    alert = parse_alert(subject)
    target = open_alert(alert)
    if target:
        add_to_alert(target, alert, decision.rule, sender, subject, content)
        return True
    if decision.action == MERGE or alert.resolved:
        # nothing open to add it to, and a resolved or follow-up mail opens nothing
        log(IGNORED, decision.rule, sender, subject)
        return True
    return False


def add_to_alert(
    ticket: str,
    alert: AlertSubject,
    rule: str,
    sender: str | None,
    subject: str | None,
    content: str | None,
):
    """A repeat goes on the open alert as a comment; a resolved one also closes it."""
    excerpt = " ".join(strip_html_tags(content or "").split())[:COMMENT_EXCERPT_CHARS]
    add_comment(
        ticket,
        "<p><b>{0}</b> {1}</p>{2}".format(
            escape_html(_("Monitor update:")),
            escape_html(subject or ""),
            f"<p>{escape_html(excerpt)}</p>" if excerpt else "",
        ),
    )
    if alert.resolved:
        doc = frappe.get_doc("HD Ticket", ticket)
        doc.status = resolved_status()
        save_as_automation(doc)
        announce(ticket, _("Alert resolved: {0}").format(doc.subject))
    log(RESOLVED if alert.resolved else GROUPED, rule, sender, subject, ticket)


def resolved_status() -> str:
    """Resolved by monitor, or Closed on a site the intake patch hasn't set up yet."""
    if frappe.db.exists("HD Ticket Status", MONITOR_RESOLVED_STATUS):
        return MONITOR_RESOLVED_STATUS
    return CLOSED


def add_comment(ticket: str, content: str):
    comment = frappe.get_doc(
        {
            "doctype": "HD Ticket Comment",
            "reference_ticket": ticket,
            "commented_by": automation_user(),
            "content": content,
        }
    )
    comment.flags.skip_notifications = True
    comment.insert(ignore_permissions=True)


def save_as_automation(doc):
    with as_automation_user():
        doc.save(ignore_permissions=True)


def log(
    action: str,
    rule: str,
    sender: str | None,
    subject: str | None,
    ticket: str | None = None,
):
    frappe.get_doc(
        {
            "doctype": LOG,
            "action": action,
            "rule": rule,
            "sender": (sender or "")[:140],
            "subject": subject or "",
            "ticket": ticket,
        }
    ).insert(ignore_permissions=True)


def announce(ticket: str, text: str):
    """Post an alert opening or closing to the escalation channel, when Settings → Ticket
    intake asks for it; after the commit, so a rolled-back mail posts nothing."""
    from helpdesk.chat_notifications import is_enabled

    if not (
        frappe.db.get_single_value(SETTINGS, "post_alerts_to_channel") and is_enabled()
    ):
        return
    frappe.enqueue(
        "helpdesk.intake.post_to_channel",
        text=text,
        ticket=str(ticket),
        queue="short",
        enqueue_after_commit=True,
    )


def post_to_channel(text: str, ticket: str):
    from helpdesk.chat_notifications import ChatError, helpdesk_url
    from helpdesk.chat_notifications import post_to_channel as post

    try:
        post(text, helpdesk_url(f"/tickets/{ticket}"))
    except (ChatError, requests.RequestException) as e:
        # not log_error: the error digest posts to the same channel, which just failed
        frappe.logger("helpdesk").warning(f"Alert not posted to the channel: {e}")


# --- one-off cleanup: Settings → Ticket intake → Apply rules to open tickets ---


def plan_cleanup() -> list[dict]:
    """What applying the rules to the open tickets that came in by email would do, in
    the order the mails arrived. Nothing changes here; `apply_cleanup` runs the plan.

    Steps: `close` (an ignored sender, or a resolved alert with nothing open),
    `mark_alert` (the first ticket of an alert), `group` (a repeat, closed into the
    first) and `resolve` (the monitor resolved the first)."""
    tickets = frappe.get_all(
        "HD Ticket",
        filters={
            "status_category": ("in", OPEN_CATEGORIES),
            "email_account": ("is", "set"),
            "is_merged": 0,
        },
        fields=["name", "subject", "raised_by", "ticket_type"],
        order_by="creation asc",
        limit_page_length=CLEANUP_LIMIT,
    )
    plan, open_alerts = [], {}
    for ticket in tickets:
        decision = decide(ticket.raised_by, ticket.subject)
        if not decision:
            continue
        step = {
            "ticket": str(ticket.name),
            "subject": ticket.subject,
            "raised_by": ticket.raised_by,
            "rule": decision.rule,
            "target": None,
        }
        if decision.action == IGNORE:
            plan.append({**step, "action": "close"})
            continue
        alert = parse_alert(ticket.subject)
        target = open_alerts.get(alert.key)
        if target:
            plan.append({**step, "action": "group", "target": target["ticket"]})
            if alert.resolved:
                plan.append({**target, "action": "resolve", "rule": decision.rule})
                del open_alerts[alert.key]
        elif alert.resolved:
            plan.append({**step, "action": "close"})
        else:
            open_alerts[alert.key] = step
            if ticket.ticket_type != ALERT_TICKET_TYPE:
                plan.append({**step, "action": "mark_alert"})
    return plan


def apply_cleanup() -> dict:
    """Run `plan_cleanup` as the automation user. A step that fails is reported and
    the others still run."""
    plan = plan_cleanup()
    done, failed = 0, []
    for step in plan:
        try:
            run_step(step)
            done += 1
        except Exception as e:  # noqa: BLE001 - one bad ticket mustn't stop the rest
            failed.append(f"#{step['ticket']}: {e}")
    return {"plan": plan, "done": done, "failed": failed}


def run_step(step: dict):
    doc = frappe.get_doc("HD Ticket", step["ticket"])
    action = step["action"]
    if action == "close":
        add_comment(
            doc.name,
            escape_html(
                _("Closed by the intake rule “{0}”: this mail doesn't need a ticket.")
            ).format(escape_html(step["rule"])),
        )
        doc.status = CLOSED
    elif action == "resolve":
        doc.status = resolved_status()
    else:
        doc.ticket_type = ALERT_TICKET_TYPE
        doc.alert_key = parse_alert(doc.subject).key
    if action == "group":
        add_comment(
            step["target"],
            "<p><b>{0}</b> #{1}: {2}</p>".format(
                escape_html(_("Grouped here:")),
                escape_html(step["ticket"]),
                escape_html(doc.subject or ""),
            ),
        )
        doc.is_merged = 1
        doc.merged_with = step["target"]
        doc.status = CLOSED
    doc.flags.skip_feedback = True
    save_as_automation(doc)


# --- defaults ---


def ensure_intake_defaults():
    """The Alert ticket type, the Resolved by monitor status and, once, the default
    rules and public mail domains. Run on install and by the intake patch."""
    if not frappe.db.exists("HD Ticket Type", ALERT_TICKET_TYPE):
        frappe.get_doc(
            {
                "doctype": "HD Ticket Type",
                "name": ALERT_TICKET_TYPE,
                "description": "A monitoring alert (Grafana and the like). No SLA; not counted in Home or the SLA figures.",
            }
        ).insert(ignore_permissions=True)
    if not frappe.db.exists("HD Ticket Status", MONITOR_RESOLVED_STATUS):
        frappe.get_doc(
            {
                "doctype": "HD Ticket Status",
                "label_agent": MONITOR_RESOLVED_STATUS,
                "color": "Green",
                "enabled": 1,
                "category": "Resolved",
                "label_customer": "Resolved",
                "different_view": 1,
                "order": 6,
            }
        ).insert(ignore_permissions=True)
    settings = frappe.get_single(SETTINGS)
    if settings.rules or settings.public_email_domains:
        return
    for rule in DEFAULT_RULES:
        settings.append("rules", {"enabled": 1, **rule})
    settings.public_email_domains = "\n".join(PUBLIC_EMAIL_DOMAINS)
    settings.save(ignore_permissions=True)
