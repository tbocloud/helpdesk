"""Follow-ups and escalation: the one engine for reminders about tasks and tickets.

The company follows up on the work, not on people's hours: a task or ticket that
needs someone keeps coming back, in the app and in Teams, until it moves, and the
longer it waits the more people hear about it. docs/follow-ups.md has the rules,
the ladder and the delivery.

Every 15 minutes `run()`:
- works out what needs whom right now (`evaluate()`), from the rules switched on in
  HD Follow Up Settings;
- records how far up the ladder each overdue task and breached ticket has gone
  (Task.escalation_level, HD Ticket.custom_escalation_level);
- keeps one notification per person and item per day in the notification panel,
  rewritten as the item moves to another rule or level (`post_notices`);
- pings at once (chat, or email) only for L2+ escalations, SLA breaches and late key
  tasks and milestones: once per person, item, rule, level and day;
- at each digest time sends every person one message with all of it, grouped by
  severity, the first of the day with their plan for today (helpdesk.home_plan);
- emails customers who haven't replied, when that is switched on.

Nothing is sent outside working hours (the default SLA's hours) or on days off (the
weekly off, Saturdays off and holidays, see helpdesk.work_calendar), except SLA breach
pings when the settings allow it.
"""

import html
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

import frappe
import requests
from frappe import _
from frappe.query_builder.functions import Max
from frappe.utils import (
    add_days,
    cint,
    flt,
    format_datetime,
    formatdate,
    get_datetime,
    get_fullname,
    get_time,
    getdate,
    now_datetime,
)

from helpdesk.api.ticket import _sla_calendar
from helpdesk.api.work import ON_HOLD, PENDING_REVIEW, WAITING_ON_TASK, is_task_overdue
from helpdesk.automation import automation_user
from helpdesk.recurrence import working_day_checker
from helpdesk.tasky.permissions import (
    COORDINATOR_PROJECT_ROLE,
    MANAGER_PROJECT_ROLE,
    department_heads,
    get_assigners,
)
from helpdesk.utils import is_agent
from helpdesk.work_reminders import (
    _agent_managers,
    _assignees,
    enabled_users,
    new_notification,
)

SETTINGS = "HD Follow Up Settings"
CACHE_KEY = "follow_ups"
# longer than the 15-minute run that refreshes it; task and settings changes clear it
CACHE_SECONDS = 16 * 60
NOTICE_PREFIX = "follow-up"
OPEN_TASK_STATUSES = ("Completed", "Cancelled", "Template")
WAITING_ON_CUSTOMER = "Waiting on customer"
# working days counted one by one; anything older is simply "very late"
LOOKBACK_DAYS = 400
DIGEST_ITEMS_PER_SECTION = 8
# from least to most pressing: a person's notice for an item is its most pressing one
SEVERITIES = ("waiting", "due", "overdue", "escalated", "breach")
TASK_FIELDS = [
    "name",
    "subject",
    "project",
    "status",
    "exp_end_date",
    "is_key",
    "is_milestone",
    "_assign",
    "creation",
    "modified",
    "hold_since",
    "hold_by",
    "hold_reason",
    "depends_on_task",
    "custom_timer_start",
    "custom_timer_elapsed",
    "custom_actual_hours",
    "custom_estimated_hours",
]
TICKET_FIELDS = [
    "name",
    "subject",
    "status",
    "status_category",
    "agent_group",
    "_assign",
    "creation",
    "modified",
    "sla",
    "response_by",
    "first_responded_on",
    "resolution_by",
    "resolution_date",
    "service_level_agreement_creation",
    "last_customer_response",
    "last_agent_response",
    "custom_customer_followed_up_on",
]


def severity_labels() -> dict[str, str]:
    return {
        "breach": _("SLA breached"),
        "escalated": _("Escalated"),
        "overdue": _("Overdue"),
        "due": _("Due now"),
        "waiting": _("Waiting on you"),
    }


def level_labels() -> dict[int, str]:
    return {
        1: _("Escalated to lead"),
        2: _("Escalated to head"),
        3: _("Escalated to managers"),
    }


def rule_labels() -> dict[str, str]:
    return {
        "due_tomorrow": _("Due next working day"),
        "due_today": _("Due today, not started"),
        "overdue": _("Overdue"),
        "untouched": _("Assigned, untouched"),
        "review": _("Waiting for review"),
        "hold": _("On hold"),
        "no_due_date": _("No due date"),
        "blocked": _("Blocking other work"),
        "sla": _("SLA"),
        "unassigned": _("Unassigned ticket"),
        "customer_replied": _("Customer waiting for an answer"),
        "awaiting_customer": _("Waiting on the customer"),
    }


@dataclass
class FollowUp:
    """One thing that needs people now: a rule that fired on a task or ticket."""

    doctype: str
    name: str
    title: str
    rule: str
    # with the rule, what a person was last told (dedupe): "L2", "afternoon", "resolution:80"
    stage: str
    severity: str
    text: str
    recipients: list[str]
    # whose work it is (the assignees): the banner and the manager view count by them
    owners: list[str] = field(default_factory=list)
    level: int = 0
    immediate: bool = False
    link: str = "/my-work"
    days: int = 0

    @property
    def key(self) -> str:
        return f"{self.rule}:{self.stage}"

    def rank(self) -> tuple[int, int]:
        return SEVERITIES.index(self.severity), self.level

    def rule_label(self) -> str:
        return rule_labels().get(self.rule, self.rule)


def get_settings():
    return frappe.get_cached_doc(SETTINGS)


# --- the calendar -------------------------------------------------------------


