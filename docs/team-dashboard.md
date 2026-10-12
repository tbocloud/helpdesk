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
  `TeamRepeatIssues`, `RepeatIssueCard`, `TeamAnalysis`, `TeamTrendChart`); types and labels
  in `teamDashboardMeta.ts`.
- Numbers and scoring: `helpdesk/team_dashboard.py`. Who sees what and the page's API:
  `helpdesk/api/team_dashboard.py`. Closed periods: doctype **HD Team Champion**.
- Repeat issues: `helpdesk/repeat_issues.py` (detection), `helpdesk/api/repeat_issues.py`
  (the section's API and actions), doctype **HD Repeat Issue** (decisions).

## Periods

Today, This week (Monday to Sunday), This month, This quarter, Half year (January to June or
July to December) and This year; `period_bounds()` is the one definition. Every figure is
compared with the **previous period up to the same point** (`comparison_bounds()`): on a
Wednesday, this week is compared with Monday to Wednesday of last week, so a week in progress
isn't compared with a whole one. Tiles show "↑ 3 vs last week" (`StatTile`'s `delta` and
`deltaText`: an arrow icon, a screen-reader "Up"/"Down" and text, never colour alone; a rise
is green, a fall stays gray). "Overdue now" has no comparison, since it is today's state.
The tiles' icon circles follow the colour rule in [ui-guidelines.md](ui-guidelines.md) §8:
Tasks finished and Posts published success, On time by its rate (`onTimeTone`), Overdue now danger, Hours
logged info. The period and Departments / People / Projects switches are frappe-ui
`TabButtons`.

The URL keeps `period`, `department`, `view` (`people`, `projects`, `repeats`; Departments is the default),
`person` (the open score breakdown) and `project` (highlighted in Projects).

## What is counted

All read in a few grouped `frappe.qb` queries per period (no per-person or per-task queries),
cached for 5 minutes per period (`collect()`, key `team_dashboard:<start>:<end>:…`). A period
that has already ended, read without today's overdue (the comparisons and the app's 8-period
trends), is cached for an hour (`CLOSED_CACHE_SECONDS`): its numbers no longer depend on the
day, so a late edit to an old task shows within the hour.

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

## Repeat issues

The owner asked for the Scoreboard to point out **work of a repeated nature from the same
customer**: the same problem coming back as tickets and tasks. It is the fourth view,
**Repeat issues** (`view=repeats`), for the same period and department as the rest of the page.

### What counts as a repeat

`helpdesk/repeat_issues.py`, deterministic, no AI:

- **Window**: the period plus the **90 days before it** (`LOOKBACK_DAYS`), up to today, so
  "this keeps happening" shows even in a week. Counts are given for the period and for the
  whole window.
- **Records**: the customers' tickets raised in the window, and tasks created in it in the
  customers' projects (the project's customer). Left out:
  - tickets **merged** into another (`is_merged`): counted once, as the ticket they went into;
  - tasks a **recurring-task schedule** made (`custom_recurring_task`, see
    [recurring-tasks.md](recurring-tasks.md)) and **content calendar** tasks (`content_post`):
    planned repeats;
  - a task **made from a ticket** in the window (`hd_ticket`): the same issue, so only the
    ticket counts;
  - a **root-cause task** (below): the answer to a repeat, not one more of it;
  - cancelled and template tasks.
- **Scope**: tasks are in a department by their project's department; tickets belong to the
  support department (Settings → Follow-ups), as in the team insights.
- **Words**: subject and description (the first 40 meaningful words), lowercased, without
  `Re:`/`Fwd:`, the sign-off ("Regards, …"), emails and links, and **any word with a digit**
  (ticket and document numbers, dates, amounts, GSTINs). Stopwords and greeting words are
  dropped (the search's and the AI suggestion's lists plus a few, e.g. "kindly", "sir"). A
  light stem makes "printed", "printing" and "prints" one word, and a few synonyms are folded
  ("incorrect" and "invalid" → "wrong", "display" and "appear" → "show").
- **Alike**: two items of **one customer** are alike when either
  - their words overlap by **0.3** or more (`WORD_THRESHOLD`): Jaccard over IDF weights
    (`log((n + 1) / df)` across every item in the window), so shared rare words ("GSTIN")
    count much more than words every ticket has ("invoice"); subject words count twice; or
  - their subjects' letter trigrams overlap by **0.6** or more (`TRIGRAM_THRESHOLD`): nearly
    the same subject, typos included.

  The **same ticket type or task category** adds **0.1** to the word overlap (`KIND_BONUS`):
  enough to tip a close pair, never to link unrelated ones. "Unspecified", and any type or
  category on more than half of the items (the default one, `KIND_MAX_SHARE`), say nothing
  and are ignored.
- **Clusters**: items joined by a chain of alike pairs (union-find), per customer only, so
  two customers never share a cluster.
- **A repeat issue** has at least **3 items in the window** and **at least 1 in the period**
  (`MIN_OCCURRENCES`, `MIN_IN_PERIOD`; site config `repeat_issues_min_occurrences` and
  `repeat_issues_min_in_period` may change them, never below 2 and 1).
- **Rising**: at least 2 this period and happening more than 1.5 times as fast as in the 90
  days before it (`RISING_MIN`, `RISING_RATIO`); else **steady**.

