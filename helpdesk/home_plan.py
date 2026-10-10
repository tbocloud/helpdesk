"""Home's "Your action plan": three to five steps for the user's day.

The steps come from the user's own day (helpdesk.api.home._day): what to close
first, what is in progress, what waits, what was given out, replies and reviews.
The hub's AI writes them from those facts only, and any step with a number that
isn't in the facts is dropped (the Scoreboard's guard, ai_engine.invents_numbers).
When the AI is off, fails or answers badly, the same priority order builds the
plan without it, and the plan says which one it is. See docs/home.md.
"""

import hashlib
import json
import re
from datetime import datetime, time

import frappe
from frappe import _
from frappe.utils import add_days, getdate, now_datetime, nowdate

from helpdesk.ai_engine import call_haiku, fact_numbers, invents_numbers
from helpdesk.api.ticket_ai import truncate

CACHE_PREFIX = "home_plan"
# get_home keeps the day this long, so the plan request needn't rebuild it
DAY_CACHE_SECONDS = 120
# after a failed AI call, plans are built without it for this long
AI_RETRY_SECONDS = 15 * 60
REFRESH_COOLDOWN_SECONDS = 60
MIN_STEPS = 3
MAX_STEPS = 5
FACT_ITEMS = 5
STEP_CHARS = 220
NOTE_CHARS = 160
AI = "ai"
RULES = "rules"

SYSTEM_PROMPT = """You plan one person's working day at TBO, a company that implements ERPNext, builds apps and websites and runs digital marketing for its customers.
Use only the facts in the JSON you are given: their own tasks, tickets and reviews. Never invent tasks, people, numbers, dates or causes. Every number you write must appear in the facts.
Write 3 to 5 steps in the order to do them: overdue work first, then work due today, then key work in progress, then replies and reviews, then following up on held work and work they gave out, then dates to set.
Each step is one short, plain sentence in the imperative ("Finish ...", "Follow up with ..."), names the task, and says why now. No HTML, no markdown, no numbering.
Reply with JSON only: {"steps": ["...", "..."]}"""


def day_cache_key(user: str) -> str:
    return f"{CACHE_PREFIX}_day:{user}"


def plan_cache_key(user: str) -> str:
    return f"{CACHE_PREFIX}:{user}:{nowdate()}"


def clear_cache(user: str) -> None:
    """Forget the user's cached day, today's plan, the refresh lock and a recent AI failure."""
    for key in (
        day_cache_key(user),
        plan_cache_key(user),
        _refresh_key(user),
        _failed_key(user),
    ):
        frappe.cache.delete_value(key)


def _refresh_key(user: str) -> str:
    return f"{CACHE_PREFIX}_refresh:{user}"


def check_refresh_allowed(user: str) -> None:
    """At most one asked-for plan a minute per person: each is an AI call."""
    # one atomic SET NX, so two quick clicks can't both get through
    acquired = frappe.cache.set(  # key is site-prefixed via make_key; set_value can't do NX - nosemgrep
        frappe.cache.make_key(_refresh_key(user)),
        1,
        nx=True,
        ex=REFRESH_COOLDOWN_SECONDS,
    )
    if not acquired:
        frappe.throw(_("Your plan was refreshed less than a minute ago."))


