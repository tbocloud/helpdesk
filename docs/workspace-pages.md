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
| A Project Manager (role) who is on the project's team | Every task of that project, but no manager powers |
| Digital Marketing Head, DM Coordinators | Every task of content calendar projects and of Digital projects |
| Everyone else (developers, functional consultants, content people) | Only their own tasks: assigned to them, given out by them (they assigned it to someone), or created by them, assigned or not |

`sees_all_tasks(project)` answers the first four rows for one project, and
`get_project_detail` returns it as `sees_all_tasks`. "Assigned to" and "given out by" come
from the task's ToDos (`allocated_to`, `assigned_by`), matched exactly: a LIKE on `_assign`
would read `_` in a user ID as a wildcard. A finished assignment (Closed ToDo) still counts,
so people keep seeing the tasks they completed; a withdrawn one (Cancelled) doesn't. The
department walls ([departments.md](departments.md)) apply on top of every row except admins.

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

## Board (`/my-board`)

The sidebar's **Board** (after My Work, for everyone including the Content Team) is the project
board (`pages/tasky/Kanban.vue`, route `MyBoard`, no `projectId`) showing the current user's own
tasks from every project they're assigned in, by status: Open, In progress, In review, On hold,
Completed, Cancelled. `get_kanban_tasks()` without `project` returns tasks whose `_assign` holds
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
  lead, for the whole task (`_get_own_task`). Open tasks only, with the timer stopped.
- **To whom:** an active agent on the project's team; managers and leads may pick anyone
  (they join the team). A content post's task may go to any active agent, since content
  people work on the content calendar without joining its project (`TeammatePicker`
  `anyone`); the department walls still refuse the other team, and an ERP Employee is refused
  a content task before anything changes. Tasks outside a project can't be handed over.
- **What changes:** the hander's ToDo is cancelled and the teammate's names the task's
  original assigner (`get_assigners`) as `assigned_by`, not the hander. So "Assigned by"
  keeps showing who gave the work out, and the task leaves the hander's lists unless they
  gave it out or created it. Other people sharing the task keep it. On a content post's task
  the post's role (or every role, for the post's shared task) gets the teammate in the
  hander's place (`HDContentPost.replace_on_part`, saved without re-syncing its tasks), so
  the post's next save doesn't give the task back.
- **Record and notices:** comments "Reassigned from … to … by …" and "Handed over by …:
  reason"; the teammate is notified ("… handed you a task"), and the project lead (or its
  managers when it has no lead) and the original assigner hear who took it and why.

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
reads "Overdue · past its estimate"), Overview buckets, Team and Projects counts, the morning
brief, the project board, My tasks and the Overdue page ("Past its estimate"), the project
dashboard (count and milestones) and the ticket page's Linked work (`is_overdue` from
`get_ticket_linked_work`). Reminders and the weekly AI summaries still go by due date only.
Overdue is worked out when the page loads, so an open page turns red on its next refresh.

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
