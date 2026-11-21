# Sales dashboards

Status: built 2026-11-20 from the owner's two mockups (the salesperson's "Good afternoon,
Fidha" dashboard and the "Sales team dashboard"). This document is the source of truth for both
pages and changes with them.

Every figure is read **live from the ERP site** through the Leads proxies
([leads.md](leads.md)); nothing is stored in the hub. Each page is **one request** that reads its
parts one after another (`helpdesk/api/sales_dashboard.py`), because the hub and the ERP site
share one worker pool ([leads.md, "How the Overview loads"](leads.md#how-the-overview-loads)).
A part the ERP site refuses (or an older TBO Smart without it) is left out with its message in
`errors`, and the page shows that card's error in place; the rest still shows.

## Sales → Dashboard (`/helpdesk/sales/dashboard`, `SalesDashboard`)

The signed-in person's own day. In the sidebar first under Sales, for everyone with Leads
(`leadsOnly`), BDs included. `get_my_dashboard(fresh)`.

| Card | Figure | Source |
| --- | --- | --- |
| Header | date, department (the running batch's, else what they call for), greeting, the slot and its time left, calls left in it | `get_my_calls` (never cached): `batch`, `focus`, `counts.pending`, `next_slot` |
| Find prospects | shown when `can_find_prospects` and not a BD, as on Leads | `get_options` |
| Start calling | opens the first call of the queue on the lead page (`?item=`), else Today's calls | `get_my_calls` pending, then overdue |
| Calls today / Contacted / Contact rate | `today.called`, `today.connected`, contacted ÷ called; *still to call* and the *goal* (the slots' planned calls, or what was handed out when more) | `get_my_calls` `today`, `slots` |
| Sparklines | the same three figures for each day since Monday | the week (below) |
| Open leads | open leads they own, and how many they won this month | ERP `get_overview(period=month, owner=self)` `totals` |
| Today's calls | ring: called against still to call; Called, Contacted, Call backs (`Follow-up Required` among the day's stages), Still to call; contact rate | `get_my_calls` |
| Targets | this month's counted targets, as **Sales targets** counts them (`progressOf`), a ring per target with its standing. Only for people with targets (`has_sales_targets`); read by `get_my_targets` and `get_progress` | [sales-targets.md](sales-targets.md) |
| My pipeline | their open stages that hold leads, as neutral bars; each opens My leads at that stage | `get_overview(month, owner=self)` `pipeline` |
| Calls this week | called and contacted each day from Monday; today's point is the live Today's calls count | ERP `get_lead_analysis` for each day, the person's own row (`called`, `reached`) |
| How today's calls ended | where the day's called leads stand now, as a ring and a legend with counts and shares; stage colours as on Today's calls (`stageColors` in `callBatches.ts`) | `get_my_calls` `today.stages` |
| Up next to call | the queue (pending, then overdue with a red pill), the first three, each with a Call button to the lead page | `get_my_calls` |
| Follow-ups | the first three due (`Since 13 Nov` red when past, `Due …` blue), the stage pill, and the AI's next step when the AI plan has the lead; the overdue count | `list_leads(view=follow_up)`, `get_follow_up_counts`, the overview's `ai.plan` |

Without call batches for their department, the call cards are left out and a line says why.
The page reads again every two minutes; Refresh sends `fresh=1`.

## Sales → Team dashboard (`/helpdesk/sales/team-dashboard`, `SalesTeamDashboard`)

The team's figures, under Team in the sidebar for everyone with Leads **except BDs**
(`salesManagersOnly`; the server refuses a BD with "This is for managers…", `refuse_bd`).
`get_team_dashboard(period, owner, fresh)`; `period` is today, week or month and, with `owner`,
in the URL.

| Card | Figure | Source |
| --- | --- | --- |
| Tiles | New leads, Contacted (% of new), Hot leads, Overdue follow-ups (with the leads gone quiet for the stale days), Open pipeline (with the win rate); each opens its leads (`metric`) | ERP `get_overview(period, owner)` `totals` |
| Team calls this week | each salesperson's calls per day since Monday, one line each in the chart palette, up to five (those who called most) | `get_lead_analysis` per day |
| Pipeline by stage | the four biggest open stages and the rest as *Other open stages* | `get_overview` `pipeline` |
| Your team (today / this week / this month) | per salesperson: called of handed out, contacted, contact rate; for a **Sales Head** also the month's target progress (`overallOf`, as the Assign sales targets page) and On track / Behind | `get_lead_analysis(period)` `calling`; `get_team` and `get_team_progress` |
| Lead funnel | new, contacted, meetings held, proposals sent, won, each as a share of the step before, and the biggest drop in words | `get_overview` `funnel` |
| Calls this week (leaderboard) | the week's calls per person, ranked | the week |
| Leads handed out today | today's batches by slot and department, in the order they start: called of handed out | `get_call_batches_report` |
| Needs a nudge | overdue follow-ups, leads gone quiet, and the AI's high intent, unhappy and stage moves to check; each opens its leads | `get_overview` `totals`, `ai` |

The people (the owner picker, the team table, the week) are cut to the **sales team** (enabled
users with the Sales Employee role, `only_sales_team`), as the New leads strip is, plus a person
picked explicitly.

## What "called" and "contacted" mean

Both pages count calls the way Today's calls does: **called** is a lead on a call list that got
an answer logged or was moved on by hand; **contacted** is someone answered (Connected, Call back
or Not interested). These come from the batches, not from the call log, so they match Today's
calls and the Call batches table. (The ERP site's `get_my_call_counts` counts calls from the call log, which
misses leads moved without a logged call, so it isn't used here.)

## Caching

The overview, the period's analysis and the follow-ups use the Leads reads' one-minute cache per
person (`cached_read`). A day of the week that has ended is kept for an hour
(`CLOSED_DAY_TTL`, part `analysis_day`), since it no longer changes; Refresh renews today only.
`get_my_calls` is never cached.

## Left out of the mockups, on purpose

- **Best time to reach leads** (contact rate by weekday and hour): the ERP site has no call
  times by hour to count it from. It needs a TBO Smart endpoint first.
- **"#1 in StayVeX"** on the personal week chart, and the sparklines on the team tiles: there is
  no per-day series behind those figures, and a BD may not read the team's numbers.
- **"Not handed out" slots** on Leads handed out today: the batches report lists only the
  batches that were made.
- **The team chart's "goal 100" line**: the call plan per person isn't part of these reads.

## Code

- API: `helpdesk/api/sales_dashboard.py`; tests `helpdesk/tests/test_sales_dashboard.py`.
- Pages: `desk/src/pages/sales-dashboard/` — `SalesDashboard.vue`, `SalesTeamDashboard.vue`,
  `MyTargetsCard.vue`, the charts `DonutChart.vue`, `WeekLineChart.vue`, `Sparkline.vue` (ECharts
  with `pages/performance/chartTheme.ts`), `CardLink.vue`, `PartError.vue`, types and helpers in
  `salesDashboard.ts`.
- Shared: `stageColors` (`pages/leads/callBatches.ts`, also used by Today's calls), `TargetRing`'s
  `text` prop, `token` exported from `chartTheme.ts`.
