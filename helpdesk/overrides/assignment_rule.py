import frappe
from frappe.automation.doctype.assignment_rule.assignment_rule import AssignmentRule

from helpdesk.content_team import is_sales_employee


def get_agents_by_category(category: str) -> set[str]:
    """User ids of HD Agents whose current status falls under the given category."""
    statuses = frappe.get_all(
        "HD Agent Status",
        filters={"category": category},
        pluck="name",
    )
    if not statuses:
        return set()
    return set(
        frappe.get_all(
            "HD Agent",
            filters={"availability": ["in", statuses]},
            pluck="user",
        )
    )


class HelpdeskAssignmentRule(AssignmentRule):
    def get_user(self, doc):
        """
        Override get_user method from framework.
        always Active agents are preferred; fall back to Away if no Active is available;
        fall back to the full pool (including Unavailable) only if no one else
        is available, so the ticket is never left unassigned.
        Sales Employees are never in the pool: they can't be given tickets or tasks
        (docs/departments.md), and picking one would fail the document's save.

        Tickets follow helpdesk.ticket_assignment instead (get_ticket_user).
        """
        if self.document_type == "HD Ticket" and self.rule != "Based on Field":
            return self.get_ticket_user(doc)

        # "Based on Field" assigns through the document field, so the
        # availability filter does not apply.
        if self.rule == "Weighted Distribution":
            user_pool_fieldname = "weighted_users"
        elif self.rule in ("Round Robin", "Load Balancing"):
            user_pool_fieldname = "users"
        else:
            return super().get_user(doc)

        original_pool = getattr(self, user_pool_fieldname)
        pool = [u for u in original_pool if not is_sales_employee(u.user)]
        away = get_agents_by_category("Away")
        unavailable = get_agents_by_category("Unavailable")
        if len(pool) == len(original_pool) and not away and not unavailable:
            return super().get_user(doc)

        active_only = [
            u for u in pool if u.user not in away and u.user not in unavailable
        ]
        not_unavailable = [u for u in pool if u.user not in unavailable]

        # Tier: Active → Away → full pool (Unavailable as last resort)
        if active_only:
            preferred_pool = active_only
        elif not_unavailable:
            preferred_pool = not_unavailable
        else:
            preferred_pool = pool

        setattr(self, user_pool_fieldname, preferred_pool)
        try:
            return super().get_user(doc)
        finally:
            setattr(self, user_pool_fieldname, original_pool)

    def get_ticket_user(self, doc):
        """A ticket goes to someone working today (not on leave, not Unavailable, an active
        agent, not a Sales Employee), Active before Away: the least busy for Round Robin
        and Load Balancing, the weighted pick for Weighted Distribution. Nobody when no one
        in the rule is working: the ticket then waits for its coordinators
        (ticket_assignment.ask_for_unassigned) instead of going to someone away."""
        from helpdesk.ticket_assignment import least_busy, working_today

        fieldname = (
            "weighted_users" if self.rule == "Weighted Distribution" else "users"
        )
        original_pool = getattr(self, fieldname)
        working = working_today([u.user for u in original_pool])
        pool = [u for u in original_pool if u.user in working]
        away = get_agents_by_category("Away")
        pool = [u for u in pool if u.user not in away] or pool
        if not pool:
            return None
        if self.rule != "Weighted Distribution":
            return least_busy([u.user for u in pool])
        setattr(self, fieldname, pool)
        try:
            return super().get_user(doc)
        finally:
            setattr(self, fieldname, original_pool)