class WorkCalendar:
    """The hub's working days (HD Work Settings and the holiday list) and working hours
    (the default SLA's), so thresholds count working time only."""

    def __init__(self, today):
        self.today = getdate(today)
        self.is_working_day = working_day_checker(
            add_days(self.today, -LOOKBACK_DAYS), add_days(self.today, 31)
        )
        name = frappe.db.get_value(
            "HD Service Level Agreement", {"default_sla": 1, "enabled": 1}
        )
        self.sla = frappe.get_doc("HD Service Level Agreement", name) if name else None
        self.hours = self.sla.get_working_hours() if self.sla else {}
        self._since = {}

    def working_days_since(self, day) -> int:
        """Working days after `day`, up to and including today (0 for today or later)."""
        day = getdate(day)
        if day not in self._since:
            if (self.today - day).days > LOOKBACK_DAYS:
                self._since[day] = (self.today - day).days
            else:
                count, current = 0, add_days(day, 1)
                while current <= self.today:
                    count += self.is_working_day(current)
                    current = add_days(current, 1)
                self._since[day] = count
        return self._since[day]

    def next_working_day(self):
        day = add_days(self.today, 1)
        while not self.is_working_day(day):
            day = add_days(day, 1)
        return day

    def in_working_hours(self, moment) -> bool:
        moment = get_datetime(moment)
        if not self.is_working_day(moment.date()):
            return False
        # without a default SLA the whole working day counts
        return not self.sla or bool(self.sla.is_working_time(moment, self.hours))

    def working_seconds(self, start, end) -> float:
        start, end = get_datetime(start), get_datetime(end)
        if self.sla:
            return self.sla.calc_elapsed_time(start, end)
        return max((end - start).total_seconds(), 0)


# --- what needs whom ---------------------------------------------------------


class Context:
    """Everything one evaluation reads once: the settings, the clock, the calendar and
    the people who lead and head things."""

    def __init__(self, settings=None, now=None, calendar=None):
        self.settings = settings or get_settings()
        self.now = get_datetime(now or now_datetime())
        self.today = self.now.date()
        self.calendar = calendar or WorkCalendar(self.today)
        self.agent_managers = sorted(set(_agent_managers()))
        self.customer_follow_ups = []
        self._heads = {}

    def heads(self, department: str | None) -> list[str]:
        """department_heads, read once per department; None is the Agent Managers."""
        if department not in self._heads:
            self._heads[department] = department_heads(department)
        return self._heads[department]

    def ladder_level(self, days: int) -> int:
        s = self.settings
        if days >= cint(s.ladder_l3_days):
            return 3
        if days >= cint(s.ladder_l2_days):
            return 2
        if days >= cint(s.ladder_l1_days):
            return 1
        return 0


def evaluate(ctx: Context | None = None) -> list[FollowUp]:
    """Every follow-up due now, without sending anything."""
    ctx = ctx or Context()
    return [*TaskRules(ctx).evaluate(), *TicketRules(ctx).evaluate()]


def _unique(users) -> list[str]:
    return list(dict.fromkeys(u for u in users if u))


