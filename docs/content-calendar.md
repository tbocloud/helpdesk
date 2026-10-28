# Content calendar

The content calendar (`/helpdesk/content`, route `ContentCalendar`) is where the content team
plans, staffs and ships social posts (`HD Content Post`) for customers.

- Page: `desk/src/pages/content/ContentCalendar.vue`, with its views and dialogs in
  `desk/src/pages/content/components/` and shared types and rules in
  `desk/src/pages/content/constants.ts`.
- Data: posts come from `frappe.client.get_list` on `HD Content Post`, so everyone only sees
  posts they can read. The team on each card comes from
  `helpdesk.api.content_board.get_team_task_status`, occasions from
  `helpdesk.api.content_board.get_occasions`. Every number on the page is worked out in the
  browser from the posts loaded for the period and filters on screen; there is no separate
  stats call. The role tasks of the posts on screen come from one call,
  `helpdesk.api.content_tasks.get_content_tasks`, which feeds the Tasks view, the "Your tasks"
  strip, the role boxes' Start / Pause / Complete and each card's parts line (see
  [Tasks view](#tasks-view)).
- Posts in production (Drafting to Approved, not yet published) also show on the **In
  progress** page, next to the started tasks of every project, with the part each post waits
  on and who has it; see [workspace-pages.md](workspace-pages.md#in-progress-in-progress).

## Filters and navigation

The filter bar (customer, channel, status, person, **My posts**, Clear) applies to every view.
The person filter (and My posts) also matches the "More people" table (`HD Content Post Member`),
which joins it to the query, so the post lists sort on `` `tabHD Content Post`.`publish_on` `` /
`` `creation` ``: a bare `creation` is ambiguous with the joined table and failed with an Internal
Server Error (owner's report, 2026-10-14).
Cancelled posts are hidden unless the status filter asks for them; the Board and Sheet views
load them and show them behind their own chip. In the Tasks view the person filter keeps the
tasks assigned to that person, and **My posts** reads **My tasks**.

Board, Sheet and Tasks have a **Day / Week / Month** period switch, Today, previous/next (← / →,
T for today) and a date picker. The Calendar view has its own navigation.

- **Today always works** (owner's feedback, 2026-10-14: "the Today button is not working
  sometimes"). The button is filled in the brand teal while the day, week or month on screen holds
  today (`showingToday`, `aria-pressed`), like the selected Day / Week / Month option, and
  gray otherwise (owner's choice, 2026-10-14). It works in both states. It moves to today's day, week or month and, when that period is already on
  screen, scrolls to today's posts (`day-<date>`) or the today marker (`goToday`). It used to
  be disabled whenever today was inside the period on screen, so in Week or Month view it did
  nothing.
- **Today stays current:** the date pages read it from `useToday()`
  (`desk/src/composables/today.ts`, checked every minute), so a page left open overnight or
  over a weekend moves on to the new day; it used to keep the day the page was opened, and
  Today then jumped to that old day and the strip ringed the wrong one.

## Views

| View | What it is |
| --- | --- |
| **Board** (default) | Stat tiles, a progress bar and a day-grouped list of entry cards for the period. Follows the owner's mockup in the TBO light theme. |
| **Calendar** | frappe-ui month/week calendar. Drag a post to reschedule it; click an empty cell to add an entry. |
| **Sheet** | A table of the period's posts. |
| **Tasks** | The period's role tasks as a work queue by stage, worked in place. See [Tasks view](#tasks-view). |

The chosen view and period are remembered per browser.

## Board view

`desk/src/pages/content/components/ContentBoard.vue`.

### Occasions strip

Above the board (Board and Sheet): festivals and national days in the period, from
`HD Content Occasion` for the regions in the customer's package. Each chip shows the date and
name; clicking it opens Add entry on that date.

### Stat tiles

| Tile | Value | Line below | Tint |
| --- | --- | --- | --- |
| Month progress (Day/Week progress) | Published ÷ planned, as % and a ring. Planned = posts in the period that aren't cancelled. | "X of Y published" | Neutral; the ring is green (success). |
| On-time rate | Published on or before their planned day ÷ published. "—" when nothing is published. | "X of Y on the planned day" | Same thresholds as the delivery report: green ≥ 95%, amber ≥ 80%, red below, neutral when nothing is published. |
| Postponed | Posts in the period postponed at least once (`times_postponed > 0`). | "this month", plus "N moves" when some were postponed more than once. | Amber when above 0, otherwise neutral. |
| Next post | Date and time of the next post that isn't published or cancelled and hasn't passed yet. | Title · platforms | Info (blue) when there is one, neutral otherwise. |

A post postponed out of the period counts in the period it now sits in.

### Progress bar and chips

A segmented bar (no gradient) with a legend: **Published on time** (green), **Published late**
(amber, published after the planned day, the same rule as the delivery report), **Missed**
(red, past its time and not published or cancelled), **Upcoming** (blue). Cancelled posts are
left out. Segments with nothing in them are hidden.

The chips below filter the list: All, Missed, Upcoming, Published, Cancelled, each with its
count; empty ones are hidden unless selected. A red banner offers "Show them" when posts are
missed. **Upcoming** is only posts that aren't published or cancelled and haven't passed their
time, so it already lists today onward, in date order.

### Opening on today (owner's feedback, 2026-10-12)

The month list starts on the 1st, so on the 12th the team landed on past days and the posts
for the 15th and 20th sat below the fold. The board now opens on what's next. The rules are
pure functions in `desk/src/pages/content/dayFocus.ts` (`planDays`, `firstFromToday`); the
frontend has no test runner, so they were checked with a scratch Node script.

- **Coming up strip** (Week and Month, between the banner and the chips): the next 7 upcoming
  posts as small cards: date and time ("Today" for today), status pill, client · copy. Pressing
  one scrolls to its entry, outlines it in `brand` for 2 seconds and focuses its copy button
  (switching the filter back to All if the entry was filtered out). **View all upcoming** (with
  the count) turns on the Upcoming chip. Cards are 44px tall and the strip scrolls sideways
  inside itself on phones.
- **Earlier this month / week:** with the All chip, past days fold into one row ("Earlier this
  month · N entries · published or cancelled", **Show** / **Hide**). A past day with a missed
  post stays listed, because the "needs action" banner points at it. Nothing folds when no day
  is today or later (a past month, or a month with nothing left), with Missed, Published or
  Cancelled on, or in Day view.
- **Today marker:** when today is in the period and has no posts (All or Upcoming), a slim row
  sits where today would be: "Today: nothing scheduled · Next: Thu 15 Oct" (or "Nothing else
  this month"), with the orange today ring.
- **Scroll on open:** once per period, after the posts load, the list scrolls to today, else the
  marker, else the next day with entries, but only when that is in the lower 40% of the screen
  or below (`revealIfLow`), so it doesn't jump away from the summary when today is already in
  view. Reloads after an action don't scroll again.
- **Sheet:** opens on the first row from today on, by the same rule. It lists every row, so
  nothing folds.
- **Calendar:** unaffected; the month grid shows every day at once.

### Entry cards

Grouped by day (day number, weekday, number of entries that day), sorted by time. On wider
screens the day's date column stays pinned at the top of the list while its cards scroll past.

- **Header:** a building tile, then the client in a larger semibold font (always shown, even
  with the customer filter set); below it the copy, labelled **Copy:** like the Sub copy box (owner's request,
  2026-10-14: people didn't know what it was; the post's `title`, opens the post) and the
  post type as a tinted tag (brand-soft, its `PostTypeIcon` and name, 28px tall; owner's request,
  2026-10-14: "catchy and attractive"). On the right: the platforms (brand mark + name, from `ChannelIcon.vue`, coloured with
  the `--channel-*` tokens), the time, the status pill (`StatusPill.vue` at `size="md"`), and a
  round button that opens the post, the same as clicking the copy: a pencil ("Edit …") for
  people who can edit content (`auth.canEditContent`), a paperclip ("Open … to add files") for
  everyone else.
- **Warning line** "Goes live within 2 days and isn't approved yet." when the post isn't
  Approved/Scheduled/Published and goes live within 48 hours.
- **Sub Copy** (`caption`) and **Description** (`brief`) side by side in white boxes ("Not
  written yet" / "No description yet" when empty).
- **Roles** (`RoleBox.vue`): Writer, Designer, Video editor, Digital marketer. Each assigned
  person shows with a role-coloured initial tile, their name and task status (and "late" when
  the task is past due); an empty role shows a dashed **+ Assign** box in the card's tone,
  which opens the assign dialog. People who can't edit content see **Not assigned** instead.
  On a **published** post the role boxes are read-only (`readonly`): they still show who did
  each part and their task status, but there is no + Assign, change, task step or open-task
  button, and an empty role just says **Not assigned**. The progress line is hidden: the work
  is done, so there is nothing left to assign or chase (owner's decision, 2026-10-14).
  - **Open the task in place** (owner's feedback, 2026-10-12: "to know what that task is we
    have to go back into the project"): pressing the people in a filled box opens the role's
    linked Task (`task` from `get_team_task_status`, already in the payload, so no API change)
    in the shared task dialog (`TaskDetailDialog.vue`), without leaving the page: subject,
    status, due date, timer, hold note, description and activity, with the same actions as
    everywhere else. `mine` is set when the viewer is one of the role's people, so the
    assignee gets Complete, hold/resume, help and hand-over; the project's manager, lead or
    coordinator get theirs from the project. **Open project board** in the dialog goes to the
    full project view. A task change reloads the posts (`changed`). A clipboard icon marks the
    button, whose accessible name is "Open Designer task for Avera IoT · World Mental Health
    Day" (the names and statuses stay as its description). Everyone who can see the board can
    open it; the server decides what the task shows.
  - **Change who is on it:** editors get a separate small person-pen button (32px, 44px to
    press), "Change who is on Designer · …", which opens the assign dialog as the whole box
    used to. A role with people but no task (e.g. the customer has no project yet) shows the
    people as plain text, plus the Change button for editors.
  - The buttons are native `<button>`s, not `<component :is="'button'">`, which resolves to
    frappe-ui's global `Button` and clipped the names to its fixed height.
  - **The assignee's one step** (owner's request, 2026-10-12): when the viewer is assigned
    the role's task, the box shows one small primary button, picked by the task's state:
    **Start** an open task (`move_task` to In progress, which starts the timer), **Pause** a
    running timer (`stop_timer`), **Complete** a task in progress with its timer paused (the
    task dialog's Complete step, so hours and review rules apply). Its name says whose
    ("Pause: Designer · Avera IoT · Global Handwashing Day"); 32px, 44px to press. It comes
    from the task's `actions` in `get_content_tasks` (`boxStep` in `contentTasks.ts`), so it
    only shows when the server allows the step. Resuming a paused timer and holding are on
    the Tasks view's card and in the task dialog; the open-task and Change buttons stay.
  - Each person's task status shows with its icon as well as its text (`taskStatusMeta`),
    never colour alone.
- **Parts line:** under the roles, "3 of 4 parts done · waiting on Writer (Ajmal), due
  tomorrow" (or "waiting on the client's approval"), from the post's `progress` in
  `get_content_tasks` (see [Who a post waits on](#who-a-post-waits-on)). A late part reads
  "2 days late" in red with an alert icon. Hidden on published and cancelled posts and on
  posts with nobody on them.
- **Footer:** "Goes live …" (or the published / missed / cancelled line), then **Mark
  published** (primary), **Postpone**, and a cancel icon button, all through
  `EntryActionDialog.vue`. Published posts link to the live post instead.

This is the owner's mockup design, so the cards carry a tint (an exception to the neutral-card
rule in [ui-guidelines.md](ui-guidelines.md)). The tint always comes with text that says the
same thing:

| Tint | When |
| --- | --- |
| Red (danger) | Missed, or going live within 2 days without approval |
| Green (success) | Published |
| Neutral gray | Cancelled |
| Blue (info) | Anything else still upcoming |

## Tasks view

Owner's request (2026-10-12): writers, designers, video editors and digital marketers do their
work as Tasks, but had to leave the calendar for Projects to work them. The **Tasks** view
(`components/ContentTasks.vue`, cards in `components/ContentTaskCard.vue`, shared logic in
`contentTasks.ts`) shows the role tasks of the posts going live in the period and filters on
screen as a work queue, and every step is taken in place.

### Data: `helpdesk.api.content_tasks.get_content_tasks`

`get_content_tasks(start, end, customer?, channel?, status?, person?)`, dates inclusive, at
most 62 days (a calendar month grid shows six weeks). One call for the Tasks view, the strip,
the role boxes' step and the cards' parts line; the page loads it for the period on screen (the
Calendar view's grid range in Calendar view) and doesn't pass `person`, which it applies in
the browser, so one answer serves every part.

- **Who gets what** (all on the server):
  - Outside the content team (`in_content_team`, so ERP Employees too, whatever other role
    they hold) the call is refused with a PermissionError: the calendar is opt-in.
  - Posts come through `frappe.get_list` on HD Content Post (the calendar's own rule), with the
    calendar's filters: customer, a platform (`platforms` like the channel) and status;
    Cancelled posts are left out unless the status asks for them.
  - Tasks come through `frappe.get_list` on Task (`content_post` in those posts, a
    `content_role` set, not Cancelled or Template), so [the #94 rule](workspace-pages.md#who-sees-which-tasks)
    decides: writers, designers and marketers get their own tasks (assigned to them, given out
    or created by them); the Digital Marketing Head and DM Coordinators get every task of
    content calendar and Digital projects; a project's managers, lead and coordinators get
    their project's. `sees_all` is `_is_content_lead` (heads, coordinators, Project Managers,
    admins) and only words the page. `person` keeps the tasks assigned to that person
    (`assigned_to_filter`, exact ToDo match).
  - The newest task per post and part counts, as on the role boxes.
- **No per-row queries:** posts, teams (`role_teams_of`), every part's task (`role_tasks`),
  the visible tasks, open dependencies, holders' names, people's names and project names are
  one query each; whether the viewer runs a task's project (`can_coordinate_project`) is
  asked once per project.
- **Answer:** `{sees_all, can_edit, tasks, counts {todo, in_progress, review, on_hold,
  done}, posts {name: post}, truncated}`. 1,000 posts and 1,000 tasks at most (`truncated`).
  - A task: `name`, `subject`, `status`, `stage`, `review_label`, `role` (the post's field, or
    null for the one task shared by the whole post, `role_label` "Whole post"), `role_label`,
    `post`, `publish_on`, `project`, `project_name`, `assignees`, `assignee_names`, `mine`,
    `due`, `is_overdue` (the hub's rule, `is_task_overdue`), `hold_reason`, `hold_note`,
    `hold_by_name`, `hold_days`, `custom_timer_start`, `custom_timer_elapsed`,
    `estimated_hours`, `escalation_level`, `waiting_on` (the open task it depends on) and
    `actions`. Sorted by stage, overdue first, then due date.
  - A post: the calendar's fields (title, customer, status, publish_on, channel, platforms,
    format, special_day, the four role fields and their hours, so Reassign can open the assign
    dialog), `is_missed`, and `progress` (below). Every post in the period is answered,
    whatever `person` is, so every board card gets its line.

### Stages

`task_stage(status, post_status, running)`:

| Column | Tasks |
| --- | --- |
| **To do** | Open (or the old Overdue status), not started |
| **In progress** | Working, timer running or paused |
| **In review** | Pending Review ("Waiting on the lead's review"), or **not started while the post sits in Internal Review, Client Review or Head Review**: that part waits on the review, not on its person ("Waiting on the client's approval") |
| **On hold** | On Hold, with the reason, note and who held it |
| **Done** | Completed, in the period. Folded by default ("Done in October 2026 · 6 tasks", Show / Hide) and folded again when the period changes |

A task someone has started stays In progress even while its post is in a review stage.

### Who a post waits on

`post_progress` gives each post `{parts, done, waiting_on}`. `parts` counts the roles with
someone on them and `done` those whose task is Completed (the role's task as the role boxes
pick it, `task_for_role`). `waiting_on` is, in order:

1. nothing once the post is published or cancelled;
2. `{kind: "review", label}` in Internal Review, Client Review or Head Review (`waiting_review`:
   "internal review", "the client's approval", "the Digital Marketing Head's approval");
3. the first part the post's stage waits on and isn't finished (the In progress page's rule,
   `_pending_parts`: the writer while drafting, the designer and video editor in design, the
   marketer once approved; on Changes Requested every creative part again);
4. else the first staffed part, in role order, whose task isn't done.

A part is `{kind: "part", role, label, people [{user, full_name}], task, task_status, due}`
(`in_progress.part_item`). Like the role boxes, this reads every part's task whatever the
viewer's Task access, so a member sees how their teammates' parts stand; only the status and
due date leave the server.

### Cards

Each card (`ContentTaskCard.vue`): the role chip (the role boxes' colours, `ROLE_TONES` in
`constants.ts`, always with the role's name), the due chip ("Due tomorrow", "Due Thu 15 Oct";
red with an alert icon when the task is overdue, "Past its estimate" when it's due today and
worked past its estimate, or its post was missed), the post's copy, the customer and the
platform icons (named for screen readers), "Goes live Thu 15 Oct, 10:00 AM" (red "Missed · was
due …" once the post passed its time unpublished, `is_missed`), one line saying what it waits on
(the review, the task it depends on, or "The post is waiting on Writer (Ajmal)" for a part not
started while another comes first), the hold badge and `HoldNote`, the people (avatar and name,
"You" for the viewer), and the timer as on In progress (`taskTimer`, `formatElapsed`, a
`TaskyBadge`: tracking in info blue, paused neutral; the list ticks every 30 seconds).

- **Pressing the card** (its title button stretches over it) opens `TaskDetailDialog` in place,
  `mine` for the assignee, so every step the viewer may take is there.
- **Steps on the card**, only those in the task's `actions` (`task_actions`, which follows the
  task APIs' rules):
  - the assignee: **Start** an open task (`move_task` to Working); while it's in progress a
    **Pause** / **Resume timer** icon button (`stop_timer` / `start_timer`) next to
    **Complete**; **Resume** a held task; **Put on hold** in the menu. Complete, Put on hold
    and Resume open the task dialog straight on that step (`TaskDetailDialog` `action`), so
    hours, notes, review-before-done and the hold reasons are the existing flows. A task
    waiting on another can't start or complete, as the server refuses both;
  - whoever runs the task's project (`can_coordinate_project`): Put on hold, Resume, and
    **Approve** a task in review (`useApproveTask`, with its rating offer);
  - content editors (`can_edit_content`): **Reassign**, the role's assign dialog
    (`EntryActionDialog`, `content_board.assign`). Not offered on a whole-post task or a
    finished one;
  - everyone: **Open task** and **View post** (opens the post dialog) in the "More" menu.
  No step adds a new mutation path: they are the task APIs the boards already use.
- Buttons are 32px with a 44px press area, and the card's buttons sit above its title button.

### Layout and states

- **Desktop** (`lg` up): four columns side by side, To do, In progress, In review, On hold,
  each with its icon (`taskStatusMeta`) and count, an empty column saying so ("Nothing on
  hold"); Done folded below. **Phones and tablets:** one stage at a time, picked with
  frappe-ui `TabButtons` (with counts), opening on the first stage with work in it.
- **Defaults:** the view opens on **My tasks** (the person filter set to the viewer) for
  content people who don't lead the team, and on **Everyone** for heads, coordinators and
  admins (`canEditContent` or `isDmHead`). The person filter switches between them; a filter
  the view set by itself is dropped again when the viewer leaves the view, so the Board isn't
  left on "My posts".
- **States:** skeleton columns while loading; an error with "Try again"; "Nothing on your
  plate" when the viewer has no tasks in the period (with "Show everyone's tasks" for leads);
  "No content tasks in October 2026" when the period has none; "No tasks match these filters"
  with Clear filters when the person filter hides them all; and "Nothing on your plate:
  everything in October 2026 is done" above Done when only finished work is left.
- **Live:** the page reloads the call on Task `list_update` (`useListUpdate`, debounced), so
  a teammate starting, pausing or finishing a task shows without a reload, and after every
  step taken on the page.

### "Your tasks" strip

`components/YourTasksStrip.vue`, one line at the top of the Board, Calendar and Sheet views,
above the scrolling list so it stays in view: "Your tasks: 2 to do · 2 in progress · 1 on hold
· ⚠ 1 overdue · next: Designer · Festive offer reel, 5 days late". It counts the viewer's own
open tasks (`mine`, not Done) in the period on screen, whatever the person filter; overdue is
red with an icon; next is the soonest-due task to do or in progress. Pressing it (44px on
phones) opens the Tasks view filtered to the viewer. It is hidden when they have no open
tasks in the period, and the whole page is only for the content team.

### Decisions (owner away, "do the recommended way")

- **A new module, not `content_board`:** `content_tasks.py` reuses the In progress page's
  part rules (`_pending_parts`, `part_item`) and `in_progress` already imports
  `content_board`, so adding it there would have made a circular import.
- **One call, filtered in the browser by person:** the strip and the cards' lines need the
  viewer's tasks and every post whatever the person filter, so the page loads the period once
  and the Tasks view narrows by person locally. The app can pass `person`.
- **The period on screen, not all open work:** the strip and the view follow the period and
  filters like the rest of the page, so the numbers always match what's on screen; an overdue
  task of a post in an earlier month shows when that month is on screen (and on My Work).
- **A not-started part of a post in review is "In review":** it waits on the review, not on
  its person, and that's what the owner asked the column to show.
- **The role box's step is Start, Pause or Complete only:** as asked; a paused timer offers
  Complete there, and Resume timer lives on the Tasks card, one click away through the strip.
- **Refused outside the content team** rather than an empty answer, as the calendar's other
  calls (`get_content_performance`) do; the page itself is never shown to them.

## In the daily stand-up

The async stand-up ([standup.md](standup.md#content-calendar)) carries the content work of
the content team (`helpdesk/standup_content.py`), read as each person so these walls apply:

- **Their stand-up:** the role parts they finished yesterday ("Designer · Global Handwashing
  Day (Avera IoT)", Done) and the posts they published or moved on; today their open parts
  (else the next one due) and the posts they're on going live today and tomorrow, with time,
  channels and status (the Digital Marketing Head and DM Coordinators also every post going
  live today); blockers for missed posts, posts going live within 24 hours without approval,
  Changes Requested, Client Review longer than `client_reminder_days`, and parts waiting on
  someone else's part (`post_progress`, "Waiting on Writer (Ajmal)"). A role task shows once,
  as its part.
- **The department's summary and team view:** a **Content today** block after the blockers:
  the posts going live that day and the ones missed in the week before, missed and
  not-approved first, with names.
- **Settings → Stand-up → Content calendar:** "Include content calendar" per department, on
  by default for Digital and every department with Content Calendar projects or post tasks.
- Post lines open the post here (`/content?post=…`); part lines open the task.

## Adding and editing a post

**Add entry** (`AddEntryDialog.vue`) creates posts through
`helpdesk.api.content_board.add_entries`; clicking a post opens `PostDialog.vue`. Both use the
same labels and fields:

| Label | Field | Notes |
| --- | --- | --- |
| Copy | `title` | Optional (owner's request, 2026-10-24). Without it the post is named by its post type, then its ID: `label` on the controller, `copyOf()` in `pages/content/constants.ts`, also in task names, reminders and the client approval. |
| Campaign (optional) | `campaign` | Free text (Data), e.g. "Diwali 2026". |
| Special day (optional) | `special_day` | Free text, e.g. "Diwali". Highlights the post on the calendar (see below). |
| Platforms | `platforms`, `channel` | Chips; one post can go out on several. The first is `channel`. |
| Post type | `format` | Chips, one per post. |
| Sub Copy | `caption` | The post's text; Draft with AI fills it. In the post dialog the caption box sits right under the Sub Copy label, and the **Brief for AI** box (what to tell the AI, never saved) comes after it with its own label: it used to sit first, looked like the Sub Copy, and text typed there was lost on save (owner's report, 2026-10-14). |
| Description | `brief` | For the creative team; never shown to the client. |
| Writer / Designer / Video editor / Digital marketer | role fields + `extra_team` | Several people per role. |
| Est. hours (next to each role) | `writer_hours`, `designer_hours`, `video_editor_hours`, `marketer_hours` | Optional; see below. |

The Desk form uses the same labels (Copy, Sub Copy, Description).

### Campaign is free text

`campaign` used to link to `HD Content Campaign`; it is now a plain Data field, because the team
names campaigns as they go. The patch `content_campaign_as_text` replaced the stored campaign IDs
with the campaign names. With the link gone, a post's tasks always go to the customer's open
project (see below), the customer is never filled in from a campaign, and Draft with AI
passes the campaign text as "Campaign: …". The `HD Content Campaign` doctype itself is unchanged.

### What the task says

A content task's description carries the post's **Copy**, **Sub copy** and **Description**
(`HDContentPost.task_description`), so whoever does the work has the text without opening the
post (owner's request, 2026-10-24). Each part is left out when empty. When the post's copy, sub
copy or description changes, its open tasks get the new text (`refreshes_description`), unless
someone has written the task's description by hand; then it stays.

### When the tasks are due

Each role's task is due on the publish date minus that role's lead time in Content Settings
(`writer_days_before`, `designer_days_before`, `video_editor_days_before`; the digital
marketer's is always 0, so it's due on the publish date). "One task for the post" uses the
designer's. In `wanted_tasks` (`due()`):

- **A lead time that has already passed makes the task due today**, not on a past date: a post
  publishing tomorrow with a 3-day writer lead time gives the writer a task due today, so it
  isn't overdue the moment it's made.
- **Never after the publish date:** a post whose publish date has passed (a missed post) keeps
  its publish date as the due date.
- **The date is set once** when the task is made, and moves only when the post moves to
  another **day** (Postpone or editing the date), with the same rules (`plan_task`,
  `redates`). Other saves, and a new time on the same day, leave it alone: recalculating
  would push a late task's date to today and hide that it's late. A task that is already
  late only moves when the post moves to a **later** day; bringing the post earlier keeps it
  late. A change to the lead times in Content Settings applies to new tasks and to posts moved
  to another day.
- **A part reopened by hand** (cancelled or completed, then reopened in Tasky) keeps the date
  it had; whoever reopens it sets a new one if the post has moved since.

When a task counts as overdue (past its date, or due today and past its estimated hours) is
described in [workspace-pages.md](workspace-pages.md#when-a-task-is-overdue), and who hears
about it in [follow-ups.md](follow-ups.md).

### Setting a task's due date when assigning

The Assign dialog (`EntryActionDialog.vue`) has a **Due date** beside the people and hours
(owner's request, 2026-10-24). It starts at the role's task date, or, before the role has a
task, the date it would get (`get_role_due`; `HDContentPost.role_due`, from the days before in
Content Settings; the shared task follows the designer's). Saving passes `due` to `assign`,
which sets it on the role's open task (`set_role_due`). Any date can be picked (owner's
request, 2026-10-26): a date after the post goes live, or one already past, is only pointed out
under the field, not refused. An unchanged date is left alone.
Postponing the post to a later day moves the task's date again, as before.

### Which project the tasks go to

A post's tasks go to **one of the customer's open projects, of any type**
(`content_project_for(customer)` in `hd_content_post.py`). When the customer has several, a
project with Project type "Content Calendar" wins, then the most recently changed one. The
owner's decision (2026-10-11): the project's customer is what links it, not its type.

The project's customer is matched on `customer` and, where the field exists, `hd_customer`
("Helpdesk Customer", `project_customer_fields()`). On sites with ERPNext, `Project.customer`
links to ERPNext's Customer while posts use the HD Customer. Some of those sites (tboindia)
keep the HD Customer in an `hd_customer` Custom Field that was added by hand; this app doesn't
create it, it only uses it when it's there.

- **No project, no tasks:** while the customer has no open project, a save that **adds people**
  (a new post with people on it, a role that gets its first person, or tasks turned on by the
  task mode) or **moves a post with open tasks to that customer** is refused
  (`require_content_project`, `adds_tasks`, `moves_tasks`): "The customer *Y* has no open
  project, so new tasks for this entry can't be created. Set *Y* as the customer on a project
  first." (`missing_content_project_message`). Saves that add nobody go through, so finishing
  a task, client and ERP approvals and edits to older posts never fail on it, even when a role
  is missing its task.
- **Background jobs aren't refused:** the spreadsheet import (`content_calendar_import`) and
  monthly package planning (`HDContentPackage.make_post`) set `flags.tasks_join_project_later`,
  so their posts and tasks are still made; the tasks join the customer's project once it has
  one (below).
- **The dialogs say where:** under Customer, Add entry and the post dialog show "Tasks go to
  *project*" (a link, opening in a new tab), or the same message as a warning before saving
  (`ContentProjectNote.vue`, `content_board.get_content_project`, which returns
  `{name, project_name}` or `{name: null, missing}`). Someone who can read posts but can't open
  the project gets `{name: null, hidden: true}` and sees "Tasks go to this customer's project",
  without its name or link. The note drops an answer for a customer
  picked earlier and checks again when the window gets focus, since the project is often fixed
  in the tab its link opens.
- **Missing projects are filled in later.** Saving a post gives its open tasks without a
  project the customer's project (`plan_task`). Saving an open project that is the one a
  customer's tasks go to moves that customer's open content tasks without a project into it
  (`attach_content_tasks`, a Project `on_update` doc event, so it runs whichever controller
  the site's Project uses). Each task is saved through the Task controller, so the project's
  rollups follow; one that can't be saved is logged and left for the next save.
- **A new customer moves the tasks:** changing a post's customer moves its open tasks to the
  new customer's project. Otherwise a project set on a task by hand stays.

### Platforms and post types the team adds

Platforms (`HD Content Platform`) and post types (`HD Content Post Type`) are records, not
fixed Select options. `channel` on the post and on monthly plan items links to
`HD Content Platform`; `format` links to `HD Content Post Type`. Every site gets today's options
(Instagram, Facebook, LinkedIn, X, YouTube, Blog, Email, WhatsApp; Post, Carousel, Reel, Story,
Video, Article, Newsletter) on install and through the patch `seed_content_options`
(`helpdesk/content_options.py`).

- Both dialogs end each chip row with **+ Add platform** / **+ Add post type**: type a name and
  press Enter. The new option is saved, selected, and offered everywhere (dialogs, the channel
  filter, monthly plans). Typing an existing name, in any case, just selects it.
- Anyone with the Agent or Content Team role can add options; renaming, reordering
  (`sort_order`) and deleting is for managers, from the Desk lists.
- `platforms` on a post keeps only names that exist as platforms.
- Draft with AI has writing guidelines for the default platforms and post types; for ones the
  team added it writes for the platform by name.
- The chips carry icons: each platform its brand mark in its `--channel-*` colour
  (`ChannelIcon.vue`), each post type a Lucide icon (`PostTypeIcon.vue`). Options the team
  added get a generic icon (a globe for platforms, shapes for post types) in gray.

### Special days

A post with a **Special day** (`special_day`, e.g. "Diwali", "Brand anniversary") is highlighted
everywhere it shows, always as a star plus the day's name (`SpecialDayBadge.vue`, amber):

- **Board:** a badge under the card's post type line, and the day heading lists that day's
  special days.
- **Day strip:** a star next to the day's count (the tooltip and screen-reader label name it).
- **Calendar view:** the event title starts with "★ Diwali ·".
- **Sheet:** a badge next to the copy.

Clicking an occasion chip (festivals from `HD Content Occasion`) opens Add entry on that date
with the occasion already filled in as the special day. Add entry sends it through
`add_entries`, so every post it creates carries it.

### Estimated hours per role

Each role has an optional hours estimate. It goes on that role's task as
`custom_estimated_hours` (the field the workload and timesheet reports add up) when the task is
created, and is updated when the post's hours change. With **One task for the post**, the shared
task gets the sum of all roles' hours. A role with no hours leaves the task's own estimate (for
example the AI estimate) alone; clearing a role's hours that were set (`hours_cleared`) sets its
task's estimate to 0 so the two agree. "Save and add next" keeps the hours with the team.

The **Assign** dialog on a board card (`EntryActionDialog.vue`) has the same Est. hours box next
to the people, filled with the role's current hours; saving sends them to
`helpdesk.api.content_board.assign` (`hours`), and clearing the box sets the role to 0.

## Who sees the content calendar

Only the **content team** sees it (opt-in). Everyone else, such as ERP consultants,
developers and functional consultants, doesn't, without needing any role for it.

| In the content team (`content_team.in_content_team()`) | Why |
| --- | --- |
| System Manager, Agent Manager, Project Manager, DM Coordinator (`CONTENT_EDITOR_ROLES`) | They edit content (`can_edit_content`) |
| Digital Marketing Head, DM Employee, Content Team (`CONTENT_CALENDAR_ROLES`) | Content calendar roles |
| Administrator | Always |

Holding **ERP Employee** keeps someone out even with a content role, unless they also edit
content: the ERP wall from [departments.md](departments.md) is unchanged.

For everyone outside the content team:

- **Screens:** the sidebar hides **Content** and **Performance** (the Performance page is the
  content delivery report), and the router sends `ContentCalendar`, `ContentReport`,
  `ContentPlans` and `Performance` to Home (`CONTENT_ROUTES` in
  `desk/src/pages/content/contentTeam.ts`, `authStore.inContentTeam` from the `in_content_team`
  flag in `helpdesk.api.auth.get_user`). The work **Calendar** stays: it shows their own Teams
  meetings and due tasks, not content. It stays hidden from ERP Employees, as before.
- **Posts:** the HD Content Post `permission_query` returns none and `has_permission` refuses,
  even for a member of the client's project.
- **Content performance:** `content_performance.get_content_performance` and
  `get_customer_performance` refuse them. The Scoreboard still shows every department's
  numbers, Digital and content included, to everyone.
- **A content task given to them** (say a developer asked for a website banner) stays theirs:
  `task_query` and `task_has_permission` leave out a post's tasks (`Task.content_post` set)
  unless they're the person's own (assigned to them, given out by them or created by them, as
  `is_own_task`). They work on that task from My Work and the task page, but don't see the post
  or the calendar. ERP Employees still can't be given content tasks at all.

**Adding someone:** Settings → Agents shows a **Content team** badge on everyone in it
(`helpdesk.api.departments.get_content_team(users)`, System and Agent Managers). Picking
**Digital team: content calendar, no ERP** from the agent's menu gives them DM Employee, which
adds them; **No wall** takes it away. Members through another role (a DM Coordinator, a
manager) keep the badge whatever their wall.

**Moving to opt-in:** existing DM and Content Team roles keep working. Anyone with none of
these roles stopped seeing the calendar on deploy, including people already on posts' teams
without a role; they keep their own content tasks, and need the Digital team wall to see the
calendar again.

## Who can edit entries

Roles (created on install and migrate by `content_team.ensure_role()`, given to **agents**):

| Who | Can do |
| --- | --- |
| **DM Coordinator**, System Manager, Agent Manager, Project Manager (`CONTENT_EDITOR_ROLES`, `can_edit_content()`) | Add entries and change everything on them: fields, status, team and hours, Mark published, Postpone, Cancel, dragging on the calendar. They see every entry. |
| **DM Employee**, and everyone else who can see an entry (writers, designers, agents) | Open the entry (read-only) and use only its **Attachments**: add, download, and remove the files they added themselves. |
| Digital Marketing Head | Approve or send back in Head Review (see below), whether or not they can edit. |

How it's enforced:

- **Server:** `HDContentPost.guard_editing()` runs first in `validate` and refuses any insert or save
  by a non-editor with "Only a DM Coordinator can add or change content entries. You can attach
  files to them." Changes the app makes on someone's behalf pass `ignore_permissions` and are
  allowed: the client's portal and ERP decisions, the head's approve/send back, a finished task
  moving the post to its next stage, monthly plans creating posts, scheduled jobs. Write
  permission on the post itself stays as it was, because Frappe needs it to attach a file
  (attaching never saves the post).
- **Files:** `HelpdeskFile.check_content_file_removal()` lets a non-editor delete only the files
  they uploaded on an entry.
- **Screens** (`authStore.canEditContent`, from `can_edit_content` in `get_user`): the post dialog
  shows every field disabled with "You can view this entry and add files to it", keeps the
  Attachments section working, and offers Close instead of Save. The board hides Add entry, Mark
  published, Postpone, Cancel and the Assign buttons ("Not assigned" instead) and shows a paperclip
  "Open to add files" instead of the pencil. The calendar doesn't allow dragging or adding, and
  occasion chips are disabled.

## Approval: the client, then the Digital Marketing Head

Statuses run Idea → Drafting → Design → Internal Review → Client Review → **Head Review** →
Approved → Scheduled → Published (Changes Requested and Cancelled on the side). Head Review
means the client approved and the **Digital Marketing Head** (role `Digital Marketing Head`,
created on install and migrate by `content_team.ensure_role()`) hasn't yet.

**Every client approval lands in Head Review**, whichever way it is recorded:

| Route | Where |
| --- | --- |
| Client portal, one post or several | `approve_from_portal` (`content_portal.approve` / `approve_many`, which returns each post's new status for the page) |
| Client's ERP | `content_sync.DECISION_TO_STATUS` maps the ERP's "Approved" to Head Review |
| Staff setting the status | `HDContentPost.guard_head_review()`: setting Approved while the post is in Client Review lands in Head Review instead |

**No way around either approval** (`guard_head_review`, run first in `validate`):

- From Head Review only someone with the role — or a System Manager / Administrator, so a post
  never waits on a head nobody was given — can change the status (`record_head_decision`), except
  to Cancelled, which stays open to the team. Anyone else gets "Only the Digital Marketing Head
  can approve this post or send it back."
- Head Review can only be entered from Client Review, so an unapproved post can't be pushed in.
- A post that has been to the client (`client_review_since` set) can't reach Approved, Scheduled
  or Published any other way: not Scheduled/Published straight from Client Review, and not from
  Changes Requested (after the client or the head asked for changes), Internal Review or earlier
  stages — not even by a head. It's refused with "… went to the client, so the client and then
  the Digital Marketing Head approve it before it can be …. Send it to Client Review." The board
  hides Mark published on Client Review posts for the same reason.
- Moving between ready statuses (Approved → Scheduled → Published) is unchanged, and posts that
  never went to the client (e.g. Internal Review → Approved) are unchanged.

The head acts from the post's card on the board (`EntryActionDialog.vue`; the card shows
**Approve** and **Send back** instead of Mark published, and "Client approved · waiting for the
Digital Marketing Head" for everyone else):

- **Approve** (`content_board.head_approve`) → Approved; the digital marketer hears it's their turn
  (as before).
- **Send back** (`content_board.head_send_back`, reason required) → Changes Requested with
  `head_feedback`; the writer, designer and video editor hear it's their turn. Choosing Changes
  Requested in the status select without a reason is refused.

The head's decision is kept apart from the client's: `head_decided_by`, `head_decided_on`,
`head_feedback`. `client_decided_on` stays the client's, so the delivery report's approval time
and the performance page's client change requests are unaffected. Entering Client Review again
clears the head fields (their decision was on an older version). The post dialog shows "Client
approved · waiting for the Digital Marketing Head" in Head Review and "The Digital Marketing Head
asked for changes" with the reason after a send-back.

**Who hears what:** reaching Head Review notifies every enabled head (`head_approvers()` in
`content_team.py`); while nobody has the role, the System Managers are notified instead, since
they can act. The daily due reminder for a post publishing within 48 hours that's still in Head
Review goes to them as well as the team. Heads see every post (`_is_content_lead`, which also covers editors).
**Give the role to an agent:** like Content Team, it adds no app access or DocType permissions of
its own, so someone with only this role can't open the helpdesk. `is_dm_head` comes to the
frontend as `authStore.isDmHead`.

**Elsewhere:** Head Review is amber "in review" on the board, calendar and status pill; the
delivery report counts it under In review; the client portal shows it to the client as
"Approved · final check" and counts it with their approved posts. The legacy calendar import
still maps "Client Approved" straight to Approved (old calendars, already past both approvals).

## Client approval colour

Each post shows where the client stands, beside its status (`ClientApprovalChip.vue`,
`clientApproval()` in `desk/src/pages/content/constants.ts`). The status machine is unchanged.

| Status | Shown | Colour |
| --- | --- | --- |
| Client Review, Changes Requested | clock icon, "Awaiting client" | `danger` |
| Head Review, Approved, Scheduled, Published | check icon, "Client approved" | `success` |
| Earlier statuses, Cancelled | nothing: the post hasn't reached the client | |

The chip is on the board's list and entry cards and in the Sheet. The calendar colours these
posts red and green and adds the label to the event's text, and its legend reads Planning,
Internal review, Awaiting client, Client approved. Head Review counts as client approved
because it is entered only from the client's approval.

## Colour rules

From `desk/src/theme.css`: the brand teal is only for the primary action (Add entry) and the
selected view/period/chip; today's date gets a logo-orange ring (`highlight`). Status colours appear only where they mean
something and always with a label or icon. Numbers, dates and times use Geist Mono with
tabular figures.
