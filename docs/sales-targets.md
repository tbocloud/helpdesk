# Sales targets

**Status:** built 2026-11-17. This document is the living source of truth for the feature;
update it with every change.

A Sales Head gives Presales Executives and Sales Users their targets for a month. Each person
sees their own on **Sales targets**.

## Roles

| Role | What they get |
| --- | --- |
| `Sales Head` (or System Manager) | **Assign sales targets** (Sales → Team): picks people and assigns the month's targets. **Team targets** (Sales → Team): how everyone is doing against them. |
| `Presales Executive`, `Sales User` | **Sales targets** (Sales): their own targets as cards, month by month, read-only. |

`Sales Head` and `Presales Executive` are created on migrate (`ensure_role` in
`helpdesk/content_team.py`). `Sales User` is ERPNext's role, also given to the CRM's
salespeople by the CRM user sync. The role names live in `helpdesk/content_team.py` and
`helpdesk/sales_targets.py`. People also need to be helpdesk agents to open the app at all.
Administrator and Guest are never listed.

## Data model

| DocType | What it is |
| --- | --- |
| `HD Sales Target` | One person's targets for one month: employee (User), month (the 1st), assigned by, criteria. Named `<user>::<YYYY-MM>`, so there is only ever one per person per month. Tracks changes. |
| `HD Sales Target Criterion` | Child: criterion name, value type (Amount, Number, Percent or Text), the target (`target_value` for numbers, `target_text` for text), what it counts from (`measure`, numbers only; blank: not counted) , for a Text target, whether it is information only (`info_only`) and, when it isn't, the KPI's state (`kpi_status` blank / Done / Confirmed, `kpi_note`, `kpi_done_on`, `kpi_confirmed_by`). |

New targets start with seven criteria (`DEFAULT_CRITERIA` in `helpdesk/sales_targets.py`):
Target Amount (Amount, counts won value), Quality Target (Percent, counts the meeting rate),
Client Meeting (Number, counts meetings held), Sales KPI (Text, ticked off), Proposal Count
(Number, counts proposals sent), and Industry and Location (Text, information only; added
2026-11-19). The head can remove any of them, add their own (up to 30) and change what each
counts.

### Validation (on save)

- The employee is enabled and has Presales Executive or Sales User.
- At least one criterion, and no name twice (case-insensitive).
- Every criterion has a target. Numbers can't be below 0, and a percent can't be over 100.
- A measure fits its value type (`MEASURES`): won value and money collected count towards an
  Amount, the counts towards a Number, the rates towards a Percent. A Text target has none.
- Assigning to several people checks everyone first and saves nobody's if one can't be given
  targets.

## Assign sales targets page (`/helpdesk/sales-targets`)

`desk/src/pages/sales-targets/SalesTargets.vue`, redesigned 2026-11-18 and again 2026-11-22 to
the owner's mockup. The month is in the URL (`?month=2026-12`), from three months ahead to a
year back, picked with a **Month** select in the header.

- **Steps strip**: *Pick people*, *Fill in targets* for the month, *Assign*, and a **Team
  coverage** card ("0 of 6 have targets" over a green meter).
- **People** (left card): the heading with "N selected" and Clear, search, **Select all shown
  (N)**, **Pick the N without targets** (the usual job), and the roles as pills with counts
  (`ViewTabs`: All, Presales Executive, Sales User). One row a person: checkbox, avatar, name,
  role badges, and for the month a green "5 targets" pill (with their month overall or first
  Amount target under it) or a gray *No targets yet*. A click on a row picks only that person;
  the checkbox adds or drops one. The footer says how many of the team have targets.
- **Progress** on the Team list: each person with targets shows the month overall (a small
  bar and "62% reached", or "62% · 2 behind" in warning) once their progress is read.
