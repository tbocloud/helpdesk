# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""GitHub calls for Copilot fixes: read a pull request, its files and its checks,
hold it with a label, merge it with the approved commit pinned.

Unlike the task sync's helper, every call raises GitHubError with GitHub's own
status and message: a refused merge must never pass for a network blip.
"""

import re
from urllib.parse import quote

import requests
from frappe import _

GITHUB_API = "https://api.github.com"
TIMEOUT = 15
# a check run in one of these conclusions does not block a merge (the org merge bot's rule)
GREEN = {"success", "neutral", "skipped"}
MAX_FILE_PAGES = 3


class GitHubError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"GitHub {status}: {message}" if status else message)
        self.status = status
        self.message = message


def token() -> str:
    from frappe.utils.password import get_decrypted_password

    value = get_decrypted_password(
        "HD GitHub Settings",
        "HD GitHub Settings",
        "github_token",
        raise_exception=False,
    )
    if not value:
        raise GitHubError(0, _("No GitHub token is saved in Settings → GitHub."))
    return value


REPO_PATH = re.compile(r"^/repos/([^/]+)/([^/]+)")


def _bearer(path: str, owner: str | None) -> str:
    """The GitHub App's key for the repository (or owner) when the App is set up, else the personal token."""
    from helpdesk.copilot import github_app

    if github_app.configured():
        if found := REPO_PATH.match(path):
            return github_app.token_for_repo(f"{found.group(1)}/{found.group(2)}")
        if owner:
            return github_app.token_for_owner(owner)
    return token()


