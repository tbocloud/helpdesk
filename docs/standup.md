# Async daily stand-up

The owner's need (2026-10-14): every morning the developers and consultants met in a room to
say what they did yesterday, what they plan today and what blocks them. The stand-up replaces
that meeting with something in the hub that takes a minute: a draft filled in from the
person's own work, checked and submitted, and one summary per department in Teams.

**Task control, not time tracking.** The stand-up follows the work. Hours appear only as a
fact ("6.5h logged", when the setting is on), never in the AI's facts and never as a
judgement. "Plan against done" is a count of linked work, not a score, and is shown only to
the people who run the team.

## The flow

`helpdesk/standup.py`, run every 15 minutes (`helpdesk.standup.run`, in the same cron entry
as the follow-ups). Nothing happens while **Settings → Stand-up** is off (the default) or on
a day off (the weekly off, Saturdays off and business holidays, through follow-ups'
`WorkCalendar`).

| When (setting) | What |
| --- | --- |
| **Drafts open** (09:00) | Everyone gets a draft HD Standup filled in from their work, and a notification: "Your stand-up is ready, check it and submit (1 min)", linking to `/helpdesk/standup`. It goes through `work_reminders.notify_users`, so it lands in the bell and as a Teams direct message (or email when chat can't reach them), like every Reminder. |
| **Reminder** (10:00) | One reminder to everyone whose stand-up is still a draft: "Your stand-up isn't submitted yet. It goes to your team at 10:30." |
| **Summary posts** (10:30) | Drafts become **Auto-posted** (posted as filled in, marked "(auto)"), then each department's summary goes to its Teams channel. |

- **Who gets a draft:** active agents (HD Agent) with an enabled account, in the stand-up's
  departments. **Skipped:** anyone on approved leave that day (HD Leave, full days; a half
  day still gets one), and anyone with no open task or ticket, nothing done on the
  previous working day and no content post to report today (a post going live, missed or
  waiting, see [Content calendar](#content-calendar): their part can be done while the post
  still needs them). Sales Employees never get one: their work is leads, which the stand-up
  doesn't read ([departments.md](departments.md#sales-wall-sales-employee)).
- **Departments left out** of Settings → Stand-up (when any are listed) get no draft and
  no reminder, can't start or edit one from the page (`takes_part`; a stand-up made before
  they were left out stays readable, as history), and are never posted, not even to the
  escalation channel; their drafts stay drafts.
- **Long queue:** filling everyone's draft and composing the summaries run as jobs on the
  `long` queue (`open_drafts_job`, `post_summaries_job`, 1500 seconds), since the cron job
  itself runs on the default queue's 300 seconds and a step cut off after its day was
  recorded would not run again. A late run that opens drafts and posts at once does both
  in the drafts' job (`open_drafts_job(post=True)`), so two workers can't post before the
  drafts exist.
- **Once a day:** each step records its day (`opened_on`, `reminded_on`, `posted_on` on the
  settings) and commits **before** sending, so a job that dies halfway never sends twice.
  The draft's name is `SU-<date>-<user>`, so a second run, or a person saving while the run
  creates theirs, still leaves one stand-up. The reminder also goes through `notify_users`'
  once-per-document guard.
- **A late server:** a run that starts after several times does them in order once; drafts
  that only just opened aren't reminded in the same run.
- **No draft yet?** The page shows today's draft filled in fresh (not saved) whenever the
  stand-up is on, so someone skipped (no work yesterday, a new joiner) can still write one;
  saving creates it.

## Auto-fill (`autofill`)

A function that writes nothing and reuses the hub's queries, run **as the person** (so only
what they may open is listed, the department walls included):

