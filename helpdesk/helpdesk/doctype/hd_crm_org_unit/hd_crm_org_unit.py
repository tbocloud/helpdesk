# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from helpdesk.crm_dashboard.registry import ORG_LEVELS, UNIT_PARENTS, UNIT_TYPES

DOCTYPE = "HD CRM Org Unit"
# which dashboard grouping each unit is, e.g. "Branch" → "branch"
LEVEL_OF = {label: level for level, label in UNIT_TYPES.items()}


class HDCRMOrgUnit(Document):
    """One company, branch, department, team or employee of a data source, by the name its
    leads carry, with where it sits: its company, branch, department and team. The sync adds
    the ones it finds; admins add teams, set leaders and relationships, and switch units off
    (docs/crm-dashboard.md)."""

    def validate(self):
        self.normalise()
        self.validate_unique()
        self.validate_user()
        self.inherit_parents()

    def on_update(self):
        self.refresh_report()

    def on_trash(self):
        self.validate_unused()

    def after_delete(self):
        self.refresh_report()

    # ---------- validation ----------

    def normalise(self):
        if self.unit_type not in UNIT_PARENTS:
            frappe.throw(
                _(
                    "Pick the kind of unit: a company, branch, department, team or employee."
                )
            )
        self.unit_name = (self.unit_name or "").strip()
        self.label = (self.label or "").strip() or self.unit_name
        allowed = UNIT_PARENTS[self.unit_type]
        for level in ORG_LEVELS[:-1]:
            value = (self.get(level) or "").strip()
            self.set(level, value if level in allowed else "")
        if self.unit_type != "Employee":
            self.user = None
        if self.unit_type != "Team":
            self.leader = None

    def validate_unique(self):
        other = frappe.db.get_value(
            DOCTYPE,
            {
                "source": self.source,
                "unit_type": self.unit_type,
                "unit_name": self.unit_name,
                "name": ("!=", self.name),
            },
        )
        if other:
            frappe.throw(
                _("{0} already has the {1} {2}.").format(
                    self.source, _(self.unit_type).lower(), self.unit_name
                ),
                frappe.DuplicateEntryError,
            )

    def validate_user(self):
        if not self.user:
            return
        other = frappe.db.get_value(
            DOCTYPE,
            {
                "source": self.source,
                "unit_type": "Employee",
                "user": self.user,
                "name": ("!=", self.name),
            },
            "label",
        )
        if other:
            frappe.throw(
                _("{0} is already linked to the employee {1}.").format(self.user, other)
            )

    def inherit_parents(self):
        """Each parent must be a unit of this source. Its own parents carry down when they're
        empty here, and must agree when they're set: a team in the Sales department sits in
        the Sales department's branch."""
        allowed = UNIT_PARENTS[self.unit_type]
        # the closest parent first, so a team's department decides its branch
        for level in reversed(allowed):
            if not self.get(level):
                continue
            parent = self.parent_unit(level)
            for upper in UNIT_PARENTS[UNIT_TYPES[level]]:
                inherited = parent.get(upper)
                if not inherited:
                    continue
                if not self.get(upper):
                    self.set(upper, inherited)
                elif self.get(upper) != inherited:
                    frappe.throw(
                        _("{0} {1} is in the {2} {3}, not {4}.").format(
                            _(UNIT_TYPES[level]),
                            self.get(level),
                            _(UNIT_TYPES[upper]).lower(),
                            inherited,
                            self.get(upper),
                        )
                    )

    def parent_unit(self, level: str) -> dict:
        unit_type = UNIT_TYPES[level]
        parent = frappe.db.get_value(
            DOCTYPE,
            {
                "source": self.source,
                "unit_type": unit_type,
                "unit_name": self.get(level),
            },
            ["unit_name", *ORG_LEVELS[:-1]],
            as_dict=True,
        )
        if not parent:
            frappe.throw(
                _("{0} has no {1} {2}. Add it under Organisation first.").format(
                    self.source, _(unit_type).lower(), self.get(level)
                )
            )
        return parent

    def validate_unused(self):
        from helpdesk.helpdesk.doctype.hd_crm_dashboard.hd_crm_dashboard import (
            HDCRMDashboard,
        )

        HDCRMDashboard.refuse_if_covering([self.name], self.label or self.unit_name)
        level = LEVEL_OF[self.unit_type]
        if level == "employee":
            return
        child = frappe.db.get_value(
            DOCTYPE,
            {"source": self.source, level: self.unit_name},
            ["unit_type", "label"],
            as_dict=True,
        )
        if child:
            frappe.throw(
                _(
                    "The {0} {1} sits under it. Move it first, or switch this one off."
                ).format(_(child.unit_type).lower(), child.label)
            )

    # ---------- after a change ----------

    def refresh_report(self):
        """Leads take their team, department, branch and company from these relationships,
        and an inactive unit's leads are left out: count them again."""
        from helpdesk.crm_dashboard.sync import enqueue_recompute

        if self.flags.from_sync:
            return
        enqueue_recompute(self.source)