class TaskRules:
    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.s = ctx.settings
        self.tasks = frappe.qb.get_query(
            "Task",
            fields=TASK_FIELDS,
            filters={"status": ("not in", OPEN_TASK_STATUSES)},
        ).run(as_dict=True)
        self.by_name = {t.name: t for t in self.tasks}
        self.people = self.load_people({t.project for t in self.tasks if t.project})
        first_assignee = {t.name: _assignees(t._assign)[:1] for t in self.tasks}
        self.assigners = get_assigners(
            {name: users[0] for name, users in first_assignee.items() if users}
        )

    def evaluate(self) -> list[FollowUp]:
        found = []
        untouched_since = self.untouched_since()
        review_since = self.review_since()
        for task in self.tasks:
            found += [
                follow_up
                for follow_up in (
                    self.overdue(task),
                    self.due_today(task),
                    self.due_tomorrow(task),
                    self.untouched(task, untouched_since.get(task.name)),
                    self.review(task, review_since.get(task.name)),
                    self.hold(task),
                    self.no_due_date(task),
                    self.blocked(task),
                )
                if follow_up
            ]
        return found

    # --- who ---

    @staticmethod
    def load_people(projects: set) -> dict:
        """Each project's lead, managers (its creator and members with the Project
        Manager role), coordinators and department, in two queries."""
        if not projects:
            return {}
        project = frappe.qb.DocType("Project")
        rows = (
            frappe.qb.from_(project)
            .select(
                project.name,
                project.project_lead,
                project.owner,
                project.custom_department,
            )
            .where(project.name.isin(list(projects)))
            .run(as_dict=True)
        )
        people = {
            r.name: frappe._dict(
                lead=r.project_lead,
                managers=[r.owner],
                coordinators=[],
                department=r.custom_department,
            )
            for r in rows
        }
        member = frappe.qb.DocType("Project User")
        roles = {
            MANAGER_PROJECT_ROLE: "managers",
            COORDINATOR_PROJECT_ROLE: "coordinators",
        }
        for row in (
            frappe.qb.from_(member)
            .select(member.parent, member.user, member.custom_role)
            .where(
                (member.parenttype == "Project")
                & member.parent.isin(list(projects))
                & member.custom_role.isin(list(roles))
            )
            .run(as_dict=True)
        ):
            if row.parent in people:
                people[row.parent][roles[row.custom_role]].append(row.user)
        return people

    def project(self, task):
        return self.people.get(task.project) or frappe._dict(
            lead=None, managers=[], coordinators=[], department=None
        )

    def leads(self, task) -> list[str]:
        """The project lead, or its managers when it has none."""
        p = self.project(task)
        return [p.lead] if p.lead else list(p.managers)

    def owners(self, task) -> list[str]:
        """Whose task it is: its assignees, or who should hand it out."""
        return _assignees(task._assign) or self.leads(task)

    def ladder(self, task, level: int) -> list[str]:
        """L0 the assignee; L1 plus the assigner and lead; L2 plus the coordinators and
        the department heads (the project managers without a department); L3 plus the
        Agent Managers. Each level adds people, never replaces them."""
        p = self.project(task)
        people = self.owners(task)
        if level >= 1:
            people += [self.assigners.get(task.name), *self.leads(task)]
        if level >= 2:
            people += [
                *p.coordinators,
                *(self.ctx.heads(p.department) if p.department else p.managers),
            ]
        if level >= 3:
            people += self.ctx.agent_managers
        return _unique(people)

    def follow_up(self, task, rule, stage, severity, text, recipients, **kwargs):
        label = ""
        if task.is_milestone:
            label = _("Milestone") + ": "
        elif task.is_key:
            label = _("Key task") + ": "
        title = f"{label}{task.subject}"
        return FollowUp(
            doctype="Task",
            name=task.name,
            title=title,
            rule=rule,
            stage=stage,
            severity=severity,
            text=text.replace("{title}", title),
            recipients=_unique(recipients),
            owners=self.owners(task),
            link=f"/projects/{task.project}" if task.project else "/my-work",
            **kwargs,
        )

    # --- the rules ---

    def deadline(self, task):
        return getdate(task.exp_end_date) if task.exp_end_date else None

    @staticmethod
    def not_started(task) -> bool:
        return (
            task.status == "Open"
            and not task.custom_timer_start
            and not flt(task.custom_timer_elapsed)
            and not flt(task.custom_actual_hours)
        )

    def overdue(self, task):
        """Every working day it is late, one more step up the ladder (key work sooner)."""
        deadline = self.deadline(task)
        if not self.s.overdue or task.status == PENDING_REVIEW:
            return None
        if not is_task_overdue(task, deadline, self.ctx.today):
            return None
        days = self.ctx.calendar.working_days_since(deadline)
        key = bool(task.is_key or task.is_milestone)
        level = self.ctx.ladder_level(days)
        if key and self.s.key_tasks_escalate_faster:
            level = min(level + 1, 3)
        text = (
            _("Overdue {0} working day(s): {{title}}").format(days)
            if days
            else _("Due today and past its estimated hours: {title}")
        )
        if level:
            text += " · " + level_labels()[level]
        return self.follow_up(
            task,
            "overdue",
            f"L{level}",
            "escalated" if level >= 2 else "overdue",
            text,
            self.ladder(task, level),
            level=level,
            immediate=level >= 2 or key,
            days=days,
        )

    def due_today(self, task):
        """Due today and not started: in the morning, then again in the afternoon."""
        if not self.s.due_today or self.deadline(task) != self.ctx.today:
            return None
        if not self.not_started(task):
            return None
        afternoon = self.ctx.now.time() >= get_time(
            self.s.afternoon_nudge_at or "14:00"
        )
        return self.follow_up(
            task,
            "due_today",
            "afternoon" if afternoon else "morning",
            "due",
            _("Due today and still not started: {title}")
            if afternoon
            else _("Due today, not started yet: {title}"),
            _assignees(task._assign),
        )

    def due_tomorrow(self, task):
        if not self.s.due_tomorrow or task.status in (ON_HOLD, PENDING_REVIEW):
            return None
        deadline = self.deadline(task)
        if not deadline or deadline != self.ctx.calendar.next_working_day():
            return None
        return self.follow_up(
            task,
            "due_tomorrow",
            "L0",
            "due",
            _("Due {0}: {{title}}").format(formatdate(deadline)),
            _assignees(task._assign),
        )

    def untouched_since(self) -> dict:
        """Not started tasks with nobody's word on them: {task: when it was assigned},
        for those whose latest assignment has no comment after it. Two queries."""
        if not self.s.untouched:
            return {}
        names = [
            t.name
            for t in self.tasks
            if self.not_started(t) and t._assign not in (None, "[]")
        ]
        if not names:
            return {}
        todo = frappe.qb.DocType("ToDo")
        assigned = dict(
            frappe.qb.from_(todo)
            .select(todo.reference_name, Max(todo.creation))
            .where(
                (todo.reference_type == "Task")
                & todo.reference_name.isin(names)
                & (todo.status == "Open")
            )
            .groupby(todo.reference_name)
            .run()
        )
        comment = frappe.qb.DocType("Comment")
        commented = dict(
            frappe.qb.from_(comment)
            .select(comment.reference_name, Max(comment.creation))
            .where(
                (comment.reference_doctype == "Task")
                & comment.reference_name.isin(names)
                & (comment.comment_type == "Comment")
            )
            .groupby(comment.reference_name)
            .run()
        )
        return {
            name: on
            for name, on in assigned.items()
            if not commented.get(name) or commented[name] < on
        }

    def untouched(self, task, assigned_on=None):
        """Assigned and not started, no timer, no comment: the assignee, then the assigner."""
        if assigned_on is None:
            return None
        days = self.ctx.calendar.working_days_since(assigned_on)
        threshold = cint(self.s.untouched_days)
        if days < threshold:
            return None
        level = 1 if days > threshold else 0
        people = _assignees(task._assign)
        if level:
            people += [self.assigners.get(task.name)]
        return self.follow_up(
            task,
            "untouched",
            f"L{level}",
            "waiting",
            _("Assigned {0} working day(s) ago and not started: {{title}}").format(
                days
            ),
            people,
            level=level,
            days=days,
        )

    def review_since(self) -> dict:
        """{task: when it went to review}, from the task's history, for tasks in review."""
        if not self.s.review:
            return {}
        names = [t.name for t in self.tasks if t.status == PENDING_REVIEW]
        if not names:
            return {}
        version = frappe.qb.DocType("Version")
        found = dict(
            frappe.qb.from_(version)
            .select(version.docname, Max(version.creation))
            .where(
                (version.ref_doctype == "Task")
                & version.docname.isin(names)
                & version.data.like(f'%"{PENDING_REVIEW}"%')
            )
            .groupby(version.docname)
            .run()
        )
        # without a history row (set straight in the database), the last change
        return {name: found.get(name) or self.by_name[name].modified for name in names}

    def review(self, task, since=None):
        """Waiting for review: the reviewer (the coordinators, else the lead), then the
        lead (else the project managers)."""
        if since is None:
            return None
        days = self.ctx.calendar.working_days_since(since)
        threshold = cint(self.s.review_days)
        if days < threshold:
            return None
        p = self.project(task)
        reviewers = list(p.coordinators) or self.leads(task)
        level = 1 if days > threshold else 0
        people = list(reviewers)
        if level:
            people += self.leads(task) if p.coordinators else p.managers
        return self.follow_up(
            task,
            "review",
            f"L{level}",
            "waiting",
            _("Waiting for review for {0} working day(s): {{title}}").format(days),
            people,
            level=level,
            days=days,
        )

    def hold(self, task):
        """On hold too long: whoever held it, to resume or update the note; then the lead.
        Waiting on the customer also asks the assignee to follow up with them."""
        if not self.s.hold or task.status != ON_HOLD or not task.hold_since:
            return None
        days = self.ctx.calendar.working_days_since(task.hold_since)
        threshold = cint(self.s.hold_days)
        if days < threshold:
            return None
        level = 1 if days >= 2 * threshold else 0
        people = [task.hold_by] if task.hold_by else _assignees(task._assign)
        waiting_on_customer = task.hold_reason == WAITING_ON_CUSTOMER
        if waiting_on_customer:
            people += _assignees(task._assign)
            text = _(
                "Waiting on the customer for {0} working day(s): follow up with them, then resume it or update the note: {{title}}"
            ).format(days)
        else:
            text = _(
                "On hold for {0} working day(s) ({1}): resume it or update the note: {{title}}"
            ).format(days, task.hold_reason or _("no reason"))
        if level:
            people += self.leads(task)
        return self.follow_up(
            task, "hold", f"L{level}", "waiting", text, people, level=level, days=days
        )

    def no_due_date(self, task):
        """Open without a due date: whoever gave it out, or the lead, should set one."""
        if not self.s.no_due_date or task.exp_end_date:
            return None
        if task.status in (ON_HOLD, PENDING_REVIEW):
            return None
        days = self.ctx.calendar.working_days_since(task.creation)
        if days < cint(self.s.no_due_date_days):
            return None
        assigner = self.assigners.get(task.name)
        people = [assigner] if assigner else self.leads(task)
        return self.follow_up(
            task,
            "no_due_date",
            "L0",
            "waiting",
            _("No due date after {0} working day(s): set one: {{title}}").format(days),
            people,
            days=days,
        )

    def blocked(self, task):
        """`task` waits on an overdue task: its assignees hear someone is waiting on them."""
        if not self.s.blocked or not task.depends_on_task:
            return None
        blocking = self.by_name.get(task.depends_on_task)
        if not blocking or not is_task_overdue(
            blocking, self.deadline(blocking), self.ctx.today
        ):
            return None
        return self.follow_up(
            blocking,
            "blocked",
            "L0",
            "waiting",
            _("“{0}” is waiting on your overdue task: {{title}}").format(task.subject),
            _assignees(blocking._assign) or self.leads(blocking),
        )


