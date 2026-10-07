"""AI-written task descriptions.

Every task should say what it is for, what to do and when it is done. People
can ask for a draft from the New task and Edit task dialogs ("Write with AI"),
and a task created with no description gets one in the background, from
whichever path made it (dialogs, templates, content posts, tickets, the API).
The background job only fills a description that is still empty when it runs,
so a person's text is never replaced. AI-written descriptions are marked with
Task.custom_ai_description until someone edits them. See docs/ai-task-descriptions.md.
"""

import re
import time

import frappe
from frappe import _
from frappe.utils import cint, flt, strip_html

from helpdesk.ai_engine import call_haiku
from helpdesk.ai_suggestion import is_ai_configured
from helpdesk.automation import automation_user

JOB_TIMEOUT = 900
# a template can create dozens of tasks at once; each job takes a bounded share
BATCH_SIZE = 10
# pause between AI calls inside one job, so a big template doesn't hit the provider in a burst
PAUSE_SECONDS = 2
MAX_SIBLINGS = 5
MAX_PROJECT_NOTES = 1200
MAX_DESCRIPTION_CHARS = 1500
# drafts one person may ask for in the dialogs per window
DRAFTS_PER_WINDOW = 30
DRAFT_WINDOW_SECONDS = 600
PENDING_FLAG = "ai_task_descriptions_pending"
SKIP_STATUSES = ("Template", "Completed", "Cancelled")

SYSTEM_PROMPT = """You write task descriptions for TBO, a company that implements ERPNext, builds mobile apps and websites, and runs digital marketing and content for its customers.

You get one task and its project. Write the description the assignee reads before starting: what the task is for, how to do it and how everyone knows it is done.

Write it in this shape, as plain text:
<one or two sentences: the goal of the task and why it matters to the project>

Steps
- <3 to 6 short steps, each starting with a verb>

Done when
- <2 to 4 checks someone else can verify>

Match the kind of work:
- ERP, development and DevOps tasks: the configuration or code to change, testing with sample data, and a short note or document for the team or customer.
- Creative tasks (design, video, motion graphics, social media, content writing, digital marketing): the deliverables, sizes or formats and channels when they follow from the task, brand guidelines, and an internal review before it goes to the customer.
- Support and coordination tasks: who to talk to, what to agree and where to record it.

Rules:
- Plain text only: no Markdown headings, bold, tables or code blocks. Use "- " for list items.
- Under 150 words.
- Use only what you are given. Never invent customer facts, names, dates, amounts, systems or requirements; when something isn't known, write the step so it asks for it (e.g. "Confirm the approval levels with the customer").
- The other tasks in the phase are context only; don't repeat their work.
- Don't include personal data, credentials or links.

Reply with JSON only: {"description": "<the description, with \\n for line breaks>"}"""


def is_enabled() -> bool:
    return bool(frappe.db.get_single_value("HD Work Settings", "ai_task_descriptions"))


def has_description(text: str | None) -> bool:
    return bool(strip_html(text or "").strip())


def should_describe(task) -> bool:
    """A new task gets an AI description when it has none, the setting is on and AI is set up."""
    return (
        not has_description(task.description)
        and task.status not in SKIP_STATUSES
        and is_enabled()
        and is_ai_configured()
    )


def queue_description(task_name: str):
    """Collects the tasks of this transaction and queues them once it commits.

    A template inserts many tasks in one request; they go out as a few batched
    jobs instead of one job (and one burst of AI calls) per task.
    """
    pending = frappe.flags.get(PENDING_FLAG)
    if pending is None:
        pending = frappe.flags[PENDING_FLAG] = []
        frappe.db.after_commit.add(enqueue_pending)
        # a rollback drops the commit callback; drop the tasks with it
        frappe.db.after_rollback.add(drop_pending)
    if task_name not in pending:
        pending.append(task_name)


def pending_tasks() -> list[str]:
    return list(frappe.flags.get(PENDING_FLAG) or [])


def drop_pending():
    frappe.flags.pop(PENDING_FLAG, None)


