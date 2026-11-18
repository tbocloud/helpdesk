# Sales targets

**Status:** built 2026-11-17. This document is the living source of truth for the feature;
update it with every change.

A Sales Head gives Presales Executives and Sales Users their targets for a month. Each person
sees their own on **Sales targets**.

## Roles

| Role | What they get |
| --- | --- |
| `Sales Head` (or System Manager) | **Assign sales targets** (Sales → Team): picks people and assigns the month's targets. |
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
| `HD Sales Target Criterion` | Child: criterion name, value type (Amount, Number, Percent or Text), the target (`target_value` for numbers, `target_text` for text), what it counts from (`measure`, numbers only; blank: not counted) and, for a Text target, the KPI's state (`kpi_status` blank / Done / Confirmed, `kpi_note`, `kpi_done_on`, `kpi_confirmed_by`). |

New targets start with five criteria (`DEFAULT_CRITERIA` in `helpdesk/sales_targets.py`):
Target Amount (Amount, counts won value), Quality Target (Percent, counts the meeting rate),
Client Meeting (Number, counts meetings held), Sales KPI (Text, ticked off) and Proposal Count
(Number, counts proposals sent). The head can remove any of them, add their own (up to 30) and
change what each counts.

### Validation (on save)

- The employee is enabled and has Presales Executive or Sales User.
- At least one criterion, and no name twice (case-insensitive).
- Every criterion has a target. Numbers can't be below 0, and a percent can't be over 100.
- A measure fits its value type (`MEASURES`): won value and money collected count towards an
  Amount, the counts towards a Number, the rates towards a Percent. A Text target has none.
- Assigning to several people checks everyone first and saves nobody's if one can't be given
  targets.

## Assign sales targets page (`/helpdesk/sales-targets`)

`desk/src/pages/sales-targets/SalesTargets.vue`, redesigned 2026-11-18. The month is in the URL
(`?month=2026-12`), from three months ahead to a year back, picked with `MonthStepper.vue` (a
month select with an earlier and a later step either side; both pages share it).

- **Team** (left card): "4 of 6 have targets for November 2026" over a green meter. **Pick the
  N without targets** picks everyone still without them, the usual job. The filter bar holds
  search, a role select (All roles, Presales Executive, Sales User) and a Not set / Set
  toggle. Then a table: a select-everyone-shown box in the heading row, and one row a person
  (avatar, name, roles in plain text, and for the month either "5 targets" with a check and
  their first Amount target, or "Not set"). A click on a row picks only that person, and a
  checkbox adds or drops one. The footer says how many are shown and picked, with Clear.
- **Progress** on the Team list: each person with targets shows the month overall (a small
  bar and "62% reached", or "62% · 2 behind" in warning) once their progress is read.
- **Targets** (right, sticky, `TargetCriteriaForm.vue`): under each numeric target a **Counts**
  picker (its measures, or *Nothing: a target only*) with what it counts in words; with one
  person picked who has targets, their progress against each target (live as the figure is
  edited) and their KPI with **Confirm it's done** / **Reopen**. "Assigning to" with the person's face
  (or the first three overlapping and "+N") and a clear button. The criteria are a numbered
  list, one row each: name and kind (with its icon) on the left, the figure right-aligned on
  the right (amounts with the currency sign, percents with %), a remove button; a Text target
  takes a text box under its name. A problem shows on its own line under the row, in red with
  an icon, and the field gets a red border. **Add a target** takes a name, a kind and Add. The
  list scrolls; **Assign to N people** stays at the foot of the panel. One person with targets
  opens on their saved targets. Anyone else starts from the five defaults, and the panel says
  whose targets will be replaced.
- States: loading, load error with Try again, not a Sales Head, no one with a target role,
  no one matching the filters (with Show everyone; filtered to Not set and none left says
  everyone shown has targets), nobody picked.

The currency is the CRM dashboards' reporting currency (`HD CRM Settings.dashboard_currency`),
else the site default, else INR.

## Sales targets page, for the people given targets (`/helpdesk/my-targets`)

`desk/src/pages/sales-targets/MyTargets.vue` (the file and route keep the earlier name *My
targets*; the sidebar says **Sales targets** and the page **Your sales targets**). Only
Presales Executives and Sales Users see it. One card a month: its heading is the month and the
count, with who set them (avatar, "Set by …", "Last changed …") on the right. Under it the
figures sit in a hairline grid (`TargetFigure.vue`), one cell per numeric target in the order
the Sales Head set them: a neutral icon for its kind, its name and the figure (amounts with the
currency sign, percents with %). Text targets follow as a list, name on the left and the text as
written on the right. The card's foot says to ask the Sales Head about a target. A counted target
shows what they achieved *of* the target, the bar with the pace marker, where they stand and
**How it's counted**; a target not counted says so. Each KPI shows its state and **Mark as done**
(with what they did) or **Not done after all**. The heading adds the month overall. No colour per
target: the figures are what matter (docs/ui-guidelines.md §8). The month stepper offers this
month and every month the person has targets in. A month with no targets says so and links to
the newest month that has some.

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

## API (`helpdesk.api.sales_targets`)

- `get_team(month)`: Sales Heads only. Returns the people, their targets for the month, the
  defaults and the currency.
- `assign_targets(month, employees, criteria)` (POST): Sales Heads only. Replaces each
  person's targets for the month.
- `get_my_targets(month)`: Presales Executives and Sales Users. Returns their own targets and
  the months they have targets in.
- `get_progress(month, employee=None, fresh=0)`: the person's own progress, or anyone's for a
  Sales Head. `{state: counted | not_started | unavailable | no_targets, reason, from_date,
  to_date, month_over, criteria: {name: {achieved, parts?}}}`.
- `get_team_progress(month, fresh=0)`: Sales Heads. The same for everyone with targets, by user.
- `mark_kpi_done(month, criterion, done, note)` (POST): the person ticks a KPI off or takes it
  back.
- `confirm_kpi(month, employee, criterion, confirmed)` (POST): Sales Heads confirm or reopen.

`get_user` sends `can_assign_sales_targets` and `has_sales_targets`, which show the sidebar
items and let the router open the pages. Both routes are in `SALES_EMPLOYEE_ROUTES`, so a
Sales Employee who also has one of these roles can reach them.

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
confirmed, a confirmed one not taken back, and kept or reset on re-assigning.
