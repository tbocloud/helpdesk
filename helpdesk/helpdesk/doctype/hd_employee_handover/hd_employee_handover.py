"""Someone leaving hands their work over (docs/project-access.md).

`complete` moves the person's open tasks on each project to the person taking it over,
puts that person in their place on the project's team (and as its lead, if they led it),
takes the leaver off the team, and does the same for their tasks outside a project."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, escape_html, get_fullname, now_datetime

from helpdesk.utils import assigned_names_query

DRAFT = "Draft"
DONE = "Done"
CLOSED_TASK_STATES = ("Completed", "Cancelled", "Template")


class HDEmployeeHandover(Document):
    def validate(self):
        self.check_people()
        self.check_projects()

    def check_people(self):
        owners = [row.new_owner for row in self.projects] + [self.default_owner]
        if self.employee in owners:
            frappe.throw(_("The person leaving can't take over their own work."))

    def check_projects(self):
        seen = set()
        for row in self.projects:
            if row.project in seen:
                frappe.throw(_("{0} is listed twice.").format(row.project))
            seen.add(row.project)

    def complete(self):
        """Hand everything over and mark the handover done. Owns its whole change, so it
        saves the projects, the tasks and itself."""
        if self.status == DONE:
            frappe.throw(_("This handover is already done."))
        for row in self.projects:
            # tasks first: giving a task to someone off the team adds them to it
            row.tasks_moved = self.move_tasks(row.project, row.new_owner)
            project = frappe.get_doc("Project", row.project)
            self.pass_on_project(project, row)
            project.save(ignore_permissions=True)
            project.add_comment("Info", self.project_comment(row))
        if self.default_owner:
            self.other_tasks_moved = self.move_tasks(None, self.default_owner)
        self.status = DONE
        self.completed_by = frappe.session.user
        self.completed_on = now_datetime()
        self.save(ignore_permissions=True)

    def move_tasks(self, project: str | None, new_owner: str) -> int:
        """Give the leaver's share of each open task (in `project`, or outside any
        project for None) to `new_owner`; others on the task keep theirs."""
        from helpdesk.tasky.api import _reassign
        from helpdesk.tasky.new_assignments import told_by_caller

        names = self.open_task_names(self.employee, project)
        with told_by_caller():
            for name in names:
                _reassign(
                    frappe.get_doc("Task", name),
                    [self.employee],
                    new_owner,
                    ignore_permissions=True,
                )
        if names:
            from helpdesk.work_reminders import notify_users

            notify_users(
                [new_owner],
                # the project, or for tasks outside one the first of them
                "Project" if project else "Task",
                project or names[0],
                _("{0} handed you {1} open tasks").format(
                    get_fullname(self.employee), len(names)
                ),
            )
        return len(names)

    @staticmethod
    def open_task_names(user: str, project: str | None) -> list[str]:
        task = frappe.qb.DocType("Task")
        query = (
            frappe.qb.from_(task)
            .select(task.name)
            .where(
                task.name.isin(assigned_names_query("Task", user))
                & task.status.notin(CLOSED_TASK_STATES)
            )
        )
        if project:
            query = query.where(task.project == project)
        else:
            query = query.where(task.project.isnull() | (task.project == ""))
        return query.run(pluck=True)

    def pass_on_project(self, project, row):
        """The new owner takes the leaver's place (and role) on the team, and the lead
        if the leaver led it; the leaver leaves the team."""
        leaving = [u for u in project.users if u.user == self.employee]
        role = leaving[0].custom_role if leaving else None
        row.project_role = role or row.project_role
        if not any(u.user == row.new_owner for u in project.users):
            project.append("users", {"user": row.new_owner, "custom_role": role})
        for member in leaving:
            project.remove(member)
        if project.project_lead == self.employee:
            project.project_lead = row.new_owner

    def project_comment(self, row) -> str:
        text = _(
            "{0} left and handed this project to {1}; {2} open tasks moved."
        ).format(
            get_fullname(self.employee),
            get_fullname(row.new_owner),
            cint(row.tasks_moved),
        )
        note = (row.note or "").strip()
        return escape_html(f"{text} {_('Note')}: {note}" if note else text)
