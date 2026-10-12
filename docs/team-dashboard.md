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
  `TeamRepeatIssues`, `RepeatIssueCard`, `TeamAnalysis`, `TeamTrendChart`, `ScoreRulesDialog`);
  types and labels in `teamDashboardMeta.ts`. A task's weight and quality show in the task
  dialog (`desk/src/pages/tasky/components/TaskQuality.vue`).
- Numbers and scoring: `helpdesk/team_dashboard.py`. Who sees what and the page's API:
  `helpdesk/api/team_dashboard.py`. Closed periods: doctype **HD Team Champion**.
- Repeat issues: `helpdesk/repeat_issues.py` (detection), `helpdesk/api/repeat_issues.py`
  (the section's API and actions), doctype **HD Repeat Issue** (decisions).

## Periods

Day, Week, Month, Quarter, Half year (January to June or July to December) and Year;
`period_bounds()` is the one definition.

**Everything is month-based** (the owner, 2026-10-12): the month is the calendar month, from
the 1st to its last day (28, 29, 30 or 31), and it starts fresh on the 1st. Days and weeks
live inside it: a **week runs Monday to Sunday clipped to its month**, so a month's weeks
partition it exactly (October 2026: 1–4, 5–11, 12–18, 19–25, 26–31) and a week crossing a
month boundary is two weeks, one in each month. Weekly champions are stored per clipped week
(`close_period` runs on Sundays and on a month's last day), and the badges, streaks and the
weekly challenge use the same weeks (`podium_streak` steps back week by week with
`period_bounds`, never by 7 days). The year is the months compared (below).

**Cut-over (no migration, on purpose):** weeks closed before this change were stored as full
Monday-to-Sunday weeks (HD Team Champion, HD Badge Award) and stay exactly as they were:
stored history is never rewritten. They can't clash with new records, because a period is
only stored the day after it ends and the old weeks had all ended. Reading still finds them:
the week before a clipped week starts on the Monday an old record starts on (or on the 1st,
inside a month), so "previous champion" and the history show them. One effect: a podium streak
that ran across the change counts again from the first clipped week.

Every figure is compared with the **previous period up to the same point**
(`comparison_bounds()`). A day or a week is compared with the same weekdays 1 or 7 days
earlier: on a Wednesday, this week is compared with Monday to Wednesday of last week, and the
clipped week Thursday 1 to Saturday 3 October with Thursday 24 to Saturday 26 September, so a
short week is never set against a shorter or longer piece. A month, quarter, half or year is
compared with the one before up to the same point. Tiles show "↑ 3 vs last week" (`StatTile`'s `delta` and
`deltaText`: an arrow icon, a screen-reader "Up"/"Down" and text, never colour alone; a rise
is green, a fall stays gray). "Overdue now" has no comparison, since it is today's state.
The tiles' icon circles follow the colour rule in [ui-guidelines.md](ui-guidelines.md) §8:
Tasks finished and Posts published success, On time by its rate (`onTimeTone`), Overdue now danger, Hours
logged info. The period and Departments / People / Projects switches are frappe-ui
`TabButtons`.

### Browsing past periods

Under the period switch, **‹ October 2026 ›** steps to the period before or after (never past
today), with **Back to this month** when looking back, and for Day, Week and Month a **month
picker** (this year and last). The page then shows that period (`get_team_dashboard(day=…)`:
the period `day` falls in; a future day is refused):

- a **closed period** (ended before today) shows its full figures and ranking, and its
  **champions as stored when it closed** (HD Team Champion, read by `Champions` in
  `helpdesk/api/team_dashboard.py`), never a recomputation, so the history doesn't shift with
  a later formula or late edits; nobody stored means no champion. Its own stored analysis
  shows, nothing can be refreshed, and "Overdue now" is left out (it is today's state);
- the **period before's champion** shows under the champion card on every view ("September
  2026: Rahul Nair · 28.5", with the first reason), read from its stored record
  (`previous_champion`); it opens that period;
- repeat issues follow the browsed period too: a closed period's are worked out for its own
  window (its 90 days of history before it, nothing after its end).

### The year: months compared

The Year view adds **Month by month** (`year_months`): for the scope (team, group or
department) each month's tasks done, weighted work, on-time %, quality (the tasks' average
quality, weighted by weight, `totals()["quality"]`) and champion: stored for a closed month,
worked out for the month in progress, none for a month to come. A month opens its Month view.
Each person's row in the People view opens to their month-by-month scores too. Quarter and
half stay as they were.

The URL keeps `period`, `day` (a past period), `department` or `group`, `view` (`people`, `projects`, `repeats`; Departments is the default),
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
| Weight | Each completed task's weight (`task_weight`, [below](#weight-and-quality)); **weighted work** is their sum. A shared task counts in full for each person, once in team totals |
| Quality | Each completed task's close rating (`quality_rating`), send-backs ("Sent back: …" comments from `send_back_task`) and comebacks (`reopen_count`) |
| Slips | `slip_count` of the tasks completed in the period |
| Overdue now | Open tasks (Open, Working, Overdue) past their due date today. On Hold and Pending Review are left out: they wait on someone else |
| Hours | Time logs of draft and submitted Timesheets in the period, by the timesheet's owner (as `get_timesheet_summary` does) |
| Posts | Content posts due in the period (`content_performance.scored_posts`): on time, late or missed, for everyone on the post. Upcoming posts aren't counted |

A row's **department** is its project's `custom_department`; a post's is the department of
its tasks' project. Rows without one fall under **No department**.

## Score and champion

`score(stats, period)` in `helpdesk/team_dashboard.py` is the single source of truth: the
dashboard, the stored champions, the AI and the app's Compete screen all use it, with
`task_weight()` and `task_quality()` for each task. Points (`WEIGHTS`):

| Part | Points |
| --- | --- |
| Each completed task (`tasks`) | half of its **weight** for finishing it |
| On time (`on_time`) | the other half of its weight, only when finished by its due date |
| Quality (`quality`) | what the task's quality adds or takes away: (quality − 1) × the task's points above. So each task earns weight × quality in all |
| Posts | `+1` on time, `+0.5` late, `−1` missed |
| Overdue now | `−1` per task |
| Slips | `−0.5` per due-date move |
| Hours | `+0.05` per hour, **capped at a tenth of the points earned by delivering**, so hours alone score 0 and long hours never beat on-time delivery (the owner's rule: task control, not time tracking) |

- **Minimum activity** before anyone can be champion: **weighted work** (the tasks' weights
  plus posts published) of Today 2, week 3, month 5, quarter 8, half year 12, year 20, from
  at least 2 tasks or posts (`MIN_DELIVERED`). Weighted, so a pile of tiny self-assigned
  tasks doesn't qualify sooner than a few real ones; and one big task alone never wins.
- **Ties** go to the better on-time rate, then more tasks done, then fewer overdue.
- **Why**: each score carries its breakdown (`breakdown`: part, points, words) and the three
  biggest positive parts as `reasons`. The champion card (`ChampionCard`, the one place
  the gold `champion` tokens are used) shows a trophy label ("Champion · This week"), a
  rosette badge, the avatar, name and score, the reasons as a checked list and "How the
  score adds up"; a People row opens to the same breakdown. The breakdown names the weight
  ("Tasks done: 12, weighted work 31 (3 key or milestones, 2 self-assigned at half
  weight)") and the quality ("Quality: 4 rated excellent, sent back 1×").
- **How weight works**: a link under the page's intro opens `ScoreRulesDialog`, which
  explains weight, quality and the score with a worked example. Its numbers come from the
  server (`score_rules()`, the page's `rules`), so it can't drift from the formula.

## Weight and quality

The owner's rule: the Scoreboard must look at **what** was finished and **how well**, not
only how many tasks, or whoever makes many small tasks and closes them wins. Weight and
quality are both worked out by the system; nobody types a weight.

### Weight (`task_weight`, `TASK_WEIGHT`)

| Part | Weight |
| --- | --- |
| Every task | `1` |
| Key task or milestone | `+1` |
| Estimate (`custom_estimated_hours`) | `+0.125` per hour, up to `+2` (16 hours) |
| Priority | High `+0.25`, Urgent `+0.5` |
| **Self-assigned** (the doer created it and gave it to themselves: its creator is an assignee and `get_assigners` names them) | starts at `0.5`; key and priority don't count; the estimate counts up to `+0.5` (4 hours) |

Weight runs from **0.5** (a self-assigned task) to **4.5** (a key, Urgent task estimated at
16 hours or more). Each task's weight comes with its reasons, e.g. "Weight 3.25 — key, 8h
estimate, High priority".

- **Against gaming**: nothing the doer alone sets can inflate their own task. On a task
  they made for themselves the key flag and priority are ignored and the estimate is capped
  at 4 hours (an AI estimate is treated the same, since the doer wrote the description it
  reads). Ten tiny self-assigned tasks weigh 5; two key tasks of 8 hours at High priority
  weigh 6.5 (`test_ten_tiny_own_tasks_dont_beat_two_big_key_tasks`). Work that matters gets
  assigned by a lead, a manager or a teammate and counts in full.
- **Not used**: logged hours (task control, not time tracking: long hours never make a
  task heavier); the category (a kind of work, not a size, and weighting development over
  design would set ERP against Digital); subtasks and checklists (Task has neither; a
  template's checklist is separate tasks, each with its own weight).

### Quality (`task_quality`, `QUALITY`)

| Part | Quality |
| --- | --- |
| Rated Excellent | `×1.25` |
| Rated Good | `×1` |
| Rated Needs rework | `×0.5` |
| Not rated | `×1` (no penalty, no bonus) |
| Each send-back on review | `−0.15` |
| Each comeback (the task reopened after it was done, or its ticket reopened) | `−0.25` |

Quality stays between **0.25** and **1.25**. Examples: Good and sent back once is 0.85;
Excellent, sent back once and reopened once is 0.85; Needs rework that came back three
times is 0.25.

- **The rating** (`quality_rating`, `rated_by`, `rated_on` on Task) is optional and never
  needed to close a task. Who may rate (`can_rate_task` in `helpdesk/tasky/permissions.py`):
  whoever assigned it, the project's managers, lead and coordinators (its reviewers), the
  heads of its project's department and admins; **never an assignee of the task**, so
  nobody rates their own work. It is given in the task dialog (`TaskQuality`): on a
  completed task the choice is saved at once (`rate_task`, POST); on a task waiting for
  review it goes with **Approve** (`approve_task(task, rating)`). The doer's Complete dialog
  has no rating, since the doer can't rate.
- **Rating after a one-click Approve** (Kanban, Checklist, Home and My Work): `approve_task`
  returns the task's `quality`, and when the approver may rate it (`can_rate`) and nothing is
  rated yet, the "Approved" toast offers **Excellent / Good / Needs rework / Skip**
  (`useApproveTask` showing `TaskQuality` with `compact`). Picking one saves it through
  `rate_task`; Skip, closing the toast or letting it time out (15 seconds, paused while the
  pointer is on it) leaves the task unrated. It is a toast, not a dialog, so approving stays
  one click and the rating stays optional. The doer never sees it, since an assignee can't
  rate. The task dialog doesn't offer it again (`offerRating: false`): its rating already
  sits next to Approve. Best first here, since a quick "Excellent" is the common answer; the
  dialog keeps worst to best. A form or Desk save can't change the rating
  (`Task.guard_quality_rating`): only those calls set it (`Task.set_quality_rating`).
- **Comebacks** (`reopen_count`, shown as "Came Back"): `Task.track_reopen` counts a
  Completed task moved back to an open status (a send-back isn't one: the task wasn't done
  yet), and the HD Ticket hook `count_ticket_comeback` counts a ticket reopened after it
  was resolved (Resolved → Open status category) against the completed tasks made from it
  (`hd_ticket`): the customer came back.
- **Repeat issues** don't lower a task's quality beyond that: a repeat cluster is per
  customer and by look-alike words, not per task, so blaming one task's doer for it would be
  unfair (see [Fairness](#fairness)). The same ticket coming back is the per-task form of a
  repeat, and it counts.
- **Slips** aren't in quality: each due-date move already costs `−0.5` in the score
  whatever the task's size; counting it again would charge twice.
- **Approved first time** (`+0.5` per reviewed task not sent back) was removed: a
  send-back now lowers that task's quality instead, so it isn't counted twice.

### Worked example

A key task estimated at 8 hours, High priority, weighs `1 + 1 + 1 + 0.25 = 3.25`. Rated
Excellent and finished on time it earns `3.25 × 1.25 = 4.1` (1.6 finishing, 1.6 on time,
0.8 quality); finished late, half of that, 2.0. The same task rated Needs rework and on
time earns 1.6. A self-assigned task with no estimate earns 0.5 on time.

## Views

- **Departments**: one row per department the viewer may see (people, done, **weighted**,
  on time, overdue, hours, champion), so "12 done · 31 weighted"; a row opens that
  department's People. Each **department group** (a main department with its
  sub-departments, [departments.md](departments.md#department-groups)) comes first as a row
  of its own ("ERP group", its totals and its champion), with its departments indented under
  it; the main department's own row reads "ERP, own projects". Departments in no group
  follow, then a **No department** row when such work exists. People = members of the
  department's open projects plus anyone with work in it this period.
- **The department filter** lists the whole team, each group ("ERP group") and each
  department. A group shows its departments together: summary, people, projects, champion,
  history and analysis (`group` in the URL and the API; `department` and `group` can't both
  be given). Repeat issues follow the same department or group.
- **People**: everyone in scope, best score first (sort by score, done, weighted work, on
  time, overdue, hours or name): score, done, weighted, on time, key, overdue, slips, posts
  (only when someone has posts) and hours. Below `lg` each row is two lines. A row expands to its breakdown. With no
  department picked, active agents with nothing this period are listed too.
- **Projects**: projects in scope with more than one member that are open or had work in the
  period: progress (done of all tasks), done this period, overdue, hours, and each
  contributor's done, hours and overdue.
- The **Tasks finished** tile shows the weighted work under the count ("141.5 weighted
  work").
- Side column: the **analysis**, a **Tasks finished** trend (per day for a week or month,
  per week for a quarter or half, per month for a year; none for Today) and **Champions this
  year** (stored weekly and longer champions of the department, or of the whole team).

## Repeat issues

The owner asked for the Scoreboard to point out **work of a repeated nature from the same
customer**: the same problem coming back as tickets and tasks. It is the fourth view,
**Repeat issues** (`view=repeats`), for the same period (the browsed `day` included) and
department or department group as the rest of the page.

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
issues. The result is cached for 10 minutes per period, anchor day, scope (the departments
in it) and today (`frappe.cache`, key `repeat_issues:{period}:{start}:{day}:{scope}:{today}`,
`scope` a SHA-256 hash of the departments' JSON so no name can collide with another scope):
the anchor tells a browsed period from the one in progress, and today keeps the period in
progress growing. Stored decisions and AI titles are read on top of it, so a dismissal
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
champion as clusters: handling a repeat counts like any other ticket or task, and only the
same ticket reopened lowers a task's quality ([Quality](#quality-task_quality-quality)). The optional "Root cause
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
the whole team, each department group and each active department it stores one **HD Team
Champion** (period type, start, end, department or empty for the whole team, `is_group` for a
group's record, champion or empty when nobody reached the minimum, score, breakdown,
analysis). A group's record is named `…-group_<department>` so it never clashes with its main
department's own (`HDTeamChampion.record_name`). The record name is derived from period and department,
so a second run finds the first and changes nothing; the history never shifts when tasks are
edited later. Overdue counts as of the day after the period.

Every closed period's champion, a day's included, is told once through `notify_users`
(helpdesk panel plus Teams or email): "You're the ERP champion for 9 Oct 2026", "You're the
ERP group champion for the week of 5 Oct 2026". So are the department's heads (a group's:
its main department's heads) ("Anu Menon is the ERP champion for …"),
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
reasons, and up to 15 people with score, done, weighted work, key, on time, overdue, slips,
posts, send-backs, comebacks and ratings; never hours as a judgement) to the hub's AI through
`ai_engine.call_haiku`, the
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
| `get_team_dashboard(period="week", department=None, group=None, day=None)` | GET | `period` (dates, comparison, `closed`, `current`, `earliest` for the month picker), `previous_champion`, `months` (the year only), `access` (departments, `groups` [{group, departments}], can_refresh), `department`, `group`, `summary` (with `weight` and `previous`), `champion`, `departments` (rows with `kind`, `parent`, `weight`), `people` (with `weight`, `self_made`, `excellent`, `good`, `rework`, `sent_back`, `came_back`), `projects`, `trend`, `history`, `analysis`, `rules` (`score_rules()`) |
| `refresh_analysis(period="week", department=None, group=None)` | POST | A new analysis for the period in progress (System and Agent Managers) |

`helpdesk/tasky/api.py`: `rate_task(task, rating=None)` (POST; a completed task's rating, or
none to clear it; returns the task's `quality`), `approve_task(task, rating=None)` (the
approved task, with its `quality` so a one-click Approve can offer the rating) and
`get_task_detail(task)`, whose `quality` is `{weight, weight_reasons, quality,
quality_reasons, rating, rated_by, rated_by_name, rated_on, can_rate, self_made}`.

`helpdesk/api/repeat_issues.py`, agents only:

| Method | HTTP | What |
| --- | --- | --- |
| `get_repeat_issues(period="week", department=None, group=None, day=None)` | GET | `period` (with `lookback_start`), `rules`, `summary`, `customers` (each with `projects` and `clusters`), `department`, `access` (`can_act`, `can_draft_kb`) |
| `create_root_cause_task(period, cluster, project, department=None, group=None, day=None)` | POST | `{task, project, issue}` |
| `draft_kb_article(period, cluster, department=None, group=None, day=None)` | POST | `{name, title, status, existing}` |
| `dismiss_repeat_issue(period, cluster, department=None, group=None, day=None)` | POST | `{issue}` |
| `restore_repeat_issue(issue)` | POST | `{issue}` (undo "Not a repeat") |

`department`, `group` and `day` are checked as `get_team_dashboard` checks them (`scope_of`,
`anchor_day`: a department or a group, not both; no future day). The actions take the same
scope as the list, so a cluster found on a browsed period can be acted on there. While the
list reloads for a new scope its cards are inert, and a failed reload shows the error with
Retry instead of the old cards, so an old card can't act in the new scope.

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
- **Weight and quality (2026-10-12)** replaced "1 + key + estimate" and the "approved first
  time" bonus. **The new formula applies from the deploy on.** Champions of closed periods
  are stored records (HD Team Champion: score and breakdown as they were) and are never
  recomputed, so the history doesn't move; badges already awarded stay too. The period in
  progress is scored with the new formula as soon as it is deployed (the cached numbers are
  versioned, `CACHE_VERSION`, so no old-shaped rows are read). Existing tasks have no
  rating and no comebacks, so their quality is 1.
- **Weight is automatic only** (the owner's decision): no field to type, so nobody argues
  about it and nobody can inflate it.
- **The rating is optional** and given by someone other than the doer; unrated work is
  neutral, so nobody is punished because a lead didn't rate.
- **Period ranges are computed on the server only**, so the page and the stored champions
  can't disagree about where a week or quarter starts.