class TicketRules:
    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.s = ctx.settings
        self.tickets = frappe.qb.get_query(
            "HD Ticket",
            fields=TICKET_FIELDS,
            filters={"status_category": ("in", ["Open", "Paused"])},
        ).run(as_dict=True)
        self.calendars = {}
        self.teams = self.load_teams({t.agent_group for t in self.tickets})
        self.support_heads = ctx.heads(self.s.ticket_department or None)
        # HD Settings' auto-close (General) closes tickets left waiting on the customer
        auto_close, self.auto_close_status, close_after = frappe.db.get_value(
            "HD Settings",
            "HD Settings",
            ["auto_close_tickets", "auto_close_status", "auto_close_after_days"],
        )
        self.auto_close = bool(cint(auto_close))
        self.close_after_days = cint(close_after) or 14

    def evaluate(self) -> list[FollowUp]:
        found = []
        for ticket in self.tickets:
            for rule in (
                self.sla,
                self.unassigned,
                self.customer_replied,
                self.awaiting_customer,
            ):
                if follow_up := rule(ticket):
                    found.append(follow_up)
        return found

    @staticmethod
    def load_teams(teams: set) -> dict[str, list[str]]:
        teams = [t for t in teams if t]
        if not teams:
            return {}
        member = frappe.qb.DocType("HD Team Member")
        found = {}
        for team, user in (
            frappe.qb.from_(member)
            .select(member.parent, member.user)
            .where((member.parenttype == "HD Team") & member.parent.isin(teams))
            .run()
        ):
            found.setdefault(team, []).append(user)
        return found

    def owners(self, ticket) -> list[str]:
        """The assignees, or the ticket's team, or the Agent Managers."""
        return (
            _assignees(ticket._assign)
            or list(self.teams.get(ticket.agent_group) or [])
            or list(self.ctx.agent_managers)
        )

    def ladder(self, ticket, level: int) -> list[str]:
        """L0 the assignee; L1 and L2 plus the support department's heads (the team
        lead; the Agent Managers without a department); L3 plus the Agent Managers."""
        people = self.owners(ticket)
        if level >= 1:
            people += self.support_heads
        if level >= 3:
            people += self.ctx.agent_managers
        return _unique(people)

    def follow_up(self, ticket, rule, stage, severity, text, recipients, **kwargs):
        title = _("Ticket #{0}: {1}").format(ticket.name, ticket.subject)
        return FollowUp(
            doctype="HD Ticket",
            name=str(ticket.name),
            title=title,
            rule=rule,
            stage=stage,
            severity=severity,
            text=text.replace("{title}", title),
            recipients=_unique(recipients),
            owners=_assignees(ticket._assign),
            link=f"/tickets/{ticket.name}",
            **kwargs,
        )

    def sla_used(self, ticket, deadline) -> float:
        """How much of the SLA's working time has gone, in percent (100 at the deadline)."""
        deadline = get_datetime(deadline)
        if self.ctx.now >= deadline:
            return 100.0
        start = get_datetime(ticket.service_level_agreement_creation or ticket.creation)
        sla = _sla_calendar(ticket.sla, self.calendars)
        if sla:
            total = sla.calc_elapsed_time(start, deadline)
            left = sla.calc_elapsed_time(self.ctx.now, deadline)
        else:
            total = (deadline - start).total_seconds()
            left = (deadline - self.ctx.now).total_seconds()
        return 100.0 * (1 - left / total) if total > 0 else 100.0

    def sla(self, ticket):
        """First reply and resolution: a warning at each threshold, then the breach,
        which climbs to the Agent Managers after a few working days."""
        if not self.s.sla_warnings or ticket.status_category != "Open":
            return None
        clocks = []
        if ticket.response_by and not ticket.first_responded_on:
            clocks.append(("first_reply", _("First reply"), ticket.response_by))
        if ticket.resolution_by and not ticket.resolution_date:
            clocks.append(("resolution", _("Resolution"), ticket.resolution_by))
        worst = None
        for kind, label, deadline in clocks:
            follow_up = self.sla_stage(ticket, kind, label, deadline)
            if follow_up and (worst is None or follow_up.rank() > worst.rank()):
                worst = follow_up
        return worst

    def sla_stage(self, ticket, kind: str, label: str, deadline):
        used = self.sla_used(ticket, deadline)
        due = format_datetime(deadline, "d MMM, HH:mm")
        if used >= 100:
            days = self.ctx.calendar.working_days_since(get_datetime(deadline).date())
            gap = cint(self.s.ladder_l3_days) - cint(self.s.ladder_l2_days)
            level = 3 if days >= max(gap, 1) else 2
            text = _("{0} SLA breached at {1}: {{title}}").format(label, due)
            text += " · " + level_labels()[level]
            return self.follow_up(
                ticket,
                "sla",
                f"{kind}:breach:L{level}",
                "breach",
                text,
                self.ladder(ticket, level),
                level=level,
                immediate=True,
                days=days,
            )
        for threshold, level in (
            (cint(self.s.sla_second_warning), 1),
            (cint(self.s.sla_first_warning), 0),
        ):
            if used >= threshold:
                return self.follow_up(
                    ticket,
                    "sla",
                    f"{kind}:{threshold}",
                    "due",
                    _("{0} SLA {1}% used, due {2}: {{title}}").format(
                        label, threshold, due
                    ),
                    self.ladder(ticket, level),
                    level=level,
                )
        return None

    def unassigned(self, ticket):
        """Nobody has picked it up for a while in working hours: its team and the managers."""
        if not self.s.unassigned or ticket.status_category != "Open":
            return None
        if _assignees(ticket._assign):
            return None
        minutes = self.ctx.calendar.working_seconds(ticket.creation, self.ctx.now) // 60
        if minutes < cint(self.s.unassigned_minutes):
            return None
        return self.follow_up(
            ticket,
            "unassigned",
            "L1",
            "overdue",
            _("Unassigned for {0} working minute(s): {{title}}").format(int(minutes)),
            [*(self.teams.get(ticket.agent_group) or []), *self.ctx.agent_managers],
            level=1,
        )

    def customer_replied(self, ticket):
        """The customer answered and nobody has replied: the assignee, then the team lead."""
        if not self.s.customer_replied or ticket.status_category != "Open":
            return None
        if not ticket.first_responded_on or not ticket.last_customer_response:
            return None
        if ticket.last_agent_response and get_datetime(
            ticket.last_agent_response
        ) >= get_datetime(ticket.last_customer_response):
            return None
        hours = (
            self.ctx.calendar.working_seconds(
                ticket.last_customer_response, self.ctx.now
            )
            / 3600
        )
        threshold = cint(self.s.customer_replied_hours)
        if hours < threshold:
            return None
        level = 1 if hours >= 2 * threshold else 0
        return self.follow_up(
            ticket,
            "customer_replied",
            f"L{level}",
            "overdue" if level else "waiting",
            _(
                "The customer replied {0} working hour(s) ago and is waiting for an answer: {{title}}"
            ).format(int(hours)),
            self.ladder(ticket, level),
            level=level,
        )

    def awaiting_customer(self, ticket):
        """We answered and the customer hasn't. After a few working days they get a
        polite follow-up email (when switched on), else the assignee is asked to follow
        up; when that gets no answer either, the ticket is closed by HD Settings'
        auto-close, or the assignee is asked to close it."""
        if not self.s.awaiting_customer or ticket.status_category != "Paused":
            return None
        if ticket.status == WAITING_ON_TASK:
            return None
        waiting_since = get_datetime(ticket.last_agent_response or ticket.modified)
        followed_up = ticket.custom_customer_followed_up_on and get_datetime(
            ticket.custom_customer_followed_up_on
        ) >= waiting_since - timedelta(minutes=5)
        if followed_up:
            days = self.ctx.calendar.working_days_since(
                get_datetime(ticket.custom_customer_followed_up_on).date()
            )
            closes_itself = self.auto_close and ticket.status == self.auto_close_status
            if closes_itself or days < self.close_after_days:
                return None
            return self.follow_up(
                ticket,
                "awaiting_customer",
                "close",
                "waiting",
                _(
                    "No reply {0} working day(s) after the follow-up email: close the ticket or call the customer: {{title}}"
                ).format(days),
                self.owners(ticket),
                days=days,
            )
        days = self.ctx.calendar.working_days_since(waiting_since.date())
        if days < cint(self.s.awaiting_customer_days):
            return None
        if self.s.customer_follow_up_email:
            self.ctx.customer_follow_ups.append(ticket.name)
            return None
        return self.follow_up(
            ticket,
            "awaiting_customer",
            "L0",
            "waiting",
            _(
                "Waiting on the customer for {0} working day(s): follow up with them or close it: {{title}}"
            ).format(days),
            self.owners(ticket),
            days=days,
        )