def action_plan(user: str, day: dict, refresh: bool = False) -> dict:
    """Today's AI plan for the user, cached until midnight, else a plan built
    from the rules. `stale` says the user's work changed since it was written;
    `ai_enabled` whether asking again can bring an AI plan."""
    from helpdesk.ai_suggestion import is_ai_configured

    fallback = rule_steps(day)
    ai_enabled = is_ai_configured()
    plan = {"source": RULES, "reason": None, "ai_enabled": ai_enabled, "stale": False}
    if not fallback:
        # nothing open: no plan to write, and no reason to ask the AI
        return {**plan, "steps": []}
    facts = plan_facts(day)
    digest = hashlib.sha256(
        json.dumps(facts, sort_keys=True, default=str).encode()
    ).hexdigest()
    key = plan_cache_key(user)
    cached = None if refresh else frappe.cache.get_value(key, expires=True)
    if cached:
        return {**plan, **cached, "stale": cached["digest"] != digest}

    if not ai_enabled:
        reason = _("AI isn't set up on this hub.")
    elif not refresh and frappe.cache.get_value(_failed_key(user), expires=True):
        reason = _("The AI couldn't write a plan a few minutes ago.")
    else:
        steps, reason = write_steps(facts)
        if steps:
            written = {
                "source": AI,
                "steps": [{"text": s} for s in steps],
                "generated_at": str(now_datetime()),
                "digest": digest,
            }
            frappe.cache.set_value(key, written, expires_in_sec=_seconds_to_midnight())
            return {**plan, **written}
        frappe.cache.set_value(_failed_key(user), 1, expires_in_sec=AI_RETRY_SECONDS)
    return {
        **plan,
        "reason": reason,
        "steps": fallback,
        "generated_at": str(now_datetime()),
    }


def _failed_key(user: str) -> str:
    return f"{CACHE_PREFIX}_failed:{user}"


def _seconds_to_midnight() -> int:
    midnight = datetime.combine(add_days(getdate(nowdate()), 1), time.min)
    return max(int((midnight - now_datetime()).total_seconds()), 60)


# --- facts -------------------------------------------------------------------


def plan_facts(day: dict) -> dict:
    """What the AI may use: the user's own work and what waits on them, nothing
    about anyone else's tasks beyond the ones they gave out."""
    today = getdate(nowdate())
    return {
        "today": f"{today} ({today.strftime('%A')})",
        "counts": day["summary"],
        "close_first": [_task_fact(t, today) for t in _items(day, "close_first")],
        "in_progress": [_task_fact(t, today) for t in _items(day, "in_progress")],
        "waiting": [_task_fact(t, today) for t in _items(day, "waiting")],
        "coming_up": [_task_fact(t, today) for t in _items(day, "coming_up")],
        "no_due_date": {
            "count": day["no_date"]["count"],
            "tasks": [t["title"] for t in _items(day, "no_date")],
        },
        "tickets_waiting_for_reply": [
            {"ticket": t["title"], "customer": t.get("customer")}
            for t in _items(day, "replies")
        ],
        "tasks_to_review": [t["title"] for t in _items(day, "approvals")],
        "given_out": [
            {
                **_task_fact(t, today),
                "assignee": ", ".join(t.get("assignee_names") or []),
            }
            for t in _items(day, "given_out")
        ],
    }


def _items(day: dict, section: str) -> list[dict]:
    return day[section]["items"][:FACT_ITEMS]


def _task_fact(task: dict, today) -> dict:
    fact = {
        "task": task["title"],
        "project": task.get("project_name"),
        "status": task["status"],
        "due": task["deadline"],
    }
    if task["is_overdue"]:
        fact["days_overdue"] = _days_late(task, today)
    if task["is_key"]:
        fact["key"] = True
    if task.get("timer"):
        fact["timer"] = task["timer"]
    if task.get("hold_reason"):
        fact["hold_reason"] = task["hold_reason"]
        fact["days_on_hold"] = task.get("hold_days")
        if task.get("hold_note"):
            fact["hold_note"] = truncate(task["hold_note"], NOTE_CHARS)
    if task.get("assigned_by_name"):
        fact["assigned_by"] = task["assigned_by_name"]
    return fact


def _days_late(task: dict, today) -> int:
    return max((today - getdate(task["deadline"])).days, 0) if task["deadline"] else 0


# --- the AI ------------------------------------------------------------------


