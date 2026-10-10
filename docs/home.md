# Home

Home answers "what should I do now, and is anything on fire?". Every user, whatever their
role, first gets their own plan for today: a factual line about their open work, a short
numbered action plan, and their work in the order to tackle it. People who run projects get
the company sections below that. Analysis (charts, buckets,
filters by project, customer, assignee and department) lives on the **Overview**
(`/helpdesk/overview`); Home links into it instead of repeating it. Who delivered most and
who is champion is on the **Scoreboard** (`/helpdesk/team-dashboard`, see
[team-dashboard.md](team-dashboard.md)).

- Page: `desk/src/pages/home/Home.vue` (route `Home`, `/helpdesk/home`), with its parts in
  `desk/src/pages/home/components/` and types, link builders and the status sentence in
  `desk/src/pages/home/homeMeta.ts`.
- Data: `helpdesk.api.home.get_home` (agents only), then the action plan as its own
  request, `helpdesk.api.home.get_action_plan` (POST), so a slow AI never holds the page
  up. Every list goes through
  `frappe.get_list` (or is narrowed to records the user can read), so nobody sees records
  they couldn't open.

## Who sees what

| Section | Who | Key in `get_home` |
| --- | --- | --- |
| Header and status line | Everyone | `day.summary` (+ replies and reviews) |
| Follow-ups strip | Everyone with overdue, escalated or waiting work | `follow_ups` |
| Your action plan | Everyone with open work | `get_action_plan` |
| Your day | Everyone | `day` |
| Your projects | Everyone on an open project | `day.projects` |
| Pulse strip | People who can see the Overview (`can_see_overview`: admins, project managers, anyone leading a project) | `company` |
| Needs attention | Same | `company.attention_groups` |
| Customers at risk | Same, only when a customer they may read is at risk or on watch | `company.customer_health` |
| Open tickets by customer, Ending in the next 14 days, Team load | Same | `company.tickets.by_customer`, `company.ending_soon`, `company.people` / `free_people` |
| Systems | Admins (System Manager, Agent Manager) | `systems` |

`company` and `systems` are `null` for people who don't qualify. On screens 1280px and wider
Your projects and the customers, projects and team cards sit in a right-hand column; below
that they follow the main column (action plan, your day, then the rest). **Systems** sits in the main column under Needs attention (two columns on wider
screens), so the side column stays short. The page never scrolls sideways.

## Header

Greeting by time of day, today's date, and one line of facts about the user's **own** open
work, most urgent first, joined with "·", each with an icon (never colour alone) and tabular
numbers, e.g. "1 overdue · 1 due today · 2 on hold · 8 open in 1 project": overdue (red),
due today, on hold, tickets waiting for your reply, tasks waiting for your review, and
"N open across M projects" (all open tasks and tickets, including held, undated and later
ones).

The green "All clear. You have no open work." shows only when that line is empty: nothing
open and nothing waiting for the user's review.

Company problems (SLAs breached, unassigned tickets, overdue work across projects) are not
repeated here; managers see them in the pulse strip right below.

## Follow-ups strip (`follow_ups`)

Under the header, `FollowUpStrip.vue` says what the follow-ups found for this person, e.g.
"2 overdue · 1 escalated to your head · 3 waiting on you" (own overdue work, own work escalated
to L2 or above, own breached tickets, and items waiting on them as reviewer, lead or head),
linking to My Work. It stays until the work moves, and the same strip sits at the bottom of the
sidebar. The plan for today below is also the first part of the person's first Teams digest of
the day. See [follow-ups.md](follow-ups.md).

**Why the old line said "All clear" wrongly (fixed):** the header and Your day counted only
tasks that were overdue, due today or at risk. On-hold tasks, tasks in progress due later,
key tasks and tasks with no due date were left out, so someone with eight open tasks (two on
hold waiting on the customer, a paused task, key tasks, undated ones) and none due today saw
"All clear" and "Nothing due today". Now every open task lands in exactly one section of
Your day and is always counted in the header (`helpdesk/tests/test_home_plan.py`).

## Your action plan (`get_action_plan`, `helpdesk/home_plan.py`)

Three to five numbered steps for today, shown above Your day with a skeleton while they load.

