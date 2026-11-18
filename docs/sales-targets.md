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
| `HD Sales Target Criterion` | Child: criterion name, value type (Amount, Number, Percent or Text) and the target (`target_value` for numbers, `target_text` for text). |

New targets start with five criteria (`DEFAULT_CRITERIA` in `helpdesk/sales_targets.py`):
Target Amount (Amount), Quality Target (Percent), Client Meeting (Number), Sales KPI (Text) and
Proposal Count (Number). The head can remove any of them and add their own, up to 30.

### Validation (on save)

- The employee is enabled and has Presales Executive or Sales User.
- At least one criterion, and no name twice (case-insensitive).
- Every criterion has a target. Numbers can't be below 0, and a percent can't be over 100.
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
- **Targets** (right, sticky, `TargetCriteriaForm.vue`): "Assigning to" with the person's face
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
written on the right. The card's foot says to ask the Sales Head about a target. No colour per
target: the figures are what matter (docs/ui-guidelines.md §8). The month stepper offers this
month and every month the person has targets in. A month with no targets says so and links to
the newest month that has some.

## API (`helpdesk.api.sales_targets`)

- `get_team(month)`: Sales Heads only. Returns the people, their targets for the month, the
  defaults and the currency.
- `assign_targets(month, employees, criteria)` (POST): Sales Heads only. Replaces each
  person's targets for the month.
- `get_my_targets(month)`: Presales Executives and Sales Users. Returns their own targets and
  the months they have targets in.

`get_user` sends `can_assign_sales_targets` and `has_sales_targets`, which show the sidebar
items and let the router open the pages. Both routes are in `SALES_EMPLOYEE_ROUTES`, so a
Sales Employee who also has one of these roles can reach them.

## Known limits

- Targets only: progress against them (achieved so far) isn't tracked yet.
- No notification is sent when targets are assigned.

## Tests

`helpdesk/tests/test_sales_targets.py`: who is listed, who may assign, one target per person
per month, replacing, months kept apart, validation (blank, below 0, over 100, duplicates),
all-or-nothing assigning, reading only your own targets, and the `get_user` flags.