def enqueue_pending():
    tasks = frappe.flags.pop(PENDING_FLAG, None) or []
    for start in range(0, len(tasks), BATCH_SIZE):
        batch = tasks[start : start + BATCH_SIZE]
        frappe.enqueue(
            "helpdesk.task_descriptions.describe_tasks",
            tasks=batch,
            queue="long",
            timeout=JOB_TIMEOUT,
            job_id=f"ai-task-descriptions-{batch[0]}",
            deduplicate=True,
        )


def describe_tasks(tasks: list[str]):
    """Background job: write descriptions for new tasks that still have none."""
    previous_user = frappe.session.user
    # the hub's own work, credited to TBO AI
    bot = automation_user()
    frappe.set_user(bot)  # nosemgrep
    try:
        for index, task in enumerate(tasks):
            if index and not frappe.flags.in_test:
                time.sleep(PAUSE_SECONDS)
            try:
                describe_task(task)
            except Exception:  # noqa: BLE001 - provider errors vary; the task just keeps no description
                frappe.log_error(
                    title=f"AI task description failed for {task}",
                    message=frappe.get_traceback(),
                )
    finally:
        frappe.set_user(previous_user)  # back to whoever enqueued it - nosemgrep


def describe_task(task: str) -> bool:
    """Writes the AI description when the task still has none; True when it did."""
    doc = frappe.db.get_value(
        "Task",
        task,
        [
            "name",
            "subject",
            "description",
            "project",
            "status",
            "priority",
            "custom_category",
            "custom_phase",
            "custom_estimated_hours",
            "_assign",
        ],
        as_dict=True,
    )
    if not doc or not should_describe(doc):
        return False
    assignees = frappe.parse_json(doc.pop("_assign", None) or "[]") or []
    doc.assigned_role = assignee_role(doc.project, assignees[0] if assignees else None)
    text = draft_description(task_context(doc))
    if not text:
        return False
    return save_if_still_empty(task, doc.description, text)


def save_if_still_empty(task: str, seen: str | None, text: str) -> bool:
    """Writes only if the description is still what the job read, so nobody's text is lost."""
    Task = frappe.qb.DocType("Task")
    query = (
        frappe.qb.update(Task)
        .set(Task.description, text)
        .set(Task.custom_ai_description, 1)
        .where(Task.name == task)
    )
    query = (
        query.where(Task.description == seen)
        if seen
        else query.where(Task.description.isnull() | (Task.description == ""))
    )
    query.run()
    written = frappe.db.get_value("Task", task, "description") == text
    if written:
        frappe.clear_document_cache("Task", task)
    return written


def task_context(task) -> dict:
    """What the AI may know about a task: the task, its project and its phase."""
    context = {
        "task": {
            "name": " ".join(str(task.get("subject") or "").split())[:200],
            "category": task.get("custom_category") or "not set",
            "phase": task.get("custom_phase") or "not set",
            "priority": task.get("priority") or "Medium",
            "estimated_hours": flt(task.get("custom_estimated_hours")) or None,
        }
    }
    if task.get("assigned_role"):
        context["task"]["assignee_role"] = task.get("assigned_role")
    project = task.get("project")
    if not project:
        return context
    info = frappe.db.get_value(
        "Project",
        project,
        ["project_name", "customer", "custom_department", "project_type", "notes"],
        as_dict=True,
    )
    if not info:
        return context
    context["project"] = {
        "name": info.project_name,
        "customer": info.customer or "not set",
        "department": info.custom_department or "not set",
        "type": info.project_type or "not set",
    }
    notes = " ".join(strip_html(info.notes or "").split())[:MAX_PROJECT_NOTES]
    if notes:
        context["project"]["description"] = notes
    siblings = sibling_tasks(
        project, task.get("custom_phase"), task.get("name"), task.get("subject")
    )
    if siblings:
        context["other_tasks_in_this_phase"] = siblings
    return context


def sibling_tasks(
    project: str, phase: str | None, exclude: str | None, subject: str | None
) -> list[str]:
    # get_list, so only tasks the user may read reach the AI
    filters = {
        "project": project,
        "status": ("not in", ["Template", "Cancelled"]),
        "custom_phase": phase if phase else ("is", "not set"),
    }
    if exclude:
        filters["name"] = ("!=", exclude)
    try:
        names = frappe.get_list(
            "Task",
            filters=filters,
            pluck="subject",
            order_by="creation asc",
            limit_page_length=MAX_SIBLINGS + 1,
        )
    except frappe.PermissionError:
        # siblings are only context; a user without Task access still gets a draft
        return []
    return [n for n in names if n and n != subject][:MAX_SIBLINGS]


