# Extra hours over a task's estimate

Status: built 2026-11-27 (TASK-2026-02366, the owner's request: "when the estimated hours are
exceeded, the time needs the project manager's approval; it goes to review automatically with an
explanation note, and once the project manager accepts, the extra hours are allowed"). This
document is the source of truth for the rule and changes with it.

## Why it works this way

Time reaches a timesheet in the hub only when a task is completed (`helpdesk.tasky.api.
complete_task`, the Complete task dialog and the mobile app): the working-day limits and the
hand-entry window ([workspace-pages.md](workspace-pages.md), `time_sessions.check_hand_entered`)
already apply there, so the estimate rule sits in the same place. Hours within the estimate are
logged at once, so timesheets stay current; only the hours over it wait, and they are logged on
the days they were worked once approved, so reports and invoicing see accurate days.

A task without an estimate (0) has no limit.

## The rule (`helpdesk/tasky/extra_hours.py`)

- **What counts:** the hours already on the task's timesheets (its actual hours without the
  timer's banked time, which the completion replaces) plus the hours being completed, plus any
  still waiting from this person's earlier completion. Over the estimate by more than 0.01 h is
  over.
- **Explanation required:** `complete_task(…, extra_hours_reason)` refuses hours over the
  estimate without one ("This is 0.5 h over the task's 4 h estimate. Explain the extra hours for
  the project manager."), up to 1,000 characters.
- **The split:** the hours that still fit the estimate are taken from the earliest days and
  logged now; the rest, from the latest days, are **held** on the task. A day split in two stays
  one stretch: its logged part starts at the day's usual start and the held part's start is kept
  right after it.
- **Review, always:** the task goes to **Pending Review** even on a project that doesn't ask for
  reviews. The reviewers' notice says "Ready for review, 0.5 h over the estimate to approve",
  and the task's timeline gets "Asked for 0.5 h over the 4 h estimate: <explanation>".
- **Stored on the Task:** `extra_hours` (the hours waiting), `extra_hours_by` (who worked them),
  `extra_hours_reason`, and `extra_hours_days` (hidden JSON: each held day's hours and start,
  and the completion's note for their timesheets). Nothing is on a timesheet until approved.

## Who decides

Only the **project's manager or lead** (`can_manage_project`: its owners and listed managers,
its lead, and tasky admins; for a task without a project, tasky admins). A Project Coordinator
still reviews tasks but can't approve or decline extra hours (403).

- **Approve** (`approve_task(task, rating, approve_extra_hours=1)`): the held hours are logged on
  their own days as timesheets of the person who worked them (their `owner`, which reports and
  permissions read, is that person, not the approver), added to the task's actual hours, and the
  task completes. The worker is told. A one-click Approve from a list, without
  `approve_extra_hours`, is refused ("Open it to read why, then approve or decline them"), so
  nobody approves extra hours without seeing the explanation.
- **Decline** (`decline_extra_hours(task, note)`, the note required): the held hours are never
  logged, the task completes with the hours within the estimate, and the worker is told why.
- **Send back** works as before. The held hours stay on the task; when the same person completes
  it again they come along with the new hours, all over the estimate now, so the explanation is
  asked for again (filled in with the earlier one). If someone else completes it, the earlier
  person's held hours are dropped with a line on the timeline.

## Screens

- **Complete task dialog** (`CompleteTaskDialog.vue`): `get_completion_days` also sends
  `estimate`, the hours already `logged`, and the person's own `waiting` hours with their
  `waiting_reason`. Going over shows "0.5 h over the 4 h estimate. The hours within it are logged
  now; the 0.5 h extra go to the project manager with your explanation, and the task goes to
  review." and a required **Why the extra hours?** field. The success toast says how much was
  logged and how much waits.
- **Task dialog** (`TaskDetailDialog.vue`): a task with hours waiting shows them, the
  explanation and who asked. For the project's manager or lead the review actions are **Send
  back**, **Decline extra hours** (`DeclineExtraHoursDialog.vue`, a required note) and
  **Approve with 0.5 h extra**; a coordinator sees Send back and "The project's manager or lead
  decides them".
- **Mobile app** (`helpdesk.api.mobile.complete_task`): takes `extra_hours_reason`. Until the
  app sends it, completing over the estimate from the app shows the server's message; approving
  extra hours from the app's review list is refused with the same "open it" message.

## Tests

`helpdesk/tests/test_extra_hours.py`: within the estimate completes as before; no estimate, no
limit; over it needs an explanation and nothing is logged without one; the estimate's hours
logged (earliest days first) and the rest held, the task in review, the reviewers told with the
hours; one-click approve refused, a coordinator refused, the lead's approval logging the held
hours as the worker's own timesheet right after that day's earlier hours, the worker told;
decline needs a note, is refused for a coordinator, logs nothing more and completes; sent back,
the held hours come along with the next completion and are asked for again.
