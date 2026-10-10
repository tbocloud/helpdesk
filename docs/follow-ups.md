# Follow-ups and escalation

The owner's direction (2026-10-10): the company follows the **work**, not people's hours.
Everyone must follow through on their tasks and tickets; when something isn't done, the
reminders keep coming, in the app and in Teams, and the longer it waits the more people
hear about it. The same approach for tasks and for tickets. There is no timer policing and
no hour budget here: the rules look at due dates, status, SLAs and replies.

One engine does all of it: `helpdesk/follow_ups.py`, run every 15 minutes
(`helpdesk.follow_ups.run` in `hooks.py`). It replaced the old scheduled reminders
(`send_task_reminders`, `send_hold_reminders`, `send_ticket_reminders` in
`helpdesk/work_reminders.py`) and the 10:00 morning brief (`helpdesk/morning_brief.py`),
which are gone. `work_reminders.notify_users` stays the one way the hub notifies people
about events (assignments, holds, reviews, completions); the engine posts through the same
module (`new_notification`).

## How a run works

1. **Evaluate** (`evaluate(ctx)`): every open task (not Completed, Cancelled or Template)
   and every open or paused ticket goes through the rules switched on in **HD Follow Up
   Settings**. Each hit is a `FollowUp`: the item, the rule, its stage (with the rule, what
   people were last told), a severity, the text, the recipients, the owners (assignees),
   the ladder level and whether it pings at once. Nothing is sent here, so the banner, the
   preview and the manager view use the same function.
2. **Quiet hours**: outside working hours, or on a day off, nothing is sent, except SLA
   breach notices when *Send SLA breaches outside working hours* is on (off by default).
3. **Record levels** (`save_levels`): `Task.escalation_level` / `escalated_on` and
   `HD Ticket.custom_escalation_level` / `custom_escalated_on`, written without touching
   `modified`. A level goes back to 0 when the item is no longer late; `Task.clear_escalation`
   (validate) also resets it as soon as a task is Completed, Cancelled or put On Hold.
   Switching follow-ups off clears every stored level on the next run (`clear_levels`), so
   no badge outlives the engine.
4. **Notices** (`post_notices`): one notification per person and item per day, see Dedupe.
5. **Customer follow-up emails** (`send_customer_follow_ups`), when switched on.
6. **Digests** (`send_due_digests`) at the digest times.

The result of step 1 is cached for 16 minutes (`current()`), longer than the run that
refreshes it, so page loads don't evaluate everything themselves; the cache is dropped when a
task's status or due date changes (`Task.refresh_follow_ups`) and when the settings are
saved.

## Working days and hours

`WorkCalendar` in `follow_ups.py`, from what the hub already has; nothing new to set up:

