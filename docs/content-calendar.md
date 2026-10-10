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
  stats call.

## Filters and navigation

The filter bar (customer, channel, status, person, **My posts**, Clear) applies to every view.
Cancelled posts are hidden unless the status filter asks for them; the Board and Sheet views
load them and show them behind their own chip.

Board and Sheet have a **Day / Week / Month** period switch, Today, previous/next (← / →, T for
today) and a date picker. The Calendar view has its own navigation.

## Views

| View | What it is |
| --- | --- |
| **Board** (default) | Stat tiles, a progress bar and a day-grouped list of entry cards for the period. Follows the owner's mockup in the TBO light theme. |
| **Calendar** | frappe-ui month/week calendar. Drag a post to reschedule it; click an empty cell to add an entry. |
| **Sheet** | A table of the period's posts. |

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
missed.

### Entry cards

Grouped by day (day number, weekday, number of entries that day), sorted by time. On wider
screens the day's date column stays pinned at the top of the list while its cards scroll past.

- **Header:** a building tile, then the client in a larger semibold font (always shown, even
  with the customer filter set); below it the copy (the post's `title`, opens the post) · post
  type. On the right: the platforms (brand mark + name, from `ChannelIcon.vue`, coloured with
  the `--channel-*` tokens), the time, the status pill (`StatusPill.vue` at `size="md"`), and an
  edit (pencil) button that opens the post, the same as clicking the copy.
- **Warning line** "Goes live within 2 days and isn't approved yet." when the post isn't
  Approved/Scheduled/Published and goes live within 48 hours.
- **Sub Copy** (`caption`) and **Description** (`brief`) side by side in white boxes ("Not
  written yet" / "No description yet" when empty).
- **Roles** (`RoleBox.vue`): Writer, Designer, Video editor, Digital marketer. Each assigned
  person shows with a role-coloured initial tile, their name and task status (and "late" when
  the task is past due); an empty role shows a dashed **+ Assign** box in the card's tone.
  Either opens the assign dialog. The filled box is a native `<button>` (or a plain `<div>` for
  people who can't reassign), not `<component :is="'button'">`, which resolves to frappe-ui's
  global `Button` and clipped the names to its fixed height.
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

## Adding and editing a post

**Add entry** (`AddEntryDialog.vue`) creates posts through
`helpdesk.api.content_board.add_entries`; clicking a post opens `PostDialog.vue`. Both use the
same labels and fields:

| Label | Field | Notes |
| --- | --- | --- |
| Copy | `title` | Required. |
| Campaign (optional) | `campaign` | Free text (Data), e.g. "Diwali 2026". |
| Special day (optional) | `special_day` | Free text, e.g. "Diwali". Highlights the post on the calendar (see below). |
| Platforms | `platforms`, `channel` | Chips; one post can go out on several. The first is `channel`. |
| Post type | `format` | Chips, one per post. |
| Sub Copy | `caption` | The post's text; Draft with AI fills it. |
| Description | `brief` | For the creative team; never shown to the client. |
| Writer / Designer / Video editor / Digital marketer | role fields + `extra_team` | Several people per role. |
| Est. hours (next to each role) | `writer_hours`, `designer_hours`, `video_editor_hours`, `marketer_hours` | Optional; see below. |

The Desk form uses the same labels (Copy, Sub Copy, Description).

### Campaign is free text

`campaign` used to link to `HD Content Campaign`; it is now a plain Data field, because the team
names campaigns as they go. The patch `content_campaign_as_text` replaced the stored campaign IDs
with the campaign names. With the link gone, a post's tasks always go to the customer's open
Content Calendar project, the customer is never filled in from a campaign, and Draft with AI
passes the campaign text as "Campaign: …". The `HD Content Campaign` doctype itself is unchanged.

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

## Colour rules

From `desk/src/theme.css`: the brand violet is only for the primary action (Add entry), the
selected view/period/chip and today's date. Status colours appear only where they mean
something and always with a label or icon. Numbers, dates and times use Geist Mono with
tabular figures.
