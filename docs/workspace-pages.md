# Workspace pages: Overview, Scoreboard, Team, Summaries, Projects, My Work, Timesheets

Pages for the people who run projects (what's late, who is doing what, what each customer was
told) and for everyone doing the work (their projects, what to do next, the hours logged). They follow [ui-guidelines.md](ui-guidelines.md): neutral tiles, colour only
where it means something (always with an icon or text), and only figures the server computes.
No invented trends ("+12% vs last week") and no activity feed.

Shared building blocks, in `desk/src/components/`:

- **`StatTile`**: the one stat tile. Static, a link (`to`, shows a chevron) or a toggle
  (`pressed`, a button with `aria-pressed`). `loading` shows a skeleton. The icon sits in a
  circle: soft-tinted by `iconTone` only when that carries meaning (done success, overdue
  danger, time info; [ui-guidelines.md](ui-guidelines.md) §8), neutral gray otherwise.
  `valueTone` colours the number the same way; `delta`, `deltaText` and `deltaTone` add a
  change line with an up/down arrow; `compact` tightens it for a strip above a list (an
  inline icon, no circle). Used by Overview, Team, the By project view, Performance, the
  tickets summary strip ([tickets-and-calendar-pages.md](tickets-and-calendar-pages.md)), and
  the customer report and the customer and contact pages ([customer-pages.md](customer-pages.md)).
- **`DirectoryList`**: the Customers and Contacts list (link rows, bulk delete, paging and
  every state), with `useDirectory()` keeping search and sort in the URL
  ([customer-pages.md](customer-pages.md)).
- **`SectionCard`**: the one titled card (optional icon and count, title, description,
  header actions slot, "See all" link). Used by Home, Overview and Team.
- **Segmented controls**: frappe-ui `TabButtons` everywhere a page switches view, period or
  status filter (Scoreboard, Team, Timesheets, My Work, My tasks, Projects, Performance,
  content plans); `theme.css` fills the checked option in brand. Counts go in its `suffix`
  slot. Wrap it in `overflow-x-auto` where it may be wider than a phone.
- **`TaskyState`**: the one empty, error and no-access message (icon, title, message, actions).
- **`TaskyBadge`**: the one small status badge (label, tone, icon).
- **`tone.ts`**: the one `Tone` type (`neutral`, `info`, `warning`, `success`, `danger`) and
  its class maps: `INK` (text), `TRACK` and `FILL` (meters and bars), `TONE_CLASSES` (badges).

A failed call's message comes from `errorText(error, fallback)` in `desk/src/utils.ts`.

## Who sees which tasks

Inside a project, people who run it see every task; everyone else sees only their own.
One rule on the server, `task_query` (lists) and `task_has_permission` (a task opened
directly) in `helpdesk/tasky/permissions.py`, so every page that lists tasks through
`frappe.get_list` follows it: the project Dashboard, Checklist, Board, Timeline, Overdue
and Recurring tabs, My board, My Work, My tasks, the Overview, Team, the work Calendar,
Home, the project cards' stats, the timesheet task pickers and task details.

