"""Repeat issues: the same problem coming back from the same customer.

For a Scoreboard period and scope, the customers' tickets and tasks of the last
LOOKBACK_DAYS (plus the period itself) are grouped per customer into clusters of
look-alike items. A cluster is a repeat issue when it has at least
MIN_OCCURRENCES items in that window and at least MIN_IN_PERIOD in the period.
The detection is plain word matching, so it costs no AI call and works offline;
the AI only gives a cluster a short title, a likely cause and a fix
(`label_clusters`), and the page falls back to the most common subject without it.

Repeats are a customer and process insight: they never change anyone's score.
Dismissals and root-cause tasks are kept in HD Repeat Issue. The rules and their
reasons are in docs/team-dashboard.md (Repeat issues).
"""

import hashlib
import json
import math
import re
from collections import Counter, defaultdict

import frappe
from frappe import _
from frappe.query_builder.functions import Substring
from frappe.utils import add_days, cint, flt, getdate

from helpdesk import team_dashboard as td
from helpdesk.ai_engine import call_haiku, fact_numbers, invents_numbers
from helpdesk.ai_suggestion import GREETING_WORDS
from helpdesk.api.ticket_ai import html_to_text, truncate
from helpdesk.duplicates import REPLY_PREFIX
from helpdesk.helpdesk.doctype.hd_repeat_issue.hd_repeat_issue import HDRepeatIssue
from helpdesk.search import STOPWORDS

# the history a period's items are compared with, before the period starts
LOOKBACK_DAYS = 90
# a repeat issue: this many items in the look-back window (the period included),
# at least MIN_IN_PERIOD of them in the period; site config may change both
MIN_OCCURRENCES = 3
MIN_IN_PERIOD = 1
# two items are alike when their words overlap by WORD_THRESHOLD (Jaccard over
# IDF weights, so shared rare words count most) or their subjects' letter trigrams
# by TRIGRAM_THRESHOLD (near-identical subjects, typos); the same ticket type or
# task category adds KIND_BONUS to the words, so it can tip a close pair but
# never link unrelated ones
WORD_THRESHOLD = 0.3
TRIGRAM_THRESHOLD = 0.6
KIND_BONUS = 0.1
# a ticket type or task category on more than this share of the items is ignored
KIND_MAX_SHARE = 0.5
# subject words count twice as much as description words
SUBJECT_WEIGHT = 2.0
DESCRIPTION_WORDS = 40
DESCRIPTION_CHARS = 2000
# "rising": at least RISING_MIN this period, and RISING_RATIO times faster than
# in the look-back before the period
RISING_MIN = 2
RISING_RATIO = 1.5
# bounds that keep the page fast however many tickets there are
MAX_ROWS = 6000
MAX_ITEMS_PER_CUSTOMER = 300
MAX_CLUSTERS = 60
KEYWORDS = 6
# a stored decision still applies to a cluster with this share of its keywords
KEYWORD_MATCH = 0.5
MAX_SUBJECTS_FOR_AI = 8
AI_BATCH = 20
AI_TEXT_CHARS = 160

CACHE_PREFIX = "repeat_issues"
CACHE_SECONDS = 10 * 60
LABEL_SECONDS = 14 * 24 * 60 * 60
# after a failed AI call, clusters keep their subject titles for this long
LABEL_RETRY_SECONDS = 15 * 60
LABEL_JOB_TIMEOUT = 600

TICKET = "HD Ticket"
TASK = "Task"
SKIPPED_TASK_STATUSES = ("Cancelled", "Template")
# ticket types that say nothing about the problem
GENERIC_KINDS = {"", "unspecified"}

