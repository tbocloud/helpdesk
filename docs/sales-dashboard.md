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

The signed-in person's own day: a salesperson's page, for Sales Users, Presales Executives and
BDs. In the sidebar first under Sales, for everyone with Leads (`leadsOnly`) **except Sales Heads
and Sales Managers** (`ownDashboardOnly`, `has_own_sales_dashboard` from `auth.get_user`,
`helpdesk.content_team.manages_sales`), who follow the team on the Team dashboard instead; the
route sends them Home and `get_my_dashboard` refuses them (PermissionError), even when they
also hold Sales User. `get_my_dashboard(fresh)`.

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
`get_team_dashboard(period, owner, department, source, fresh)`; `period` is today, week or month
and, with `owner`, `department` and `source`, in the URL.

**Department and Source** (selects beside the person, from `get_options`: the active lead
departments, shown only when there are two or more, and the ERP site's lead sources) keep every
figure to the leads of that lead department and lead source: the tiles, the pipeline, the funnel,
Needs a nudge (the AI's counts too), and the calls (the team table, the week chart, the
leaderboard), where only batch calls and logged calls on those leads count, so a logged call on no
lead drops out. *Leads handed out today* follows the department only: the batches report isn't
counted per lead, so with a source picked the card says so. Every link to the Leads list carries
both. They go to the ERP site's `get_overview` and `get_lead_analysis` only when picked
(`leads.narrowing`), and the answer must say them back (`narrowed`, TBO Smart's
`hub-leads-api.md` v1.37; `leads.applied`). An older TBO Smart silently drops arguments it
doesn't know and answers with everyone's figures, so those are refused: the page says the ERP
site can't narrow by department or source yet, and the filter card stays to clear it. Without a
filter the page works on any TBO Smart. The selects are `sm:w-*`, since frappe-ui's FormControl
adds `w-full`, which a plain width loses to.

Redesigned 2026-11-25 from the owner's photos of a "CRM Intelligence Command Center": the same
cards in the same order, neon on near-black in the dark theme and the same design light in the
light theme ([ui-guidelines.md](ui-guidelines.md) §8, *the command center look*: the `--cc-*`
palette, `cc-card` with one colour each; the rest of the app now shares it).

**Every card opens the data behind it** (2026-11-27). The won cards (Won revenue, the podium,
the period's won value and deals, Forecasted revenue, Conversion ratio) open the period's won
leads; the money cards (Collected, To collect, Revenue received, Total receivables, Payments
overdue) open the Leads Overview at the same period and person, scrolled to *Proposals & money*
(`?section=money`: the Leads page rewrites its query, which would drop a `#hash`), where the
payment splits are listed; Sales target opens Team targets; each Period performance row opens
that figure's leads for the period now; Active pipeline stages opens the open leads; the two
calls cards open Call logs; Leads handed out opens Assign leads. A whole card is clickable
through its heading's link stretched over it (`CcCard` `to`), so the links and buttons inside a
card (a stage, a podium place, `CardLink`) sit above it with `relative z-[1]` and keep their own
target. The Lead funnel, Stage pipeline and Needs a nudge stay as they are: everything in them
is already its own link.

| Card | Figure | Source |
| --- | --- | --- |
| Won revenue vs target (pink, `RevenueHero`) | a half gauge: the period's won value against the team's (or the person's) **won value target**, summed from the Sales targets (`measure = won_value`; month view, Sales Heads only) **of the people on this page only** (a target set for anyone else, such as a test account, would inflate it), what is still to go and the target; without a target the won value, deals won and the period before. Won leads with no amount (`won_unpriced`) aren't in the won value, so the card says how many there are | `get_overview` `totals.won_value`; `get_team` |
| Top revenue by salesperson (amber) | the top three by won value, then deals won, on a podium (first in the middle with the crown), level ones sharing a place; everyone who won a deal is on it, even at ₹0 when their won leads have no amount; each opens their won leads. Everyone's view only | `revenue` |
| Four small cards | the period's won value and deals won, each with the change against the same days before (arrow and %); Collected (receipts posted in the period) and To collect (outstanding **now**, not the period) | `previous`, `money` |
| Forecasted revenue (orange) | a running month only: won value ÷ days gone × days in the month, the rate per day now and the rate per day the target still needs | `forecastOf` |
| Active pipeline stages (blue) | every open stage holding leads, in the ERP site's order: its leads (the bar) and their value; each opens its leads | `get_overview` `pipeline` (`count`, `value`) |
| Team calls this week (cyan) | each salesperson's calls per day since Monday, one line each in the chart palette, up to five (those who called most) | `get_lead_analysis` per day |
| Period performance (violet, `PeriodCompare`) | new leads, contacted, meetings, proposals, won and won value, now and on the same days before, with the change | `previous` |
| Number cards (`CcStat`) | Total leads, Active pipeline (its value), Hot leads, Contacted (% of new), Proposals sent (their value), Converted (its value, or how many have no amount), Conversion ratio (the ERP site's `conversion_rate`: leads created in the period that are won now; with the win rate), Sales target (with what's to go), Revenue received (in the period), Total receivables and Payments overdue (both now), Overdue follow-ups; the lead counts open their leads (`metric`) | `get_overview` `totals`; `money`; the target |
| Lead funnel (violet) | new, contacted, meetings held, proposals sent, won, each as a share of the step before, and the biggest drop in words | `get_overview` `funnel` |
| Stage pipeline (amber, `StageBars`) | the open stages as upright bars, one colour each, the count on top; a bar opens its leads | `get_overview` `pipeline` |
| Sales executive performance & target leaderboard (`TeamLeaderboard`) | everyone in the sales team with calls **or** leads in the period (someone who only held meetings has no call row), ranked by won value, then deals won, answered and called: called of handed out, **Answered** (call-list leads where someone answered, and its share of those called; not the Contacted card, which counts every touch), talk time per **answered** call (calls − missed; "—" when the call log has no talk time, never 0s), meetings, proposals, won, won value; for a **Sales Head** also the month's target progress (`overallOf`) and On track / Behind | `people` (`get_lead_analysis(period)` `calling`), `overview.by_owner`, `revenue`; `get_team` and `get_team_progress` |
| Calls this week (green, leaderboard) | the week's calls per person, ranked | the week |
| Leads handed out today | today's batches by slot and department, in the order they start: called of handed out | `get_call_batches_report` |
| Needs a nudge | overdue follow-ups, leads gone quiet, and the AI's high intent, unhappy and stage moves to check; each opens its leads | `get_overview` `totals`, `ai` |

**Checked against the live ERP site (2026-11-25)**, as a Sales Head: per-person won deals match
TBO Smart's own `get_sales_activity`; the open stages add up to `totals.open` and `open_value`;
the comparison dates are like for like. The Won and Converted totals count everyone in the
viewer's sales scope, so they can be more than the leaderboard's sum (leads won by people
outside the sales team).

**The parts the API adds for the redesign** (`get_team_dashboard`):

- `previous`: the Overview's totals for the **same days of the period before**
  (`previous_bounds`), so a running period is compared like for like: yesterday for today, last
  week's Monday to the same weekday, last month's 1st to the same date (its last day when that
  month is shorter). One more `get_overview` read, narrowed like the rest.
- `revenue`: each salesperson's won value. The Overview counts won leads per person
  (`by_owner`) but their value only for everyone together, so each person **who won something**
  is read on their own (`get_overview(owner=…)`, cached a minute); nobody else is asked. Left
  out (null) when one person is picked: the overview is then theirs alone.
- `money`: `get_proposal_money`'s collected (`advances`), still to collect, overdue and
  proposals' value. **Not read while a department or source is picked**: the ERP site doesn't
  count money that way, and showing everyone's money beside narrowed figures would mislead; the
  panel says so.
- `people` rows also carry the call log's `calls`, `missed`, `talk_seconds` and `overdue`;
  `overview` carries `currency` and `by_owner` (cut to the sales team).

The people (the owner picker, the team table, the week) are cut to the **sales team** (enabled
users with the Sales Employee role, `only_sales_team`), as the New leads strip is, plus a person
picked explicitly.

## What "called" and "contacted" mean

Both pages count calls the way Today's calls does: **called** is a lead on a call list that got
an answer logged or was moved on by hand; **contacted** is someone answered (Connected, Call back
or Not interested). These come from the batches, not from the call log, so they match Today's
calls and the Call batches table. (The ERP site's `get_my_call_counts` counts the call log, which
misses leads moved without a logged call, so it isn't used here.)

## Caching

The overview, the period's analysis and the follow-ups use the Leads reads' one-minute cache per
person (`cached_read`). A day of the week that has ended is kept for an hour
(`CLOSED_DAY_TTL`, part `analysis_day`), since it no longer changes; Refresh renews today only.
`get_my_calls` is never cached.

**In the browser** (`useLiveRead` and `dropOnLeave` in `salesDashboard.ts`, both pages and the
targets card): a page reads again every two minutes, and when the person comes back to its tab
only if its figures are older than that. Leaving the page **drops the reads still on their way**:
the team dashboard's read takes 20–35 s against the live ERP site (eight ERP calls one after
another) and a Sales Head's target progress another ~17 s, and a browser keeps only six requests
open per site across its tabs, so left running they queued the next page's requests: a card
opened onto a Leads list that stayed loading until a refresh (2026-11-25). Changing a filter
drops the read on its way too, so only the latest answer lands.

## Left out of the mockups, on purpose

- **Best time to reach leads** (contact rate by weekday and hour): the ERP site has no call
  times by hour to count it from. It needs a TBO Smart endpoint first.
- **"#1 in StayVeX"** on the personal week chart, and the sparklines on the team tiles: there is
  no per-day series behind those figures, and a BD may not read the team's numbers.
- **"Not handed out" slots** on Leads handed out today: the batches report lists only the
  batches that were made.
- **The team chart's "goal 100" line**: the call plan per person isn't part of these reads.
- From the command-center photos (2026-11-25), each needs a TBO Smart endpoint first:
  - **Revenue day by day** (the cumulative "this month vs last month vs target pace" line and
    the daily lead creation and won chart): there is no per-day series of won value or new
    leads; Period performance compares the totals instead (`previous`), and the big chart is
    the team's calls per day.
  - **Warm and cold leads**: the Overview counts only hot leads.
  - **Unassigned leads** and **collections by department**: neither is counted.
  - **Average time to attend a lead** and **follow-ups per lead**: not counted per person.
  - **Efficiency score and grades** ("Solid contributor", "Needs coaching"): no agreed formula;
    the leaderboard ranks by won value instead.
  - **Recent deals feed**: the Overview lists no won deals with their amounts.

## Code

- API: `helpdesk/api/sales_dashboard.py`; tests `helpdesk/tests/test_sales_dashboard.py`.
- Pages: `desk/src/pages/sales-dashboard/` — `SalesDashboard.vue`, `SalesTeamDashboard.vue`,
  `RevenueHero.vue`, `PeriodCompare.vue`, `TeamLeaderboard.vue`, `StageBars.vue`, the card
  parts `CcCard.vue` and `CcStat.vue`, `MyTargetsCard.vue`, the charts `DonutChart.vue`, `WeekLineChart.vue`, `Sparkline.vue` (ECharts
  with `pages/performance/chartTheme.ts`), `CardLink.vue`, `PartError.vue`, types and helpers in
  `salesDashboard.ts`.
- Shared: `fullAmount` / `shortAmount` / `rangeText`
  (`pages/leads/business/businessFormat.ts`), `stageColors` (`pages/leads/callBatches.ts`, also used by Today's calls), `TargetRing`'s
  `text` prop, `token` exported from `chartTheme.ts`.