# --- the run -----------------------------------------------------------------


def run():
    """Every 15 minutes (hooks.py): evaluate, record, notify and send due digests."""
    settings = get_settings()
    if settings.enabled:
        process(Context(settings))
    else:
        clear_levels()


def clear_levels() -> None:
    """Follow-ups switched off: nothing is escalated any more, so the badges go too."""
    for doctype, level_field, date_field in (
        ("Task", "escalation_level", "escalated_on"),
        ("HD Ticket", "custom_escalation_level", "custom_escalated_on"),
    ):
        table = frappe.qb.DocType(doctype)
        (
            frappe.qb.update(table)
            .set(table[level_field], 0)
            .set(table[date_field], None)
            .where(table[level_field] > 0)
            .run()
        )


def process(ctx: Context) -> None:
    settings = ctx.settings
    follow_ups = evaluate(ctx)
    cache(follow_ups, ctx.today)
    if not ctx.calendar.in_working_hours(ctx.now):
        if settings.breach_pings_outside_hours:
            post_notices([f for f in follow_ups if f.severity == "breach"], ctx.today)
        return
    save_levels(follow_ups, ctx)
    post_notices(follow_ups, ctx.today)
    send_customer_follow_ups(ctx)
    send_due_digests(follow_ups, ctx)


def cache(follow_ups: list[FollowUp], today) -> None:
    frappe.cache.set_value(
        CACHE_KEY,
        {"day": str(today), "items": [asdict(f) for f in follow_ups]},
        expires_in_sec=CACHE_SECONDS,
    )