- **Yesterday** is the **previous working day** (`WorkCalendar.previous_working_day`): Friday
  (or Saturday when it is worked) on a Monday, the day before a holiday after it.
  - tasks they completed that day (`completed_on`, matched through ToDos like My Work);
  - tickets they resolved (`resolution_date`) or replied to (a sent Communication they wrote);
  - content posts whose stage they changed (the post's history; for the content team,
    worded with the client and "Published", see [Content calendar](#content-calendar));
  - hours logged that day (the Scoreboard's `logged_hours`), as a fact.
- **Today**, from `get_my_work` and Home's timers, in this order: overdue tasks, due today,
  in progress (with "timer running"), due on the next working day; then **today's Home plan
  when Home already wrote one** (the cached AI plan). The stand-up never calls the AI for the
  plan, as the follow-up digest doesn't.
- **Blockers:** tasks on hold (reason, days and the hold note), tasks waiting on another open
  task ("Waiting on …"), overdue key tasks, and tickets in *Waiting on Task*.
- A task lands in one place at most; tasks in review wait on the reviewer and aren't listed.
- Every linked item opens its record: tasks open in place (the task dialog), tickets go to
  the ticket, posts to the content calendar on that post (`/content?post=…`).

## Content calendar

Owner's request (2026-10-14): "standup also need Content Calendar, Digital team." Writers,
designers, video editors and digital marketers work on content posts, so their stand-up
shows each part with its post, not as a bare task. `helpdesk/standup_content.py`
(`ContentDay`), called by `autofill` **as the person**, so the calendar's walls apply:

- **Who:** anyone in the content team (`content_team.in_content_team`), when their
  department's switch is on (Settings → Stand-up, below). Outside the content team (ERP
  Employees included, whatever other role they hold) nothing is added.
- **Yesterday:**
  - their role parts completed that day: "Designer · Global Handwashing Day (Avera IoT)",
    *Done*;
  - the posts they published or moved on (the post's history): "Diwali offer (Avera IoT)",
    *Published* or *Moved to Design*. A move that came with their own finished part on the
    same post isn't listed again (finishing the part moves the post).
- **Today**, after the generic plan:
  - their open parts in the plan's order (overdue, due today, in progress, due on the next
    working day), worded as parts; when none of them is on the list, **the next part due**
    ("Next: due Fri 16 Oct");
  - the open posts they're on **going live today and tomorrow** (calendar days, as posts go
    out at weekends too): "Goes live today, 10:00 · Instagram, LinkedIn · Approved";
  - for the **Digital Marketing Head and DM Coordinators** (`CONTENT_LEAD_ROLES`), every
    post going live today that they may see, not only their own; one whose time already
    passed reads "Missed · was due …" (their own missed posts are blockers).
- **Blockers**, one line per post they're on, the most pressing reason only:
  1. **missed**: its time passed and it isn't published or cancelled (the board's
     `isMissed`): "Missed · was due Tue 13 Oct, 10:00";
  2. going live **within 24 hours without approval** (not Approved, Scheduled or
     Published): "Goes live Wed 14 Oct, 17:00, not approved yet (Client Review)";
  3. **Changes Requested**, with the head's or the client's note;
  4. **Client Review for more than N days**, N being HD Content Settings'
     `client_reminder_days` (2 when unset): "Waiting on the client's approval for 3 days";
  5. and their **parts waiting on someone else's part**: a part not started while the post
     waits on another part first (the Tasks view's `post_progress`, #131): "Waiting on
     Writer (Ajmal)". Such a part is a blocker, not today's plan.
- **Each task once:** a role task is also on My Work, so it would show as a plain task; it
  shows once, as its part with the post around it (the generic row is rewritten, never
  added twice).
- **Lines keep their post:** a content line stores `content_post`, `content_role`,
  `customer`, `go_live` and `stage` (HD Standup Item), which the page and the app get as
  `content` ({post, part, part_label, client, go_live, stage}). A part's line is still a
  Task line (opens the task dialog, with "Goes live …" under it); a post's line opens the
  post on the calendar. Like any linked row they can only be kept or removed.
- **Missed posts** are looked at for a week back (`MISSED_DAYS`); older ones are the
  board's to chase.

### Decisions (owner away, "no questions, recommended way")

- **Reuse, not a second rule:** missed is the board's rule, "waiting on" the Tasks view's
  `post_progress`, the part names `in_progress._role_label`, the channels
  `in_progress._platforms`, the team `role_teams_of`, the client wait the client reminder's
  setting. The only new number is the **24-hour** approval window the owner asked for (the
  board's amber "needs approval soon" stays 48 hours).
- **A new module, not `standup.py`:** the content rules sit in `standup_content.py`, which
  imports the stand-up's row helpers; `standup.py` imports it inside functions, so there's
  no import cycle.
- **Snapshots:** a stand-up keeps what was true when it was filled in (stage, go-live);
  the content calendar is where to see the post now.

## Editing (My stand-up)

`/helpdesk/standup` (route `Standup`, in the sidebar after In progress), mobile first with
44px targets:

- Three cards, Yesterday (titled "Last working day · Fri 9 Oct" when that wasn't yesterday),
  Today and Blockers, each with the filled-in rows and a remove button per row.
- Yesterday and Today take free text ("Anything else…"); a blocker is always **its own row**
  ("Add a blocker"), so the team can act on it.
- **I need help** (a checkbox), **Save draft** and **Submit stand-up** (the one primary
  action) in a bar that stays at the bottom on phones. After submitting it reads **Update
  stand-up**: today's stand-up stays editable all day (a late submit after the post changes
  the status to Submitted; the channel isn't posted again).
- **Linked rows can only be kept or removed** (`edited_rows`): the server takes them from the
  stored stand-up, so nobody can link work that isn't theirs. Text rows and notes are cleaned
  of HTML and capped (300 and 1000 characters).
- A reload (for example after changing a task opened from a row) keeps unsaved edits to the
  same stand-up; saving makes what was saved the new starting point, and edits typed while
  the save was on its way stay (the saved copy only becomes the baseline).
- Past days are read-only. The day is picked with the date field (kept in the URL as `date`).
- **Home** shows a card in the morning while today's stand-up is a draft: "Your stand-up is
  ready … it goes to your team at 10:30" with **Open stand-up** (`get_home().standup`,
  `standup.home_card`).

## The Teams summary (`compose_summary`)

One message per department, to its own channel (a Teams Workflows URL per department in
Settings → Stand-up), else the escalation channel of **Chat & Teams** (also for Slack, which
has no per-department channel here). Nothing is posted while chat is off. Markdown, as Teams
cards show it:

```
**Stand-up · ERP · Wed 14 Oct**

<2–3 lines from the AI, when it answers>

**Blockers and help needed (2)**
- Anu Varghese (needs help): [Customer GST file](…/projects/PROJ-0012): On hold 3 day(s): Waiting on customer
- Biju Thomas: Waiting for VPN access from Cochin Ship Supplies

**Content today (3)**            (departments with content work only)
- Missed: [Teachers' Day](…/content?post=…) · Avera IoT · was due Tue 13 Oct, 10:00 · Jasir
- Not approved: 17:00 [Flash sale](…) · Kerala Agro Foods · Instagram · Client Review · Ajmal
- 18:30 [World Food Day](…) · Kerala Agro Foods · Instagram, LinkedIn · Scheduled

**Anu Varghese**
Yesterday: [Configure GST settings](…) (Completed); [Sales invoice PDF …](…/tickets/4821) (Resolved) · 7h logged
Today: [Bank reconciliation](…) (Due today)

**Biju Thomas (auto)**
…

[Open the stand-up](…/helpdesk/standup?team=ERP&date=2026-10-14)
```

- **Blockers and help needed come first**, with names; someone who ticked "I need help"
  without a blocker is listed too.
- **Content today** comes next, for a department with content work (Digital, or one with
  Content Calendar projects or post tasks) whose switch is on: the posts going live that day
  that the department's people (those with a stand-up) are on, and their posts missed in
  the week before, **missed and not-approved first, with first names**; at most 8 lines
  ("and 2 more"). Every post of those eight days is read (no row cap), since the people
  filter runs after the query. Left out when there is nothing. It is composed whole (the summary goes to
  the department's own channel).
- Then each person: Yesterday and Today, at most 4 items each ("and 3 more"), plus their note.
- **The AI headline** goes through `ai_engine.call_haiku` (OpenAI first, with failover,
  [ai-providers.md](ai-providers.md)) with names, titles and counts only, never hours. The
  lines go through Home's `clean_steps`, which drops any line with a number that isn't in the
  facts (the Scoreboard's guard); fewer than two usable lines, an AI that isn't set up or a
  failed call means **no headline**, and the summary goes out without it.
- Titles are stripped of Markdown characters so a task name can't break the message.

## Team view (`/helpdesk/standup?team=…`)

- **Who:** admins (System Manager, Agent Manager) for every department (and "No department");
  per Settings → Stand-up, **department heads** for the ones they head, **project leads and
  coordinators** for the departments of the projects they lead or coordinate, and **project
  managers** (the role) for the departments of the projects they manage. Never a department
  the walls hide from them (an ERP Employee never leads Digital).
- **What leads get:**
  - counts: people, submitted, not submitted, blockers; who is on leave (names only);
  - **Blockers and help needed** in one list, each with **Assign help** (the agent picker
    from Home's Assign, with its own label), **Create task** and, for a task, **Comment**;
  - **Not submitted yet** with **Nudge** (a Reminder every time it is pressed: "Celine Joseph
    is waiting for your stand-up …");
  - **Everyone**: status, plan against done ("2 of 3 planned done · 1 more": the linked work
    on their previous stand-up's Today, how much of it is in today's Yesterday, and what else
    they did), hours as a fact when shown, Yesterday and Today side by side, and **History**.
- **Content today** (`components/ContentToday.vue`), under the blockers for departments with
  content work, for leads and members alike: each post's time (Geist Mono), title (opens the
  post on the calendar), client, channels and people, with a badge: **Missed** (red, alert
  icon, "Was due …"), **Not approved · Client Review** (amber, warning icon), **Published**
  (green, check) or the stage in gray. "Nothing goes live today and nothing was missed this
  week." when empty; **Open content calendar** in the card's header. Read as the viewer
  (`frappe.get_list`), so they only see posts they may open.
- **Assign help** (`assign_help`): the helper is told ("Celine Joseph asked you to help Anu
  Varghese: …"). When the blocker is a task the lead may change, the helper also joins its
  assignees (the department-wall ToDo hook still applies); a blocker in words, or a task the
  lead can't change (a department head outside the project), only notifies. The row
  remembers the helper ("Help asked of Reshma Nair").
- **Create task** (`create_task_from_blocker`): through tasky's `add_task`, so its rules
  apply (the lead must be able to add tasks to the project; assigning someone outside the
  team follows `_check_can_bring_in`). The description says whose stand-up it came from; the
  row remembers the task.
- **Comment** uses tasky's `add_task_comment` (anyone who can see the task may comment).
- **Plain members** see their own department's view read-only: the same content as the Teams
  channel, without plan against done, Nudge or actions. Any other department is refused.
- **Walls:** rows linked to a project in a department hidden from the viewer are left out of
  what they see (`walled_projects`), and someone outside the content team (an ERP Employee
  heading a mixed department) gets no content lines and no Content today
  (`content_today: null`).

## History

- The date field on the page shows any past day (My stand-up or Team).
- **History** tab: the viewer's own stand-ups, newest first (status, help asked, counts); a
  lead opens a teammate's from the team view (`?tab=history&person=…`), limited to the
  departments they lead.

## Settings → Stand-up

`desk/src/components/Settings/Standup/StandupSettings.vue`, System Managers and Agent
Managers (`helpdesk.api.standup.get_settings` / `save_settings`, which check the roles):

- **Enabled** in the header (off by default).
- **Times:** drafts open, reminder, summary posts (24-hour Data fields, in that order;
  Frappe fills a new document's Time fields with the current time, see follow-ups).
- **Show hours logged** (on).
- **Departments and channels:** the departments in the stand-up, each with its Teams channel
  workflow URL (a secret: masked once saved, sent only to replace or remove it, checked like
  Chat & Teams' URLs). None listed: everyone, posted to the escalation channel.
- **Team view:** department heads, project leads and coordinators, project managers (each on).
- **Content calendar:** "Include content calendar" per department, listed for every active
  department with content work (Digital, and the departments of Content Calendar projects
  and of projects with post tasks, `content_departments`), **on by default**. Off leaves
  the content lines out of that department's drafts (a stand-up already filled in keeps
  them) and Content today out of its summary and team view. Stored as the departments
  switched off (`content_off`), so a department that later gets content work starts on.

The patch `v16_0_2.seed_standup_settings` stores the defaults on existing sites.

## Who is in which department

`home_departments`: the department a person heads; else the one with most of their open
tasks (by the project's department); else one whose open projects they are on (in Settings →
Departments order); else none. It is stored on the stand-up when the draft is made, so history
keeps the department it was posted to.

## API

`helpdesk/api/standup.py` (agents only): `get_my_standup(date?)`, `save_standup(values)` POST,
`submit_standup(values?)` POST, `get_team_standup(team?, date?)`, `get_standup_history(user?,
limit?)`, `nudge(name)` POST, `assign_help(name, row, helper)` POST,
`create_task_from_blocker(name, row, project, subject, assigned_to?, due_date?)` POST,
`get_settings()` (with `content`: [{department, include}]), `save_settings(values)` POST
(`content_off`: the departments switched off).

`values`: `yesterday`, `today`, `blockers` (rows as returned; a row without
`reference_name` is text), `notes` {yesterday, today}, `needs_help`. A section left out is
kept as it is.

The TBO Smart app gets `get_my_standup`, `save_standup`, `submit_standup` and
`get_team_standup` in `helpdesk.api.mobile`, each row with `app_route` and `content`, and the
team view with `content_today` ([tbo-smart-api.md](tbo-smart-api.md#stand-up)).

## Data

- **HD Standup**: user, full_name, date, department, status (Draft, Submitted, Auto-posted),
  submitted_on, needs_help, hours, yesterday / today / blockers (HD Standup Item),
  yesterday_note, today_note. System Manager full, Agent Manager read; written through the
  API only.
- **HD Standup Item**: kind (task, ticket, post, plan, note), title, detail,
  reference_doctype, reference_name, project, auto, helper, help_task; on content lines
  content_post, content_role, customer, go_live, stage.
- **HD Standup Settings** (Single) with **HD Standup Department** rows (department,
  channel_webhook) and `content_off` (Table MultiSelect of **HD Standup Content Off**,
  department): the departments without the content calendar.

## Files

- Engine `helpdesk/standup.py`, content `helpdesk/standup_content.py`; API
  `helpdesk/api/standup.py`; mobile in
  `helpdesk/api/mobile.py`; `WorkCalendar.previous_working_day` in `helpdesk/follow_ups.py`;
  `chat_notifications.teams_post_url` (a channel's own URL).
- UI `desk/src/pages/standup/` (`Standup.vue`, `MyStandup.vue`, `TeamStandup.vue`,
  `StandupItems.vue`, `BlockerDialog.vue`, `StandupHistory.vue`, `ContentToday.vue`,
  `standupMeta.ts`),
  `pages/home/components/StandupCard.vue`, `components/Settings/Standup/StandupSettings.vue`;
  `AssignPicker.vue` gained `label` and `touch`.
- Tests `helpdesk/tests/test_standup.py` and `test_standup_content.py`; helpers in
  `helpdesk/test_utils.py` (`set_standup_settings`, `standup_calendar`, `make_standup`,
  `get_standup_notices`, `make_content_post_at`, `log_post_move`, `complete_task_on`).

## After deploy (owner)

1. Settings → Stand-up: check the times, add the departments in the stand-up with each
   one's Teams channel workflow URL (Teams template "Post to a channel when a webhook request
   is received"), choose who gets the team view, then switch it **on**.
2. Settings → Chat & Teams must be on, with the Direct Message workflow (for the "ready" and
   reminder messages) and the escalation channel (the fallback for departments without one).
3. Settings → Departments: set each department's heads, and give projects a department.
4. Optional: AI providers set up for the headline (the summary works without it).
5. Content calendar: on for every department with content work. Switch it off per
   department in Settings → Stand-up → Content calendar if a team doesn't want it. Give
   content projects a department (Digital) so the right summary carries Content today, and
   check HD Content Settings' client reminder days (the stand-up's "waiting on the client"
   threshold).
