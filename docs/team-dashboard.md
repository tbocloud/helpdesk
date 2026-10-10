# Scoreboard (team dashboard)

Who finished what in a period, how much of it was on time, and who the **champion** is: per
department, per person and per shared project. Asked for by the owner as a "team dashboard"
under Home and Overview; it is called **Scoreboard** in the app because **Team** (current
workload and capacity) and **Performance** (content delivery by customer and employee, for the content team)
already exist.

- Page: `desk/src/pages/work/TeamDashboard.vue` (route `TeamDashboard`,
  `/helpdesk/team-dashboard`), sidebar item right after Overview, open to every agent
  (`agent_only`; Content Team members who aren't agents don't get it). Parts in `desk/src/pages/work/components/` (`ChampionCard`,
  `ScoreBreakdown`, `TeamDepartmentList`, `TeamPeopleList`, `TeamProjectList`,
  `TeamAnalysis`, `TeamTrendChart`); types and labels in `teamDashboardMeta.ts`.
- Numbers and scoring: `helpdesk/team_dashboard.py`. Who sees what and the page's API:
  `helpdesk/api/team_dashboard.py`. Closed periods: doctype **HD Team Champion**.

## Periods

Today, This week (Monday to Sunday), This month, This quarter, Half year (January to June or
July to December) and This year; `period_bounds()` is the one definition. Every figure is
compared with the **previous period up to the same point** (`comparison_bounds()`): on a
Wednesday, this week is compared with Monday to Wednesday of last week, so a week in progress
isn't compared with a whole one. Tiles show "↑ 3 vs last week" (`StatTile`'s `delta` and
`deltaText`: an arrow icon, a screen-reader "Up"/"Down" and text, never colour alone; a rise
is green, a fall stays gray). "Overdue now" has no comparison, since it is today's state.
The tiles' icon circles follow the colour rule in [ui-guidelines.md](ui-guidelines.md) §8:
Tasks finished and Posts published success, On time success, Overdue now danger, Hours
logged info. The period and Departments / People / Projects switches are frappe-ui
`TabButtons`.

The URL keeps `period`, `department`, `view` (`people`, `projects`; Departments is the default),
`person` (the open score breakdown) and `project` (highlighted in Projects).

## What is counted

All read in a few grouped `frappe.qb` queries per period (no per-person or per-task queries),
cached for 5 minutes per period (`collect()`, key `team_dashboard:<start>:<end>:…`).

| Figure | Source |
| --- | --- |
| Tasks done | Tasks with status Completed and `completed_on` in the period; credited to everyone in `_assign` (a shared task counts in full for each person, once in team totals) |
| On time | Completed on or before `exp_end_date`. Tasks without a due date count as done but not as on time, and are left out of the on-time % |
| Key | `is_key` or `is_milestone` |
| Approved first time | Completed tasks in projects with **Review before done**, without a "Sent back: …" comment (`send_back_task`) |
| Slips | `slip_count` of the tasks completed in the period |
| Overdue now | Open tasks (Open, Working, Overdue) past their due date today. On Hold and Pending Review are left out: they wait on someone else |
| Hours | Time logs of draft and submitted Timesheets in the period, by the timesheet's owner (as `get_timesheet_summary` does) |
| Posts | Content posts due in the period (`content_performance.scored_posts`): on time, late or missed, for everyone on the post. Upcoming posts aren't counted |

A row's **department** is its project's `custom_department`; a post's is the department of
its tasks' project. Rows without one fall under **No department**.

## Score and champion

`score(stats, period)` in `helpdesk/team_dashboard.py` is the single source of truth: the
dashboard, the stored champions and the AI all use it. Weights (`WEIGHTS`):