def request(
    method: str,
    path: str,
    body: dict | None = None,
    params: dict | None = None,
    owner: str | None = None,
):
    """One REST call; the parsed JSON, or GitHubError. `owner` picks the App's key for calls outside a repository (search)."""
    bearer = _bearer(path, owner)
    try:
        response = requests.request(
            method,
            f"{GITHUB_API}{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {bearer}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json=body,
            params=params,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise GitHubError(
            0, _("GitHub could not be reached: {0}").format(str(e)[:200])
        ) from e
    if response.status_code >= 400:
        try:
            message = response.json().get("message") or response.text
        except ValueError:
            message = response.text
        raise GitHubError(response.status_code, str(message)[:300])
    if not response.content:
        return {}
    return response.json()


def get_pull(repo: str, number: int) -> dict:
    return request("GET", f"/repos/{repo}/pulls/{int(number)}")


def pull_files(repo: str, number: int) -> list[dict]:
    """The changed files (name, status, additions, deletions, patch), at most 300."""
    files = []
    for page in range(1, MAX_FILE_PAGES + 1):
        batch = request(
            "GET",
            f"/repos/{repo}/pulls/{int(number)}/files",
            params={"per_page": 100, "page": page},
        )
        files.extend(batch or [])
        if len(batch or []) < 100:
            break
    return files


def checks(repo: str, sha: str) -> dict:
    """Whether every check on `sha` passed, as the org merge bot decides it.

    Every check run completed as success, neutral or skipped, and the combined
    commit status success (or no status at all). Returns
    `{green, total, pending, failing, partial}` with the names of the ones that
    block; `partial` when only GitHub Actions could be read (see `_check_runs`).
    """
    runs, partial = _check_runs(repo, sha)
    pending = [r.get("name") for r in runs if r.get("status") != "completed"]
    failing = [
        r.get("name")
        for r in runs
        if r.get("status") == "completed" and r.get("conclusion") not in GREEN
    ]
    status = request("GET", f"/repos/{repo}/commits/{sha}/status") or {}
    if status.get("total_count") and status.get("state") == "pending":
        pending.append(_("commit status"))
    elif status.get("total_count") and status.get("state") != "success":
        failing.append(_("commit status"))
    return {
        "green": not pending and not failing,
        "total": len(runs) + int(status.get("total_count") or 0),
        "pending": pending,
        "failing": failing,
        "partial": partial,
    }


def _check_runs(repo: str, sha: str) -> tuple[list[dict], bool]:
    """The commit's check runs, and whether they are only part of them.

    GitHub lets no fine-grained personal token read check runs (only GitHub Apps
    and classic tokens); refused that way, the commit's GitHub Actions workflow
    runs stand in, which a fine-grained token with Actions read may see.
    """
    try:
        found = request(
            "GET", f"/repos/{repo}/commits/{sha}/check-runs", params={"per_page": 100}
        )
        return (found or {}).get("check_runs") or [], False
    except GitHubError as e:
        if e.status != 403:
            raise
    try:
        found = request(
            "GET",
            f"/repos/{repo}/actions/runs",
            params={"head_sha": sha, "per_page": 100},
        )
    except GitHubError as e:
        if e.status in (403, 404):
            raise GitHubError(
                e.status,
                _(
                    "This GitHub token cannot read test results: give it Actions read (a fine-grained token cannot read check runs)."
                ),
            ) from e
        raise
    latest = {}
    for run in (found or {}).get("workflow_runs") or []:
        key = (run.get("workflow_id"), run.get("event"))  # a re-run replaces its run
        if (run.get("created_at") or "") >= (
            latest.get(key, {}).get("created_at") or ""
        ):
            latest[key] = run
    runs = [
        {
            "name": r.get("name"),
            "status": r.get("status"),
            "conclusion": r.get("conclusion"),
        }
        for r in latest.values()
    ]
    return runs, True


def merge_method(repo: str) -> str:
    """The repository's own method, chosen as the org merge bot chooses it."""
    settings = request("GET", f"/repos/{repo}") or {}
    for method, allowed in (
        ("merge", "allow_merge_commit"),
        ("squash", "allow_squash_merge"),
        ("rebase", "allow_rebase_merge"),
    ):
        if settings.get(allowed):
            return method
    return "merge"


METHOD_REFUSED = re.compile(
    r"(merge commits|squash merges|rebase merges) are not allowed", re.I
)


def merge(repo: str, number: int, sha: str, title: str = "") -> str:
    """Merges with `sha` pinned: GitHub refuses (409) if the head moved. Returns the merge commit.

    A token that may not read the repository's merge settings gets the default
    method; when GitHub refuses that method (405), the next one is tried.
    """
    first = merge_method(repo)
    for method in [first] + [m for m in ("merge", "squash", "rebase") if m != first]:
        body = {"merge_method": method, "sha": sha}
        if title:
            body["commit_title"] = title[:250]
        try:
            result = request(
                "PUT", f"/repos/{repo}/pulls/{int(number)}/merge", body=body
            )
        except GitHubError as e:
            if e.status == 405 and METHOD_REFUSED.search(e.message or ""):
                refused = e
                continue
            raise
        return (result or {}).get("sha") or ""
    raise refused


def pull_commits(repo: str, number: int) -> list[dict]:
    """The pull request's commits (GitHub lists at most 250)."""
    commits = []
    for page in range(1, MAX_FILE_PAGES + 1):
        batch = request(
            "GET",
            f"/repos/{repo}/pulls/{int(number)}/commits",
            params={"per_page": 100, "page": page},
        )
        commits.extend(batch or [])
        if len(batch or []) < 100:
            break
    return commits


def copilot_only(repo: str, pull: dict, email: str) -> bool:
    """Whether Copilot alone made the pull request: the GitHub App opened it and every commit carries Copilot's email."""
    from helpdesk.copilot import github_app

    if not (email and github_app.configured()):
        return False
    if pull.get("author") != github_app.bot_login():
        return False
    commits = pull_commits(repo, pull["number"])
    return bool(commits) and all(
        ((c.get("commit") or {}).get("author") or {}).get("email", "").lower()
        == email.lower()
        for c in commits
    )


REVERT = (
    "mutation($id: ID!, $title: String, $body: String) {"
    " revertPullRequest(input: {pullRequestId: $id, title: $title, body: $body})"
    " { revertPullRequest { number url } } }"
)


def revert_pull(repo: str, number: int, title: str, body: str) -> dict:
    """GitHub's own revert of a merged pull request (as its Revert button): `{number, url}` of the new pull request."""
    node = get_pull(repo, number).get("node_id")
    result = request(
        "POST",
        "/graphql",
        body={"query": REVERT, "variables": {"id": node, "title": title, "body": body}},
        owner=repo.split("/")[0],
    )
    if (result or {}).get("errors"):
        raise GitHubError(422, str(result["errors"][0].get("message"))[:300])
    created = (((result or {}).get("data") or {}).get("revertPullRequest") or {}).get(
        "revertPullRequest"
    ) or {}
    if not created.get("number"):
        raise GitHubError(0, _("GitHub did not create the revert pull request."))
    return {"number": int(created["number"]), "url": created.get("url") or ""}


def add_label(repo: str, number: int, label: str):
    request(
        "POST", f"/repos/{repo}/issues/{int(number)}/labels", body={"labels": [label]}
    )


def remove_label(repo: str, number: int, label: str):
    try:
        request("DELETE", f"/repos/{repo}/issues/{int(number)}/labels/{quote(label)}")
    except GitHubError as e:
        if e.status != 404:  # the label was not there
            raise


def comment(repo: str, number: int, text: str):
    request("POST", f"/repos/{repo}/issues/{int(number)}/comments", body={"body": text})


# --- releases (Phase 7): what a branch gained since the deployed commit ---------------


def branch_head(repo: str, branch: str) -> str:
    """The commit at the tip of `branch`."""
    found = request("GET", f"/repos/{repo}/branches/{quote(branch, safe='')}") or {}
    return (found.get("commit") or {}).get("sha") or ""


def compare(repo: str, base: str, head: str) -> dict:
    """`{status, commits}` from `base` to `head`, oldest commit first (GitHub lists at most 250)."""
    found = request("GET", f"/repos/{repo}/compare/{base}...{head}") or {}
    return {"status": found.get("status") or "", "commits": found.get("commits") or []}


def commit_pulls(repo: str, sha: str) -> list[dict]:
    """The pull requests a commit belongs to (open or merged)."""
    return request("GET", f"/repos/{repo}/commits/{sha}/pulls") or []