def clear_cache() -> None:
    frappe.cache.delete_value(CACHE_KEY)


def current() -> list[FollowUp]:
    """Today's follow-ups, worked out at most every few minutes (the banner and the
    manager view read them on every page)."""
    cached = frappe.cache.get_value(CACHE_KEY, expires=True)
    today = str(now_datetime().date())
    if cached and cached.get("day") == today:
        return [FollowUp(**item) for item in cached["items"]]
    if not get_settings().enabled:
        return []
    ctx = Context()
    follow_ups = evaluate(ctx)
    cache(follow_ups, ctx.today)
    return follow_ups


def save_levels(follow_ups: list[FollowUp], ctx: Context) -> None:
    """Record each overdue task's and breached ticket's ladder level; back to 0 once
    it is no longer late (Task.clear_escalation also resets it on completion)."""
    for doctype, rule, level_field, date_field, when in (
        ("Task", "overdue", "escalation_level", "escalated_on", ctx.today),
        (
            "HD Ticket",
            "sla",
            "custom_escalation_level",
            "custom_escalated_on",
            ctx.now,
        ),
    ):
        levels = {}
        for f in follow_ups:
            if f.doctype == doctype and f.rule == rule and f.level:
                levels[f.name] = max(levels.get(f.name, 0), f.level)
        table = frappe.qb.DocType(doctype)
        condition = table[level_field] > 0
        if levels:
            condition = condition | table.name.isin(list(levels))
        stored = (
            frappe.qb.from_(table)
            .select(table.name, table[level_field])
            .where(condition)
            .run()
        )
        for name, old in stored:
            new = levels.get(str(name), 0)
            if new == (old or 0):
                continue
            values = {level_field: new}
            if new > (old or 0):
                values[date_field] = when
            elif not new:
                values[date_field] = None
            frappe.db.set_value(doctype, name, values, update_modified=False)


def post_notices(follow_ups: list[FollowUp], today) -> None:
    """One notification per person and item per day: the most pressing follow-up for
    them. A later run rewrites it (unread again) when the rule or level changes; a ping
    goes to chat or email only for L2+, breaches and late key work, once per stage."""
    from helpdesk.chat_notifications import post_escalation

    chosen = most_pressing(follow_ups)
    if not chosen:
        return
    reachable = set(enabled_users({user for user, _dt, _name in chosen}))
    prefix = f"{NOTICE_PREFIX}:{today}:"
    notice = frappe.qb.DocType("HD Notification")
    existing = {
        (n.user_to, n.reference_doctype, n.reference_name): n
        for n in frappe.qb.from_(notice)
        .select(
            notice.name,
            notice.user_to,
            notice.reference_doctype,
            notice.reference_name,
            notice.dedupe_key,
        )
        .where(notice.dedupe_key.like(f"{prefix}%"))
        .run(as_dict=True)
    }
    escalated = {}
    for (user, doctype, name), f in chosen.items():
        if user not in reachable:
            continue
        key = prefix + f.key
        old = existing.get((user, doctype, name))
        if old is None:
            new_notification(
                user, doctype, name, f.text, f.link, dedupe_key=key, deliver=f.immediate
            )
        elif old.dedupe_key != key:
            doc = frappe.get_doc("HD Notification", old.name)
            doc.update(
                {"message": f.text, "link": f.link, "dedupe_key": key, "read": 0}
            )
            doc.save(ignore_permissions=True)
            doc.announce()
            if f.immediate:
                doc.deliver()
        else:
            continue
        if f.immediate:
            escalated[(doctype, name, f.key)] = f
    for f in escalated.values():
        # the team channel hears once per item and stage
        label = (
            severity_labels()["breach"]
            if f.severity == "breach"
            else level_labels().get(f.level) or severity_labels()[f.severity]
        )
        post_escalation(f"{label} ({f.rule_label()}): {f.title}", f.link)


def send_customer_follow_ups(ctx: Context) -> None:
    """The polite email to customers who haven't replied, once per wait, as a reply on
    the ticket (so HD Settings' auto-close counts its days from it)."""
    for name in ctx.customer_follow_ups:
        # a failed send must not leave a reply on the ticket that never reached them
        savepoint = f"customer_follow_up_{name}"
        frappe.db.savepoint(savepoint)
        try:
            send_customer_follow_up(name, ctx.settings)
        except Exception:  # noqa: BLE001 - one ticket's email must not stop the rest
            frappe.db.rollback(save_point=savepoint)
            frappe.log_error(title=f"Customer follow-up not sent for ticket {name}")


