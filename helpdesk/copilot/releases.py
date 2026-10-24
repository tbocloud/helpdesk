# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Releases (Phase 7): every merge into a branch a customer site runs goes out the same way.

Every ten minutes `watch` reads the tip of each branch that a Production site
card deploys through Press, for the repositories listed in HDS Copilot
Settings → Releases. Commits the bench does not run yet become a release: an
HDS Deploy Request without a Copilot run, holding the commits and the pull
requests that brought them, the task and ticket they close, and the
customers' sites on that bench. A release still waiting for CI or for its
approval takes in later commits; one already approved is followed by a new
release. Copilot's own merged fixes keep their own path (the run's Deploy).
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from helpdesk.copilot import deploy, github, press
from helpdesk.copilot import settings as copilot_settings
from helpdesk.copilot.github import GitHubError
from helpdesk.copilot.press import PressError

DEPLOY = deploy.DEPLOY
# a release still takes in later commits until it is approved
GROWING = ("Waiting for CI", "Waiting for approval")
MAX_COMMITS = 100
SEEN_KEY = "copilot_release_seen"
TROUBLE_HOURS = 6


def enabled() -> bool:
    return bool(copilot_settings.get_settings().get("releases_enabled"))


def repositories() -> set[str]:
    """The repositories in the pipeline, as `owner/name` in lower case."""
    from helpdesk.copilot.fixes import _repo_name

    text = copilot_settings.get_settings().get("release_repositories") or ""
    return {_repo_name(line) for line in text.splitlines() if line.strip()}


def targets() -> dict[tuple[str, str, str], list[dict]]:
    """(repository, branch, bench) → the Production sites on that bench that run the branch."""
    from helpdesk.copilot.fixes import _repo_name

    wanted = repositories()
    if not wanted:
        return {}
    cards = {
        card.name: card
        for card in frappe.get_all(
            "HDS Site Registry",
            filters={
                "environment": "Production",
                "press_site": ["is", "set"],
                "press_release_group": ["is", "set"],
            },
            fields=["name", "customer_name", "press_site", "press_release_group"],
        )
        if card.press_site != deploy.hub_site()
    }
    found = {}
    for row in frappe.get_all(
        "HDS Site App",
        filters={"parenttype": "HDS Site Registry", "parent": ["in", list(cards)]},
        fields=["parent", "app", "repository", "branch", "deployed_commit"],
        order_by="parent asc",
    ):
        repo, card = _repo_name(row.repository), cards[row.parent]
        if repo not in wanted or not row.branch:
            continue
        found.setdefault((repo, row.branch, card.press_release_group), []).append(
            {
                "registry": card.name,
                "customer": card.customer_name,
                "site": card.press_site,
                "app": row.app,
                "deployed_commit": row.deployed_commit or "",
            }
        )
    return found


# --- the cron -----------------------------------------------------------------------


def watch():
    """Cron: new commits on the deployed branches become releases, one branch at a time."""
    if not enabled():
        return
    for key, sites in targets().items():
        try:
            look(key, sites)
            frappe.db.commit()  # one branch at a time - nosemgrep
        except GitHubError as e:
            # not read this time (GitHub down, or the App not installed there): said once in a
            # while; look() reads GitHub before it writes anything, so nothing is half done
            _trouble(key, e.message)
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title=_("Copilot release of {0} {1}").format(key[0], key[1])
            )


def look(key: tuple[str, str, str], sites: list[dict]) -> str | None:
    """Makes or grows the release of one branch on one bench; its name, or None when nothing is new."""
    repo, branch, group = key
    head = github.branch_head(repo, branch)
    if not head or _seen(key) == head:
        return None
    growing = latest(key, GROWING)
    if growing and growing.apps[0].to_commit == head:
        return _remember(key, head)
    in_flight = None if growing else latest(key, deploy.OPEN)
    if growing:
        base = growing.apps[0].from_commit
    elif in_flight:
        base = in_flight.apps[0].to_commit
    else:
        base = running_commit(group, sites)
    if not base or _same(base, head):
        return _remember(key, head)
    compared = github.compare(repo, base, head)
    if compared["status"] in ("identical", "behind"):
        return _remember(key, head)
    changes = commit_changes(repo, branch, compared["commits"][-MAX_COMMITS:])
    if not growing and all(change.get("run") for change in changes):
        return _remember(
            key, head
        )  # only Copilot's merged fixes: their runs deploy them
    doc = (
        grow(growing, head, changes)
        if growing
        else create(key, sites, base, head, changes)
    )
    _remember(key, head)
    return doc.name


def latest(key: tuple[str, str, str], statuses: tuple):
    """The newest release of the branch on the bench in one of `statuses`."""
    repo, branch, group = key
    name = frappe.db.get_value(
        DEPLOY,
        {
            "repository": repo,
            "branch": branch,
            "release_group": group,
            "status": ["in", statuses],
        },
        "name",
        order_by="creation desc",
    )
    return frappe.get_doc(DEPLOY, name) if name else None


def running_commit(group: str, sites: list[dict]) -> str:
    """What the bench runs now: Press's answer, or the site card's when Press can't be asked."""
    app = sites[0]["app"]
    if press.configured():
        try:
            info = press.deploy_information(group)
            row = next(
                (
                    a
                    for a in info.get("apps") or []
                    if (a.get("app") or a.get("name")) == app
                ),
                None,
            )
            if row and (current := press.app_commits(row)[0]):
                return current
        except PressError:
            pass
    return next((s["deployed_commit"] for s in sites if s["deployed_commit"]), "")


