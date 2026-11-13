# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Copilot's queries in the form Frappe v16 accepts (TBO Support has run v16 since 31 Oct 2026).

v16 rejects an SQL function written as a string in a `fields` list ("sum(x) as y"), and backticks in
`order_by`; `helpdesk.utils.aggregate()` writes an aggregate the way the running Frappe accepts it.
This scans Copilot's own modules, so a new query in the v15-only form fails here, not on the real site.
"""

import re
from pathlib import Path
from unittest import TestCase

import helpdesk

ROOT = Path(helpdesk.__file__).parent
COPILOT_FILES = [
    *sorted((ROOT / "copilot").rglob("*.py")),
    *sorted((ROOT / "api").glob("copilot*.py")),
    ROOT / "mcp_client.py",
]
# a string that starts with an SQL aggregate, as a `fields` entry would
AGGREGATE_STRING = re.compile(r"[\"'](count|sum|max|min|avg)\s*\(", re.I)
BACKTICKED_ORDER_BY = re.compile(r"order_by\s*=\s*f?[\"'][^\"']*`")


class TestCopilotQueriesForFrappeV16(TestCase):
    def test_no_aggregate_written_as_a_string(self):
        found = []
        for path in COPILOT_FILES:
            for number, line in enumerate(path.read_text().splitlines(), 1):
                code = line.split("#", 1)[0]
                if AGGREGATE_STRING.search(code):
                    found.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
        self.assertEqual(found, [], "use helpdesk.utils.aggregate()")

    def test_no_backticks_in_order_by(self):
        found = [
            f"{path.relative_to(ROOT)}:{number}"
            for path in COPILOT_FILES
            for number, line in enumerate(path.read_text().splitlines(), 1)
            if BACKTICKED_ORDER_BY.search(line)
        ]
        self.assertEqual(found, [], "Frappe v16 rejects backticks in order_by")