- **Facts only.** `plan_facts()` takes the first five items of each section of the user's
  day: their own tasks (subject, project, status, due date, days overdue, key, timer, hold
  reason, days on hold, hold note, assigned by), tickets waiting for their reply, tasks
  waiting for their review and tasks they gave out (with the assignee's name). Nothing else
  about other people's work is sent, and the facts never include a task the user can't see
  (#94's rules apply through `get_my_work` and `frappe.get_list`).
- **AI.** `call_haiku` writes the steps from those facts (the same client as the Scoreboard
  and task descriptions). `clean_steps()` keeps plain text, strips the model's own numbering
  and **drops any step with a number that isn't in the facts** (`ai_engine.fact_numbers` /
  `invents_numbers`, shared with the Scoreboard's `clean_analysis`). Fewer than three usable
  steps counts as a failed answer.
- **Rules fallback.** When AI isn't set up, fails or answers badly, `rule_steps()` builds the
  plan from the same priority order: close overdue work, finish what's due today, keep key
  work going, resume paused timers, reply to tickets, review tasks, follow up on holds, check
  in on tasks given out, set or ask for due dates, plan ahead. Steps about one task link to
  its project. The card says which it is ("Written by AI from your open work, 5 minutes ago."
  or "Built from your open work, most urgent first." plus the reason).
- **Cache.** An AI plan is cached per user per day (`home_plan:<user>:<date>`, until
  midnight) with a digest of its facts; when the user's work changes, the cached plan is
  still shown, with "Your work changed since this plan was written", until they refresh.
  After a failed AI call, plans come from the rules for 15 minutes before the AI is tried
  again. Nothing open means no plan and no AI call; the card is hidden.
- **Refresh plan** (shown when AI is set up): `get_action_plan(refresh=1)`, at most once a
  minute per person ("Your plan was refreshed less than a minute ago.").
- **Speed.** `get_home` keeps the day it built for two minutes (`home_plan_day:<user>`), so
  the plan request doesn't rebuild it.

## Your day (`day`)

Built from `helpdesk.api.work.get_my_work` (the user's open tasks and tickets, with
`assigned_by_name` and `can_plan`) plus a few grouped queries; no per-task lookups. Each part
is `{count, items}` with at most 6 items; only parts with items are shown, with "See all N"
to My Work with a tab in the URL (`?tab=overdue`, `task`, `ticket`). An empty day shows one
calm line instead.

Every open task of the user lands in exactly one task section, the first that fits, in the
order below. Tasks due more than 7 days out are only counted (header and Your projects).

| Part | What | Quick action |
| --- | --- | --- |
| `close_first` | Overdue (`is_task_overdue`), then due today, then key tasks in progress. Rows show project, due label and "Assigned by". | **Complete** (Working), **Start** (Open), **Resume timer** (timer paused) |
| `in_progress` | Other tasks in Working, with "Timer running" or "Timer paused" (one query on `custom_timer_start`). | **Resume timer** (`helpdesk.tasky.api.start_timer`) or **Complete** |
| `replies` | Tickets assigned to me in a status whose category is Open (the agent owes the next reply). Replied / Waiting on Task are Paused and not listed. | Row opens the ticket |
| `approvals` | Tasks in Pending Review in projects I manage or lead (`get_managed_projects` ∪ `get_led_projects`), the same people `approve_task` accepts. | **Approve** (`helpdesk.tasky.api.approve_task`) |
| `waiting` | My tasks On Hold (longest hold first) or in review. Held rows say "Waiting on customer for 3 days · follow up" ("check on it" for another task) and show the note and who held it (`HoldNote`). | **Resume** (the Resume dialog) |
| `coming_up` | Due in the next 7 days, soonest first. | **Start** / **Complete** |
| `no_date` | Open tasks without a due date. The hint says "Set a date…" when the user may plan them (`can_plan`), else "Ask your lead for a date…". | **Set date** (the Plan dialog) for leads and managers, else **Start** |
| `given_out` | Tasks I gave someone else (an open ToDo with `assigned_by` = me) that are overdue or in review, minus ones already in my approvals; rows name the assignee. | Row opens the project |
| `files` | Project files marked "for" me by someone else in the last 7 days (`HD Project File User` rows, see `docs/project-files.md`), only from projects I can read. | Row opens the project's Files tab |

The page shows them in that order (replies and reviews right after the work in progress).
Steps that need the whole task (Complete, Resume, Set date) open `TaskDetailDialog` with that
step, as My Work does. `summary` holds the header's counts: `open` (tasks and tickets),
`overdue`, `due_today`, `on_hold`, `in_review`, `in_progress`, `projects`.

## Your projects (`day.projects`)

Open projects the user is on (a member, the lead, or with an open task in it), at most 6,
most overdue first, each opening the project. Every row shows **the user's own** open and
overdue tasks and the next open milestone they can see (dated first). People who run the
project (it is in their portfolio, `get_project_portfolio`) also get the whole project's open
and overdue counts; everyone else never sees totals that would include tasks hidden from them
(#94).

## Pulse strip (`company.tickets`, `company.work`)

Small chips, not tiles. Always shown: open tickets (with "N new today"), open projects
(with "N people busy"), and the customer rating over the last 30 days (hidden when there
are no ratings; amber when some are low). Problem stats are shown only when non-zero, in
their status colour with an icon: SLA breached, first reply overdue, unassigned tickets,
overdue work, work at risk. Zero problem stats collapse into one muted line, e.g.
"No issues: SLA, first reply, overdue work".

Each chip links to a filtered list:

- Ticket chips open the agent tickets list with `?filters=` (read by `ListViewBuilder`), e.g.
  unassigned is `status_category in (Open, Paused)` and `_assign is not set`; SLA breached is
  `status_category = Open` and `resolution_by < now`.
- Work chips open the Overview on a bucket (`/overview?bucket=at_risk`; overdue is its
  default).
- Open projects opens Projects.

Ticket numbers come from one `frappe.get_list` of open tickets (`_open_tickets`), counted in
Python: paused tickets don't run the SLA clock, so they don't count as breached.

## Needs attention (`company.attention_groups`)

Grouped by reason, in this order, each item only under its first reason; reasons with
nothing in them are left out. Each group carries its full `count` and at most 5 `items`;
"See all N" goes to the matching Overview bucket or filtered tickets list.

| Reason | Source |
| --- | --- |
| `overdue` | Overview's overdue bucket (tasks past their due date or, due today, past their estimated hours — see workspace-pages.md "When a task is overdue"; tickets past their SLA) |
| `at_risk` | Overview's at-risk bucket (not started close to the deadline, rescheduled often, waiting on an open dependency, SLA due within 4h, high priority unassigned) |
| `unassigned_tickets` | Open or paused tickets with no assignee, overdue and key first |
| `waiting_on_customer` | Paused tickets (not Waiting on Task) whose last agent reply (or last change) is over 3 days old, oldest first; rows say "We replied N days ago" |

Rows show the full title (wrapping to two lines, never cut to one), project or customer
(task customers come from their project in one query), the reference, assignee, due date
and risks. Unassigned tickets offer **Take it** to agents, which assigns the ticket to them
through `frappe.desk.form.assign_to.add`, the same endpoint as the ticket page.

## Side column

- **Customers at risk** (`company.customer_health`): first, and only when a customer is at
  risk or on watch: "N at risk, M to watch", the 5 worst with their health badge and reasons
  (each opens the customer's Health tab), and a link to the Customers list filtered to at risk
  or watch, worst first. See [customer-health.md](customer-health.md).
- **Open tickets by customer**: the 6 customers with the most open tickets.
- **Ending in the next 14 days** (`company.ending_soon`): open projects from
  `get_project_portfolio("Open")` whose expected end date is within 14 days or already
  past, soonest first, at most 6, with progress, overdue tasks and "Ends in N days" /
  "Ended N days ago" (red when past).
- **Team load**: the 10 busiest people from the portfolio with their open and in-progress
  counts and projects; admins also see who has no open project work ("Free: …").
- **Systems** (admins): customer ERP connections, mailboxes, Teams notifications, TBO Chat
  and AI triage health.

## Compatibility

`get_home` still returns `mine` (counts and first 8 items), `company.attention`,
`company.projects` and `company.project_count`, used by tests
(`helpdesk/tests/test_home.py`, `helpdesk/tests/test_sla_alerts.py`).

## Removed from Home

- The old `day.tasks` part ("Due today, overdue or at risk"), replaced by the task sections
  above, and the header's company status line and "All clear on tickets" (the pulse strip
  shows those numbers).


The eight big KPI tiles (most showed 0 or "-"), the single "Needs attention" list that
truncated titles, and the full projects table. Their information is in the pulse strip,
grouped Needs attention and the side column; detail and charts are on the Overview.
