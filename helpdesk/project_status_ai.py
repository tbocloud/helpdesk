"""Splits one spoken or pasted weekly update into a proposed update per project.

The coordinator talks through every project in one go, in Malayalam and English mixed.
The AI proposes; nothing is saved until the person has reviewed and saved the rows
(helpdesk.api.project_status.save_status_updates). Only what the text says is proposed:
a date is kept only when the words it came from are in the text, and a project is kept
only when it is one the person may write. See docs/project-status-report.md.
"""

import difflib
import re

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from helpdesk.ai_engine import call_haiku, fact_numbers, invents_numbers
from helpdesk.ai_suggestion import is_ai_configured
from helpdesk.project_status import select_options

MAX_TEXT_CHARS = 12000
MAX_UPDATE_CHARS = 600
MAX_STEP_CHARS = 140
# how close a heard name must be to a project's name or alias (0 to 1)
NAME_MATCH_CUTOFF = 0.8
MIN_ALIAS_CHARS = 3
# a next-step date further out than this is more likely a slip of the model
MAX_DAYS_AHEAD = 366

SYSTEM_PROMPT = """You turn a project coordinator's weekly status talk into one update per project for TBO, a company that implements ERPNext, builds mobile apps and websites and runs digital marketing.

You get TODAY (a date and weekday), a TEXT and the PROJECTS the speaker may update, each with an id, a name, its client and aliases. The text is spoken or typed English, Malayalam (in Malayalam script or in English letters) or a mix of them. Names are often misspelled or shortened: match them to the closest project. Write everything in English; keep names as they are.

For each project the text talks about, return:
- project: the id from PROJECTS.
- stage: one of STAGES, only when the text says or clearly means it; else null.
- waiting_on: one of WAITING_ON ("Nothing" only when the text says nobody is being waited for), only when the text says it; else null.
- update: one to three short lines, each starting with "- ", saying what is done and what is pending, using only the text.
- next_step: a short phrase for what happens next, only if the text says it; else null.
- next_step_date_words: the exact words of the text that give the date of the next step (for example "Monday", "within 2 days", "5 Nov"), else null.
- next_step_date: that date as YYYY-MM-DD worked out from TODAY, else null.

Rules:
- Leave out projects the text does not talk about. Never add a project that is not in PROJECTS.
- Use only what the text says. Never invent facts, names, numbers or dates. When the text gives no date, next_step_date and next_step_date_words are null.
- One entry per project: put everything said about it in that entry.
- Plain text only, no Markdown other than the "- " bullets.

Reply with JSON only: {"updates": [{"project": "<id>", "stage": null, "waiting_on": null, "update": "- ...", "next_step": null, "next_step_date_words": null, "next_step_date": null}]}"""


def aliases(project: dict) -> list[str]:
    """Names a speaker may use for a project: its name, its client, and the first word
    of each (the "Avera" of "Avera IoT"), lowercase, without repeats."""
    found = []
    for name in (project.get("project_name"), project.get("customer")):
        name = " ".join(str(name or "").lower().split())
        if not name:
            continue
        found.append(name)
        found.append(name.split()[0])
    return [a for a in dict.fromkeys(found) if len(a) >= MIN_ALIAS_CHARS]


def alias_index(projects: list[dict]) -> dict[str, str]:
    """{alias or id: project id}. An alias two projects share points to neither."""
    index, shared = {}, set()
    for project in projects:
        for alias in [project["project"].lower(), *aliases(project)]:
            if index.setdefault(alias, project["project"]) != project["project"]:
                shared.add(alias)
    return {alias: name for alias, name in index.items() if alias not in shared}


def match_project(heard: str | None, index: dict[str, str]) -> str | None:
    """The project a name from the AI means: exactly, or the closest alias."""
    heard = " ".join(str(heard or "").lower().split())
    if not heard:
        return None
    if heard in index:
        return index[heard]
    close = difflib.get_close_matches(heard, list(index), n=1, cutoff=NAME_MATCH_CUTOFF)
    return index[close[0]] if close else None