| Who | Sees in a project |
| --- | --- |
| System Managers, Agent Managers | Every task of every project |
| The project's owner, its members with the Project Manager project role, its lead | Every task of that project (`can_manage_project`) |
| Its members with the Project Coordinator project role | Every task of that project, and they run its tasks (`can_coordinate_project`, see [What a Project Coordinator may do](#what-a-project-coordinator-may-do)) |
| A Project Manager (role) who is on the project's team | Every task of that project, but no manager powers |
| Digital Marketing Head, DM Coordinators | Every task of content calendar projects and of Digital projects |
| Everyone else (developers, functional consultants, content people) | Only their own tasks: assigned to them, given out by them (they assigned it to someone), or created by them, assigned or not |

`sees_all_tasks(project)` answers the first five rows for one project, and
`get_project_detail` returns it as `sees_all_tasks`. "Assigned to" and "given out by" come
from the task's ToDos (`allocated_to`, `assigned_by`), matched exactly: a LIKE on `_assign`
would read `_` in a user ID as a wildcard. A finished assignment (Closed ToDo) still counts,
so people keep seeing the tasks they completed; a withdrawn one (Cancelled) doesn't. The
department walls ([departments.md](departments.md)) apply on top of every row except admins,
and so does the content team rule: outside the content team, a content post's tasks are only
seen when they're the person's own, whatever the row
([content-calendar.md](content-calendar.md#who-sees-the-content-calendar)).

**Exact "assigned to" everywhere.** Every list of someone's tasks or tickets matches the
assignment through ToDos, never a LIKE (or JSON_SEARCH) on `_assign`: My tasks
(`get_my_tasks`), the sidebar Board (`get_kanban_tasks` without a project), My Work and its
Completed tab, the Overview's assignee filter, the work Calendar, the sidebar counts
(`helpdesk.api.sidebar.get_nav_counts`), the projects a member sees through an assigned task
(`project_query`, `has_assigned_task`), the agent home's ticket lists and analytics (`analytics_utils`), the ticket permission query (agents see tickets assigned to them), the analytics dashboard's
agent filter, the Ticket Analytics and Ticket Summary reports, and the ticket list's "Assigned
to" filter (`handle_assigned_to_filter` in `helpdesk/api/doc.py`, which turns `_assign like
%user%` into a name filter). The one rule is `assigned_names_query(doctype, user, finished)` in
`helpdesk/utils.py` (a subquery for `frappe.qb`; `assigned_to_filter` turns it into a
`frappe.get_list` name filter with one ToDo query, since `get_list` can't take a subquery;
`_assigned_tasks_subquery` in `permissions.py` is the same rule in SQL for the permission query
conditions). Tasks count finished (Closed) assignments; open-ticket lists and counts don't
(`finished=False`, what `_assign` holds), since resolving a ticket closes its ToDos and a
reopened ticket may go to someone else, and the same holds for the dashboard and the reports; only My Work's Completed tab counts them.

- **What a member sees of the project**: the project itself stays visible (members, lead,
  files). On the task tabs a line under the tab bar says they see their own tasks
  (`ProjectNav`, when `sees_all_tasks` is false). The Dashboard's tiles, phases and
  milestones count only their tasks and its progress reads "Your progress"; the Team list
  hides its per-person open-task counts, which would be partial.
- **Recurring tab**: members see the schedules assigned to them or that they set up
  ([recurring-tasks.md](recurring-tasks.md)).
- **Deliberate exceptions**: "Waiting on" shows the blocking task's ID and subject even when
  the viewer can't open it, so they know what they wait for. A ticket's Linked work lists
  the tasks raised from that ticket to whoever can read the ticket. The content calendar
  shows each post's team and how far each person's part is (`get_team_task_status`); the
  tasks themselves follow the rule.

## What a Project Coordinator may do

A member whose project role (`Project User.custom_role`) is **Project Coordinator** runs that
project's tasks, without managing the project. One rule, `can_coordinate_project(project)` in
`helpdesk/tasky/permissions.py` (its managers and lead, plus its coordinators), backs the
server checks; `get_project_detail` returns it as `can_coordinate`, and the board, checklist,
task details, Edit task and the project dashboard show the task controls on it. The role
counts only on the project where the person holds it.

| Action | Coordinator | Where it's checked |
| --- | --- | --- |
| See every task of the project | Yes | `sees_all_tasks`, `task_query` |
| Create tasks and assign them to the team | Yes | `add_task` (`can_add_tasks`) |
| Reassign, hand over any task | Yes, to people on the team | `update_task`, `hand_over_task` (`_get_own_task`) |
| Edit a task, move it between phases | Yes | `update_task` (`_check_can_edit`) |
| Change due dates (recorded as slips), key, milestone, dependency; AI due dates | Yes | `update_task_plan`, `estimate_undated_tasks` |
| Put on hold, resume, move on the board | Yes | write permission (`task_has_permission`) |
| Approve or send back a review; their own "done" skips review | Yes | `approve_task`, `send_back_task`, `Task.route_completion_to_review` |
| Approvals on Home, Plan and Approve on My Work | Yes | `_approvals` (`get_coordinated_projects`), `_items` |
| Give a task to someone outside the team (adds them to it) | No | `_check_can_bring_in` |
| Edit the project, its team, roles or lead | No | `update_project`, `set_project_lead`, `rotate_project_lead` (`is_project_owner`) |
| Delete tasks | No | `task_has_permission` |
| Recurring schedules, Sign-off, Generate checklist | No | `can_manage_project`, project write permission |
| Invoicing | No | admins only (`helpdesk/api/invoices.py`) |
| Move a task to another project | Only one they assigned, as anyone may | `can_move_task`, also on a plain form save (`Task.check_project_move`) |

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
- **Follow-ups** (System Managers and Agent Managers): escalated (L2+), breached and overdue
  counts, the escalated items, the oldest overdue tasks and who has the most open escalations
  (`FollowUpControl.vue`, see [follow-ups.md](follow-ups.md#where-escalation-shows)).

## Scoreboard (`/team-dashboard`)

`desk/src/pages/work/TeamDashboard.vue`; API `helpdesk.api.team_dashboard.get_team_dashboard`.
Who finished what in a period (today to this year), on-time rates, hours, overdue work, and the
champion per department and for the whole team, with an AI analysis, open to every agent. Its
comparisons ("↑ 3 vs last week") are computed by the server from the same records for the
previous period up to the same point, not invented. Everything else is in
[team-dashboard.md](team-dashboard.md).

## Team (`/team`)

`desk/src/pages/work/Team.vue`; API `helpdesk.api.work.get_team_workload(project, customer)`
for By person, `get_project_portfolio` for By project (`components/ProjectPortfolio.vue`),
`helpdesk.api.capacity.get_capacity` for Capacity (`components/CapacityPlanner.vue`, see
[Capacity](#capacity-teamviewcapacity)).

- **By person / By project / Capacity** switch, kept in the URL as `view` (`project`,
  `capacity`; By person is the default and left out).
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

### Capacity (`/team?view=capacity`)

Planning, not time tracking: "can we take this on, and who has room?" It never shows the
hours someone spent, only how much open work is planned against the time they have. API
`helpdesk.api.capacity.get_capacity(weeks, department, project)`; project managers and project
leads only (`can_see_overview`), over the same people as By person (`_team_members`: everyone
for admins, else the people on the projects they manage or lead). A lead can't filter to a
project they don't run (it returns no one).

- **Window**: 1, 2 or 4 calendar weeks (`weeks`, 2 by default), from today to the Sunday of
  the last week. When this week has no working day left (a Sunday, or a Saturday off), it
  starts next Monday.
- **Available hours** per working day are HD Work Settings' `dev_hours_per_day` (focused
  hours, 6 by default; `hours_per_day()` in `api/customization.py`). Working days skip the
  weekly off, the Saturdays off rule (`work_calendar.py`) and the holidays in the default
  SLA's holiday list. The hub keeps no leave records, so leave isn't counted.
- **Planned hours** come from open tasks assigned to the person with status Open, Working,
  Overdue or Waiting on Task (On Hold and Pending Review wait on someone else). Each task's
  remaining hours = `custom_estimated_hours` (else the standard estimate from
  `task_estimates.fallback_estimate`, marked "~" and counted in a note) minus the hours
  already logged on it in draft or submitted timesheets, floored at 0. A task shared by
  several people is split evenly between them.
- **Load-spreading rule** (`task_allocation`): the remaining hours spread evenly over the
  working days from the task's start (today, or its planned start if later) to its due date.
  Only the share that falls in the window counts, so a task due in six weeks takes its
  proportional bite now. An overdue task is owed in full from the first working day on, a
  full day's hours at a time. A task with no due date gets one from the standard estimate's
  working days, as a new task would. A due date on a day off puts it all on the next working
  day.
- **Flags** (`load_flag`): Overloaded above 100% of the available hours, Busy from 80% to
  100%, Available under 80%; each a badge with an icon and text. A week or day with no working
  time says "No working days".
- **Tiles**: Team load (planned of available hours), then Overloaded, Busy and Available
  people; a flag tile narrows the list (`load` in the URL).
- **People**: name (opens their My Work, `?user=`), flag, a meter and "planned / available h"
  per week (neutral fill, red with an icon only when over), the window's total. Sort
  (`sort`): most loaded first (the server's order), most free hours, name. Expanding a row
  (`components/CapacityDetail.vue`) shows a bar per working day, hours by project and the
  biggest tasks. Work on projects the viewer doesn't run counts toward the person's load but
  shows only as hours under "Other projects", without task names.
- **Who's free next week** (or this week with a 1-week window; "next week" goes by the
  server's `today`, not the browser's clock): people under 80% that week,
  most free hours first. Typing hours of new work (the "what if") lists who has that many free
  hours in the whole window, with their load before and after.
- **By department / By project**: the window's planned hours by the department of each task's
  project, and per project with how many people. In both, work on projects the viewer doesn't
  run is one "Other projects" row, so a lead never sees another project's department.
- **Filters** in the URL: `department` (that department's projects' people) and `project`
  (shared with By person). With a filter, a person's load is still all their planned work,
  since their time is one pool.

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
- **Held tasks** (`helpdesk/work_summary.py`, `task_stats`): each held task in the stats
  carries its reason, its note (`hold_note`) and who put it on hold (`hold_by`, as a name from
  one User query for the list, `hold_by_names`), so the AI and the plain summary's Risks line
  ("On hold since … (Other: note): task (project). Put on hold by …") say what would unblock it.

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

### Project dashboard tiles (`/projects/:id`)

`desk/src/pages/tasky/PMDashboard.vue`; API `helpdesk.tasky.api.get_project_dashboard`.

- **Eight tiles** (the shared `StatTile`, each a link named "Show on hold tasks: 2" and so on;
  two columns on a phone, four from `sm`): Total tasks, Completed, In progress, Waiting
  review, Overdue, On hold, Rescheduled, Cancelled. Waiting review (info), Overdue (danger),
  On hold and Rescheduled (warning) are coloured only when above zero.
- **What each counts** is `DASHBOARD_STAT_RULES` in `helpdesk/tasky/api.py`, over the tasks the
  viewer can see: Completed, In progress (Working), Waiting review (Pending Review), On hold
  and Cancelled by status; Rescheduled is any task whose due date was ever moved later
  (`slip_count > 0`, whatever its status now); Overdue is `is_task_overdue` in
  `helpdesk/api/work.py`, the Overdue page's rule (past its due date, or due today and already
  worked past its estimate, and not Completed, Cancelled or On hold). The API returns the counts in `stats` and the
  task names behind each in `stat_tasks`, both built from the same rules, so a tile's number is
  always its list's length.
- **Where a tile goes**: Total tasks opens the Checklist unfiltered; Overdue opens the Overdue
  page; every other tile opens the Checklist with `?status=<key>` (`completed`, `in_progress`,
  `reviewing`, `on_hold`, `rescheduled`, `cancelled`). A tile at 0 still links, to the
  filtered empty state.
- **Checklist filter** (`desk/src/pages/tasky/Checklist.vue`): with a known `status` key it
  shows the dashboard's `stat_tasks` for that key instead of the collapsible phases. A bar
  reads "Showing: On hold · 2 tasks · Clear filter" (Clear removes `status` from the URL).
  Rows stay grouped by phase in the checklist's order, with No phase last, and phases with no
  match are left out. Nothing matching shows "No tasks match this filter" with Clear filter.
  An unknown key is ignored. The labels live in `CHECKLIST_FILTERS` in `taskMeta.ts`. The
  Checklist rather than the Board is the target because it lists every status (including
  Completed and Cancelled) and Rescheduled isn't a status column.

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
  over; the project's manager, lead or coordinator may edit, plan, approve and send back, and also hold, resume and hand it over. "Move to
  project…" shows when the task says `can_move` (see [Moving a task](#moving-a-task-to-another-project)).
- **Rows** say "Assigned by Arun" next to the project when someone other than the assignee gave
  the task out.

## Board (`/my-board`)

The sidebar's **Board** (after My Work, for everyone including the Content Team) is the project
board (`pages/tasky/Kanban.vue`, route `MyBoard`, no `projectId`) showing the current user's own
tasks from every project they're assigned in, by status: Open, In progress, In review, On hold,
Completed, Cancelled. `get_kanban_tasks()` without `project` returns tasks assigned to
the user (through `frappe.get_list`, so permissions and department walls apply), with finished
and cancelled ones only if changed in the last 30 days. Each card names its project. Dragging,
the timer, hold/resume, complete, edit, ask for help and hand over work as on a project board,
each using the task's own project; project-level actions (New task, Plan, Approve/Send back,
Make recurring) stay on the project's board.

## Tasks: assigned by, on hold, moving, the timer

### Assigned by

Every task payload (`get_task_detail`, `get_kanban_tasks`, `get_my_tasks`, and the task items
of `get_my_work` and `get_overview`) carries `assigned_by` and `assigned_by_name`, added in
bulk by `add_assigners()` in `helpdesk/tasky/api.py` (a few queries per list, no per-task
lookups). The source is `get_assigners()` in `helpdesk/tasky/permissions.py`: the current
assignee's latest ToDo that wasn't cancelled (`assign_to` records `assigned_by`), else whoever
created the task. The UI (`assignedByName()` in `taskMeta.ts`) shows it as muted "Assigned by
…" text on board cards and My Work rows, as a row in the task details and in Edit task, and
hides it when the assignee took the task themselves.

### On hold: why, and who

`helpdesk.tasky.api.hold_task(task, reason, note)` puts a task on hold through the Task
controller (`start_hold`), which stores `hold_reason`, `hold_note`, `hold_since` and
`hold_by` (the user who held it; read-only). Resuming (`resume_task`, or a board move out of
On Hold) clears all four in `end_hold`.

- **Reason "Other" needs a note.** `start_hold` refuses an Other hold with a blank note, since
  "Other" alone tells the lead nothing. `HoldTaskDialog.vue` labels the note "Why is it on
  hold?", marks it required, shows an inline error after the field is left empty, and keeps
  Put on hold disabled until it's filled. The note stays optional for the other reasons.
  GitHub's automatic hold (a PR closed without merging) always writes a note, as Other.
- **Payloads.** Task lists select the hold fields from one list, `TASK_HOLD_FIELDS` in
  `helpdesk/tasky/api.py` (`get_kanban_tasks`, `get_my_tasks`, `get_phase_tasks`,
  `get_project_dashboard`, and `TASK_FIELDS` in `helpdesk/api/work.py`). `_format_task` adds
  `hold_by_name`. List endpoints (`_format_tasks`, and `_items` and `get_team_workload` in
  `work.py`) fetch every holder's name in one User query (`hold_by_names`) and pass it in, so
  a board doesn't query User per card; a single task (details, a dialog's response) looks
  the user up directly (`hold_by_name`). Work items (`get_my_work`, `get_overview`, team pages) carry
  `hold_note` and `hold_by_name` only while the task is on hold.
- **UI.** The warning pill still shows the reason and days held; under it,
  `components/HoldNote.vue` shows the note as neutral text (clamped to two lines) and "Put on
  hold by …", on board cards, checklist rows, My Tasks rows and work rows (`WorkItemRow`), so
  the reason is readable without hovering. The full note, and "Put on hold by … · date", are
  in the task details and the Resume dialog.

### Handing a task over

`helpdesk.tasky.api.hand_over_task(task, teammate, reason)` (POST), "Hand over" in the board
card's menu, the checklist row's menu and the task details (`HandOverTaskDialog`).

- **Who:** the task's assignee, for their own share of it, or the project's managers and
  lead or coordinators, for the whole task (`_get_own_task`). Open tasks only, with the timer stopped.
- **To whom:** an active agent on the project's team; managers and leads may pick anyone
  (they join the team). A content post's task may go to any active agent, since content
  people work on the content calendar without joining its project (`TeammatePicker`
  `anyone`); the department walls still refuse the other team, and an ERP Employee is refused
  a content task before anything changes. Tasks outside a project can't be handed over. A
  content post's task follows the post's team, so only someone on the post's part for it (its
  role, or any role for the shared task) can hand it over; anyone else given the task directly
  is asked to have a DM Coordinator change the post's team.
- **What changes:** the hander's ToDo is cancelled and the teammate's names the task's
  original assigner (`get_assigners`) as `assigned_by`, not the hander. So "Assigned by"
  keeps showing who gave the work out, and the task leaves the hander's lists unless they
  gave it out or created it. Other people sharing the task keep it. On a content post's task
  the post's role (or every role, for the post's shared task) gets the teammate in the
  hander's place (`HDContentPost.replace_on_part`, saved without re-syncing its tasks), so
  the post's next save doesn't give the task back.
- **Record and notices:** comments "Reassigned from … to … by …" and "Handed over by …:
  reason"; the teammate is notified ("… handed you a task"), and the project lead (or its
  managers when it has no lead) and the original assigner hear who took it and why, each
  only while they may still read the task.

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

### Recurring tasks

A project's **Recurring** tab lists the schedules that create repeating tasks (monthly
backup check, GST filing reminder, weekly status report); "Make recurring…" in a board
card's menu and the task panel starts one from a task. See
[recurring-tasks.md](recurring-tasks.md).

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

### Telling the assigner a task is done

When a task becomes **Completed**, whoever assigned it (the same person the "Assigned by" label
shows, from `get_assigners()`) gets a **Task Completed** notification: "Fathima Rizwana completed
Bank reconciliation", credited to the assignees who did the work (when a lead's review approval
completes it) or else to whoever completed it, linking to the task's project (My Work when it has none).
`Task.tell_assigner_it_is_done()` sends it through `notify_users(…, notification_type="Task
Completed", user_from=…, once=False)`, so completing a reopened task notifies again. It isn't sent
when the assigner completed (or, on review projects, approved) it themselves, when the assignee
took the task themselves, or when a published or cancelled content post closes its tasks
(`flags.from_content_post`). On projects with review before done, the notice goes out when the
lead approves, not when the assignee sends it for review.

It stays inside the helpdesk: no email or chat (`HDNotification.deliver` only sends those for
Mention and Reminder). Every new HD Notification is pushed to its recipient's open tabs
(`announce()` publishes `helpdesk:new-notification` to that user after commit), so the bell's
count updates without a reload. For Task Completed the notification store
(`stores/notification.ts`) also plays a short two-note chime (`composables/notificationSound.ts`,
made with the Web Audio API, no sound file) and shows the message as a toast. Browsers only play
sound after the person has used the page; if audio is blocked the chime is skipped and the bell
and toast still show. The panel shows the completer's avatar and the message
(`isTextOnly()` in `Notifications.vue` and `MobileNotifications.vue`).

### When a task is overdue

One rule everywhere, on the server (`is_task_overdue` in `helpdesk/api/work.py`) and in the
browser (`isOverdue()` / `isOverEstimate()` in `taskMeta.ts`). A task that isn't Completed,
Cancelled or On Hold is overdue when:

- its due date (`exp_end_date`) has passed, or
- **it is due today and has been worked longer than its estimate**: the timer's banked time plus
  its running stretch (`custom_timer_elapsed` + now − `custom_timer_start`) exceeds
  `custom_estimated_hours`. E.g. due today with 2 hours, moved to In progress at 10:00 and still
  open at 12:01: overdue.

The hours clock is the board timer, so it starts when the task moves to In progress (not when it
was created or assigned), stops while the timer is paused, and counts plain clock hours (nights
too, while the timer runs). Tasks due on a later day only go overdue when their date passes; a
task with no estimate only by date. An overdue task carries no "at risk" reasons, so it's counted once (overdue), not in both buckets.
My tasks and the phase checklist load the timer fields for this. Where it shows: My Work
(Overdue group and tab; the label
reads "Overdue · past its estimate"), Overview buckets, Team and Projects counts, the
follow-ups ([follow-ups.md](follow-ups.md)), the project board, My tasks and the Overdue page ("Past its estimate"), the project
dashboard (count and milestones) and the ticket page's Linked work (`is_overdue` from
`get_ticket_linked_work`). The weekly AI summaries still go by due date only.
Overdue is worked out when the page loads, so an open page turns red on its next refresh.

### Follow-ups and escalation

Reminders about tasks (due next working day, due today and not started, overdue, untouched,
waiting for review, on hold, no due date, blocking an overdue task) and the overdue ladder
(the assignee, then the assigner and lead, the coordinators and department heads, the Agent
Managers) come from one engine, described in [follow-ups.md](follow-ups.md). How far up the
ladder an overdue task has gone is `Task.escalation_level`, shown as a badge
(`EscalationBadge`: "Escalated to lead / head / managers") on board cards, checklist rows, My
Tasks rows, work rows and the task details, and counted in the strip on Home and in the
sidebar. It goes back to 0 when the task is completed, cancelled or put on hold.

### Activity

The task details show the task's history, newest first, with a box to add a comment.
`helpdesk.tasky.api.get_task_activity(task)` returns `{"items": [...], "can_comment": bool}`;
the logic is `TaskActivity` in `helpdesk/task_activity.py`.

- **Who may see it:** anyone who can read the task (`check_permission("read")`, so own-tasks-only,
  department walls and the ERP rules apply). Anyone who can read it may also comment;
  `can_comment` is true for every signed-in viewer. Someone who can't read the task gets a
  PermissionError from both endpoints.
- **Every item** has `kind`, `at` (`YYYY-MM-DD HH:MM:SS`, site time as stored), `by` (user or
  null) and `by_name` (full name or null). Items are sorted by `at` (to the microsecond, so one
  save keeps its order) and capped at 300; each source is read newest first, at most 300 rows.
  All names come from one bulk User query (`user_full_names`) over `by` and the `to` of
  `assigned` / `unassigned` items (elsewhere `to` is a status, date or hours, not a person).
- **Kinds and where they come from:**
  - `created` — the Task's `owner` and `creation`; `origin` is `{type, name}` with type
    `ticket` (`hd_ticket`), `content_post` (`content_post`), `recurring`
    (`custom_recurring_task`) or null.
  - `assigned` — one per ToDo on the task, any status: `to`, `to_name`, `by` = `assigned_by`
    (else the ToDo's owner), `at` = its creation. `note` is the ToDo description as plain text,
    or null when it is Frappe's own "Assignment for Task …" filler or just the task's subject
    (what a monthly content plan writes).
  - `unassigned` — for each cancelled ToDo: `to`, `to_name`, `by` = `modified_by`, `at` =
    `modified`. Closed ToDos (the task was completed) are not an unassignment. When `by` is
    the person removed (a hand-over removes the giver's own ToDo) it reads "X left it".
  - `status` (`from`, `to` as raw values, e.g. `Working`), `due` (`from`, `to` as
    `YYYY-MM-DD`, `reason` null; a stored value that isn't a date passes through as is) and
    `estimate` (`from`, `to` as floats) — from the task's Version history (`status`,
    `exp_end_date`, `custom_estimated_hours` in `changed`); `by` is the Version's owner.
    Only Versions whose data mentions one of those fields are read (filtered in SQL), so saves
    that change other fields don't use up the 300-row cap. That filter only narrows rows down (a
    field name can also appear inside an unrelated value, e.g. a description), so rows are read
    300 at a time until 300 real changes are found or the history runs out
    (`TaskActivity.change_items`). Versions store dates in the site's
    display format (e.g. `05-10-2026` on a `dd-mm-yyyy` site), so `due` values are parsed with
    `parse_date`, which tries the site's format first (`getdate` would read them month first).
    The UI shows only the new status; a value it doesn't know (`Overdue`, `Template`, or a
    status stored translated) is shown as stored with a neutral icon, not as Open.
  - `note` — the app's own Info comments (on hold, resumed, due date moved with its reason,
    sent for review, approved, sent back, handed over, reassigned, moved project, help asked…)
    as plain text (html stripped and unescaped).
  - `comment` — people's comments (Comment type `Comment`): `text` as plain text with line
    breaks kept, and `name` (the Comment).
  - `time` — one per time log (Timesheet Detail) on this task whose timesheet isn't cancelled:
    `hours`, `date` (the log's `from_time` day), `by` = the timesheet's owner, `at` = when the
    log was saved. **Decision:** everyone who can read the task sees who logged how many hours
    on which day for this task; the log's description and other tasks' time are not shown.
- **One change, one item:** a status or due date change that a note already explains is
  dropped and the note kept: same user, within 10 seconds, and the note starts with "Due date
  moved" (explains due), "On hold" or "Resumed" (status and due), or "Sent for review",
  "Approved", "Sent back", "Handed over", "Reassigned" (status). So moving a due date later
  through Plan shows one "Due date moved from … to …. Reason: …" note, not also a bare date
  change. Moving it earlier writes no note, so it shows as a `due` item.
- **Not shown:** the `Assigned` / `Assignment Completed` comments Frappe writes (the ToDo rows
  replace them), and other comment types (likes, attachments, edits).
- **Adding a comment:** `add_task_comment(task, content)` (POST only) needs read permission,
  strips the text, refuses an empty one ("Write a comment first.") or one over 5000 characters,
  stores it as a `Comment` with the html escaped and line breaks as `<br>` (`comment_email` /
  `comment_by` the session user), and returns the new `comment` item.
- **Tests** (`helpdesk/tests/test_task_activity.py`) turn version history on with
  `record_versions()`, since Frappe skips it in tests unless a save asks.

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
- **Download CSV** has a Billable column.
- **List**: a titled card; Timesheet, Person (Team), Status, Hours (right-aligned, tabular)
  and Updated columns from `md`; below that a two-line row with person, status and date in
  the second line. Empty states tell "no time logged in these dates" (Clear filters) from
  "no timesheets yet" (Log time).
- **Log time** dialog: a Billable checkbox, on by default. Non-billable time doesn't use up a
  customer's support hours ([support-contracts.md](support-contracts.md)).