# words that say nothing about the problem, besides the search stopwords and the
# AI suggestion's greeting words
EXTRA_STOPWORDS = {
    "about",
    "after",
    "again",
    "all",
    "already",
    "am",
    "before",
    "best",
    "can",
    "check",
    "customer",
    "dated",
    "day",
    "did",
    "does",
    "done",
    "fix",
    "get",
    "gives",
    "had",
    "hai",
    "hi",
    "kind",
    "kindly",
    "madam",
    "my",
    "need",
    "now",
    "only",
    "rs",
    "same",
    "should",
    "sir",
    "some",
    "still",
    "support",
    "takes",
    "ticket",
    "today",
    "us",
    "very",
    "warm",
    "we",
    "were",
    "yesterday",
}
STOP = set(STOPWORDS) | GREETING_WORDS | EXTRA_STOPWORDS
# a few words customers use for the same thing, after stemming
SYNONYMS = {
    "incorrect": "wrong",
    "invalid": "wrong",
    "display": "show",
    "appear": "show",
    "fail": "error",
}
SIGN_OFF = re.compile(
    r"\b(regards|thanks|thank you|thanking you|best wishes|cheers)\b.*$",
    re.IGNORECASE | re.DOTALL,
)
EMAIL_OR_URL = re.compile(r"\S+@\S+|https?://\S+|www\.\S+", re.IGNORECASE)
# any word with a digit in it: ticket and document numbers, dates, amounts, GSTINs
WITH_DIGIT = re.compile(r"\S*\d\S*")
WORD = re.compile(r"[a-z]{2,}")

LABEL_PROMPT = """You name recurring support issues for TBO's support managers. TBO supports ERPNext / Frappe users.
Each cluster lists the subjects of tickets and tasks one customer raised about what looks like the same problem.
For each cluster write:
- title: what keeps going wrong, at most 8 words, specific (e.g. "Sales invoice print shows old GSTIN");
- cause: one short sentence with the most likely root cause, worded as a likelihood;
- fix: one short sentence with the change that would stop it coming back.
Use only the subjects. Never invent names, document numbers, amounts, dates or facts; never include numbers that aren't in that cluster's subjects.
Plain text only, no HTML or markdown.
Reply with JSON only: {"clusters": [{"id": "...", "title": "...", "cause": "...", "fix": "..."}]}"""


# --- words ---------------------------------------------------------------------


def stem(word: str) -> str:
    """A light stem so "printed", "printing" and "prints" match "print", and
    "invoices" matches "invoice"."""
    if len(word) > 4 and word.endswith("ies"):
        word = word[:-3] + "y"
    elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    for suffix in ("ing", "ed"):
        if len(word) - len(suffix) >= 3 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    if len(word) > 3 and word.endswith("e"):
        word = word[:-1]
    return SYNONYMS.get(word, word)


def clean_text(text: str | None) -> str:
    """Lowercase text without reply prefixes, the sign-off, emails, links, or any
    word with a digit (numbers, dates, amounts and IDs)."""
    text = REPLY_PREFIX.sub("", text or "")
    text = SIGN_OFF.sub("", text)
    text = EMAIL_OR_URL.sub(" ", text)
    return WITH_DIGIT.sub(" ", text).lower()


def words(text: str | None) -> list[str]:
    """The meaningful words of a text, stemmed, in order, stopwords and greetings out."""
    found = []
    for raw in WORD.findall(clean_text(text)):
        if raw in STOP:
            continue
        word = stem(raw)
        if word not in STOP and len(word) > 1:
            found.append(word)
    return found


def trigrams(text: str) -> set[str]:
    """Letter trigrams of a cleaned subject: catches "GSTIN"/"GST IN" and typos."""
    squashed = " ".join(words(text))
    return {squashed[i : i + 3] for i in range(len(squashed) - 2)}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def weighted_jaccard(a: dict, b: dict) -> float:
    """Jaccard over word weights: shared rare words count more than shared common ones."""
    keys = a.keys() | b.keys()
    top = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
    if not top:
        return 0.0
    return sum(min(a.get(k, 0), b.get(k, 0)) for k in keys) / top