def write_steps(facts: dict) -> tuple[list[str], str | None]:
    """The AI's steps, or none and why. Never raises: Home works without it."""
    try:
        result = call_haiku(SYSTEM_PROMPT, json.dumps(facts, indent=1, default=str))
    except Exception:  # noqa: BLE001 - provider errors vary; the rules plan still works
        frappe.log_error(
            title="Home action plan failed", message=frappe.get_traceback()
        )
        return [], _("The AI couldn't be reached.")
    response = result.get("response") if isinstance(result, dict) else None
    steps = clean_steps(response, facts)
    if len(steps) < MIN_STEPS:
        frappe.log_error(
            title="Home action plan: AI answer not usable",
            message=str(response)[:3000],
        )
        return [], _("The AI's answer couldn't be used.")
    return steps, None


def clean_steps(response, facts: dict) -> list[str]:
    """Plain-text steps, at most MAX_STEPS, without any that has a number the
    facts don't have."""
    if not isinstance(response, dict) or not isinstance(response.get("steps"), list):
        return []
    known = fact_numbers(facts)
    steps = []
    for raw in response["steps"]:
        if not isinstance(raw, str):
            continue
        # the page numbers the steps; drop the model's own "1." before the guard
        text = re.sub(r"^\s*\d+[.)]\s*", "", re.sub(r"<[^>]+>", "", raw)).strip()
        if text and not invents_numbers(text, known):
            steps.append(truncate(text, STEP_CHARS))
    return steps[:MAX_STEPS]


# --- the rules ---------------------------------------------------------------


def rule_steps(day: dict) -> list[dict]:
    """The plan without AI, in Home's priority order. Steps about one task carry
    its name and project so the page can link them."""
    today = getdate(nowdate())
    today_str = str(today)
    steps = []

    def task_step(text: str, task: dict):
        steps.append({"text": text, "task": task["name"], "project": task["project"]})

    for task in day["close_first"]["items"]:
        title = task["title"]
        if task["is_overdue"]:
            late = _days_late(task, today)
            task_step(
                _("Close “{0}” first: it is {1} day(s) overdue.").format(title, late)
                if late
                else _("Close “{0}” first: it has run past its estimate.").format(
                    title
                ),
                task,
            )
        elif task["deadline"] == today_str:
            task_step(_("Finish “{0}” today.").format(title), task)
        else:
            task_step(_("Keep going on key task “{0}”.").format(title), task)
    for task in day["in_progress"]["items"]:
        if task.get("timer") == "paused":
            task_step(
                _("Resume “{0}”: its timer is paused.").format(task["title"]), task
            )
        else:
            task_step(_("Keep going on “{0}”.").format(task["title"]), task)
    if day["replies"]["count"]:
        steps.append(
            {
                "text": _("Reply to {0} ticket(s) waiting for you.").format(
                    day["replies"]["count"]
                )
            }
        )
    if day["approvals"]["count"]:
        steps.append(
            {
                "text": _("Review {0} task(s) waiting for your sign-off.").format(
                    day["approvals"]["count"]
                )
            }
        )
    for task in day["waiting"]["items"]:
        if task.get("hold_reason"):
            task_step(
                _("Follow up on “{0}”: {1} for {2} day(s).").format(
                    task["title"],
                    task["hold_reason"].lower(),
                    task.get("hold_days") or 0,
                ),
                task,
            )
    for task in day["given_out"]["items"]:
        names = ", ".join(task.get("assignee_names") or [])
        task_step(
            _("Check in with {0} on “{1}”.").format(names, task["title"])
            if names
            else _("Check on “{0}”.").format(task["title"]),
            task,
        )
    no_date = day["no_date"]
    if no_date["count"]:
        can_plan = any(t.get("can_plan") for t in no_date["items"])
        steps.append(
            {
                "text": (
                    _("Set due dates on {0} task(s) that have none.")
                    if can_plan
                    else _("Ask your lead for due dates on {0} task(s).")
                ).format(no_date["count"])
            }
        )
    for task in day["coming_up"]["items"]:
        task_step(
            _("Plan ahead for “{0}”, due {1}.").format(
                task["title"], _short_date(task["deadline"])
            ),
            task,
        )
    return steps[:MAX_STEPS]


def _short_date(value: str) -> str:
    day = getdate(value)
    return f"{day.day} {day.strftime('%b')}"
