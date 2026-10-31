import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate

from helpdesk.content_team import is_sales_employee
from helpdesk.project_status import NOTHING, REPORT_PROJECT_STATUSES
from helpdesk.tasky.permissions import (
    can_coordinate_project,
    is_tasky_admin,
    project_query,
)

READ_PERMISSIONS = ("read", "print", "email", "report")


class HDProjectStatusUpdate(Document):
    def validate(self):
        self.validate_is_new()
        self.validate_project_is_running()
        self.tidy_text()
        self.set_writer()
        self.set_waiting_since()

    def validate_is_new(self):
        """An update is a line of the project's history: it is never edited."""
        if not self.is_new():
            frappe.throw(_("A status update can't be changed. Write a new one."))

    def validate_project_is_running(self):
        status = frappe.db.get_value("Project", self.project, "status")
        if status not in REPORT_PROJECT_STATUSES:
            frappe.throw(
                _("{0} is {1}; it has no status to report.").format(
                    self.project, status
                )
            )

    def tidy_text(self):
        self.update_text = "\n".join(
            line.strip()
            for line in (self.update_text or "").splitlines()
            if line.strip()
        )
        self.next_step = " ".join((self.next_step or "").split())

    def set_writer(self):
        self.written_by = frappe.session.user

    def set_waiting_since(self):
        """The day a wait began: kept from the last update while it is the same wait,
        else today."""
        if self.waiting_on == NOTHING:
            self.waiting_since = None
            return
        if self.waiting_since:
            return
        last = frappe.db.get_value(
            self.doctype,
            {"project": self.project},
            ["waiting_on", "waiting_since"],
            order_by="creation desc",
            as_dict=True,
        )
        same_wait = last and last.waiting_on == self.waiting_on and last.waiting_since
        self.waiting_since = last.waiting_since if same_wait else nowdate()


def permission_query(user: str | None = None) -> str | None:
    """An update is visible wherever its project is."""
    condition = project_query(user)
    if condition is None:
        return None
    return (
        "`tabHD Project Status Update`.`project` in "
        "(select `name` from `tabProject` where " + condition + ")"
    )


def has_permission(
    doc, ptype: str | None = None, user: str | None = None
) -> bool | None:
    """Reading follows the project; writing is for the people who coordinate it (its
    managers, lead and coordinators, and the admins). Hooks deny but never grant."""
    user = user or frappe.session.user
    if is_tasky_admin(user):
        return None
    if is_sales_employee(user):
        return False
    if ptype in READ_PERMISSIONS:
        return (
            None
            if frappe.has_permission("Project", "read", doc.project, user=user)
            else False
        )
    if ptype in ("create", "write"):
        return None if can_coordinate_project(doc.project, user) else False
    return False