The thresholds were picked on realistic wording: Galom International's "GSTIN wrong on sales
invoice print", "Sales invoice print shows old GSTIN", "Wrong GSTIN printed on invoice" and
"RE: Invoice print format showing incorrect GSTIN" form one issue, while "Sales invoice print
is slow", "Salary slip email not sent" and "Stock balance mismatch" stay apart
(`helpdesk/tests/test_repeat_issues.py`).

**Speed**: two bounded queries (tickets, tasks; at most 6000 rows each, descriptions cut to
2000 characters), clustering in memory per customer (at most 300 items each), at most 60
issues. The result is cached for 10 minutes per period, department and day (`frappe.cache`,
key `repeat_issues:…`). Stored decisions and AI titles are read on top of it, so a dismissal
shows at once. The daily close job (`close_periods`, 00:30) also queues `precompute()`: this
week's and month's whole-team issues with their AI titles.

### Per issue

Customer, title, likely cause and fix (AI, optional), tickets and tasks, count this period
and in the window, first and last seen, rising or steady, who handled them (assignees, with
counts), the tickets' average resolution time, the KB article written from one of its
tickets (draft or published), the root-cause task and its status, and every occurrence
(newest first, linked to the ticket or the task's project). A summary line opens the
section: "3 repeat issues across 2 customers · 6 tickets this month · 1 task this month ·
1 rising". Customers are ranked by repeats this period; the first one opens on its own.
Rising is the only colour (`warning`, with an icon and the word); steady stays gray.

### AI titles

`label_clusters()` sends only the issues' subjects (up to 8 each, 20 issues a call) to the
hub's AI (`ai_engine.call_haiku`) for a short title, a likely root cause and a fix. The
Scoreboard's **number guard** applies per issue: a title, cause or fix with a number that
isn't in that issue's subjects is dropped, and without a usable title the issue keeps the
subject title. Titles are cached for 14 days per issue id. The page never waits for the AI:
missing titles are written in the background (`label_job`), and after a failure the AI is
left alone for 15 minutes. Without AI (or when it fails) the title is the subject most items
share, else the ticket subject with most of the issue's keywords, without "Re:".

### Actions

| Action | Who | What |
| --- | --- | --- |
| **Create root-cause task** | `can_act` (System and Agent Managers, department heads, Project Managers), and only in a project they manage or lead, or whose department they head | A key, High priority Support task "Root cause: …" in an open project of the customer (the dialog asks which), listing every occurrence with links. One per issue. |
| **Draft KB article** | Anyone who may create HD Articles, with AI set up | The existing KB draft feature (`kb_drafts.draft_article`) on the issue's most recently resolved ticket that the team answered: a draft for the Agent Managers to review. An article already written from one of its tickets is shown instead. At most once a minute per issue. |
| **Not a repeat** | `can_act` | Hides the issue for everyone, with Undo (`restore_repeat_issue`). |

**HD Repeat Issue** keeps these decisions: customer, title, status (Open, Dismissed,
Root-cause task), the task, who decided, the issue's id when first stored (`signature`), its
keywords and every ticket and task seen in it. A detected issue is matched to a record of the
same customer by the same id, **any shared ticket or task**, or half of the same keywords, so
a dismissal still holds as the issue grows. System and Agent Managers full, agents read; the
page writes through the API only.

### Fairness

Repeats are a **customer and process insight**. They never change anyone's score or the
champion: handling a repeat counts like any other ticket or task. The optional "Root cause
fixed" credit (rewarding the person whose root-cause task stops an issue for 30 days) is
**not implemented**: it would add a second scoring input that is hard to explain and easy to
game (a task closed just before a quiet month), and `score()` stays the one formula. No
repeat count was added to the People or Departments tables for the same reason: next to a
person it reads as blame.

### Who sees repeat issues

Everyone who sees the Scoreboard sees Repeat issues, with the Scoreboard's department rules
(`viewer_access`, `scope_department`): every active department, past the DM/ERP walls; an
inactive department is refused. Actions follow the permissions above, checked on the server.

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

After the champions, `close_period` awards the period's **badges** (`competition.award_badges`:
on-time streaks, key task closers, zero overdue weeks, each department's top 3, champions of
the week and month) into **HD Badge Award**, just as idempotently. The TBO Smart app's
Compete screen (`get_competition`) shows them with ranks and their change, streaks, personal
bests, the weekly challenge and how to move up, all derived from `score()`; see
[tbo-smart-api.md](tbo-smart-api.md#compete-scoreboard-for-the-app).

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

`helpdesk/api/repeat_issues.py`, agents only:

| Method | HTTP | What |
| --- | --- | --- |
| `get_repeat_issues(period="week", department=None)` | GET | `period` (with `lookback_start`), `rules`, `summary`, `customers` (each with `projects` and `clusters`), `department`, `access` (`can_act`, `can_draft_kb`) |
| `create_root_cause_task(period, cluster, project, department=None)` | POST | `{task, project, issue}` |
| `draft_kb_article(period, cluster, department=None)` | POST | `{name, title, status, existing}` |
| `dismiss_repeat_issue(period, cluster, department=None)` | POST | `{issue}` |
| `restore_repeat_issue(issue)` | POST | `{issue}` (undo "Not a repeat") |

The app reads the same answer through `helpdesk.api.mobile.get_repeat_issues`
([tbo-smart-api.md](tbo-smart-api.md#repeat-issues-scoreboard)).

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