- **Targets** (right, sticky, `TargetCriteriaForm.vue`; 30rem wide, 38rem from `xl`,
  44rem from `2xl`, 2026-11-19): under each numeric target a **Counts** picker (its measures, or
  *Nothing: a target only*), with no explanation under it (the owner asked for the panel
  without it, 2026-11-19; the person's page still explains what each counts); with one
  person picked who has targets, their progress against each target (live as the figure is
  edited) and their KPI with **Confirm it's done** / **Reopen**. "Assigning to" with the person's face (and, for one person without targets, *No targets
  for … yet*; who set them isn't shown, 2026-11-19)
  (or the first three overlapping and "+N") and a clear button. The criteria are a numbered
  list, one row each: the name on the left (no kind under it, 2026-11-19), the figure right-aligned on
  the right (amounts with the currency sign, percents with %), a remove button; a Text target
  takes a text box under its name. A problem shows on its own line under the row, in red with
  an icon, and the field gets a red border. **Add a target** takes a name, a kind (Amount, Number,
  Percent, Text, or *Text, info only*) and Add. The
  list scrolls; **Assign to N people** stays at the foot of the panel. One person with targets
  opens on their saved targets. Anyone else starts from the seven defaults, and the panel says
  whose targets will be replaced.
- States: loading, load error with Try again, not a Sales Head, no one with a target role,
  no one matching the filters (with Show everyone; filtered to Not set and none left says
  everyone shown has targets), nobody picked.

The currency is the CRM dashboards' reporting currency (`HD CRM Settings.dashboard_currency`),
else the site default, else INR.

A link with `?employee=<user>` (Team targets' **Edit targets** / **Assign targets**) opens
the page with that person picked; `?pick=without` (Team targets' **Assign to N people**) opens it
with everyone still without targets picked. Either parameter is dropped from the URL after.

Each target's kind has one colour everywhere (`VALUE_TYPE_LOOK`, the owner's mockups,
2026-11-22): **Amount** green with a ₹ icon, **Number** blue, **Percent** violet, **Text**
amber. It shows as the kind's pill on the Assign form and as the top edge, icon square and pill
of a target card; the pill always names the kind.

## Team targets page, for Sales Heads (`/helpdesk/team-targets`, 2026-11-22)

`desk/src/pages/sales-targets/TeamTargets.vue`, redesigned the same day to the owner's mockup:
everyone's targets for the month side by side, so the head doesn't have to open each person.
Same people, targets and progress as the Assign page (`get_team`, `get_team_progress`); nothing
new on the server. The month (`?month=`), the view (`?view=person`) and the person open
(`?employee=`) are in the URL. The header has the view switch (**Whole team** / **Person by
person**, `TabButtons`), Refresh (reads the ERP site past the minute's cache, `fresh=1`), the
month stepper and **Assign targets** (the Assign page for the month).

Each person's standing for the month: *behind* (at least one counted target behind pace),
*on track*, *nothing counted* (targets, but no progress yet), *not set*. Lists put who needs
attention first: behind, on track, nothing counted, not set; within each, the lowest month
overall first.

**Whole team** (the default):

- **Pace panel** (`TeamPaceHero.vue`, the dark hero): a gauge of the team average (everyone's
  month overall, averaged) with a yellow tick at today's pace (`monthPace`: days gone ÷ days in
  the month), "The team should be at 73% by today" and what the tick means; one bar of everyone
  by standing with the counts under it. A past month says it is over and where the team ended;
  a later one that it hasn't begun.
- **Targets set**: "2 / 7" over a brand meter, the people without targets (faces and names),
  how many KPIs wait on a head's confirm, and **Assign to N people** (the Assign page with them
  picked).
- **Everyone's targets** (`TeamTargetsMatrix.vue`): pills Everyone / With targets / Behind /
  Not set with counts, a key, then a table: one row a person (face, name, and "39% · 4 of 9
  behind" in warning, "4 targets · nothing counted" or *Not set*), one column each target given
  to anyone that month (case-insensitive; information-only targets get none). A cell
  (`targetCell`) shows what they achieved, *of* the target and a bar, filled by standing
  (`STANDING_LOOK`: reached green, on pace blue, behind amber, nothing counted gray) with the
  standing's icon and its words for screen readers and on hover; a KPI shows its state; a
  target they don't have is a dashed *Not a target*; someone without targets gets one dashed
  *No targets for … yet*. The person column stays put while the table scrolls sideways. A
  click on a person opens them in Person by person.
- **Team totals by target** (`TeamTotals.vue`): each counted Amount or Number target added up
  over everyone counted (rates don't add up, so Percent targets are left out): a bar coloured
  by standing with today's pace ticked, and "400 / 130".
- **Behind pace** (`BehindPace.vue`): the person behind on the most targets: up to three of
  those targets, biggest gap to the pace first ("1 of 4 · 25%", *Behind pace by 1.9*), what
  they have already reached, and **Open {name}'s targets**.

**Person by person**: the team list (search and the same pills; a row shows how many targets
and the month overall, `OverallProgress.vue`, or *Not begun* / *Couldn't count* / *Not set*)
and, on the right, **the person picked** (`TeamPersonTargets.vue`): avatar, name, who set the
targets and when, **Edit targets** (or **Assign targets**, solid), the month overall with the
days counted, then every target as a card (`TargetFigure`: kind colour, Target N, figure, progress), with
**Confirm it's done** / **Reopen** on each KPI (`KpiStatus`, head mode).

States: loading (skeletons), load error with Try again, not a Sales Head (the route sends them
Home; the server refuses), no one with a target role, no one matching the pills or search (Show
everyone; Behind with none left says no one is behind), nothing counted yet for the totals,
no one behind, nobody picked.

The Team dashboard keeps its own short column (month overall and On track / Behind per
salesperson); this page is where the detail is.

## Sales targets page, for the people given targets (`/helpdesk/my-targets`)

`desk/src/pages/sales-targets/MyTargets.vue` (the file and route keep the earlier name *My
targets*; the sidebar says **Sales targets** and the page **Your sales targets**). Only
Presales Executives and Sales Users see it. Redesigned twice on 2026-11-22 to the owner's
mockups; this is the second. The month is a **Month** select in the header (this month, the one
open, and every month the person has targets in).

- **Hero** (the dark panel): a ring of the month overall ("39%"), *Your targets for* the month,
  "9 targets set · 22 of 30 days gone" (or *month over* / *starts on the 1st*), chips for what
  is not zero (*2 reached*, *1 on pace*, *4 behind*, *2 to mark done*; each says its count in
  words) and who set them with when. A month with nothing assigned says *Your Sales Head hasn't
  assigned targets yet.* with **See {month}** for the newest month that has targets.
- **Counted from your leads** (N): every assigned Amount, Number and Percent target as a compact
  card (`TargetMeter.vue`): its kind's icon square, the name, an ⓘ button that opens the sums
  (`HowCounted.vue`, shared with `TargetProgress`, with **See these leads**), "400 of 130", the
  bar with today's pace ticked, the standing in words with its icon and the share reached. A
  target not counted (target only, month not begun, the ERP refusing) says why. A key explains
  the tick; `TabButtons` All / Reached / On pace / Behind (with counts) narrow the cards.
- **Tasks to mark done** (the KPIs, N still open): one row each with the target's text, what
  they noted, a status pill (*Not done yet*, *Waiting for confirm*, *Confirmed*) and **Mark as
  done** / **Not done after all** (`KpiStatus` compact).
- **Where to focus**: information-only targets (Industry, Location) with their text, when
  assigned.
- A line at the foot: *Questions about a target? Ask {name}, your Sales Head.*

**Only what was assigned (2026-11-22).** The page shows the targets the Sales Head set and
nothing else. Standard targets not assigned were cards at 0 (2026-11-19), then *Not assigned
yet* chips; the owner then asked for the assigned ones only, so `get_my_targets` no longer
sends `defaults`.

**No targets for the month** (the owner's mockup, 2026-11-22): a light card in place of the hero
(a dashed ring at 0, the month, "0 targets set · 22 of 30 days gone", **See {month}** for the
newest month with targets, and *Not set yet*); a card saying *No targets set for {month} yet*
with **Ask my Sales Head** (`ask_for_targets`; then *Sales Head reminded*, kept on reload by
`asked`) and **Go to my leads**; **How your targets will work** (three steps and three empty
card outlines); and **Meanwhile, keep going**: Today's calls, My leads and Dashboard, each
only when the sidebar also offers it.

## Progress: counted from the leads (2026-11-18)

Each numeric target says what it **counts from** (`measure`), and the person's progress is read
live from the ERP site's lead overview (TBO Smart `hub-leads-api.md` §2.4 and §2.8) for **the
leads they own**, from the 1st of the month to today (the whole month once it is over). Nothing
is stored: the figures are read when a page opens and cached a minute (`cached_read`, as the
Leads Overview). A month not begun counts nothing.

The ERP site is asked as the person (`acting_user` = them, `owner` = them, `period=custom`),
so their own sales scope applies whether they or a Sales Head is looking. A person with no sales
account on the ERP site gets the ERP site's reason on the card instead of a figure.

| Measure | Counts (ERP figure) | Formula shown |
| --- | --- | --- |
| `won_value` Won value | `totals.won_value`: leads that reached Closed – Won, each at its latest quotation total, else the deal's amount, else its Sales Orders' total | — |
| `collected` Money collected | `get_proposal_money` `totals.advances`: payments received against the leads' Sales Orders, by posting date | — |
| `meetings` Meetings held | `totals.meetings`: a MOM submitted, or a lead reaching First / Second / Third Meeting Completed | — |
| `proposals` Proposals sent | `totals.quotations_sent`: leads a proposal went to, each once | — |
| `won` Leads won | `totals.won` | — |
| `contacted` Leads contacted | `totals.contacted`: a call, note, email, stage change or follow-up done | — |
| `new_leads` New leads | `totals.new` | — |
| `meeting_rate` Meeting rate | meetings ÷ contacted × 100 | `7 ÷ 40 × 100 = 17.5%` |
| `win_rate` Win rate | won ÷ (won + lost) × 100 | `2 ÷ (2 + 2) × 100 = 50%` |

A rate with nothing to divide by is "nothing to count yet", not 0%.

**Where a person stands** (`progressOf` in `salesTargets.ts`), with every sum under **How it's
counted** on the card:
- **Progress** = achieved ÷ target × 100 (a rate: the rate against its target).
- **Expected by today** (a running month, sums only) = target × days so far ÷ days in the month:
  an even pace, drawn as a marker on the bar.
- **Target reached** at or over the target (success); **On pace** at or over the expected
  figure (success); **Behind pace by …** under it (warning); **Ended … short** once the month is
  over (warning); a rate under its target is **… points below target** (warning). Never danger:
  a target not reached yet isn't a failure (ui-guidelines §8, as the Daily report).
- **The month overall** (team list, the person's card heading): each counted target's share
  reached, capped at 100%, and each KPI (confirmed 100%, else 0), averaged; plus how many are
  behind.
- **See these leads** opens the Leads list behind the figure (`metric`, the dates and the
  owner), for people who can open Leads. Money collected and the rates list no single metric
  (the rates open their numerator's leads).

### Sales KPI: ticked off and confirmed

A Text target is a KPI nobody can count. The person marks it **done**, with what they did
(optional), on their Sales targets page; it then waits for a Sales Head, who **confirms** it
(or reopens it) from the person's targets on the Assign page. A confirmed KPI can't be taken back
by the person. Ticking off and confirming don't change who assigned the targets. When a head
re-assigns, a KPI with the same name and wording keeps its state; reworded, it starts again.
Only a confirmed KPI counts towards the month overall.

### Information only: Industry and Location

A Text target can be **information only** (`info_only`): it says where to focus, like the
industry (*Solar, Hospitality*) or the location (*Ernakulam, Thrissur*). The person reads it
on their Sales targets page with the other written targets, without **Mark as done**; nobody
confirms it, it never counts towards the month overall, and `mark_kpi_done` / `confirm_kpi`
refuse it. Industry and Location start as information only; the head adds their own with the
kind *Text, info only*. A number target is never information only.

## API (`helpdesk.api.sales_targets`)

- `get_team(month)`: Sales Heads only. Returns the people, their targets for the month, the
  defaults and the currency.
- `assign_targets(month, employees, criteria)` (POST): Sales Heads only. Replaces each
  person's targets for the month.
- `get_my_targets(month)`: Presales Executives and Sales Users. Returns their own targets, the
  months they have targets in, and `asked` (no targets, and a Sales Head was already asked).
- `ask_for_targets(month)` (POST): the person, with no targets for the month, reminds every
  enabled Sales Head: an `HD Notification` (Reminder, from the person, linking to the Assign
  page with them picked), one per head and month (`dedupe_key`
  `sales-targets-ask:<user>:<month>`), so asking again tells no one twice. Refused with
  targets already set or no Sales Head.
- `get_progress(month, employee=None, fresh=0)`: the person's own progress, or anyone's for a
  Sales Head. `{state: counted | not_started | unavailable | no_targets, reason, from_date,
  to_date, month_over, criteria: {name: {achieved, parts?}}}`.
- `get_team_progress(month, fresh=0)`: Sales Heads. The same for everyone with targets, by user.
- `mark_kpi_done(month, criterion, done, note)` (POST): the person ticks a KPI off or takes it
  back.
- `confirm_kpi(month, employee, criterion, confirmed)` (POST): Sales Heads confirm or reopen.

`get_user` sends `can_assign_sales_targets` and `has_sales_targets`, which show the sidebar
items and let the router open the pages (Assign sales targets and Team targets on the first,
Sales targets on the second). All three routes are in `SALES_EMPLOYEE_ROUTES`, so a Sales
Employee who also has one of these roles can reach them.

## Known limits

- Credit goes to whoever owns the lead now (the ERP site counts by the current owner), so a
  lead handed over mid-month moves its meetings and wins with it.
- Progress isn't kept: an old month is read again from the leads, so editing a lead later
  can change it. A month-end snapshot is the next step.
- The team list reads each person's progress from the ERP site (cached a minute), one request
  per person with targets.
- No notification is sent when targets are assigned.

## Tests

`helpdesk/tests/test_sales_targets.py` (added 2026-11-18; the file the first version listed
here was never committed): each measure's figure and the rates' sums, a person's progress read
as them for their own leads over the month so far, money collected read only when counted, a
month not begun, an ERP refusal shown instead of raised, who may read whose progress, a measure
that doesn't fit its value type, and the KPI: marked done and confirmed, only a done KPI
confirmed, a confirmed one not taken back, and kept or reset on re-assigning; the seven
defaults with Industry and Location information only, information kept and never ticked off,
and a number target never information only. Asking for targets: each Sales Head told once, `asked` after, refused with targets set
and for anyone not given targets.