- **Working days**: HD Work Settings' weekly off and Saturdays off, and the holidays on the
  default SLA's holiday list (`recurrence.working_day_checker`, the same check recurring
  tasks use). That list includes the holidays synced from the CRM site (see
  [tbo-crm-integration.md](tbo-crm-integration.md#holidays-and-leave-implemented-read-only)).
- **Working hours**: the default SLA policy's working days and hours (Settings → SLA
  policies). Without a default SLA, the whole working day counts.
- Every threshold counts working days, working hours or working minutes, so a weekend or a
  holiday never makes something look later than it is.
- **Leave**: see [Leave](#leave) below.

## Leave

Approved leave comes from ERPNext on the CRM site into **HD Leave** (daily, see
[tbo-crm-integration.md](tbo-crm-integration.md#approved-leave)). Each run reads who is on
leave today once (`Context.on_leave`, `work_calendar.on_leave`); a half day doesn't count,
since they still work part of it.

- **Nobody on leave is nudged or escalated to** (`Context.cover_leave`, applied to every
  follow-up): they're taken off its recipients, at every ladder level.
- **The assignee is on leave**: when an owner (an assignee) would have been told, the
  follow-up goes straight to who covers for them instead, with the text ending "Anu Varghese
  is on leave until Wed 14 Oct":
  - a task: its assigner and the project lead (else the project managers);
  - a ticket: the team lead (the support department's heads, else the Agent Managers).
- **Nobody left** (everyone told is away): the cover people, else the Agent Managers.
- The item still counts as the assignee's (`owners`), so the banner and the manager view
  show it as their work.
- **Digests** skip people on leave, including the morning plan.
- A task held with the reason *Leave* still leaves the overdue ladder like any held task.

## The rules

All thresholds are in HD Follow Up Settings (**Settings → Follow-ups**). Defaults:

| Rule | When | Who | Severity |
| --- | --- | --- | --- |
| **Due next working day** (`due_tomorrow`) | Due on the next working day, not held or in review | Assignee | Due now |
| **Due today, not started** (`due_today`) | Due today, still Open, no timer ever run | Assignee in the morning, again from 14:00 (`afternoon_nudge_at`) | Due now |
| **Overdue** (`overdue`) | Past its due date (or due today and past its estimated hours, `is_task_overdue`), not held or in review | The ladder below, every working day until Completed, Cancelled or On hold | Overdue; Escalated from L2 |
| **Assigned, untouched** (`untouched`) | Open, no timer, no comment since the latest assignment, for 2 working days | Assignee; a day later also the assigner | Waiting on you |
| **Waiting for review** (`review`) | Pending Review for 1 working day (since the change to Pending Review in the task's history) | The coordinators (else the lead); a day later also the lead (else the project managers) | Waiting on you |
| **On hold** (`hold`) | On hold for 3 working days | Whoever put it on hold, to resume it or update the note; *Waiting on customer* also asks the assignees to follow up with the customer; at twice the days also the lead | Waiting on you |
| **No due date** (`no_due_date`) | Open (not held or in review) without a due date, 1 working day after it was created | The assigner, else the lead | Waiting on you |
| **Blocking an overdue task** (`blocked`) | Another open task depends on this one, and this one is overdue | This task's assignees ("… is waiting on your overdue task") | Waiting on you |
| **SLA** (`sla`) | First reply and resolution: 50% and 80% of the SLA's working time used, then the breach | The ticket ladder below | Due now; SLA breached |
| **Unassigned ticket** (`unassigned`) | Open, nobody assigned, for 30 working minutes since it came in | The ticket's team and the Agent Managers | Overdue |
| **Customer replied, no answer** (`customer_replied`) | The customer's last message is newer than the last agent reply, for 4 working hours (first reply already given) | Assignee; at twice the hours also the team lead | Waiting on you; Overdue at L1 |
| **Waiting on the customer** (`awaiting_customer`) | Paused (e.g. Replied, not Waiting on Task) for 3 working days since the last agent reply | The follow-up email, or the assignee when emails are off | Waiting on you |

A ticket without an assignee goes to its team (HD Team members), else the Agent Managers.

## The ladder

Each level **adds** people; nobody drops off.

| Level | Tasks (working days overdue) | Tickets | Badge |
| --- | --- | --- | --- |
| **L0** | From day 0: the assignee (no assignee: the project lead, else its managers) | SLA 50%: the assignee | none |
| **L1** | From day 1: plus the assigner and the project lead (else its managers) | SLA 80%: plus the team lead | Escalated to lead |
| **L2** | From day 3: plus the project coordinators and the department heads (the project managers when the project has no department) | Breached: same people, pinged at once | Escalated to head |
| **L3** | From day 5: plus the Agent Managers | Still breached after 2 more working days (L3 − L2 days): plus the Agent Managers | Escalated to managers |

- The days are settings (`ladder_l1_days`, `ladder_l2_days`, `ladder_l3_days`); they must be
  1 or more and in order.
- **Key tasks and milestones escalate one level sooner** (`key_tasks_escalate_faster`, on):
  a key task one day late is already at L2.
- **The tickets' team lead** is the heads of the *Support department* setting (Settings →
  Departments sets the heads). Without one, it's the Agent Managers (`department_heads(None)`),
  so a ticket ladder works with nothing configured.
- **Department heads** come from `tasky.permissions.department_heads` (the department's Heads
  plus role-based heads such as the Digital Marketing Head); coordinators and managers from
  the project's team (`Project User.custom_role`).

## Delivery: persistent, not spammy

- **In the app**: one notification per person and item per day (the item's most pressing
  follow-up for that person). When a later run finds a different rule or a higher level the
  same day, the notification is rewritten and marked unread again instead of adding another.
  Follow-up notifications stay in the panel (`new_notification(..., deliver=False)`): they
  reach chat in the digest, not one message per item.
- **Immediate pings**: only for L2 and above, SLA breaches, and overdue key tasks and
  milestones. The notification then also goes to chat (Teams or Slack direct message) or,
  when chat can't reach the person, by email, through `HDNotification.deliver`. The team's
  escalation channel gets the item once per stage ("Escalated to head (Overdue): …"), through
  `chat_notifications.post_escalation`.
- **Digest**: at each digest time (default **09:30 and 15:30**, working days, in working
  hours) every person gets one message with everything that needs their action now, grouped
  by severity (SLA breached, Escalated, Overdue, Due now, Waiting on you), at most 8 per
  group, each line a link into the helpdesk. Something unresolved is in every digest, every
  working day, until it moves: that is how "Teams keeps going".
- **Morning plan**: the first digest of the day also carries the person's plan for today, as
  on Home (`helpdesk.home_plan`): today's AI plan when Home already wrote one, else the same
  steps from the rules (`rule_steps` over `api.home._day`). The digest never calls the AI.
  Everyone with an open task or ticket gets it, even with no follow-ups.
- **Where the digest goes**: chat when HD Chat Settings is on and reaches the person, else
  email (unless the person turned email notifications off, or chat is on and *Email people who
  can't be reached in chat* is off). A run that missed a digest time sends one digest, not one
  per missed time; `digest_sent_through` (hidden) records it before sending, so a failure
  halfway never sends anyone two (it is committed before the first message goes out,
  since chat posts can't be rolled back).
- **In-app strip**: `FollowUpStrip.vue` on Home (`get_home().follow_ups`) and at the bottom of
  the sidebar (`get_nav_counts().follow_ups`), e.g. "2 overdue · 1 escalated to your head ·
  3 waiting on you", linking to My Work, until the work moves (`summary_for`).

## Dedupe

The key is **(person, item, rule, stage or level, date)**:

- Stored on the notification as `HD Notification.dedupe_key`
  `follow-up:<date>:<rule>:<stage>`, one notification per (person, item) per date.
- A run with the same key changes nothing; a different key the same day rewrites it (and pings
  again only if the new stage is an immediate one); a new day starts a new notification.
- The digest's own once-per-time guard is `digest_sent_through`; the channel's is
  `HD Chat Escalation` (once per message text).

## Customer follow-up and auto-close

- **The email** (*Email customers who haven't replied*, **off** by default): after the
  waiting days, the customer gets one polite follow-up as a reply on the ticket
  (`HDTicket.reply_via_agent`, to `raised_by`, as the automation user, or Administrator when
  that user isn't an agent, since only agents may reply). Each ticket's send runs in its own
  savepoint, so a failed email leaves no reply on the ticket and is tried again. The text is the
  *Follow-up email* setting, rendered with `{{ ticket }}`, `{{ subject }}` and
  `{{ customer }}` (`HDTicket._get_rendered_template`, the same as the other ticket emails).
  `HD Ticket.custom_customer_followed_up_on` records it, so it goes once per wait; an agent's
  later reply starts a new wait.
- **Closing**: this already existed and is reused, not duplicated. HD Settings' auto-close
  (Settings → General → Tickets: *Automatically close tickets*, the status and the days,
  **off** by default) closes tickets in that status after that many days without an email,
  daily (`hd_ticket.close_tickets_after_n_days`). The follow-up email is an email on the
  ticket, so the auto-close days count from it: that is the "M more days". When auto-close is
  off (or the ticket is in another status), the assignee is asked instead, after the same
  number of working days: "No reply … after the follow-up email: close the ticket or call the
  customer".

## Settings → Follow-ups

`desk/src/components/Settings/FollowUps/FollowUpSettings.vue`, System Managers and Agent
Managers (`helpdesk.api.follow_ups`, which checks the roles itself; HD Follow Up Settings
gives the same two roles write access):

- **Enabled** in the header; Save in the header (see [settings-ui.md](settings-ui.md)).
- **Delivery**: digest times, the plan in the first digest, breaches outside working hours,
  where messages go now (chat or email), and **Send me a test digest** (`send_test_digest`:
  today's digest for the caller only, to the caller only).
- **Escalation ladder**: the three days and the key-task switch.
- **Task rules** and **Ticket rules**: a switch per rule and its threshold; the support
  department.
- **Customer follow-up**: the email switch and its template; a line on HD Settings'
  auto-close with a button to General.
- **Working hours**: read from the default SLA policy, with a button to SLA policies.
- **Preview** (`get_preview`): what each person would get in a digest right now, busiest
  first, each item with its rule and level.

Validation (`HDFollowUpSettings.validate`): digest times are 24-hour times (stored sorted,
"09:30, 15:30", at least one), the afternoon nudge is one 24-hour time stored as "14:00" (a
Data field, not Time: Frappe gives a new document's Time fields the current time instead of
their default, so a fresh or seeded site nudged "in the afternoon" from whenever it was set
up; the patch `v16_0_2.reset_seeded_afternoon_nudge` puts such a seeded value back to 14:00), the ladder days are 1 or more and in order, thresholds are 1
or more, and the SLA warnings are 1–99% with the second after the first. On the page a
cleared number box keeps its last value rather than sending 0.

Existing sites get the defaults stored by the patch `v16_0_2.seed_follow_up_settings`
(post model sync), since a new Single has nothing stored until it is saved.

## Where escalation shows

- `EscalationBadge.vue` ("Escalated to lead / head / managers", warning at L1, danger from
  L2, with an icon): board cards, checklist rows, My Tasks rows, the task details, work rows
  (My Work, Overview lists, Home), the Tickets list (next to the subject) and the ticket's SLA
  panel ("Follow-up").
- **Overview → Follow-ups** (`FollowUpControl.vue`, System Managers and Agent Managers,
  `get_follow_up_overview`), across all projects and tickets (the page's filters don't apply,
  and it says so): counts of escalated (L2+), breached and overdue items, the
  escalated items, the oldest overdue tasks, and the people with the most open escalations
  (L1+, by assignee).
- **TBO Smart app** (docs/tbo-smart-api.md): `get_escalations` lists every L2+ item
  (`follow_ups.escalations()`, the same list the Overview shows the top of), for the same
  people. A manager can **nudge** an item's assignees from there (`nudge`: a Reminder through
  `notify_users`, sent every time, plus a note on the item) or reassign it.

## Files

- Engine: `helpdesk/follow_ups.py`; API: `helpdesk/api/follow_ups.py`; settings:
  `helpdesk/helpdesk/doctype/hd_follow_up_settings/`.
- Fields: `Task.escalation_level`, `Task.escalated_on` (task.json);
  `HD Ticket.custom_escalation_level`, `custom_escalated_on`, `custom_customer_followed_up_on`
  (custom fields in `setup/install.py`); `HD Notification.dedupe_key`.
- UI: `FollowUpSettings.vue`, `EscalationBadge.vue`, `FollowUpStrip.vue`, `followUps.ts`,
  `pages/work/components/FollowUpControl.vue` and `FollowUpList.vue`.
- Tests: `helpdesk/tests/test_follow_ups.py`.

## After deploy

- **Teams**: HD Chat Settings → enabled, platform Microsoft Teams, the *Direct Message
  Workflow URL* (one workflow for everyone; it receives the recipient's email) and the
  *Escalation Channel Workflow URL*. Without the direct-message workflow, digests and pings
  go by email. People are matched by their user email.
- **Working hours and days**: the default SLA policy's hours, HD Work Settings' weekly off
  and Saturdays off, and the business holidays (synced from the CRM site when Settings → CRM
  → Holidays and leave is on, which also brings approved leave).
- **Follow-ups**: digest times, the ladder days, the support department (and its heads in
  Settings → Departments), whether to email customers, and auto-close in General.