def send_customer_follow_up(name: str, settings) -> None:
    ticket = frappe.get_doc("HD Ticket", name)
    default = frappe.get_meta(SETTINGS).get_field("customer_follow_up_message").default
    message = ticket._get_rendered_template(
        settings.customer_follow_up_message or "",
        default,
        {
            "ticket": ticket.name,
            "subject": ticket.subject,
            "customer": ticket.customer or "",
        },
    )
    previous = frappe.session.user
    # the reply is the hub's (TBO AI); reply_via_agent needs an agent, so a hub user
    # without an agent role falls back to Administrator, the job's own user
    sender = automation_user()
    if not is_agent(sender):
        sender = "Administrator"
    frappe.set_user(sender)  # nosemgrep
    try:
        ticket.reply_via_agent(message=message, to=ticket.raised_by)
    finally:
        frappe.set_user(previous)  # back to whoever ran the job - nosemgrep
    frappe.db.set_value(
        "HD Ticket",
        ticket.name,
        "custom_customer_followed_up_on",
        now_datetime(),
        update_modified=False,
    )


# --- digests -----------------------------------------------------------------


def digest_slots(settings, day) -> list[datetime]:
    from helpdesk.helpdesk.doctype.hd_follow_up_settings.hd_follow_up_settings import (
        HDFollowUpSettings,
    )

    times = HDFollowUpSettings.parse_digest_times(settings.digest_times) or []
    return [datetime.combine(getdate(day), get_time(t)) for t in times]


def send_due_digests(follow_ups: list[FollowUp], ctx: Context) -> None:
    """At each digest time, once: everyone's digest. A run that missed a time (the
    server was down) sends one digest, not one per missed time."""
    slots = digest_slots(ctx.settings, ctx.today)
    sent_through = get_datetime(ctx.settings.digest_sent_through or "2000-01-01")
    due = [slot for slot in slots if sent_through < slot <= ctx.now]
    if not due:
        return
    record_digest(ctx.now)
    morning = bool(ctx.settings.morning_plan) and slots[0] in due
    by_user = items_by_user(follow_ups)
    users = set(by_user)
    if morning:
        users |= open_work_owners()
    for user in sorted(enabled_users(users)):
        try:
            send_digest(user, by_user.get(user, []), morning)
        except Exception:  # noqa: BLE001 - one person's digest must not stop the rest
            frappe.log_error(title=f"Follow-up digest failed for {user}")


def most_pressing(follow_ups: list[FollowUp]) -> dict[tuple, FollowUp]:
    """{(person, doctype, name): the most pressing follow-up for them on that item}."""
    chosen = {}
    for f in follow_ups:
        for user in f.recipients:
            key = (user, f.doctype, f.name)
            if key not in chosen or f.rank() > chosen[key].rank():
                chosen[key] = f
    return chosen


def record_digest(moment) -> None:
    """Recorded and committed before sending: chat posts can't be rolled back, so a job
    that dies halfway must not send anyone a second digest. Written straight to the
    field (no Version row twice a day); a site that never saved the settings stores
    all of them first, so the other fields keep their defaults."""
    if frappe.db.get_singles_dict(SETTINGS):
        frappe.db.set_single_value(SETTINGS, "digest_sent_through", moment)
    else:
        settings = frappe.new_doc(SETTINGS)
        settings.digest_sent_through = moment
        settings.save(ignore_permissions=True)
    frappe.clear_document_cache(SETTINGS, SETTINGS)
    frappe.db.commit()  # nosemgrep


def items_by_user(follow_ups: list[FollowUp]) -> dict[str, list[FollowUp]]:
    """Each person's most pressing follow-up per item."""
    by_user = {}
    for (user, _dt, _name), f in most_pressing(follow_ups).items():
        by_user.setdefault(user, []).append(f)
    return by_user


def open_work_owners() -> set[str]:
    """Everyone with an open task or ticket, who gets the plan for today."""
    todo = frappe.qb.DocType("ToDo")
    return set(
        frappe.qb.from_(todo)
        .select(todo.allocated_to)
        .distinct()
        .where(
            (todo.status == "Open") & todo.reference_type.isin(["Task", "HD Ticket"])
        )
        .run(pluck=True)
    )


def plan_steps(user: str) -> list[str]:
    """The user's plan for today, as on Home: today's AI plan when Home already wrote
    one, else the same steps from the rules (no AI call from here)."""
    from helpdesk import home_plan
    from helpdesk.api.home import _day
    from helpdesk.api.work import get_my_work

    cached = frappe.cache.get_value(home_plan.plan_cache_key(user), expires=True)
    if cached and cached.get("steps"):
        return [s["text"] for s in cached["steps"]]
    previous = frappe.session.user
    frappe.set_user(user)  # Home's day is the session user's own work - nosemgrep
    try:
        day = _day(get_my_work()["items"])
    except frappe.PermissionError:
        return []
    finally:
        frappe.set_user(previous)  # back to whoever ran the job - nosemgrep
    return [s["text"] for s in home_plan.rule_steps(day)]


def compose_digest(user: str, items: list[FollowUp], steps: list[str]):
    """(subject, sections): sections are (heading, [(text, path)]), most pressing first."""
    first_name = (frappe.db.get_value("User", user, "first_name") or "").strip()
    labels = severity_labels()
    sections = []
    for severity in reversed(SEVERITIES):
        group = sorted(
            (f for f in items if f.severity == severity),
            key=lambda f: (-f.level, -f.days),
        )
        if not group:
            continue
        lines = [(f.text, f.link) for f in group[:DIGEST_ITEMS_PER_SECTION]]
        if len(group) > DIGEST_ITEMS_PER_SECTION:
            lines.append(
                (
                    _("and {0} more").format(len(group) - DIGEST_ITEMS_PER_SECTION),
                    "/my-work",
                )
            )
        sections.append((f"{labels[severity]} ({len(group)})", lines))
    if steps:
        sections.append(
            (
                _("Your plan for today"),
                [(f"{i}. {s}", None) for i, s in enumerate(steps, 1)],
            )
        )
    if items:
        subject = _("{0}, {1} item(s) need you").format(first_name or user, len(items))
    else:
        subject = _("{0}, nothing needs you right now").format(first_name or user)
    return subject, sections


