# Workspace pages: Overview, Team, Summaries, Projects, My Work, Timesheets

Pages for the people who run projects (what's late, who is doing what, what each customer was
told) and for everyone doing the work (their projects, what to do next, the hours logged). They follow [ui-guidelines.md](ui-guidelines.md): neutral tiles, colour only
where it means something (always with an icon or text), and only figures the server computes.
No invented trends ("+12% vs last week") and no activity feed.

Shared building blocks, in `desk/src/components/`:

- **`StatTile`**: the one stat tile. Static, a link (`to`, shows a chevron) or a toggle
  (`pressed`, a button with `aria-pressed`). `loading` shows a skeleton; `iconTone` and
  `valueTone` colour the icon or number only when that carries meaning; `compact` tightens it
  for a strip above a list. Used by Overview, Team, the By project view, Performance, the
  tickets summary strip ([tickets-and-calendar-pages.md](tickets-and-calendar-pages.md)), and
  the customer report and the customer and contact pages ([customer-pages.md](customer-pages.md)).
- **`DirectoryList`**: the Customers and Contacts list (link rows, bulk delete, paging and
  every state), with `useDirectory()` keeping search and sort in the URL
  ([customer-pages.md](customer-pages.md)).
- **`SectionCard`**: the one titled card (title, optional count, description, header actions
  slot, "See all" link). Used by Home, Overview and Team.
- **`TaskyState`**: the one empty, error and no-access message (icon, title, message, actions).
- **`TaskyBadge`**: the one small status badge (label, tone, icon).
- **`tone.ts`**: the one `Tone` type (`neutral`, `info`, `warning`, `success`, `danger`) and
  its class maps: `INK` (text), `TRACK` and `FILL` (meters and bars), `TONE_CLASSES` (badges).

A failed call's message comes from `errorText(error, fallback)` in `desk/src/utils.ts`.

## Overview (`/overview`)

`desk/src/pages/work/Overview.vue`; API `helpdesk.api.work.get_overview(project, customer,
assignee, department)`. Project managers and project leads only.

- **KPI row**: Active work, Unassigned, At risk, On hold open their list below the dashboard;
  Open projects links to Projects and People busy to Team (with the project and customer
  filters). The list scrolls into view when it's off screen.
- **Buckets** (server): `overdue`, `at_risk`, `due_soon`, `key`, `review`, `waiting_on_task`,
  `on_hold`, plus `unassigned` (open work with no assignee) and `all` (every open task and
  ticket, overdue first). `counts` has each bucket's size.
- **`open_projects`**: open projects the user may read under the filters (the task filters
  already carry project, customer and department). With an assignee filter, only the open
  projects that person has open tasks in.
- **`people_busy`**: distinct assignees of the open work under the filters.
- Each bucket shows up once on the page: the KPI row, the Work status column (Overdue, Waiting
  for review, Waiting on task) or the tiles beside Action required (Due soon, Key).
- **Due soon / Key** tiles say "N open · M in progress"; in progress is a task with status
  Working, open is the rest, so the two add up to the tile's count. Worked out in the browser
  from the bucket's items.
- The bucket and filters live in the URL (`bucket`, `project`, `customer`, `assignee`,
  `department`).

## Team (`/team`)

`desk/src/pages/work/Team.vue`; API `helpdesk.api.work.get_team_workload(project, customer)`
for By person, `get_project_portfolio` for By project (`components/ProjectPortfolio.vue`).

- **By person / By project** switch, kept in the URL as `view`.
- **Summary tiles**: People, Working now and Free (with their share of the team), Overdue and
  Waiting review (with how many people), Done this week (the last 7 days). A tile narrows the
  people table to those it counts; the narrowing is `show` in the URL.
- **People table**: person, current in-progress task (+N more), open work chips (open, review,
  on hold, overdue, estimated hours), due this week (next 7 days), done this week, tickets
  (with SLA breached), next due task and date. Sort select (`sort` in the URL): most overdue
  first (the server's order), most open work, most due this week, next due date, name.
- **A row opens the person's work** (`/my-work?user=...`), which leads and managers may open for
  people on their projects. The table no longer expands inline, so the API no longer sends each
  person's task list.
- Below `xl` each row becomes a card with labelled values.

## Summaries (`/work-summaries`)

`desk/src/pages/work/WorkSummaries.vue`; API `helpdesk.api.work_summary.get_summaries(customer,
week, kind, limit)` returns `{summaries, can_generate}`.

- **Filters** in the URL: `customer`, `week` (the Monday of a week: summaries whose period ends
  in it; the last 12 weeks are offered) and `kind` (`ai` or `plain`).
- **Grouped by period**, newest first. Each row: customer, kind badge, the week in numbers
  (tickets opened and resolved, tasks done, overdue in red with an icon), generated date. The
  numbers come from the summary's stored stats (`highlights`); a summary without stats shows
  "No figures" rather than zeros.
- **Duplicates explained**: one customer can have several summaries, from the Monday run and
  from "Generate summary" (which covers the 7 days up to that day). The period group tells them
  apart, and when the same customer and period was generated again, the older row is marked
  "Older version".
- **Generate summary** (primary action) only shows when `can_generate`: Agent Managers, or
  project managers of at least one customer's project (the same rule `generate_summary`
  enforces per customer).