def alike(a: dict, b: dict) -> bool:
    """Two prepared items (`prepare`) are about the same thing: enough of the same
    words, weighted by how rare they are (plus KIND_BONUS for the same ticket type
    or task category), or nearly the same subject letter by letter."""
    words_score = weighted_jaccard(a["weights"], b["weights"])
    if a["kind_key"] and a["kind_key"] == b["kind_key"]:
        words_score += KIND_BONUS
    return (
        words_score >= WORD_THRESHOLD
        or jaccard(a["grams"], b["grams"]) >= TRIGRAM_THRESHOLD
    )


# --- clustering ------------------------------------------------------------------


def prepare(items: list[dict]) -> list[dict]:
    """Adds each item's word weights (IDF over all the items, so words every
    ticket has count little), subject trigrams and kind."""
    found = []
    for item in items:
        subject = set(words(item["subject"]))
        found.append(
            (subject, subject | set(words(item["description"])[:DESCRIPTION_WORDS]))
        )
    # log((n + 1) / df): a word in nearly every item weighs almost nothing
    df = Counter(w for _subject, all_words in found for w in all_words)
    idf = {w: math.log((len(items) + 1) / n) for w, n in df.items()}
    for item, (subject, all_words) in zip(items, found):
        item["weights"] = {
            w: idf[w] * (SUBJECT_WEIGHT if w in subject else 1.0) for w in all_words
        }
        item["grams"] = trigrams(item["subject"])
        kind = (item.get("kind_label") or "").strip().lower()
        item["kind_key"] = "" if kind in GENERIC_KINDS else f"{item['kind']}:{kind}"
    # a type or category most items have (the default one) says nothing either
    kinds = Counter(item["kind_key"] for item in items)
    for item in items:
        if kinds[item["kind_key"]] > len(items) * KIND_MAX_SHARE:
            item["kind_key"] = ""
    return items