def chat_text(subject: str, sections) -> str:
    """Plain lines with Markdown links, which Teams cards show as links."""
    from helpdesk.chat_notifications import helpdesk_url

    lines = [subject]
    for heading, rows in sections:
        lines += ["", f"**{heading}**"]
        for text, path in rows:
            lines.append(f"- [{text}]({helpdesk_url(path)})" if path else text)
    return "\n".join(lines)


def send_digest(user: str, items: list[FollowUp], morning: bool) -> str | None:
    """One message with everything that needs `user`: Teams or Slack, else email.
    Returns how it went ("chat", "email") or None when there was nothing to send."""
    steps = plan_steps(user) if morning else []
    if not items and not steps:
        return None
    subject, sections = compose_digest(user, items, steps)
    return deliver_digest(user, subject, sections)


def deliver_digest(user: str, subject: str, sections) -> str | None:
    from helpdesk.chat_notifications import ChatError
    from helpdesk.chat_notifications import get_settings as chat_settings
    from helpdesk.chat_notifications import helpdesk_url, is_enabled, send_direct

    if is_enabled():
        try:
            if send_direct(
                user, chat_text(subject, sections), helpdesk_url("/my-work")
            ):
                return "chat"
        except (ChatError, requests.RequestException):
            frappe.log_error(title="Follow-up digest not sent to chat")
        if not chat_settings().email_when_unreachable:
            return None
    return email_digest(user, subject, sections)


def email_digest(user: str, subject: str, sections) -> str | None:
    from frappe.desk.doctype.notification_settings.notification_settings import (
        is_email_notifications_enabled,
    )

    from helpdesk.chat_notifications import helpdesk_url

    if not is_email_notifications_enabled(user):
        return None
    body = []
    for heading, rows in sections:
        body.append(f"<p><strong>{html.escape(heading)}</strong></p><ul>")
        for text, path in rows:
            escaped = html.escape(text)
            body.append(
                f'<li><a href="{helpdesk_url(path)}">{escaped}</a></li>'
                if path
                else f"<li>{escaped}</li>"
            )
        body.append("</ul>")
    try:
        frappe.sendmail(
            recipients=user,
            subject=subject,
            template="new_notification",
            args={"body_content": "".join(body), "doc_link": helpdesk_url("/my-work")},
            header=[_("Follow-ups"), "orange"],
        )
    except frappe.OutgoingEmailError:
        frappe.log_error(title="Follow-up digest email not sent")
        return None
    return "email"


# --- what people see -----------------------------------------------------------


def summary_for(user: str, follow_ups: list[FollowUp] | None = None) -> dict:
    """The banner: the user's own overdue, escalated and breached work, and what waits
    on them as a reviewer, lead or head."""
    follow_ups = current() if follow_ups is None else follow_ups
    mine = items_by_user(follow_ups).get(user, [])
    own = [f for f in mine if user in f.owners]
    return {
        "overdue": sum(f.rule == "overdue" for f in own),
        "escalated": sum(f.level >= 2 for f in own if f.rule == "overdue"),
        "breached": sum(f.severity == "breach" for f in own),
        "waiting_on_you": sum(user not in f.owners for f in mine),
        "total": len(mine),
    }


def overview(follow_ups: list[FollowUp] | None = None) -> dict:
    """For managers: what is escalated to L2 or above, the oldest overdue work and who
    has the most open escalations."""
    follow_ups = current() if follow_ups is None else follow_ups
    escalated = sorted(
        (f for f in follow_ups if f.level >= 2 and f.rule in ("overdue", "sla")),
        key=lambda f: (-f.level, -f.days),
    )
    overdue = sorted(
        (f for f in follow_ups if f.rule == "overdue"), key=lambda f: -f.days
    )
    counts = {}
    for f in follow_ups:
        if f.level >= 1 and f.rule in ("overdue", "sla"):
            for owner in f.owners:
                counts[owner] = counts.get(owner, 0) + 1
    people = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    return {
        "counts": {
            "escalated": len(escalated),
            "breached": sum(f.severity == "breach" for f in follow_ups),
            "overdue": len(overdue),
        },
        "escalated": [_row(f) for f in escalated[:8]],
        "oldest_overdue": [_row(f) for f in overdue[:5]],
        "people": [
            {"user": user, "full_name": get_fullname(user), "count": count}
            for user, count in people
        ],
    }


def _row(f: FollowUp) -> dict:
    return {
        "doctype": f.doctype,
        "name": f.name,
        "title": f.title,
        "text": f.text,
        "level": f.level,
        "level_label": level_labels().get(f.level),
        "days": f.days,
        "severity": f.severity,
        "link": f.link,
        "owners": [{"user": u, "full_name": get_fullname(u)} for u in f.owners],
    }


def preview(follow_ups: list[FollowUp] | None = None) -> list[dict]:
    """What each person would get in their digest now, the busiest first."""
    follow_ups = current() if follow_ups is None else follow_ups
    by_user = items_by_user(follow_ups)
    people = []
    for user in enabled_users(by_user):
        items = sorted(by_user[user], key=lambda f: f.rank(), reverse=True)
        people.append(
            {
                "user": user,
                "full_name": get_fullname(user),
                "items": [{**_row(f), "rule_label": f.rule_label()} for f in items],
            }
        )
    people.sort(key=lambda p: (-len(p["items"]), p["full_name"]))
    return people
