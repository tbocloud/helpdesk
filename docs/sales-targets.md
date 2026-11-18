# Sales targets

**Status:** built 2026-11-17. This document is the living source of truth for the feature;
update it with every change.

A Sales Head gives Presales Executives and Sales Users their targets for a month. Each person
sees their own on **Sales targets**.

## Roles

| Role | What they get |
| --- | --- |
| `Sales Head` (or System Manager) | **Assign Sales targets** (Sales → Team): picks people and assigns the month's targets. |
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

## Assign Sales targets page (`/helpdesk/sales-targets`)

`desk/src/pages/sales-targets/SalesTargets.vue`. The month is in the URL (`?month=2026-12`),
from three months ahead to a year back.

- **People** (left): everyone with a target role, filtered by role (All, Presales Executive,
  Sales User) and by search. **Select all** picks everyone shown. A click on a row picks only
  that person, and a checkbox adds or drops one. Each row says whether the person has targets
  for the month.
- **Targets** (right, `TargetCriteriaForm.vue`): the criteria, numbered, filled in one by one.
  Amounts show the currency sign and percents a % sign. **Add a criterion** takes a name and a
  value type. **Assign to N employees** saves them. One person with targets opens on their
  saved targets. Anyone else starts from the five defaults, and the panel says whose targets
  will be replaced.
- States: loading, load error with Try again, not a Sales Head, no one with a target role,
  no one matching the filter, nobody picked.

The currency is the CRM dashboards' reporting currency (`HD CRM Settings.dashboard_currency`),
else the site default, else INR.

## Sales targets page, for the people given targets (`/helpdesk/my-targets`)

`desk/src/pages/sales-targets/MyTargets.vue` (the file and route keep the earlier name *My
targets*; the sidebar and the page say **Sales targets**, 2026-11-17). Only Presales Executives
and Sales Users see it. *Your targets for November 2026* and the count head a grid of cards
(`TargetCard.vue`), one per criterion in the order the Sales Head set them: *Target 1*, the
criterion's name, its type's icon, the target (amounts with the currency sign, percents with
%) and the type. A Text target is a card too, its text as written; a long one takes two
columns. The footer says who set them and when. The month picker offers this month and every
month the person has targets in. A month with no targets says so and links to the newest month
that has some.

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