def cluster(items: list[dict]) -> list[list[dict]]:
    """Groups one customer's prepared items: two items are in one group when a
    chain of `alike` pairs joins them."""
    parent = list(range(len(items)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if root(i) != root(j) and alike(items[i], items[j]):
                parent[root(j)] = root(i)
    groups = defaultdict(list)
    for i, item in enumerate(items):
        groups[root(i)].append(item)
    return list(groups.values())


def keywords(group: list[dict]) -> list[str]:
    """The cluster's KEYWORDS heaviest words: what it is about, and how a stored
    dismissal recognises it again."""
    weight = Counter()
    for item in group:
        weight.update(item["weights"])
    return sorted(w for w, _ in weight.most_common(KEYWORDS))


def signature(customer: str, words_: list[str]) -> str:
    return hashlib.sha1(f"{customer}|{' '.join(words_)}".encode()).hexdigest()[:16]


def thresholds() -> tuple[int, int]:
    """(least items in the look-back, least in the period); site config may change
    them, never below 2 and 1."""
    return (
        max(
            cint(frappe.conf.get("repeat_issues_min_occurrences")) or MIN_OCCURRENCES, 2
        ),
        max(cint(frappe.conf.get("repeat_issues_min_in_period")) or MIN_IN_PERIOD, 1),
    )


# --- the records -----------------------------------------------------------------


def window(period: str, today) -> dict:
    """The period, how far back the history goes, and the last day counted."""
    today = getdate(today)
    start, end = td.period_bounds(period, today)
    return {
        "start": start,
        "end": end,
        "since": add_days(start, -LOOKBACK_DAYS),
        "last": min(end, today),
    }


def ticket_items(since, last) -> list[dict]:
    """The customers' tickets raised in the window. A ticket merged into another
    is left out: it is counted once, as the ticket it was merged into."""
    ticket = frappe.qb.DocType(TICKET)
    rows = (
        frappe.qb.from_(ticket)
        .select(
            ticket.name,
            ticket.subject,
            Substring(ticket.description, 1, DESCRIPTION_CHARS).as_("description"),
            ticket.customer,
            ticket.ticket_type,
            ticket.creation,
            ticket["_assign"],
            ticket.status,
            ticket.resolution_time,
        )
        .where(
            ticket.customer.isnotnull()
            & (ticket.customer != "")
            & (ticket.is_merged == 0)
            & ticket.creation.between(f"{since} 00:00:00", f"{last} 23:59:59")
        )
        .orderby(ticket.creation, order=frappe.qb.desc)
        .limit(MAX_ROWS)
        .run(as_dict=True)
    )
    return [
        {
            "kind": "ticket",
            "doctype": TICKET,
            "name": str(r.name),
            "subject": r.subject or "",
            "description": html_to_text(r.description),
            "customer": r.customer,
            "kind_label": r.ticket_type,
            "date": getdate(r.creation),
            "users": td.assignees(r._assign),
            "status": r.status,
            "project": None,
            "department": None,
            "hours": flt(r.resolution_time) / 3600 if r.resolution_time else None,
        }
        for r in rows
    ]


def task_items(since, last) -> list[dict]:
    """Tasks of the customers' projects created in the window. Planned work is
    left out: tasks a recurring-task schedule made (they are meant to repeat) and
    content calendar tasks."""
    task = frappe.qb.DocType(TASK)
    project = frappe.qb.DocType("Project")
    rows = (
        frappe.qb.from_(task)
        .join(project)
        .on(project.name == task.project)
        .select(
            task.name,
            task.subject,
            Substring(task.description, 1, DESCRIPTION_CHARS).as_("description"),
            project.customer,
            task.custom_category,
            task.creation,
            task["_assign"],
            task.status,
            task.project,
            task.hd_ticket,
            project.custom_department.as_("department"),
        )
        .where(
            project.customer.isnotnull()
            & (project.customer != "")
            & task.custom_recurring_task.isnull()
            & task.content_post.isnull()
            & task.status.notin(SKIPPED_TASK_STATUSES)
            & task.creation.between(f"{since} 00:00:00", f"{last} 23:59:59")
        )
        .orderby(task.creation, order=frappe.qb.desc)
        .limit(MAX_ROWS)
        .run(as_dict=True)
    )
    return [
        {
            "kind": "task",
            "doctype": TASK,
            "name": r.name,
            "subject": r.subject or "",
            "description": html_to_text(r.description),
            "customer": r.customer,
            "kind_label": r.custom_category,
            "date": getdate(r.creation),
            "users": td.assignees(r._assign),
            "status": r.status,
            "project": r.project,
            "department": r.department,
            "hours": None,
            "ticket": str(r.hd_ticket) if r.hd_ticket else None,
        }
        for r in rows
    ]


def scoped_items(win: dict, department: str | None) -> list[dict]:
    """Tickets and tasks in scope. Tickets belong to the support department
    (Settings → Follow-ups), as in the team insights; a task made from a ticket is
    the same issue, so only the ticket counts."""
    from helpdesk import follow_ups

    tickets = ticket_items(win["since"], win["last"])
    ticket_department = follow_ups.get_settings().ticket_department or None
    for t in tickets:
        t["department"] = ticket_department
    names = {t["name"] for t in tickets}
    # a root-cause task is the answer to a repeat, not one more occurrence of it
    issue = frappe.qb.DocType("HD Repeat Issue")
    fixes = set(
        frappe.qb.from_(issue)
        .select(issue.task)
        .where(issue.task.isnotnull() & (issue.task != ""))
        .run(pluck=True)
    )
    tasks = [
        t
        for t in task_items(win["since"], win["last"])
        if t.get("ticket") not in names and t["name"] not in fixes
    ]
    items = tickets + tasks
    if department:
        items = [i for i in items if i["department"] == department]
    return items


# --- detection -------------------------------------------------------------------


def detect(period: str, department: str | None, today) -> dict:
    """Every repeat issue in scope, without the stored decisions or AI titles
    (those change on their own; see `repeat_issues`). Cached for CACHE_SECONDS."""
    today = getdate(today)
    win = window(period, today)
    key = f"{CACHE_PREFIX}:{period}:{win['start']}:{department or ''}:{today}"
    cached = frappe.cache.get_value(key, expires=True)
    if cached is not None:
        return cached
    result = compute(win, scoped_items(win, department))
    frappe.cache.set_value(key, result, expires_in_sec=CACHE_SECONDS)
    return result


def compute(win: dict, items: list[dict]) -> dict:
    """Clusters per customer, kept when they pass the thresholds, biggest first."""
    least, least_in_period = thresholds()
    by_customer = defaultdict(list)
    for item in items:
        by_customer[item["customer"]].append(item)
    prepare(items)
    clusters = []
    for customer, own in by_customer.items():
        if len(own) < least:
            continue
        own = sorted(own, key=lambda i: i["date"], reverse=True)[
            :MAX_ITEMS_PER_CUSTOMER
        ]
        for group in cluster(own):
            in_period = [i for i in group if i["date"] >= win["start"]]
            if len(group) >= least and len(in_period) >= least_in_period:
                clusters.append(describe(customer, group, len(in_period), win))
    clusters.sort(key=lambda c: (-c["in_period"], -c["total"], c["customer"]))
    return {
        "start": str(win["start"]),
        "end": str(win["end"]),
        "since": str(win["since"]),
        "clusters": clusters[:MAX_CLUSTERS],
    }


def describe(customer: str, group: list[dict], in_period: int, win: dict) -> dict:
    """What the page shows about one cluster (before titles and decisions)."""
    group = sorted(group, key=lambda i: (i["date"], i["name"]), reverse=True)
    words_ = keywords(group)
    earlier = len(group) - in_period
    period_days = max((getdate(win["last"]) - getdate(win["start"])).days + 1, 1)
    rising = in_period >= RISING_MIN and in_period / period_days > (
        RISING_RATIO * earlier / LOOKBACK_DAYS
    )
    people = Counter(u for i in group for u in i["users"])
    hours = [i["hours"] for i in group if i["hours"]]
    kinds = Counter(i["kind_label"] for i in group if i["kind_label"])
    return {
        "id": signature(customer, words_),
        "customer": customer,
        "keywords": words_,
        "subject": most_common_subject(group, words_),
        "subjects": [i["subject"] for i in group[:MAX_SUBJECTS_FOR_AI]],
        "tickets": sum(i["kind"] == "ticket" for i in group),
        "tasks": sum(i["kind"] == "task" for i in group),
        "in_period": in_period,
        "earlier": earlier,
        "total": len(group),
        "first_seen": str(group[-1]["date"]),
        "last_seen": str(group[0]["date"]),
        "trend": "rising" if rising else "steady",
        "kinds": [{"label": k, "count": n} for k, n in kinds.most_common(3)],
        "people": [{"user": u, "count": n} for u, n in people.most_common()],
        "avg_resolution_hours": round(sum(hours) / len(hours), 1) if hours else None,
        "departments": sorted({i["department"] for i in group if i["department"]}),
        "items": [
            {
                "kind": i["kind"],
                "doctype": i["doctype"],
                "name": i["name"],
                "subject": i["subject"],
                "date": str(i["date"]),
                "status": i["status"],
                "project": i["project"],
                "in_period": i["date"] >= win["start"],
            }
            for i in group
        ],
    }


def most_common_subject(group: list[dict], words_: list[str]) -> str:
    """The title without AI: the subject most items share once cleaned, else the
    customer's ticket (before a task) with most of the cluster's keywords,
    then the latest; without "Re:"."""
    cleaned = Counter(" ".join(words(i["subject"])) for i in group)
    best, count = cleaned.most_common(1)[0]
    if count > 1 and best:
        pick = next(i for i in group if " ".join(words(i["subject"])) == best)
    else:
        keys = set(words_)
        # `group` is newest first, and max keeps the first of equals
        pick = max(
            group,
            key=lambda i: (i["kind"] == "ticket", len(keys & set(words(i["subject"])))),
        )
    return REPLY_PREFIX.sub("", pick["subject"]).strip()


# --- stored decisions --------------------------------------------------------------


def item_key(item: dict) -> str:
    return f"{item['doctype']}:{item['name']}"


def decisions(customers: list[str]) -> list[dict]:
    """The HD Repeat Issue records of these customers."""
    if not customers:
        return []
    issue = frappe.qb.DocType("HD Repeat Issue")
    task = frappe.qb.DocType(TASK)
    rows = (
        frappe.qb.from_(issue)
        .left_join(task)
        .on(task.name == issue.task)
        .select(
            issue.name,
            issue.customer,
            issue.signature,
            issue.status,
            issue.task,
            issue.keywords,
            issue.items,
            task.subject.as_("task_subject"),
            task.status.as_("task_status"),
            task.project.as_("task_project"),
        )
        .where(issue.customer.isin(customers))
        .run(as_dict=True)
    )
    for r in rows:
        r["keywords"] = set(HDRepeatIssue.parse_list(r["keywords"]))
        r["items"] = set(HDRepeatIssue.parse_list(r["items"]))
    return rows


def save_decision(cluster_: dict, status: str, task: str | None = None):
    """Stores what a manager decided about a cluster: the record that already
    recognises it (`decision_for`), else a new one."""
    record = decision_for(cluster_, decisions([cluster_["customer"]]))
    if record:
        doc = frappe.get_doc("HD Repeat Issue", record["name"])
    else:
        doc = frappe.new_doc("HD Repeat Issue")
        doc.customer = cluster_["customer"]
        doc.signature = cluster_["id"]
    label = cached_label(cluster_["id"])
    doc.apply_cluster(
        title=label["title"] if label else cluster_["subject"],
        keywords=cluster_["keywords"],
        items=[item_key(i) for i in cluster_["items"]],
    )
    doc.status = status
    if task:
        doc.task = task
    doc.decided_by = frappe.session.user
    doc.save(ignore_permissions=True)
    return doc


def decision_for(cluster_: dict, records: list[dict]) -> dict | None:
    """The stored record for this cluster: same customer, and the same signature,
    a shared ticket or task, or mostly the same keywords (clusters grow, so the
    signature alone would forget a dismissal)."""
    items = {item_key(i) for i in cluster_["items"]}
    words_ = set(cluster_["keywords"])
    for r in records:
        if r["customer"] != cluster_["customer"]:
            continue
        if r["signature"] == cluster_["id"] or r["items"] & items:
            return r
        if jaccard(r["keywords"], words_) >= KEYWORD_MATCH:
            return r
    return None


# --- AI titles -------------------------------------------------------------------


def label_key(sig: str) -> str:
    return f"{CACHE_PREFIX}_label:{sig}"


def cached_label(sig: str) -> dict | None:
    return frappe.cache.get_value(label_key(sig), expires=True)


def label_clusters(clusters: list[dict]) -> int:
    """Asks the AI for a title, a likely cause and a fix for the clusters that have
    none cached; returns how many were labelled. Never raises."""
    from helpdesk.ai_suggestion import is_ai_configured

    todo = [c for c in clusters if not cached_label(c["id"])]
    if not todo or not is_ai_configured():
        return 0
    done = 0
    for i in range(0, len(todo), AI_BATCH):
        batch = todo[i : i + AI_BATCH]
        facts = [{"id": c["id"], "subjects": c["subjects"]} for c in batch]
        try:
            result = call_haiku(LABEL_PROMPT, json.dumps({"clusters": facts}, indent=1))
        except Exception:  # noqa: BLE001 - provider errors vary; subjects still work
            frappe.log_error(
                title="Repeat issues: AI titles failed", message=frappe.get_traceback()
            )
            frappe.cache.set_value(
                f"{CACHE_PREFIX}_label_retry", 1, expires_in_sec=LABEL_RETRY_SECONDS
            )
            return done
        response = result.get("response") if isinstance(result, dict) else None
        for c in batch:
            label = clean_label(response, c)
            if label:
                frappe.cache.set_value(
                    label_key(c["id"]), label, expires_in_sec=LABEL_SECONDS
                )
                done += 1
    return done


def clean_label(response, cluster_: dict) -> dict | None:
    """The AI's title, cause and fix for one cluster, plain text, each dropped when
    it has a number that isn't in the cluster's subjects (the Scoreboard's guard).
    None when there's no usable title."""
    if not isinstance(response, dict) or not isinstance(response.get("clusters"), list):
        return None
    found = next(
        (
            c
            for c in response["clusters"]
            if isinstance(c, dict) and c.get("id") == cluster_["id"]
        ),
        None,
    )
    if not found:
        return None
    known = fact_numbers(cluster_["subjects"])

    def honest(value) -> str:
        if not isinstance(value, str):
            return ""
        text = truncate(" ".join(re.sub(r"<[^>]+>", "", value).split()), AI_TEXT_CHARS)
        return "" if invents_numbers(text, known) else text

    title = honest(found.get("title"))
    if not title:
        return None
    return {
        "title": title,
        "cause": honest(found.get("cause")),
        "fix": honest(found.get("fix")),
    }


def needs_labels(clusters: list[dict]) -> bool:
    from helpdesk.ai_suggestion import is_ai_configured

    return (
        any(not cached_label(c["id"]) for c in clusters)
        and not frappe.cache.get_value(f"{CACHE_PREFIX}_label_retry", expires=True)
        and is_ai_configured()
    )


def queue_labels(period: str, department: str | None, today):
    """The AI titles are written in the background; the page shows subjects meanwhile."""
    frappe.enqueue(
        "helpdesk.repeat_issues.label_job",
        queue="long",
        timeout=LABEL_JOB_TIMEOUT,
        job_id=f"repeat-issue-labels-{period}-{department or ''}-{today}",
        deduplicate=True,
        enqueue_after_commit=True,
        period=period,
        department=department,
        today=str(today),
    )


def label_job(period: str, department: str | None, today: str):
    label_clusters(detect(period, department, today)["clusters"])


def precompute():
    """Daily, from the Scoreboard's close job: this week's and month's repeat issues
    for the whole team, with their AI titles, so the first visit is fast."""
    today = getdate()
    for period in ("week", "month"):
        frappe.cache.delete_keys(f"{CACHE_PREFIX}:{period}:")
        label_clusters(detect(period, None, today)["clusters"])


# --- the view --------------------------------------------------------------------


def repeat_issues(period: str, department: str | None, today) -> dict:
    """The page's and the app's answer: the detected clusters with their titles and
    stored decisions, dismissed ones left out, grouped by customer."""
    today = getdate(today)
    found = detect(period, department, today)
    records = decisions(sorted({c["customer"] for c in found["clusters"]}))
    shown = []
    for c in found["clusters"]:
        record = decision_for(c, records)
        if record and record["status"] == "Dismissed":
            continue
        shown.append(present(c, record))
    if needs_labels(found["clusters"]):
        queue_labels(period, department, today)
    customers = group_by_customer(shown)
    return {
        "period": {
            "key": period,
            "start": found["start"],
            "end": found["end"],
            "lookback_start": found["since"],
        },
        "rules": {
            "lookback_days": LOOKBACK_DAYS,
            "min_occurrences": thresholds()[0],
            "min_in_period": thresholds()[1],
        },
        "summary": {
            "issues": len(shown),
            "customers": len(customers),
            "rising": sum(c["trend"] == "rising" for c in shown),
            "tickets_in_period": sum(
                i["kind"] == "ticket" and i["in_period"]
                for c in shown
                for i in c["items"]
            ),
            "tasks_in_period": sum(
                i["kind"] == "task" and i["in_period"]
                for c in shown
                for i in c["items"]
            ),
        },
        "customers": customers,
    }


def present(c: dict, record: dict | None) -> dict:
    label = cached_label(c["id"])
    out = {k: v for k, v in c.items() if k not in ("keywords", "subjects")}
    out["title"] = label["title"] if label else c["subject"]
    out["title_source"] = "ai" if label else "subjects"
    out["cause"] = (label or {}).get("cause") or None
    out["fix"] = (label or {}).get("fix") or None
    out["root_cause"] = (
        {
            "issue": record["name"],
            "task": record["task"],
            "subject": record["task_subject"],
            "status": record["task_status"],
            "project": record["task_project"],
        }
        if record and record["status"] == "Root-cause task" and record["task"]
        else None
    )
    return out


def group_by_customer(clusters: list[dict]) -> list[dict]:
    """Customers by repeat volume this period, each with their clusters, the
    people's names, the cluster's KB article and the customer's open projects."""
    if not clusters:
        return []
    names = td.people_info([p["user"] for c in clusters for p in c["people"]])
    articles = linked_articles(
        [i["name"] for c in clusters for i in c["items"] if i["kind"] == "ticket"]
    )
    projects = open_projects(sorted({c["customer"] for c in clusters}))
    grouped = defaultdict(list)
    for c in clusters:
        for p in c["people"]:
            p["name"] = names.get(p["user"], {}).get("name") or p["user"]
        c["article"] = next(
            (articles[i["name"]] for i in c["items"] if i["name"] in articles), None
        )
        grouped[c["customer"]].append(c)
    rows = [
        {
            "customer": customer,
            "issues": len(own),
            "in_period": sum(c["in_period"] for c in own),
            "total": sum(c["total"] for c in own),
            "rising": sum(c["trend"] == "rising" for c in own),
            "projects": projects.get(customer, []),
            "clusters": own,
        }
        for customer, own in grouped.items()
    ]
    rows.sort(key=lambda r: (-r["in_period"], -r["total"], r["customer"]))
    return rows


def linked_articles(tickets: list[str]) -> dict[str, dict]:
    """The KB article (published or draft) written from each ticket, if any."""
    if not tickets:
        return {}
    article = frappe.qb.DocType("HD Article")
    rows = (
        frappe.qb.from_(article)
        .select(article.name, article.title, article.status, article.source_ticket)
        .where(article.source_ticket.isin(tickets) & (article.status != "Archived"))
        .run(as_dict=True)
    )
    return {
        str(r.source_ticket): {"name": r.name, "title": r.title, "status": r.status}
        for r in rows
    }


def open_projects(customers: list[str]) -> dict[str, list[dict]]:
    """Each customer's open projects: where a root-cause task can go."""
    if not customers:
        return {}
    project = frappe.qb.DocType("Project")
    out = defaultdict(list)
    for r in (
        frappe.qb.from_(project)
        .select(
            project.name,
            project.project_name,
            project.customer,
            project.custom_department,
        )
        .where(project.customer.isin(customers) & (project.status == "Open"))
        .orderby(project.modified, order=frappe.qb.desc)
        .run(as_dict=True)
    ):
        out[r.customer].append(
            {
                "name": r.name,
                "project_name": r.project_name or r.name,
                "department": r.custom_department,
            }
        )
    return dict(out)


def find_cluster(period: str, department: str | None, cluster_id: str, today) -> dict:
    """One detected cluster by its id, or a clear error when it's gone."""
    found = detect(period, department, today)
    match = next((c for c in found["clusters"] if c["id"] == cluster_id), None)
    if not match:
        frappe.throw(
            _(
                "This repeat issue isn't in the list any more. Refresh the page and try again."
            )
        )
    return match
