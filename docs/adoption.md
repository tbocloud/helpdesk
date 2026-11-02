# Adoption

One page for management: **who is actually using the system, and what is stuck.** It is a
ranked list of findings in plain words, each saying what it means and what to do, and a table
of people. Nothing needs setting up.

Code: `helpdesk/adoption.py` (the rules), `helpdesk/api/adoption.py` (`get_adoption`),
`desk/src/pages/work/Adoption.vue` and `adoptionMeta.ts`. Tests: `helpdesk/tests/test_adoption.py`.

## How to read this page (for staff)

Open **Adoption** from the sidebar, or from the button at the top of **Team**. Pick a period
at the top: *This week* (Monday to today), *Last week* or *Last 30 days*.

- **Needs attention**: something is clearly not being used or is badly stuck. Do it first.
- **Worth watching**: not an emergency, but it will turn into one if it carries on.
- **Going well**: checked and fine. You can ignore these.

Tap a line to open it. You see *who* it is about, a longer explanation, and a button that opens
the page where it is fixed. Each line already ends with what to do, for example *"Shahana
recorded 0 call results this week. Remind them to tap the result after each call in Today's
calls."*

The **People** table lists everyone with an active account: tasks they completed, hours on
timers, stand-ups they wrote themselves, calls and call results (salespeople only) and the
last day they did anything. Tap a column heading to sort. **Quiet** means the person did
nothing in the period; people on approved leave are shown as *On leave*, never as quiet.

If the sales system can't be reached, a note says Sales results are not shown. The rest of the
page still works. When nothing needs attention you see *"Everyone is using the system this
week."*

A finding is not an accusation: it says the system shows no activity. Ask the person first.

## Who can open it

System Managers, Agent Managers, holders of the **TBO Management** role, and anyone listed as
**Project Coordinator** on a project. The role exists on the ERP site (it decides the Business
tab on Leads); the hub only checks whether a user holds it, so it works as soon as the role is
given to someone here. Everyone else gets a permission error from the endpoint and no menu
entry. The same people get the weekly digest (active agents only).

## The findings

Each finding is `{id, severity, area, title, detail, action_hint, link, who[]}`, ordered by
severity (attention, watch, good) and then by area (Sales, Delivery, Content, Support,
Accounts).

| Area | Finding | Rule |
| --- | --- | --- |
| Sales | Call results | Per salesperson handed call batches (the ERP site's `get_call_batches_report`, the latest 7 working days of the period): no results recorded is *attention*, under half recorded is *watch*, otherwise one *good* line |
| Sales | Nothing in the system | A Sales Employee with no calls, lead updates, meetings, proposals, follow-ups, wins or batch results (the Scoreboard's `get_sales_activity`): *attention* |
| Sales | Calls logged | Nobody logged a call: *attention*; some people did not: *watch* |
| Sales | Leads moved out of New Lead | People with no lead contacted (`sales_contacted`): *watch* |
| Delivery | Overdue tasks | Share of open tasks overdue (the Overview's `is_task_overdue`): 40% or more *attention*, 20% or more *watch*, else *good* |
| Delivery | Projects without a lead | Open projects with no lead: 30% or more *attention*, else *watch* |
| Delivery | Quiet people | Active non-sales agents with no task completed, no timer session and no stand-up written in the period, and no leave: over half of them *attention*, else *watch* |
| Delivery | Stand-ups | Written by people (`Submitted`) against posted by the system (`Auto-posted`): under half written *attention*, some auto-posted *watch*, all written *good*. Skipped while stand-ups are off |
| Delivery | Long hours | A timer session of 7 hours or more, or a time log of 7 hours or more typed in by hand (no timer session behind it): *watch*, "check" |
| Content | Stuck in Drafting | Posts in Drafting not touched for over 7 days: 10 or more *attention*, else *watch* |
| Content | Client review | Nothing in Client Review and nothing sent for approval in the period: *attention* |
| Content | Edits by one person | One person made over 70% of the content calendar's edits (the Version log, at least 10 edits): *watch* |
| Support | Tickets | Open tickets with no first reply after a day (5 or more *attention*, else *watch*); open tickets whose SLA failed: *attention* |
| Accounts | Odd accounts | Active agents whose email is gmail, yahoo, outlook and the like, or whose email or name looks like a test (test, demo, dummy, sample, temp): *watch* |
| Accounts | Same name twice | Two active agents with the same full name: *watch* |

Thresholds are constants at the top of `helpdesk/adoption.py`.

## Sales through the ERP site

Sales reads go through the same proxies as the Leads page, as the signed-in person
(`call_if_deployed("get_call_batches_report")`, cached for a minute with the Leads cache) and
the Scoreboard's activity reader (`sales_scoreboard.activity`, as the hub's API user). They are
skipped quietly, with no error, when Leads are off, the ERP site is unreachable or older than
the method, or the person is refused. A coordinator who is not a sales manager on the ERP site
is refused the batch report, so they see the sales activity findings but not the call results
finding. The people table then shows no quiet flag for salespeople.

Decision: "calls logged" is the Scoreboard's `calls` (answered MyOperator calls and calls
logged by hand); "leads moved out of New Lead" is `contacted`. Both come as counts per person
for the period, so the last 30 days costs one call, not thirty. Call results need one ERP
call per working day, so only the latest 7 working days of the period are read.

## The people table

Every active agent (the same list the project and task pickers use). Last activity looks back
90 days over tasks completed, timer sessions and stand-ups written. Salespeople's quiet flag
comes from the ERP activity instead of tasks. Default order: quiet people first, then by name.

## Weekly digest

Monday 09:00 (`helpdesk.adoption.send_weekly_digest`, hooks.py). For each person who may open
the page, last week's report is built as them and the five most important findings that are
not good news go out through the follow-up digest channel (`follow_ups.deliver_digest`: chat
when it is set up, else email), each with its action hint and a link, and a last link to the
page. Nothing is sent when there is no bad news.

The switch is **Weekly adoption digest** in Settings → Follow-ups (`HD Follow Up Settings`,
`adoption_digest`, on by default; patch `v16_0_2.enable_adoption_digest` turns it on where the
settings were already stored). It also needs follow-ups themselves to be on.

## Files

- `helpdesk/adoption.py`, `helpdesk/api/adoption.py`, `helpdesk/hooks.py` (Monday job)
- `helpdesk/api/auth.py` (`can_see_adoption` in the boot), `helpdesk/helpdesk/doctype/hd_follow_up_settings/`
- `desk/src/pages/work/Adoption.vue`, `adoptionMeta.ts`; route `/adoption`; sidebar entry and a
  button on Team for those allowed
