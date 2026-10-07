# Workspace pages: Overview, Team, Summaries

Three pages for the people who run projects: what's late, who is doing what, and what each
customer was told. They follow [ui-guidelines.md](ui-guidelines.md): neutral tiles, colour only
where it means something (always with an icon or text), and only figures the server computes.
No invented trends ("+12% vs last week") and no activity feed.

Shared building blocks, in `desk/src/components/`:

- **`StatTile`**: the one stat tile. Static, a link (`to`, shows a chevron) or a toggle
  (`pressed`, a button with `aria-pressed`). `loading` shows a skeleton; `iconTone` and
  `valueTone` colour the icon or number only when that carries meaning. Used by Overview, Team,
  the By project view and Performance.
- **`SectionCard`**: the one titled card (title, optional count, description, header actions
  slot, "See all" link). Used by Home, Overview and Team.

## Overview (`/overview`)

`desk/src/pages/work/Overview.vue`; API `helpdesk.api.work.get_overview(project, customer,
assignee, department)`. Project managers and project leads only.

- **KPI row**: Active work, Unassigned, At risk, On hold open their list below the dashboard;
  Open projects links to Projects and People busy to Team (with the project and customer
  filters). The list scrolls into view when it's off screen.
- **Buckets** (server): `overdue`, `at_risk`, `due_soon`, `key`, `review`, `waiting_on_task`,
  `on_hold`, plus `unassigned` (open work with no assignee) and `all` (every open task and
  ticket, overdue first). `counts` has each bucket's size.
- **`open_projects`**: open projects the user may read under the filters (the task filters
  already carry project, customer and department). With an assignee filter, only the open
  projects that person has open tasks in.
- **`people_busy`**: distinct assignees of the open work under the filters.
- Each bucket shows up once on the page: the KPI row, the Work status column (Overdue, Waiting
  for review, Waiting on task) or the tiles beside Action required (Due soon, Key).
- **Due soon / Key** tiles say "N open · M in progress"; in progress is a task with status
  Working, open is the rest, so the two add up to the tile's count. Worked out in the browser
  from the bucket's items.
- The bucket and filters live in the URL (`bucket`, `project`, `customer`, `assignee`,
  `department`).

## Team (`/team`)

`desk/src/pages/work/Team.vue`; API `helpdesk.api.work.get_team_workload(project, customer)`
for By person, `get_project_portfolio` for By project (`components/ProjectPortfolio.vue`).

- **By person / By project** switch, kept in the URL as `view`.
- **Summary tiles**: People, Working now and Free (with their share of the team), Overdue and
  Waiting review (with how many people), Done this week (the last 7 days). A tile narrows the
  people table to those it counts; the narrowing is `show` in the URL.
- **People table**: person, current in-progress task (+N more), open work chips (open, review,
  on hold, overdue, estimated hours), due this week (next 7 days), done this week, tickets
  (with SLA breached), next due task and date. Sort select (`sort` in the URL): most overdue
  first (the server's order), most open work, most due this week, next due date, name.
- **A row opens the person's work** (`/my-work?user=...`), which leads and managers may open for
  people on their projects. The table no longer expands inline, so the API no longer sends each
  person's task list.
- Below `xl` each row becomes a card with labelled values.

## Summaries (`/work-summaries`)

`desk/src/pages/work/WorkSummaries.vue`; API `helpdesk.api.work_summary.get_summaries(customer,
week, kind, limit)` returns `{summaries, can_generate}`.

- **Filters** in the URL: `customer`, `week` (the Monday of a week: summaries whose period ends
  in it; the last 12 weeks are offered) and `kind` (`ai` or `plain`).
- **Grouped by period**, newest first. Each row: customer, kind badge, the week in numbers
  (tickets opened and resolved, tasks done, overdue in red with an icon), generated date. The
  numbers come from the summary's stored stats (`highlights`); a summary without stats shows
  "No figures" rather than zeros.
- **Duplicates explained**: one customer can have several summaries, from the Monday run and
  from "Generate summary" (which covers the 7 days up to that day). The period group tells them
  apart, and when the same customer and period was generated again, the older row is marked
  "Older version".
- **Generate summary** (primary action) only shows when `can_generate`: Agent Managers, or
  project managers of at least one customer's project (the same rule `generate_summary`
  enforces per customer).