## Projects (`/projects`)

`desk/src/pages/tasky/Projects.vue`, one `components/ProjectCard.vue` per project; APIs
`helpdesk.tasky.api.get_projects` and, per project, `get_project_dashboard` (task stats built
from the tasks the viewer can see, so a plain member's card counts their own tasks).

- **Header**: "New project" (project managers) is the page's one primary action; Refresh.
- **Recent**: a row of links to the projects the user opened last (up to 8, newest first),
  above the summary tiles; hidden until they open one, and left out if it fails to load. See
  [Recent projects](#recent-projects).
- **Summary tiles**, over open projects under the department filter: Open projects; Overdue
  tasks (summed from the cards' stats, with how many projects have any, or how many projects'
  stats didn't load); Ending in 14 days (open projects whose end date is today to 14 days out,
  with how many more are past their end date). Overdue tasks and Ending in 14 days are toggles
  that narrow the cards to what they count and switch to the Open tab.
- **Filters**: status tabs (Open, Completed, Cancelled, All), search, department chips (see
  [departments.md](departments.md)). Counts on tabs and chips follow the other filters.
- **URL**: `status` (Open is the default and left out), `department` (`__none__` for No
  department), `q`, `show` (`overdue` or `ending`).
- **Card**: name (links to the project), customer and ID; status badge only when not Open;
  lead and dates, with "N days past end" in red (with an icon) or "Ends in N days" for open
  projects; one neutral progress bar (green once the project is Completed) with done/total
  and %, then overdue (red, with an icon), in progress, in review and on hold counts;
  collapsible phases. Footer: Open, Board and the files count on the left; New task (members
  who may add tasks) and a menu with Edit project (project owners) and Generate checklist
  (managers and leads) on the right. A card whose stats fail says so instead of hiding.
- **Empty states**: no projects yet (with New project for managers) vs nothing matching the
  filters (Show all projects).

## My Work (`/my-work`)

`desk/src/pages/work/MyWork.vue`; API `helpdesk.api.work.get_my_work(user)`. `?user=` opens a
team member's work, for leads and managers of their projects (the Team page links here).

- **Groups**, in this order, each with its count, from `dueGroup()` in `workMeta.ts`: Overdue
  (past the due date or SLA), Today, This week (the next 7 days, as on the Team page), Later
  (further out, no date, or a ticket whose SLA is paused), On hold, In review. Held and
  in-review tasks leave the date groups because they wait on someone. Within a group the
  server's order stays: overdue, then key, then deadline.
- **Tabs** filter before grouping and stay in the URL as `tab`: All, Overdue, At risk, Key,
  Tasks, Tickets, Completed (the last 30 days, with hours).
- **Steps on a task** (`components/WorkItemActions.vue`, in `WorkItemRow`'s `actions` slot):
  one button for the next step (Approve when the viewer may sign it off; else Start an Open
  task; Complete a working one; Resume a held one) and a menu with Details, Complete (when
  Start is the button), Put on hold and Plan. Start and Approve run straight away; Complete,
  Put on hold, Resume and Plan load the whole task first (timer, hold note, dependency)
  through `TaskDetailDialog` with `action`, so Plan can't clear a dependency it didn't load.
  A task waiting on another can't be started or completed, as the server refuses both.
- **Plan** shows only when `can_plan`: `get_my_work` marks every task with whether the viewer
  manages its project (owner or lead). The Overview doesn't ask for it, so it doesn't pay for
  the per-project lookup.
- **Someone else's work**: a banner names whose work it is, says only they can start, complete
  or pause it, and links back to your own. Rows offer only Approve and Plan, and the detail
  dialog only the lead's and manager's steps.
- **Task details** (`desk/src/pages/tasky/components/TaskDetailDialog.vue`): the one task panel,
  shared with My Tasks (`/my-tasks`). Hold and dependency notices, status, priority, project,
  phase, assigned to, assigned by, due, estimate, description, pull requests and meetings. Its
  actions follow `mine`: the assignee may edit, complete, hold or resume, ask for help and hand
  over; the project's manager or lead may edit, plan, approve and send back. "Move to
  project…" shows when the task says `can_move` (see [Moving a task](#moving-a-task-to-another-project)).
- **Rows** say "Assigned by Arun" next to the project when someone other than the assignee gave
  the task out.

## Tasks: assigned by, moving, the timer

### Assigned by

Every task payload (`get_task_detail`, `get_kanban_tasks`, `get_my_tasks`, and the task items
of `get_my_work` and `get_overview`) carries `assigned_by` and `assigned_by_name`, added in
bulk by `add_assigners()` in `helpdesk/tasky/api.py` (a few queries per list, no per-task
lookups). The source is `get_assigners()` in `helpdesk/tasky/permissions.py`: the current
assignee's latest ToDo that wasn't cancelled (`assign_to` records `assigned_by`), else whoever
created the task. The UI (`assignedByName()` in `taskMeta.ts`) shows it as muted "Assigned by
…" text on board cards and My Work rows, as a row in the task details and in Edit task, and
hides it when the assignee took the task themselves.

### Moving a task to another project

`helpdesk.tasky.api.move_task_to_project(task, project)` (POST). The name `move_task` was
already the board's column move, so this one says where it moves to.

- **Who:** whoever assigned it (from `get_assigners`), the source project's managers and lead,
  and admins (`can_move_task` in `permissions.py`). Never the assignee: someone who assigned
  the task to themselves counts as its assignee, not its assigner. The mover must also be able
  to read the task.
- **Where:** an open project the mover can add tasks to (`can_add_tasks`), not the one it's in.
- **What changes:** the project; the phase is cleared unless the new project has a task in a
  phase of the same name (phases are task fields, not a list on the project); `depends_on_task`
  is cleared, and tasks in the old project that waited on it stop waiting (a task only waits
  on tasks in its own project). The assignee keeps the task. When the mover manages the new
  project, assignees outside its team join it as Developers (`_add_member_for_assignment`);
  otherwise they're returned in `not_on_team` and the dialog warns. Closed tasks can't move.
- **Record:** an Info comment ("Moved from X to Y by Z.", plus what was cleared) and a
  notification to the assignee. The response adds `phase_cleared`, `dependency_cleared`,
  `dependents_released` and `not_on_team` to the task.
- **UI:** "Move to project…" in the board card's menu and the task details' actions, shown when
  the task's `can_move` is true; `components/MoveTaskDialog.vue` picks the project with a
  Combobox (open projects the user can add tasks to) and explains what will be cleared.

### Recent projects

`record_project_view(project)` (POST) runs when a project page (any tab) loads, from
`ProjectNav`; it records the visit in Frappe's View Log (one row per person and project, its
`modified` the last visit), so the list follows the user across devices, and keeps only the
latest 8. `get_recent_projects()` returns them newest first through `frappe.get_list`, so a
project the user can no longer read drops out, and deleted projects take their View Log rows
with them.

### The board timer

A task's timer runs only while it is In progress and has `custom_timer_start`; banked time sits
in `custom_timer_elapsed`. The server is the only record: the board derives each card's timer
from those fields (`taskTimer()` in `taskMeta.ts`) and replaces its local state on every load.
Pause calls `stop_timer` (banks the time, the task stays In progress) and Resume calls
`start_timer`, which only works on a task In progress; resuming a card that left In progress
moves it back there like a drop. Nothing else starts a paused timer, and starting one task never
touches another's: there is no one-running-task rule. Before this, Pause only changed the
board's local state, so the server timer kept running and the next load (moving or editing
another task, or coming back to the board) showed the paused task running again.

## Timesheets (`/timesheets`)

`desk/src/pages/tasky/Timesheets.vue`; APIs `helpdesk.tasky.api.get_my_timesheets` (the list,
the 500 most recently updated), `get_timesheet_summary` (the totals) and
`export_timesheets_csv` (Download CSV, one row per time log).

- **Scope**: Mine, or Team for leads and managers (the timesheets on projects they lead or
  manage). Filters: agent (Team), From and To (the day the work was done).
- **URL**: `scope=team`, `agent`, `from`, `to`.
- **Summary tiles**: Hours logged in the period, Timesheets (500+ when the list is capped) and
  Drafts.
- **By person** (Team) and **By project**: `get_timesheet_summary(team, agent, from_date,
  to_date)` adds up the time logs themselves, in the chosen dates, from the timesheets the
  viewer may see; it doesn't use each timesheet's total, so a timesheet across several
  projects or days splits correctly. Six rows each, then "N more · Xh". The bars are neutral
  and show each row's share of the period.
- **List**: a titled card; Timesheet, Person (Team), Status, Hours (right-aligned, tabular)
  and Updated columns from `md`; below that a two-line row with person, status and date in
  the second line. Empty states tell "no time logged in these dates" (Clear filters) from
  "no timesheets yet" (Log time).
- **Log time** dialog unchanged.
