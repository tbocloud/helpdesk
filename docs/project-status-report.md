# Project status report

Replaces the coordinator's hand-made weekly PDF ("PROJECT STATUS REPORT": No., Project,
Status, Details). One row per open project: what a person wrote (stage, who it waits on, a few
lines, the next step) beside facts the hub computes from the tasks, so nothing in the table can
be out of date or mistyped.

Code: `helpdesk/project_status.py` (facts, rows, saving, the Friday report, the stale list),
`helpdesk/project_status_ai.py` (the AI split), `helpdesk/api/project_status.py` (endpoints),
`helpdesk/helpdesk/doctype/hd_project_status_update/`. Page: `desk/src/pages/work/ProjectStatus.vue`
and `components/ProjectStatus*.vue`. Tests: `helpdesk/tests/test_project_status.py`.

## The data: HD Project Status Update

One row per update, never edited (a change is a new row), so the history is kept.

| Field | Notes |
| --- | --- |
| `project` | Link to Project; must be Open or On hold |
| `stage` | Planning, Development, Testing / UAT, Data migration, Training, Go-live, Live, Support, On hold |
| `waiting_on` | Nothing, Client, Internal, Third party |
| `waiting_since` | Date. Empty means "the day this wait was first written": the server keeps the previous update's day while the wait is the same, else today. Cleared for Nothing |
| `update_text` | Small Text, one to three lines or bullets. Called `update_text`, not `update`, because `update` is a method of every document |
| `next_step`, `next_step_date` | What happens next, and when |
| `written_by` | The session user, set by the server |
| `source` | Manual, AI from voice, AI from text |

Stage, waiting on and source are read from the doctype's Select options (`select_options`), the
one list the page, the AI prompt and the validation share.

**Who writes**: the people who run the project (`can_coordinate_project`): System Managers and
Agent Managers, the project's managers (creator and members with the Project Manager project
role), its lead, and its Project Coordinators. `has_permission` on the doctype enforces it for
every path (API, desk, scripts); `writable_projects` is the same rule for many projects at once
(a test checks they agree). **Who reads**: whoever can read the project (`permission_query`), so
a member sees the updates of their projects only.

Decision: the latest values are **not** copied onto Project as custom fields. The newest update per
project is one grouped query (`latest_updates`), so a copy would only add a second place to keep
true.

## Facts per project (computed)

`task_facts`, `client_wait_days`, `contradictions`, `update_age`:

- tasks done / total (cancelled and templates left out), overdue (the portfolio's
  `is_task_overdue`, so a held task is never overdue), tasks on hold with their reason and days;
- next milestone: the earliest open task flagged milestone, with its date;
- days waiting on the client: from `waiting_since` when the written status waits on the Client,
  else from the oldest task held for "Waiting on customer";
- last activity: the newest change to any of its tasks;
- update age: days since the newest update; the update is **stale** after more than 7 days
  (`STALE_DAYS`), or when there is none. A project whose stage is On hold is never stale.

Facts are counted over every task of the project whoever asks, so a member's report is as true
as a manager's; only the task titles of held tasks and the next milestone are shown.

**Contradictions** (shown in red on the row):

| Code | When |
| --- | --- |
| `live_with_overdue` | stage Live or Support, but open tasks are overdue |
| `client_hold_not_waiting` | waiting on Nothing, but tasks are held for the customer |
| `project_on_hold` | the Project is On hold, but the latest stage says otherwise |

A project that is On hold and has no update yet shows the stage "On hold".

## AI split

`split_status_update(text)` (POST) reads a pasted or spoken report, English, Malayalam or both,
and proposes one update per project mentioned. It uses the hub's one AI call, `call_haiku`
(the same providers, keys and fallback as task descriptions, triage and summaries; see
[ai-providers.md](ai-providers.md)); without a key the page says so and disables the button.

What goes to the AI: today's date, the stage and waiting-on lists, the text, and the projects
**the user may write** (id, name, client, aliases). Aliases are derived, not typed: the project
name, the client and the first word of each ("Avera" for "Avera IoT"). Nothing else about a
project is sent.

Guards, all server-side (`project_status_ai.py`):