def valid_option(value, fieldname: str) -> str | None:
    return value if value in select_options(fieldname) else None


def safe_date(value, words, text: str, today) -> str | None:
    """The next-step date, only if it is a real date from today on, not a year away,
    and the words it came from are in the text."""
    words = " ".join(str(words or "").lower().split())
    if not words or words not in " ".join(text.lower().split()):
        return None
    try:
        day = getdate(value)
    except Exception:  # noqa: BLE001 - frappe raises its own error type for a bad date
        return None
    if not today <= day <= add_days(today, MAX_DAYS_AHEAD):
        return None
    return str(day)


def clean_update(text) -> str:
    lines = [
        re.sub(r"^\s*[-*•]\s*", "", line).strip()
        for line in str(text or "").replace("**", "").splitlines()
    ]
    return "\n".join(f"- {line}" for line in lines if line)[:MAX_UPDATE_CHARS]


def clean_entry(entry: dict, project: str, text: str, today, known: set[str]) -> dict:
    update = clean_update(entry.get("update"))
    step = " ".join(str(entry.get("next_step") or "").split())[:MAX_STEP_CHARS]
    return {
        "project": project,
        "stage": valid_option(entry.get("stage"), "stage"),
        "waiting_on": valid_option(entry.get("waiting_on"), "waiting_on"),
        "update_text": update,
        "next_step": step,
        "next_step_date": safe_date(
            entry.get("next_step_date"), entry.get("next_step_date_words"), text, today
        ),
        # a number the text never said is a sign the model made something up
        "needs_check": invents_numbers(f"{update} {step}", known),
    }


def merge(entries: list[dict]) -> list[dict]:
    """One row per project: a second mention adds its lines to the first."""
    merged = {}
    for entry in entries:
        first = merged.setdefault(entry["project"], entry)
        if first is not entry:
            first[
                "update_text"
            ] = f"{first['update_text']}\n{entry['update_text']}".strip()
            first["needs_check"] = first["needs_check"] or entry["needs_check"]
            for field in ("stage", "waiting_on", "next_step", "next_step_date"):
                first[field] = first[field] or entry[field]
    return list(merged.values())


def split_update(text: str, projects: list[dict]) -> list[dict]:
    """Proposed updates from `text` for the `projects` (dicts with `project`,
    `project_name` and `customer`) the speaker may update; none is saved."""
    text = str(text or "").strip()[:MAX_TEXT_CHARS]
    if not text:
        frappe.throw(_("Paste or record the update first."))
    if not projects:
        frappe.throw(_("You have no project to write updates for."))
    if not is_ai_configured():
        frappe.throw(
            _(
                "AI isn't set up. An administrator adds an AI key in Settings → AI providers."
            )
        )
    today = getdate(nowdate())
    request = {
        "TODAY": today.strftime("%Y-%m-%d (%A)"),
        "STAGES": select_options("stage"),
        "WAITING_ON": select_options("waiting_on"),
        "PROJECTS": [
            {
                "id": p["project"],
                "name": p["project_name"],
                "client": p.get("customer"),
                "aliases": aliases(p),
            }
            for p in projects
        ],
        "TEXT": text,
    }
    try:
        answer = call_haiku(SYSTEM_PROMPT, frappe.as_json(request))
    except Exception:  # noqa: BLE001 - provider errors vary; the person gets one clear message
        frappe.log_error(
            title="AI project status split failed", message=frappe.get_traceback()
        )
        frappe.throw(_("The AI couldn't read the update just now. Try again."))
    response = answer.get("response") if isinstance(answer, dict) else None
    found = response.get("updates") if isinstance(response, dict) else None
    if not isinstance(found, list):
        frappe.throw(_("The AI couldn't read the update just now. Try again."))
    index = alias_index(projects)
    known = fact_numbers(text)
    entries = []
    for entry in found:
        project = (
            match_project(entry.get("project"), index)
            if isinstance(entry, dict)
            else None
        )
        if project:
            entries.append(clean_entry(entry, project, text, today, known))
    return merge(entries)