def commit_changes(repo: str, branch: str, commits: list[dict]) -> list[dict]:
    """Each commit with the pull request that merged it into `branch`, its task and, for Copilot's fixes, the run."""
    from helpdesk.github_sync import TASK_REF

    found = []
    for commit in commits:
        sha = commit.get("sha") or ""
        info = commit.get("commit") or {}
        entry = {
            "sha": sha,
            "title": ((info.get("message") or "").splitlines() or [""])[0][:200],
            "author": (commit.get("author") or {}).get("login")
            or ((info.get("author") or {}).get("email") or "").lower(),
        }
        pull = next(
            (
                p
                for p in github.commit_pulls(repo, sha)
                if p.get("merged_at") and (p.get("base") or {}).get("ref") == branch
            ),
            None,
        )
        if pull:
            number = int(pull["number"])
            entry["pull"] = {
                "number": number,
                "title": (pull.get("title") or "")[:200],
                "url": pull.get("html_url") or "",
                "author": (pull.get("user") or {}).get("login") or "",
            }
            refs = TASK_REF.findall(
                "\n".join(
                    [
                        pull.get("title") or "",
                        pull.get("body") or "",
                        (pull.get("head") or {}).get("ref") or "",
                    ]
                )
            )
            if refs:
                entry["task"] = refs[0].upper()
            if run := frappe.db.get_value(
                "HDS Copilot Approval",
                {"repo": repo, "number": number, "status": "Merged"},
                "run",
            ):
                entry["run"] = run
        found.append(entry)
    return found


def _fields(changes: list[dict], others: list[str], sites: list[dict]) -> dict:
    """What a release says about its commits: where they came from, who wrote them, what they close."""
    pushes = [c for c in changes if not c.get("pull")]
    task = next(
        (
            c["task"]
            for c in changes
            if c.get("task") and frappe.db.exists("Task", c["task"])
        ),
        None,
    )
    authors = []
    for change in changes:
        for who in ((change.get("pull") or {}).get("author"), change.get("author")):
            if who and who not in authors:
                authors.append(who)
    customers = {s["customer"] for s in sites}
    shared = [site for site in others if site != deploy.hub_site()]
    return {
        "source": "Push" if pushes else "Pull request",
        "task": task,
        "ticket": frappe.db.get_value("Task", task, "hd_ticket") if task else None,
        "authors": "\n".join(authors),
        "changes": json.dumps(changes, indent=1),
        # a push nobody reviewed, or other customers' sites on the bench: a senior decides
        "needs_senior": int(bool(pushes) or len(customers) > 1 or bool(shared)),
    }


def other_sites(group: str, ours: list[str]) -> list[str]:
    """The bench's other sites, as Press lists them (empty when Press can't be asked)."""
    if not press.configured():
        return []
    try:
        info = press.deploy_information(group)
    except PressError:
        return []
    return [s.get("name") for s in info.get("sites") or [] if s.get("name") not in ours]


def create(key, sites: list[dict], base: str, head: str, changes: list[dict]):
    repo, branch, group = key
    others = other_sites(group, [s["site"] for s in sites])
    doc = frappe.get_doc(
        {
            "doctype": DEPLOY,
            "status": "Waiting for CI",
            "ci_status": "Pending",
            "repository": repo,
            "branch": branch,
            "release_group": group,
            "requested_at": now_datetime(),
            "other_sites": "\n".join(others),
            "sites": [
                {
                    "site": s["site"],
                    "customer": s["customer"],
                    "registry": s["registry"],
                }
                for s in sites
            ],
            "apps": [
                {
                    "app": sites[0]["app"],
                    "repository": repo,
                    "from_commit": base,
                    "to_commit": head,
                }
            ],
            **_fields(changes, others, sites),
        }
    ).insert(ignore_permissions=True)
    doc.add_comment(
        "Info",
        _("{0} commits on {1} {2} wait for CI.").format(len(changes), repo, branch),
    )
    return doc


def grow(doc, head: str, changes: list[dict]):
    """Later commits join a release not yet approved; it waits for CI again, and any approval asked for starts over."""
    sites = [{"customer": row.customer, "site": row.site} for row in doc.sites]
    others = [s for s in (doc.other_sites or "").splitlines() if s]
    doc.apps[0].to_commit = head
    doc.update(
        {
            "status": "Waiting for CI",
            "ci_status": "Pending",
            "ci_detail": None,
            "ci_override_by": None,
            "ci_override_reason": None,
            "approval_hash": None,
            **_fields(changes, others, sites),
        }
    )
    doc.save(ignore_permissions=True)
    doc.add_comment(
        "Info",
        _("New commits up to {0} joined the release; it waits for CI again.").format(
            head[:12]
        ),
    )
    return doc


# --- small helpers ------------------------------------------------------------------


def _same(a: str, b: str) -> bool:
    return bool(a and b) and (a.startswith(b) or b.startswith(a))


def _field_key(key: tuple[str, str, str]) -> str:
    return "|".join(key)


def _seen(key) -> str | None:
    seen = frappe.cache().hget(SEEN_KEY, _field_key(key))
    return seen.decode() if isinstance(seen, bytes) else seen


def _remember(key, head: str) -> None:
    """The branch's tip is handled: the next runs skip GitHub's compare until it moves."""
    frappe.cache().hset(SEEN_KEY, _field_key(key), head)
    return None


def _trouble(key, message: str):
    marker = frappe.cache().make_key(f"copilot_release_trouble:{_field_key(key)}")
    # SET NX with an expiry: the same trouble is logged once every few hours - nosemgrep
    if frappe.cache().set(marker, 1, ex=TROUBLE_HOURS * 3600, nx=True):
        frappe.log_error(
            title=_("Copilot could not read {0} {1} on GitHub").format(key[0], key[1]),
            message=message,
        )
