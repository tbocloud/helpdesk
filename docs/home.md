# Home

Home answers "what should I do now, and is anything on fire?". Analysis (charts, buckets,
filters by project, customer, assignee and department) lives on the **Overview**
(`/helpdesk/overview`); Home links into it instead of repeating it.

- Page: `desk/src/pages/home/Home.vue` (route `Home`, `/helpdesk/home`), with its parts in
  `desk/src/pages/home/components/` and types, link builders and the status sentence in
  `desk/src/pages/home/homeMeta.ts`.
- Data: one call, `helpdesk.api.home.get_home` (agents only). Every list goes through
  `frappe.get_list` (or is narrowed to records the user can read), so nobody sees records
  they couldn't open.

## Who sees what

| Section | Who | Key in `get_home` |
| --- | --- | --- |
| Header and status line | Everyone | built in the browser from the rest |
| Your day | Everyone | `day` |
| Pulse strip | People who can see the Overview (`can_see_overview`: admins, project managers, anyone leading a project) | `company` |
| Needs attention | Same | `company.attention_groups` |
| Open tickets by customer, Ending in the next 14 days, Team load | Same | `company.tickets.by_customer`, `company.ending_soon`, `company.people` / `free_people` |
| Systems | Admins (System Manager, Agent Manager) | `systems` |

`company` and `systems` are `null` for people who don't qualify. On screens 1280px and wider
the customers, projects, team and systems cards sit in a right-hand column; below that they
follow the main column. The page never scrolls sideways.

## Header

Greeting by time of day, today's date, and one status line made only of things that need
action, most urgent first, joined with "·":

- Managers: SLAs breached, first replies overdue, items overdue, items at risk, tickets
  unassigned (company numbers), then tickets waiting for your reply and tasks waiting for
  your review.
- Everyone else: your overdue items, tickets waiting for your reply, tasks waiting for your
  review.

Danger facts are red with a warning icon, at-risk ones amber with an icon, the rest neutral.
When the ticket numbers are all zero but something else needs action the line starts with
"All clear on tickets". The green "All clear. Nothing needs action right now." shows only
when the list is empty.

## Your day (`day`)

Built from `helpdesk.api.work.get_my_work` (the user's open tasks and tickets) plus two
queries. Each part is `{count, items}` with at most 6 items; only parts with items are
shown, and an empty day shows one calm line instead.

| Part | What | Quick action |
| --- | --- | --- |
| `tasks` | My open tasks that are overdue, due today or at risk. On Hold tasks (not late while held) and Pending Review tasks (waiting on the reviewer) are left out. | **Start** on Open tasks (`helpdesk.tasky.api.update_task_status` → Working); **Complete** on Working/Overdue tasks (the existing Complete dialog, which logs hours and notes) |
| `replies` | Tickets assigned to me in a status whose category is Open (the agent owes the next reply). Replied / Waiting on Task are Paused and not listed. | Row opens the ticket |
| `approvals` | Tasks in Pending Review in projects I manage or lead (`get_managed_projects` ∪ `get_led_projects`), the same people `approve_task` accepts. | **Approve** (`helpdesk.tasky.api.approve_task`) |
| `files` | Project files marked "for" me by someone else in the last 7 days (`HD Project File User` rows, see `docs/project-files.md`), only from projects I can read. | Row opens the project's Files tab |

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
| `overdue` | Overview's overdue bucket (tasks past their due date, tickets past their SLA) |
| `at_risk` | Overview's at-risk bucket (not started close to the deadline, rescheduled often, waiting on an open dependency, SLA due within 4h, high priority unassigned) |
| `unassigned_tickets` | Open or paused tickets with no assignee, overdue and key first |
| `waiting_on_customer` | Paused tickets (not Waiting on Task) whose last agent reply (or last change) is over 3 days old, oldest first; rows say "We replied N days ago" |

Rows show the full title (wrapping to two lines, never cut to one), project or customer
(task customers come from their project in one query), the reference, assignee, due date
and risks. Unassigned tickets offer **Take it** to agents, which assigns the ticket to them
through `frappe.desk.form.assign_to.add`, the same endpoint as the ticket page.

## Side column

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

The eight big KPI tiles (most showed 0 or "-"), the single "Needs attention" list that
truncated titles, and the full projects table. Their information is in the pulse strip,
grouped Needs attention and the side column; detail and charts are on the Overview.
