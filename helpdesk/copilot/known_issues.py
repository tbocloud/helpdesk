# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Known issues (Phase 9): what Copilot remembers about an error after its ticket is closed.

One HDS Known Issue per error signature (`app | method | the error's last line`, digits as #),
across every site that runs the app: where it was seen, the root cause, the fix, and which sites
have that fix. The error watch makes and updates them; a diagnosis links its run to the errors the
worker read; a merged fix marks one Fixed.

A worker gets the known issues of its site in the run context. Another customer's issue reaches it
as code facts only (the error's type and method, the root cause, the fix): never a ticket's text,
records or the error's message, which may hold that customer's data (docs/tbo-copilot.md,
Known issues).
"""

import hashlib
import re

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, now_datetime

KNOWN_ISSUE = "HDS Known Issue"
DIGITS = re.compile(r"\d+")
ERROR_TYPE = re.compile(r"[A-Za-z_][\w.]*")
# a root cause on the customer's side: nothing to fix in the code, maybe a KB article
CUSTOMER_SIDE = ("question", "customer_mistake", "wrong_setting", "not_allowed_request")
RUN_SIGNATURES = "copilot:run-signatures:{}"
HAS_FIX = "copilot:has-fix:{}:{}:{}"
MAX_FOR_RUN = 10


def normalise(signature: str | None) -> str:
    """The signature without values: digits as # (row 12 and row 13 are one error)."""
    return " ".join(DIGITS.sub("#", signature or "").split())[:1000]


def key_of(signature: str | None) -> str:
    return hashlib.sha256(normalise(signature).encode()).hexdigest()[:32]


def parts(signature: str | None) -> dict:
    """`{app, method, last, error_type}` of `app | method | last line` ("?" for unknown is empty)."""
    app, _sep, rest = (signature or "").partition(" | ")
    method, _sep, last = rest.partition(" | ")
    head = last.split(":", 1)[0].strip() if ":" in last else ""
    return {
        "app": "" if app.strip() == "?" else app.strip(),
        "method": "" if method.strip() == "?" else method.strip(),
        "last": last.strip(),
        "error_type": head if ERROR_TYPE.fullmatch(head) else "",
    }


def title_of(signature: str) -> str:
    """The error's type and where it happens: code facts, never the message."""
    p = parts(signature)
    return _("{0} in {1}").format(
        p["error_type"] or _("An error"), p["method"] or p["app"] or _("unknown code")
    )[:140]


def find(signature: str):
    name = frappe.db.get_value(KNOWN_ISSUE, {"signature_key": key_of(signature)})
    return frappe.get_doc(KNOWN_ISSUE, name) if name else None


def repository_of(app: str, registry: str | None) -> str:
    """The app's repository (`owner/name`) from the site card, else from any card that runs it."""
    from helpdesk.copilot.fixes import _repo_name

    filters = {"app": app, "parenttype": "HDS Site Registry"}
    if registry:
        repo = frappe.db.get_value(
            "HDS Site App", {**filters, "parent": registry}, "repository"
        )
        if repo:
            return _repo_name(repo)
    repo = frappe.db.get_value(
        "HDS Site App", {**filters, "repository": ["is", "set"]}, "repository"
    )
    return _repo_name(repo) if repo else ""


def record(
    signature: str,
    registry: str | None = None,
    customer: str | None = None,
    ticket: str | None = None,
    count: int = 0,
    seen=None,
):
    """The signature's known issue, made the first time; the site's row counts it."""
    seen = get_datetime(seen) if seen else now_datetime()
    doc = find(signature)
    if not doc:
        p = parts(signature)
        doc = frappe.get_doc(
            {
                "doctype": KNOWN_ISSUE,
                "title": title_of(signature),
                "status": "Open",
                "app": p["app"][:140],
                "repository": repository_of(p["app"], registry) if p["app"] else "",
                "method": p["method"][:140],
                "error_type": p["error_type"][:140],
                "signature": normalise(signature),
                "signature_key": key_of(signature),
                "first_seen": seen,
                "last_seen": seen,
            }
        )
        try:
            doc.insert(ignore_permissions=True)
        except frappe.DuplicateEntryError:  # the watch and a diagnosis made it at the same time
            frappe.clear_last_message()
            doc = find(signature)
    if registry:
        row = next((r for r in doc.sites if r.registry == registry), None)
        if not row:
            row = doc.append(
                "sites",
                {
                    "registry": registry,
                    "customer": customer,
                    "first_seen": seen,
                    "count": 0,
                },
            )
        row.count = (row.count or 0) + max(int(count or 0), 0)
        row.last_seen = max(get_datetime(row.last_seen or seen), seen)
        row.ticket = ticket or row.ticket
        row.customer = customer or row.customer
    doc.last_seen = max(get_datetime(doc.last_seen or seen), seen)
    doc.save(ignore_permissions=True)
    return doc


# --- the fix and the sites that have it --------------------------------------------------------


def deployed_commit(issue, registry: str) -> str:
    return (
        frappe.db.get_value(
            "HDS Site App",
            {"parent": registry, "parenttype": "HDS Site Registry", "app": issue.app},
            "deployed_commit",
        )
        or ""
    )


def has_fix(issue, registry: str) -> bool | None:
    """Whether the site runs a commit that includes the fix; None when it can't be told
    (not fixed, no repository or commit, GitHub did not answer)."""
    from helpdesk.copilot import github

    merge = issue.get("merge_commit") or ""
    commit = deployed_commit(issue, registry)
    if issue.status != "Fixed" or not merge or not commit or not issue.repository:
        return None
    if commit.startswith(merge) or merge.startswith(commit):
        return True
    key = HAS_FIX.format(issue.repository, merge, commit)
    cached = frappe.cache.get_value(key, expires=True)
    if cached is not None:
        return bool(cached)
    try:
        status = github.compare(issue.repository, merge, commit)["status"]
    except Exception:
        return None
    if not status:
        return None
    found = status in ("ahead", "identical")  # the site's commit comes after the merge
    frappe.cache.set_value(key, int(found), expires_in_sec=86400)
    return found


def refresh_sites(issue):
    """Each site row's "has the fix", as far as it can be told."""
    for row in issue.sites:
        found = has_fix(issue, row.registry)
        row.has_fix = "" if found is None else ("Yes" if found else "No")


def on_merged(run):
    """A merged fix of a run linked to a known issue: the issue is Fixed by that merge."""
    name = run.get("known_issue") or frappe.db.get_value(
        "HD Ticket", run.ticket, "custom_known_issue"
    )
    if not name or not run.get("merge_commit"):
        return
    issue = frappe.get_doc(KNOWN_ISSUE, name)
    if issue.status == "Not a bug":
        return
    fix = fix_of(run)
    issue.update(
        {
            "status": "Fixed",
            "merge_commit": run.merge_commit,
            "fixed_at": now_datetime(),
            "fix_run": run.name,
            "fix_pull_request": fix.get("url") or issue.fix_pull_request,
            "fix_title": (fix.get("title") or issue.fix_title or "")[:140],
            "fix_files": "\n".join(fix.get("files") or [])[:2000] or issue.fix_files,
            "root_cause_category": run.root_cause_category or issue.root_cause_category,
        }
    )
    refresh_sites(issue)
    issue.save(ignore_permissions=True)


def fix_of(run) -> dict:
    """The fix's pull request: from the approval (Copilot's fixes), else the PR row."""
    from helpdesk.copilot import approvals

    approval = approvals.current(run) or (
        frappe.get_doc("HDS Copilot Approval", run.approval)
        if run.get("approval")
        else None
    )
    payload = frappe.parse_json(approval.payload or "{}") if approval else {}
    if payload:
        return {
            "url": payload.get("url") or approval.pr_url,
            "title": payload.get("title"),
            "files": [
                f.get("filename")
                for f in payload.get("files") or []
                if f.get("filename")
            ][:30],
        }
    if run.get("pull_request"):
        row = frappe.db.get_value(
            "HD Pull Request", run.pull_request, ["url", "title"], as_dict=True
        )
        if row:
            return {"url": row.url, "title": row.title, "files": []}
    return {}


# --- a diagnosis links its run ------------------------------------------------------------------


def remember_signatures(run: str, entries) -> None:
    """The error signatures a worker read from the site (`get_error_log`), for its diagnosis to name."""
    from helpdesk.copilot.verify import signature

    if not isinstance(entries, list):
        return
    key = RUN_SIGNATURES.format(run)
    seen = frappe.cache.get_value(key, expires=True) or []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("error"):
            found = signature(entry)
            if found not in seen:
                seen.append(found)
    frappe.cache.set_value(key, seen[-200:], expires_in_sec=2 * 86400)


def matching(run: str, reported: list) -> list[str]:
    """The signatures the site gave the run that the worker's report names: the same signature
    without values, or the same method and error type. Anything else is dropped, so memory holds
    only errors the site really had."""
    seen = frappe.cache.get_value(RUN_SIGNATURES.format(run), expires=True) or []
    chosen = []
    for text in reported or []:
        text = str(text or "")[:600]
        wanted = parts(text)
        for found in seen:
            got = parts(found)
            same = normalise(found) == normalise(text) or (
                wanted["method"]
                and wanted["error_type"]
                and (got["method"], got["error_type"])
                == (wanted["method"], wanted["error_type"])
            )
            if same and found not in chosen:
                chosen.append(found)
    return chosen[:5]


def link_run(run, reported: list | None = None):
    """The run's known issue: the ticket's (a watch ticket), else the errors its diagnosis names.
    A customer-side root cause makes a fresh issue "Not a bug". Never stops the routing."""
    frappe.db.savepoint("copilot_link_run")
    try:
        _link_run(run, reported)
    except Exception:
        frappe.db.rollback(save_point="copilot_link_run")
        frappe.log_error(title=f"Copilot could not link {run.name} to a known issue")


def _link_run(run, reported):
    names = []
    ticket_issue = frappe.db.get_value("HD Ticket", run.ticket, "custom_known_issue")
    if ticket_issue:
        names.append(ticket_issue)
    for found in matching(run.name, reported or []):
        doc = record(
            found,
            run.get("registry"),
            run.get("customer"),
            run.ticket,
            seen=now_datetime(),
        )
        if doc.name not in names:
            names.append(doc.name)
    if not names:
        return
    run.db_set("known_issue", names[0], update_modified=False)
    if not ticket_issue:
        frappe.db.set_value(
            "HD Ticket",
            run.ticket,
            "custom_known_issue",
            names[0],
            update_modified=False,
        )
    issue = frappe.get_doc(KNOWN_ISSUE, names[0])
    changed = {}
    if run.root_cause_category and not issue.root_cause_category:
        changed["root_cause_category"] = run.root_cause_category
    if run.root_cause_category in CUSTOMER_SIDE and issue.status == "Open":
        changed["status"] = "Not a bug"
    if changed:
        issue.db_set(changed, update_modified=False)


# --- what a worker, an agent and the chat see -----------------------------------------------------


def for_run(run) -> list[dict]:
    """Known issues for the worker to check first: the ticket's own, then those the site had in the
    last 30 days. Code facts only when the issue was never seen at this customer's sites."""
    names = []
    for name in (
        frappe.db.get_value("HD Ticket", run.ticket, "custom_known_issue"),
        run.get("known_issue"),
    ):
        if name and name not in names:
            names.append(name)
    if run.get("registry"):
        for name in frappe.get_all(
            "HDS Known Issue Site",
            filters={
                "registry": run.registry,
                "parenttype": KNOWN_ISSUE,
                "last_seen": [">=", add_days(now_datetime(), -30)],
            },
            pluck="parent",
            order_by="last_seen desc",
            limit=MAX_FOR_RUN * 2,
        ):
            if name not in names:
                names.append(name)
    return [
        facts(frappe.get_doc(KNOWN_ISSUE, name), run) for name in names[:MAX_FOR_RUN]
    ]


def facts(issue, run=None) -> dict:
    """One known issue as a worker may read it."""
    customer = run.get("customer") if run else None
    ours = [r for r in issue.sites if customer and r.customer == customer]
    here = next((r for r in ours if run and r.registry == run.get("registry")), None)
    found = has_fix(issue, run.registry) if run and run.get("registry") else None
    result = {
        "name": issue.name,
        "title": issue.title,
        "status": issue.status,
        "app": issue.app,
        "error_type": issue.error_type,
        "method": issue.method,
        "root_cause_category": issue.root_cause_category,
        "fix": {
            "pull_request": issue.fix_pull_request,
            "title": issue.fix_title,
            "files": [f for f in (issue.fix_files or "").splitlines() if f],
            "merge_commit": issue.merge_commit,
            "fixed_at": str(issue.fixed_at or ""),
        }
        if issue.status == "Fixed"
        else None,
        "this_site_has_the_fix": found,
        "came_back": issue.came_back or 0,
        "sites_seen": len(issue.sites),
    }
    if (
        ours
    ):  # this customer's own errors: the signature may name their data, so only for them
        result["signature"] = issue.signature
    if here:
        result["seen_here"] = {
            "first": str(here.first_seen or ""),
            "last": str(here.last_seen or ""),
            "count": here.count or 0,
        }
    return result


def card(run) -> dict | None:
    """The Copilot dialog's Known issue section (agents see every site)."""
    name = run.get("known_issue") or frappe.db.get_value(
        "HD Ticket", run.ticket, "custom_known_issue"
    )
    if not name or not frappe.db.exists(KNOWN_ISSUE, name):
        return None
    issue = frappe.get_doc(KNOWN_ISSUE, name)
    ticket = (
        frappe.db.get_value(
            "HD Ticket", run.ticket, ["status_category", "status"], as_dict=True
        )
        or frappe._dict()
    )
    return {
        "name": issue.name,
        "title": issue.title,
        "status": issue.status,
        "signature": issue.signature,
        "first_seen": str(issue.first_seen or "")[:16],
        "last_seen": str(issue.last_seen or "")[:16],
        "came_back": issue.came_back or 0,
        "fix": {
            "pull_request": issue.fix_pull_request,
            "title": issue.fix_title,
            "merge_commit": (issue.merge_commit or "")[:12],
            "fixed_at": str(issue.fixed_at or "")[:16],
        }
        if issue.status == "Fixed"
        else None,
        "sites": [
            {
                "site": frappe.db.get_value("HDS Site Registry", r.registry, "site_url")
                or r.registry,
                "customer": r.customer,
                "count": r.count or 0,
                "last_seen": str(r.last_seen or "")[:16],
                "ticket": r.ticket,
                "has_fix": r.has_fix or "",
            }
            for r in issue.sites
        ],
        "kb_article": issue.kb_article,
        "can_draft_kb": kb_refusal(run, issue, ticket) is None,
    }


# --- a KB article for a customer-side cause (decision 8) -------------------------------------------


def kb_refusal(run, issue, ticket=None) -> str | None:
    """Why no KB draft is offered now, or None when it is."""
    if issue.kb_article:
        return _("The known issue has its KB article already ({0}).").format(
            issue.kb_article
        )
    if run.root_cause_category not in CUSTOMER_SIDE:
        return _(
            "A KB article is offered for a cause on the customer's side, not for a code bug."
        )
    ticket = ticket or frappe.db.get_value(
        "HD Ticket", run.ticket, ["status_category", "status"], as_dict=True
    )
    if (ticket or {}).get("status_category") not in ("Resolved", "Closed") and (
        ticket or {}
    ).get("status") not in ("Resolved", "Closed"):
        return _(
            "Resolve the ticket first: the article is written from the team's answer."
        )
    return None


def draft_kb(run) -> dict:
    """A KB draft from the ticket's answer through the existing feature; an agent reviews and publishes it."""
    from helpdesk import kb_drafts

    issue = frappe.get_doc(
        KNOWN_ISSUE,
        run.get("known_issue")
        or frappe.db.get_value("HD Ticket", run.ticket, "custom_known_issue"),
    )
    reason = kb_refusal(run, issue)
    if reason:
        frappe.throw(reason)
    article = kb_drafts.draft_article(run.ticket)
    if not article:
        existing = frappe.db.get_value("HD Article", {"source_ticket": run.ticket})
        if not existing:
            frappe.throw(
                _(
                    "The AI didn't write a draft: an article may already cover it, or the answer wasn't clear enough."
                )
            )
        article = existing
    name = article if isinstance(article, str) else article.name
    issue.db_set("kb_article", name, update_modified=False)
    return {"article": name, "known_issue": issue.name}
