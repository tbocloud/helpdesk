# Recurring tasks

Work that repeats creates its own task: "Monthly backup check" for a customer's project on
the 1st, "GST filing reminder" on the 15th of every month, "Weekly status report" every
Friday. A project's lead or manager sets up the schedule once; a daily job creates each
task ahead of its due date, assigns it and links it back to the schedule.

## Decisions

- **One schedule per kind of work, on a project.** A schedule (**HD Recurring Task**) holds
  the task's values (name, description, category, priority, estimate, assignee, key task)
  and the rule. Tasks are ordinary tasks in the project; nothing else about them changes.
- **Task due dates are dates.** The Task doctype has no due time, so a schedule's optional
  due time is shown in the schedule ("due 18:00") and in the assignment notification, not
  stored on the task.
- **The server is the only date math.** The dialog's preview and the list's "Next due" come
  from `helpdesk/recurrence.py`, the same code the daily job runs, so they can't disagree.
- **Dates already past are skipped, not created late.** A new schedule with a start date in
  the past, a changed schedule and a resumed one start from today. Only real missed runs
  (the job didn't run for a few days) are caught up, and only with the latest occurrence.
- **Deleting a schedule keeps its tasks.** They just stop pointing at it.

## The rule

| Field | Meaning |
| --- | --- |
| Repeat (`frequency`) | Daily, Weekly, Monthly, Quarterly or Yearly. |
| Every (`interval`) | Every N days, weeks, months, quarters or years (1 to 99). |
| On (`weekdays`) | Weekly only: one or more days, stored as "Monday,Friday". Defaults to the start date's weekday. |
| Day of the month (`month_day`) or Last day (`last_day_of_month`) | Monthly, quarterly and yearly. The 29th to 31st fall on the last day of shorter months (31 → 30 April, 28 or 29 February). Defaults to the start date's day. |
| Starts on (`start_date`) | The first date the rule can fall on. Quarterly counts quarters from this month; yearly repeats in this month. Weekly with an interval counts weeks from this week. |
| Ends (`ends`) | Never; On a date (`end_date`, the last date it can fall on); or After a number of tasks (`max_occurrences`): N tasks created. Dates left out as non-working (daily) and dates skipped as already past don't count; the job compares against `occurrences_created`, so "every working day, after 10" makes 10 tasks. |
| Create it N days before it's due (`lead_days`) | The task is created on the due date minus N calendar days (0 to 365). |
| Due time (`due_time`) | Optional; see Decisions. |
| Move due dates off non-working days (`skip_non_working_days`, on by default) | Weekly, monthly, quarterly and yearly: a due date on a non-working day moves to the next working day. Daily: non-working days are left out (moving them would put two tasks on the same day). |

**Non-working days** (`working_day_checker` in `helpdesk/recurrence.py`): HD Work Settings'
weekly off (Sunday by default) and Saturdays off (the 2nd and 4th by default,
`helpdesk/work_calendar.py`), plus the holidays on the default SLA's holiday list
(`company_holidays` in `work_calendar.py`; the hub's calendar).

The schedule in words (`describe()`), e.g. "Monthly on the 1st · due 18:00 · created 3 days
ahead · moved to the next working day", is shown in the list and the dialog.

Each **occurrence** has three dates: the date the rule falls on (`on`, which with the
schedule identifies the task), the due date (moved off non-working days) and the day its
task is created (due minus lead time).

## The daily job

`create_recurring_tasks` (scheduler, daily) runs every active schedule on its own; one that
fails is rolled back and logged (Error Log "Recurring task failed for RT-…") without
stopping the others. For each schedule (`HDRecurringTask.create_due_tasks`):

1. **Project closed** (Completed or Cancelled): the schedule is deactivated with the reason
   "Stopped: project … is Completed", and the person who set it up, the project lead and the
   project's managers get a notification. Nothing is created.
2. **Pending occurrences**: the ones whose creation day has come and that come after
   `last_occurrence`. When there are several (missed runs), only the latest is created, with
   an Info comment on the task naming the dates that were missed.
3. **The task**: name, description, project, category, priority, estimate, key task, due
   date, `custom_recurring_task` (the schedule) and `custom_recurrence_date` (the date the
   rule fell on). It is created only if no task already has that schedule and date, so a
   rerun or a lost `last_occurrence` never makes a duplicate.
4. **Assignee**: assigned through `_assign_user` (`assign_to._add`, ignore_permissions) with
   the schedule's creator as the assigner, so "Assigned by" shows them, and a note in the
   assignment notification ("… (repeats: Monthly on the 1st), due 1 Nov 2026, 18:00"). An
   assignee who is no longer an active agent on the project's team is skipped: the task is
   created unassigned and the creator, lead and managers are told to pick someone.
5. **Description**: when the schedule has none, AI task descriptions
   ([ai-task-descriptions.md](ai-task-descriptions.md)) write one as for any new task.
6. The schedule records `last_occurrence`, `last_task`, `occurrences_created`, and the next
   `next_due_date` and `next_create_on`. When no dates are left it deactivates itself:
   "Finished: every task in the schedule was created."

## States

The list shows one of (`_state` in `helpdesk/api/recurring_tasks.py`):

| State | Meaning |
| --- | --- |
| Active | Creating tasks. |
| Paused | Someone paused it ("Paused by …"). Resuming starts from today: dates that went past while paused are skipped. |
| Finished | No dates left. Moving the end later (or resuming after changing it) starts it again. |
| Stopped | The project is Completed or Cancelled. It can't be resumed until the project is reopened. |

## Where it is in the app

- **Project → Recurring tab** (`/helpdesk/projects/<project>/recurring`, route
  `TaskyRecurring`, `desk/src/pages/tasky/ProjectRecurring.vue`; tab in `ProjectNav`): the
  schedules, active first. Each row: task name, state badge when not active, Key badge, the
  schedule in words, assignee, next due date (with the creation day when it differs), tasks
  created so far, why it stopped, and the last task it created (opens the task panel, only
  when the viewer may read that task). Managers get Pause / Resume and a menu with Edit and
  Delete (a confirmation that says the created tasks stay). Loading, error (Retry) and empty
  states; the empty state's "New recurring task" is the page's primary action for managers.
- **Dialog** (`components/RecurringTaskDialog.vue`): the task (name, description, assignee
  from the project team in a Combobox, category, priority, estimate, key task) and the rule
  builder (repeat, every N with the unit spelled out, weekday toggles, day of the month or
  last day, start date, ends, lead days, due time, move off non-working days), with a live
  preview of the next 5 due dates and their creation days from
  `preview_recurring_task` (debounced). A rule that can't produce dates shows why in the
  preview instead of failing.
- **"Make recurring…"** in a board card's menu and the task panel's actions (managers and
  leads of the project; not on a task a schedule created): opens the dialog prefilled from
  the task (name, description, category, priority, estimate, its assignee if on the team,
  key task; monthly on the task's due day, starting from that date or today).
- **A created task's panel** says "Created by a recurring schedule" and links to the tab.
- Labels, tones and icons of the states: `desk/src/pages/tasky/recurringMeta.ts`.

## Who can do what

| Action | Who |
| --- | --- |
| See a project's schedules | Whoever sees every task of the project (`sees_all_tasks`: admins, its managers, lead and coordinators, a Project Manager on its team, content leads on content projects) sees them all. Other members see only the schedules assigned to them or that they set up, and the last created task only when it is theirs (tasks follow `task_query`). |
| Create, edit, pause, resume, delete, preview, prefill from a task | Admins, the project's managers and the project lead (`can_manage_project`) |

The doctype gives role access to System Manager only; every call checks these rules in
`helpdesk/api/recurring_tasks.py`. The assignee must be an active agent on the project's
team when it is set or changed.

## Data model

- **HD Recurring Task** (`RT-#####`): `project`, `project_name` (fetched), `subject`,
  `is_active`, `inactive_reason`, `description`, `category` (one of Task's categories),
  `priority`, `estimated_hours`, `assignee`, `is_key`; the rule fields above; progress
  (read only): `next_due_date`, `next_create_on`, `occurrences_created`, `last_occurrence`
  (the latest date handled: created, or skipped as past), `last_task`.
- **Task** custom fields (`helpdesk/setup/install.py`): `custom_recurring_task` (Link,
  indexed) and `custom_recurrence_date` (Date). Both read only and not copied.
- A schedule change (any rule field) is detected by comparing normalised values, since the
  dialog sends dates as text; editing only the task's name or assignee doesn't restart the
  schedule.

## API

`helpdesk/api/recurring_tasks.py`:

- `get_recurring_tasks(project)` → `{rules, can_manage}`; each rule has its values,
  `state`, `schedule`, `assignee_name`, `last_task` (`{name, subject, status, due_date}` or
  null) and `has_last_task`.
- `get_recurring_task_form(project, task=None)` → `{team, categories, priorities,
  frequencies, ends, prefill}`.
- `preview_recurring_task(project, values, name=None)` (with `name` when editing, so the
  tasks already created count towards "after N"; nothing is saved) → `{schedule, dates: [{on, due, create_on}],
  error}`.
- POST: `save_recurring_task(project, values, name=None)`,
  `set_recurring_task_active(name, active)`, `delete_recurring_task(name)`.

## Tests

`helpdesk/tests/test_recurring_tasks.py` (helpers `recurrence_rule`, `make_recurring_task`,
`add_company_holiday`, `get_recurring_tasks_created` in `helpdesk/test_utils.py`;
`hold_commits`; `frappe.sendmail` mocked; dates frozen in October 2026):

- date math without the database: day 31 in short months, last day in a leap year, yearly
  on 29 February, weekly on several days every other week, daily and quarterly intervals,
  every other month, both end conditions, "after N" counting tasks rather than days left
  out, lead time, moving and dropping non-working days,
  a rule whose days are never worked, the schedule in words;
- the real calendar: the 2nd Saturday and a holiday move the due date, the 3rd Saturday is
  worked;
- the job: created lead days ahead with every value, assigned with the creator as assigner;
  reruns and a lost `last_occurrence` never duplicate; missed runs create only the latest
  with a note; a new schedule skips past dates; ends after N then restarts when extended; dates skipped as past don't use up "after N";
  a closed project stops it and blocks resuming; resuming skips the paused dates; deleting
  keeps the tasks;
- validation and API: assignee must be on the team, a schedule without dates is refused, the
  preview's dates and errors, "Make recurring…" prefill, and permissions (members view
  without the lead's task and can't change anything, the lead creates, outsiders can't see).