- A project is accepted only if it is in the list. The AI returns the id; a name it heard
  ("Galum") is matched to the closest alias (difflib, cutoff 0.8). An alias two projects share
  matches neither. Projects not mentioned are not returned.
- A **date** is kept only if the AI also quotes the words it came from (`next_step_date_words`,
  e.g. "within 2 days"), those words are in the text, and it is a real date from today to a year
  ahead. `waiting_since` is never taken from the AI.
- A stage or waiting-on outside the options is dropped (the review table keeps the project's
  current value).
- A number in the update or next step that is not in the text marks the row **Check the numbers**
  in the review.
- Two mentions of one project become one row.

Nothing is saved by the split. The page shows the rows as an editable list (stage, waiting on,
update, next step, date), each row removable; **Save all** sends them in one request, all saved
or none (a row for a project the user may not write fails the whole save). Source is "AI from
voice" if the mic was used, else "AI from text".

**Voice**: the hub already has a recorder, `pages/leads/VoiceButton.vue` (the browser's speech
service, Chrome and Edge, EN or ML, no audio to TBO or the AI). The dialog reuses it; the button
gained a `listening` event so the source can be recorded. Browsers without it paste.

## The page (`/project-status`)

Open to every agent; the server returns the open and on-hold projects the user can see, so
members see their own projects and managers, leads and coordinators theirs (admins all). Linked
from Team and Projects. Rows are sorted by attention: contradictions and overdue work, then
stale or missing updates, then waiting, then the rest, projects on hold last
(`attention_key`). Filters (client side): department, lead, stage, waiting on.

Each row: number, project (link to its board), client, lead; the stage chip (colour plus text and
an icon: Live and Support green, waiting on the client amber, overdue or a contradiction red, on
hold and the rest gray); who it waits on and for how many days; the written bullets; the facts
line ("3/12 tasks done · 1 overdue · 2 on hold (Waiting on customer)"), next milestone and
contradictions; the next step and date; the update's age (stale flagged). Actions: **Update
status** (only where the user may write; prefilled from the last update), **History**, and in the
header **Paste or record a full update** and **Download PDF**.

A reminder opens `/project-status?project=<name>`, which opens that project's update dialog
for people who may write it.

**Download PDF** is the browser's print of `ProjectStatusPrint.vue`: a table on `<body>` that is
hidden on screen and, when printing, the only thing shown, on A4 portrait. Title "Project Status
Report", the report date, then the numbered table (No., Project, Status, Details) of the rows as
filtered and sorted on screen. The file is named after the report. No new dependency.

## The Friday report

`send_weekly_report`, cron `0 17 * * 5` (the server's time zone, which is the site's): one message
per recipient through the follow-ups' delivery (`deliver_digest`): Teams or Slack when chat is on,
else email. "Needs attention" projects come first, one numbered line each: name, stage, who it
waits on and for how long, overdue count, contradictions, update age and the first line of the
update, linking to the page. It sends nothing when there is no recipient or no project; one failed
message is logged and the rest go out.

Recipients: **Settings → Tasks → Project status report → Send to** (`HD Work Settings.status_report_recipients`,
System Managers can edit it). Left empty: every System Manager plus everyone who is a Project
Coordinator on any project. Disabled users are skipped.

## The stale reminder

A follow-up rule, `stale_status` (`ProjectRules` in `follow_ups.py`; see
[follow-ups.md](follow-ups.md)): an Open project whose newest update is more than 7 days old (a
project with none counts from the day it was created) tells its **lead and coordinators**, or its
managers when it has no lead. One notice per person and project, rewritten but not unread again
while it stays stale; it ends when the update is written. Switch: **Project rules → Project status
out of date** in Settings → Follow-ups (`HD Follow Up Settings.project_status`, on by default;
patch `v16_0_2.enable_project_status_follow_up` switches it on for stored settings). Projects whose
stage is On hold are left alone.

## What the owner sets up

1. **Who writes updates**: make the coordinator (e.g. archana@) a **Project Coordinator** on each
   project (Project → team → role), or a project manager. Leads can already write theirs.
2. **Recipients** of the Friday report in Settings → Tasks (or leave empty for the default).
3. An AI key (Settings → AI providers) for the paste-or-record split.
