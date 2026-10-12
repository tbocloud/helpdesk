# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""How risky a fix is, from the files its pull request changes.

Fixed rules, no AI: a sensitive area makes the change high-risk and needs a
senior approver; a large change is high-risk; a change without a test is
medium. Every finding names its reason, for the approval card.
"""

import re

from frappe import _

LARGE_CHANGE_LINES = 300

# (reason, pattern on the file path); reasons are translated when a finding is written
SENSITIVE_PATHS = [
    (
        "accounting and tax",
        re.compile(
            r"(^|/)(accounts?|accounting|payments?)(/|$)|invoice|payment_entry|journal_entry|"
            + r"gl_entry|ledger|(^|[/_])tax|vat|zatca",
            re.IGNORECASE,
        ),
    ),
    (
        "stock",
        re.compile(
            r"(^|/)stock(/|_)|stock_entry|delivery_note|purchase_receipt|warehouse|serial_no|(^|/)bin(/|\.)",
            re.IGNORECASE,
        ),
    ),
    ("payroll", re.compile(r"payroll|salary|payslip", re.IGNORECASE)),
    (
        "permissions",
        re.compile(r"permission|(^|/)roles?(/|\.json)|custom_docperm", re.IGNORECASE),
    ),
    (
        "migrations",
        re.compile(
            r"(^|/)patches\.txt$|(^|/)patches/|after_migrate|before_migrate",
            re.IGNORECASE,
        ),
    ),
    ("app hooks", re.compile(r"(^|/)hooks\.py$")),
    ("doctype definitions", re.compile(r"/doctype/[^/]+/[^/]+\.json$")),
    (
        "dependencies",
        re.compile(
            r"(^|/)(requirements[^/]*\.txt|pyproject\.toml|setup\.py|package\.json|"
            + r"package-lock\.json|yarn\.lock|pnpm-lock\.yaml)$"
        ),
    ),
    ("CI configuration", re.compile(r"(^|/)\.github/")),
]
# (reason, pattern on the added lines of the patch)
SENSITIVE_CODE = [
    ("permissions", re.compile(r"ignore_permissions|has_permission|flags\.ignore_")),
    (
        "raw SQL writes",
        re.compile(
            r"(db\.sql|sql\()\s*\(?[^)]{0,200}\b(insert|update|delete|truncate|drop|alter)\b",
            re.IGNORECASE,
        ),
    ),
]
TEST_PATH = re.compile(r"(^|/)tests?/|(^|/)test_[^/]+\.py$|\.test\.[jt]s$|_test\.py$")


def added_lines(patch: str | None) -> str:
    return "\n".join(
        line[1:]
        for line in (patch or "").splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def assess(files: list[dict]) -> dict:
    """`{level, sensitive, reasons, files, lines, tests_changed}` for a list of GitHub pull-request files."""
    reasons: list[str] = []
    sensitive = False
    lines = 0
    tests_changed = False

    def note(reason: str, is_sensitive: bool):
        nonlocal sensitive
        sensitive = sensitive or is_sensitive
        if reason not in reasons:
            reasons.append(reason)

    for file in files:
        path = file.get("filename") or ""
        lines += int(file.get("additions") or 0) + int(file.get("deletions") or 0)
        if TEST_PATH.search(path):
            tests_changed = True
        for reason, pattern in SENSITIVE_PATHS:
            if pattern.search(path):
                note(_("changes {0} ({1})").format(_(reason), path), True)
        code = added_lines(file.get("patch"))
        for reason, pattern in SENSITIVE_CODE:
            if pattern.search(code):
                note(_("adds {0} code ({1})").format(_(reason), path), True)

    if lines > LARGE_CHANGE_LINES:
        note(
            _("changes {0} lines (more than {1})").format(lines, LARGE_CHANGE_LINES),
            False,
        )
    if not tests_changed:
        note(_("no test was added or changed"), False)

    if sensitive or lines > LARGE_CHANGE_LINES:
        level = "high"
    elif not tests_changed:
        level = "medium"
    else:
        level = "low"
    return {
        "level": level,
        "sensitive": sensitive,
        "reasons": reasons,
        "files": len(files),
        "lines": lines,
        "tests_changed": tests_changed,
    }