def draft_description(context: dict) -> str:
    """The AI's description for a task context; empty when it gave nothing usable."""
    result = call_haiku(SYSTEM_PROMPT, frappe.as_json(context))
    response = result.get("response") if isinstance(result, dict) else None
    if not isinstance(response, dict):
        return ""
    text = response.get("description")
    if not text and response.get("parse_error"):
        # some providers answer in plain text despite the JSON instruction
        raw = str(response.get("raw_response") or "").strip()
        text = "" if raw.startswith("{") else raw
    return clean_description(str(text or ""))


def clean_description(text: str) -> str:
    """Plain text for the Description box: no Markdown markers, no HTML, tidy lines."""
    text = strip_html(text).replace("\r\n", "\n")
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"^\s*#+\s*", "", line)
        line = line.replace("**", "").replace("__", "")
        line = re.sub(r"^\s*[*•]\s+", "- ", line)
        lines.append(line.rstrip())
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text[:MAX_DESCRIPTION_CHARS]


@frappe.whitelist()
def get_ai_status() -> dict:
    """Whether "Write with AI" can work here, and why not."""
    if is_ai_configured():
        return {"available": True, "reason": ""}
    return {
        "available": False,
        "reason": _(
            "AI isn't set up. An administrator adds the AI key in HDS Hub Settings."
        ),
    }


@frappe.whitelist(methods=["POST"])
def draft_task_description(
    task_name: str,
    project: str | None = None,
    task: str | None = None,
    category: str | None = None,
    phase: str | None = None,
    priority: str | None = None,
    estimated_hours: float | str | None = None,
    assigned_to: str | None = None,
) -> dict:
    """A description draft for the task being written in a dialog; nothing is saved."""
    from helpdesk.tasky.api import _check_can_edit, _resolve_project
    from helpdesk.tasky.permissions import can_add_tasks

    if task:
        doc = frappe.get_doc("Task", str(task))
        doc.check_permission("read")
        # the same rule as saving the description: lead, manager or assignee
        _check_can_edit(doc, {})
        project = doc.project
    else:
        project = _resolve_project(str(project or ""))
        if not can_add_tasks(project):
            frappe.throw(
                _("Only people on this project can add tasks to it."),
                frappe.PermissionError,
            )
    name = " ".join(str(task_name or "").split())
    if not name:
        frappe.throw(_("Type the task name first."))
    if not is_ai_configured():
        frappe.throw(get_ai_status()["reason"])
    throttle_drafts()

    context = task_context(
        frappe._dict(
            name=task,
            subject=name,
            project=project,
            custom_category=category,
            custom_phase=str(phase or "").strip(),
            priority=priority,
            custom_estimated_hours=flt(estimated_hours),
            assigned_role=assignee_role(project, assigned_to),
        )
    )
    try:
        text = draft_description(context)
    except Exception:  # noqa: BLE001 - provider errors vary; the person gets one clear message
        frappe.log_error(
            title="AI task description draft failed", message=frappe.get_traceback()
        )
        text = ""
    if not text:
        frappe.throw(_("The AI couldn't write a description just now. Try again."))
    return {"description": text}


def assignee_role(project: str | None, user: str | None) -> str | None:
    """The assignee's role on the project (e.g. Graphic Designer), never their name."""
    if not project or not user:
        return None
    return frappe.db.get_value(
        "Project User",
        {"parenttype": "Project", "parent": project, "user": str(user)},
        "custom_role",
    )


def throttle_drafts():
    key = frappe.cache.make_key(f"ai-task-description-drafts:{frappe.session.user}")
    count = cint(frappe.cache.incr(key))
    if count == 1:
        frappe.cache.expire(key, DRAFT_WINDOW_SECONDS)
    if count > DRAFTS_PER_WINDOW:
        frappe.throw(
            _("That's a lot of drafts in a few minutes. Try again in a little while."),
            frappe.RateLimitExceededError,
        )