| Part | Points |
| --- | --- |
| Each completed task | worth `1` + `1` if key or milestone + `0.125` per estimated hour (capped at `2`, i.e. 16 h); half of that worth for finishing it |
| On time | the other half of the task's worth, only when finished by its due date |
| Approved first time | `+0.5` per reviewed task not sent back |
| Posts | `+1` on time, `+0.5` late, `−1` missed |
| Overdue now | `−1` per task |
| Slips | `−0.5` per due-date move |
| Hours | `+0.05` per hour, **capped at a tenth of the points earned by delivering**, so hours alone score 0 and long hours never beat on-time delivery (the owner's rule: task control, not time tracking) |

- **Minimum activity** before anyone can be champion (tasks done plus posts published):
  Today 2, week 3, month 5, quarter 8, half year 12, year 20. One lucky task doesn't win.
- **Ties** go to the better on-time rate, then more tasks done, then fewer overdue.
- **Why**: each score carries its breakdown (`breakdown`: part, points, words) and the three
  biggest positive parts as `reasons`. The champion card (`ChampionCard`, the one place
  the gold `champion` tokens are used) shows a trophy label ("Champion · This week"), a
  rosette badge, the avatar, name and score, the reasons as a checked list and "How the
  score adds up"; a People row opens to the same breakdown.

## Views

- **Departments**: one row per department the viewer may see (people, done, on time,
  overdue, hours, champion); a row opens that department's People. A **No department** row
  shows when such work exists. People = members of the department's open
  projects plus anyone with work in it this period.
- **People**: everyone in scope, best score first (sort by score, done, on time, overdue,
  hours or name): score, done, on time, key, overdue, slips, posts (only when someone has
  posts) and hours. Below `lg` each row is two lines. A row expands to its breakdown. With no
  department picked, active agents with nothing this period are listed too.
- **Projects**: projects in scope with more than one member that are open or had work in the
  period: progress (done of all tasks), done this period, overdue, hours, and each
  contributor's done, hours and overdue.
- Side column: the **analysis**, a **Tasks finished** trend (per day for a week or month,
  per week for a quarter or half, per month for a year; none for Today) and **Champions this
  year** (stored weekly and longer champions of the department, or of the whole team).

## Who sees what

**Every agent sees the whole Scoreboard**: every department, every person's numbers and
score breakdown, the rankings, the projects and the analysis. The owner wants it open so the
team competes ("only then will there be competition").

- **Refresh analysis** (`refresh_analysis`) is for System Managers and Agent Managers only
  (`is_tasky_admin`); everyone else gets a permission error.
- **The department walls don't apply here.** DM Employees see ERP and ERP Employees see
  Digital on the Scoreboard: its departments, people, projects, history and analysis, so the
  two teams compete (the owner's decision, 2026-10-10). Every other wall stays
  (`hidden_departments` in `helpdesk/tasky/permissions.py`: projects, tasks, the content
  calendar, the department filters elsewhere). Asking for a department that isn't active is
  refused.

Both rules live in `viewer_access` and `scope_department` in `helpdesk/api/team_dashboard.py`.

## Champions of closed periods

`close_periods()` runs at 00:30 every day (`hooks.py` cron) and queues `close_period()` for
each period that ended yesterday (a day, and on Mondays a week, on the 1st a month, …). For
the whole team and each active department it stores one **HD Team Champion** (period type,
start, end, department or empty for the whole team, champion or empty when nobody reached the
minimum, score, breakdown, analysis). The record name is derived from period and department,
so a second run finds the first and changes nothing; the history never shifts when tasks are
edited later. Overdue counts as of the day after the period.

Every closed period's champion, a day's included, is told once through `notify_users`
(helpdesk panel plus Teams or email): "You're the ERP champion for 9 Oct 2026", "… for the
week of 5 Oct 2026". So are the department's heads ("Anu Menon is the ERP champion for …"),
or the Agent Managers for the whole team. Heads come from `department_heads()` in
`helpdesk/tasky/permissions.py`: the department's **Heads** setting (Settings → Departments,
see [departments.md](departments.md#department-heads)) plus holders of a role in
`DEPARTMENT_HEADS` (Digital Marketing Head for Digital). Notices go out only when the record
is first inserted, so re-running `close_period` for a closed day or week tells nobody again.

HD Team Champion: System Manager full, Agent Manager read; every agent reads it through the
page's API.

## AI analysis

`write_analysis()` sends `analysis_facts()` (the scope's totals, the champion with score and
reasons, and up to 15 people with score, done, key, on time, overdue, slips, posts and
send-backs; never hours as a judgement) to the hub's AI through `ai_engine.call_haiku`, the
same client as task descriptions and weekly summaries. The model returns a summary, risks and
who could use help. `clean_analysis()` keeps plain text and **drops any sentence or item with
a number that isn't in the facts**, so it can't invent figures.

- Written at period close (weeks and longer) and stored on the HD Team Champion. **Never
  for a day** (`QUIET_PERIODS`), to keep the AI cost down: a day's champion is stored and
  announced without an analysis.
- **Write analysis / Refresh** (System and Agent Managers, not for Today): `refresh_analysis` (POST)
  writes one for the period in progress and caches it for 12 hours per period and department
  (once a minute at most).
- The page shows this period's analysis when there is one, else the last closed period's,
  labelled with its dates.
- When AI isn't set up or fails, the page says the analysis is unavailable and why; the
  scores and champions don't depend on it.

## API

`helpdesk/api/team_dashboard.py`, agents only:

| Method | HTTP | What |
| --- | --- | --- |
| `get_team_dashboard(period="week", department=None)` | GET | `period` (dates and comparison), `access` (departments, can_refresh), `summary` (with `previous`), `champion`, `departments`, `people`, `projects`, `trend`, `history`, `analysis` |
| `refresh_analysis(period="week", department=None)` | POST | A new analysis for the period in progress (System and Agent Managers) |

## Decisions

- **Hours are shown but barely scored.** They are capped relative to delivery, so the
  dashboard never rewards long hours over finishing on time.
- **Due dates matter.** A task without a due date earns only half its worth, since it can't be
  on time; this nudges setting due dates rather than rewarding their absence.
- **Open to everyone.** All agents see all numbers, by the owner's decision, so the team can
  compete, across the DM and ERP walls too. Only the AI refresh is limited to managers.
- **Every department has heads**, set per department in Settings → Departments and told
  their department's champion. The Digital Marketing Head role still counts as a head of
  Digital, so the content calendar's approver needs no extra setup.
- **Weights didn't change** when daily champions started being announced (2026-10-10).
- **Period ranges are computed on the server only**, so the page and the stored champions
  can't disagree about where a week or quarter starts.
