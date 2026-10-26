# Leads

Status: Phase 1 implemented (list, new lead, lead page with stage, notes, edit and read-only
quotations), the **Overview** (2026-10-19), the **daily new-lead target**, **where each lead
stands on its row** and **Proposals & money** on the Overview (2026-10-24) and the **Daily report** (2026-10-26), and proposals with the segment rate card in
[proposals.md](proposals.md). This document is the source of truth for the feature and changes
with it.

## Why it works this way

The owner's decision (2026-10-16): Frappe CRM is being removed from the ERP site
(india.teambackoffice.com, the same site as tboindia.tbocloud.in). ERPNext's **Lead** becomes
the system of record there, and sales leads are created and worked **in the hub**.

The hub keeps **no copy** of a lead. The Leads page reads and writes live, through the CRM
connection in Settings → CRM (HD CRM Settings: site URL, API key and secret), against TBO
Smart's hub leads API on the ERP site. So there is nothing to sync, nothing to go stale, and
ERPNext's own rules (visibility, stages, validation) apply to every change.

The hub never gets ERPNext installed.

## Who sees it

- **Off by default.** Settings → CRM → Leads → *Show the Leads page* (`enable_leads`), and the
  CRM connection must be enabled too.
- **For these teams** (`leads_teams`, HD Team names one per line, ticked in Settings): only
  active agents in an enabled ticked team see Leads. None ticked: every active agent.
  System Managers and Agent Managers (and Administrator) always do, and so does every active
  **Sales Employee**, whatever their team.
- **Never the Digital team:** anyone with a content or DM role (Content Team, Digital
  Marketing Head, DM Coordinator, DM Employee) doesn't see Leads, Agent Managers included,
  unless they're also a System Manager or a Sales Employee.
- **Salespeople see only the sales screens:** an agent with the Sales Employee role
  (Settings → Agents → Department wall → Sales team) gets Leads, the Scoreboard,
  notifications and Help, and no tasks, projects, tickets or content; Home opens Leads →
  Overview for them, and their documents chain stops at the client documents (the Project
  and UAT steps don't open). The full rules are in
  [departments.md](departments.md#sales-wall-sales-employee).
- The check is `helpdesk.integrations.crm.leads.can_use_leads`; `helpdesk.api.auth.get_user`
  sends it as `can_use_leads`, which shows the sidebar item and lets the router open
  `/helpdesk/leads`. Every endpoint checks it again on the server.
- On the ERP site, the person also needs a User with **Sales User** or **Sales Manager**.
  The CRM user sync gives agents that role ([tbo-crm-integration.md](tbo-crm-integration.md)).

## The ERP site's API (TBO Smart)

Whitelisted methods at `tbo_smart.api.hub_leads.<name>`, called with the hub's API key.
Every call carries `acting_user` = the hub session user's email; the ERP site checks that
user exists there with a sales role, applies what they may see, and records writes as them.

| Method | HTTP | Arguments | Returns |
| --- | --- | --- | --- |
| `get_options` | GET | | `{stages: [{name, label, type, color}], sources, segments, owners: [{email, full_name}], territories, industries, can_call}` |
| `list_leads` | GET | `search, stage, owner, segment, source, temperature, metric, period, from_date, to_date, view, start, page_length` | `{rows: [{name, lead_name, company_name, email_id, mobile_no, tbo_stage, segment, lead_owner, owner_name, score, next_follow_up, modified, latest_quotation, latest_proposal}], total}` |
| `get_overview` | GET | `period, from_date, to_date, owner` | the Overview's figures (TBO Smart's `hub-leads-api.md` §2.4) |
| `get_lead_intake` | GET | `from_date, to_date` (the hub sends yesterday and today) | new leads taken each day by owner, imports left out, and the scope's salespeople (§2.4.1) |
| `get_proposal_money` | GET | `period, from_date, to_date, owner` | proposals sent, won, advances and every payment split still to collect (§2.8) |
| `get_daily_report` | GET | `date, owner` | each salesperson's day and week to date (§2.5.1) |
| `log_call` | POST | `lead, outcome, note` | `{name, status, outcomes}` (§2.7) |
| `get_lead_ai` | GET | `name` | what the AI proposes, the lead's health and likely duplicates (TBO Smart's `hub-leads-api.md` §2.6) |
| `refresh_lead_ai`, `apply_ai_stage`, `dismiss_ai_stage` | POST | `name` | as above, or the lead (apply) |
| `draft_lead_message` | POST | `name, channel (whatsapp / email), language` | `{channel, subject, text, to?, url?}`; nothing is sent |
| `log_message_sent` | POST | `name, channel, text` | the timeline entry |
| `get_sales_activity` | GET | `from_date, to_date`, **no** `acting_user` | each salesperson's activity, for the Scoreboard ([team-dashboard.md](team-dashboard.md#sales)) |
| `get_lead` | GET | `name` | `{lead: {...}, timeline: [...], quotations: [...], proposals: [...], allowed_stages: [...]}` |
| `create_lead` | POST | `data` | the lead (at least `name`) |
| `update_lead` | POST | `name, data` | the lead |
| `set_stage` | POST | `name, stage, note` | the lead |
| `add_note` | POST | `name, note` | the note |

- `metric` (`new`, `intake`, `contacted`, `meetings`, `quotations`, `won`, `lost`, `stale`,
  `overdue`, `hot`, `open`, and the AI's `high_intent`, `unhappy`, `stage_suggested`) keeps
  the leads one Overview number counts; `period` (`week`, `month`, `quarter`, `custom` with
  `from_date` and `to_date`) goes with it and is sent only with a metric. The hub's own
  `today` and `yesterday` periods go to the ERP site as a one-day `custom` range, so an older
  TBO Smart answers them too (`erp_period` in `helpdesk/api/leads.py`).
- `latest_quotation` (`{name, tbo_quote_status, grand_total, currency, tbo_sent_on}`) and
  `latest_proposal` (`{name, document_type, status, view_count, sent_on}`) say where a lead
  stands with the client; an older TBO Smart leaves them out and the row shows only the stage.
- `view` is `all`, `mine`, `call_today` or `follow_up`. The hub sends `page_length` 20
  (at most 100) and `start` from 0.
- `data` (create and update) uses these keys: `lead_name, company_name, email_id, mobile_no,
  source, segment, territory, industry, lead_owner, next_follow_up` (date, `YYYY-MM-DD`).
  An update sends only the fields that changed; an empty string clears a field.
- `allowed_stages` may be stage names or stage objects; the hub offers only those (minus the
  current stage).
- Timeline entries are TBO Smart's `{kind, at, who, who_name, text, ref}` (kind: note, call,
  activity, meeting, stage, quotation, proposal, and ai: what TBO AI did, with a bot icon),
  newest first; each kind has its own icon and a screen reader label, and `text` is shown as
  sent (a stage move reads "Contacted → Proposal Sent").
- Quotations are read as `{name, transaction_date, tbo_quote_status, grand_total, currency}`.
- Proposals are read as `{name, title, status, revision_no, view_count, …}` (empty while
  Proposals is off on the ERP site; [proposals.md](proposals.md)).
- A lead's `segment` sets its discount band, so once it has one only the people who edit
  quotation presets and prices on the ERP site move it to another; the Edit dialog shows the
  ERP site's reason otherwise.
- `next_follow_up` on create or update schedules a Sales follow-up for the lead owner on the
  ERP site (tbo_smart#25); clearing it adds nothing and doesn't close the open one.
- Stage colours from the ERP site are not used, to keep the hub's one-accent rule: a stage
  whose `type` is `Won` is green, `Lost` red, every other stage gray, always with its label.

## Calls through MyOperator

Telecallers' calls go through MyOperator, set up on the ERP site (TBO Smart's
`docs/telephony-myoperator.md`, which also lists the owner's setup steps in MyOperator).
The ERP site's `tbo_smart.api.telephony` takes the same `acting_user`:

| Method | HTTP | Arguments | Returns |
| --- | --- | --- | --- |
| `click_to_call` | POST | `lead, number` (one of the lead's own numbers; blank: the first of its mobile, phone and WhatsApp) | `{ok, message, number, reference_id}`: MyOperator rings the person's phone, then the lead |
| `call_recording` | GET | `call` | the recording (audio), only to someone who may read the lead |
| `get_settings`, `save_settings`, `test_connection`, `regenerate_webhook_secret` | GET / POST | `values` (save) | the MyOperator settings (System Managers on the ERP site); secrets never come back, a new webhook secret once |

- `get_options` and the lead's `can_call` say whether the signed-in person may use **Call**
  (telephony on and they are mapped to a MyOperator user or mobile on the ERP site).
- A call timeline entry that came through MyOperator adds `call, duration` (talk seconds),
  `direction` (incoming / outgoing), `status` (answered / missed / voicemail), `recording`
  (the call's name, or null) and `summary` (TBO AI's `{text, interest, intent, objections,
  next_step, language}`, or null). The transcript never leaves the ERP site.
- Hub: `helpdesk.api.leads.click_to_call` (POST) and `call_recording` (GET, streams the ERP
  site's file through `CRMClient.download`, served inline as audio), and
  `helpdesk/api/myoperator.py` for the settings (hub admins and managers who use leads; the
  ERP site checks its own System Manager role).

## Hub endpoints

`helpdesk/api/leads.py`, thin typed proxies (writes are POST only): `get_options`,
`list_leads`, `get_overview_page`, `get_overview`, `get_lead_intake`, `get_proposal_money`, `get_lead`, `get_lead_ai`, `refresh_lead_ai`, `apply_ai_stage`,
`dismiss_ai_stage`, `draft_lead_message`, `log_message_sent`, `create_lead`, `update_lead`,
`set_stage`, `add_note`, `click_to_call`, `call_recording`, `get_daily_report`, `log_call`. They check
`can_use_leads`, validate the view and page size, trim notes, and pass `acting_user`. The
client is `CRMClient.call` in `helpdesk/integrations/crm/client.py`; the call and error
mapping live in `helpdesk/integrations/crm/leads.py`. The API key and secret never reach the
browser.

### How the Overview loads

One request: `get_overview_page` reads the overview, the proposals and money and the intake
from the ERP site one after another and answers `{overview, money, intake, errors}`. Money and
intake are optional: one that fails (or an ERP site too old to have it) leaves the overview
whole, with its message in `errors` for the section's own error state. Only a failed overview
fails the page. The list view asks `get_lead_intake` on its own; `get_overview`,
`get_proposal_money` and `get_lead_intake` stay as they were.

Why: the hub and the ERP site share one Frappe Cloud bench, so one gunicorn worker pool. Four
parallel hub requests each held a worker while waiting for the ERP site, which needed a worker
from the same pool: all of them waited and timed out after 20 s ("Couldn't reach the ERP
site"). One request at a time needs one worker at a time.

Reads are also kept in Redis (`frappe.cache`), per signed-in person, key
`hd_leads:<user>:<part>:<params>`: overview, money and intake for 60 s, `get_options` for
10 minutes. Only successful answers are kept (not an error, not "older ERP site"); the intake's
daily target is read live. The refresh button and "Try again" send `fresh=1`, which skips the
copy and renews it. Creating or updating a lead, moving its stage, and creating or sending a
proposal clear the signed-in person's copies; other people's age out within a minute.

### Errors people see

| What happened | Message |
| --- | --- |
| No connection saved | Leads aren't connected yet. Ask an admin to set up Settings → CRM. |
| ERP site unreachable or timed out | Couldn't reach the ERP site (host). Try again in a minute. |
| 401 | The ERP site refused the hub's API key. Ask an admin to check Settings → CRM. |
| 403 saying only the hub's integration user may act for someone else | The hub's API user (email, when the ERP site says who the key belongs to) on (host) isn't the site's integration user: it needs the role in TBO Smart Settings → Hub integration role there (blank: Hub Integration). Ask an admin to add the role that field names to that user. |
| 403, 404 or 417 saying the method isn't there or isn't whitelisted | Leads need the latest TBO Smart on the ERP site (host). |
| Any other 403 | You don't have a sales account on the ERP site yet. Ask an admin to give (email) the Sales User role on (host). |
| Any other 404 | That lead isn't on the ERP site any more, or you can't see it. |
| Other 4xx with a message | The ERP site's own message (e.g. a missing field, a stage it refuses); never its exception text. |
| 5xx, or a 4xx with only an exception | The ERP site ran into a problem (status). Try again; if it keeps happening, tell an admin. |

Setup and reach problems are `LeadsUnavailableError`, the rest `LeadsError` (both
ValidationError, so the page shows the message with *Try again*). A method the ERP site's
TBO Smart doesn't have yet is `LeadsNotDeployedError` (a `LeadsUnavailableError`).

**Newer parts on an older ERP site:** `get_lead_intake` and `get_proposal_money` go through
`call_if_deployed`, which answers `None` for `LeadsNotDeployedError` and drops the queued
message, so the endpoints return `{available: false}` and the page leaves the strip, the
Created filter and Proposals & money out without a toast. The list row's status chip simply
doesn't show without its fields. The hub can be deployed before TBO Smart.

## The pages

- **Overview** (the first tab, where `/helpdesk/leads` opens; `LeadsOverview.vue`): one calm
  page for the person's leads (their own, their team's or everyone's, as the ERP site's sales
  rules give them). Its job: see where the pipeline stands and what needs a person now.
  - **Period** (Today, Yesterday, This week, This month, This quarter, Custom with from and
    to dates) and, for
    a team lead or a manager, **Owner** ("My team" / "Everyone" or one person). Both are in
    the URL (`period`, `from`, `to`, `owner`).
  - **This period**: New leads, Contacted, Meetings held, Proposals sent, Won (with its
    value), Lost. **Needs attention** now: Overdue follow-ups (red), Gone quiet (no touch for
    the ERP site's stale days, amber), Hot leads.
  - **Pipeline now**: every open stage with its leads and their latest quotations' value, as
    neutral bars (Won and Lost only when they have leads). **Funnel**: of the period's new
    leads, how many got to Contacted, Meeting, Proposal and Won, with the win rate. **Why
    leads were lost** (top five). **Hot leads** (the six best, each opens the lead). **By
    owner** (new, contacted, meetings, proposals, won, open), **By segment** and **By
    source** (new, open, won).
  - **Every number opens its leads**: a tile, a stage, an owner's or a segment's number
    goes to the list with `metric` and the period (or a stage, owner, segment or source
    filter); the list shows what it was opened with ("Won, this month") and *Clear filters*
    drops it.
  - States: skeleton while loading, error with Try again, "Pick both dates" for an
    unfinished custom period, an empty line in each panel with nothing to show.
  - Colour: one brand accent (the selected period); green only for Won, red only for
    overdue, amber for gone quiet, each with its icon and label. No other colour.
  - **Proposals & money** (`LeadsMoney.vue`, under Pipeline and Funnel, read by its own
    `get_proposal_money` with the same period and owner): four tiles, *Proposals sent* (their
    value, how many; opens the Proposals sent list), *Won* (value, leads), *Advances received*
    in the period, and *Still to collect* (with what is overdue); a note when proposals went
    out without a price. **Expected by month**: overdue (red, with its icon), this month and
    the next five, later, and *On milestone* (splits without a date), as neutral bars with
    the amounts. **Payment splits**: each split still being collected, by due date (a button
    flips soonest / latest first): client (and owner, for a team view), the split's label and
    %, its sales order or quotation, due date or *On milestone*, status and amount (what is
    left, "of" the split when part came in). Status: *Received* (green, check), *Overdue*
    (red, calendar-x), *Due* within a week (blue, calendar-clock), *Upcoming* (gray). Eight
    rows, then *Show all*. Each row opens the lead. How the ERP site finds the splits and
    what came in is in TBO Smart's `hub-leads-api.md` §2.8: a sales order's schedule (paid
    in due order from its advances and invoices), else the latest sent or accepted
    quotation's, else the proposal's Payment Terms milestones as % of the total with no
    date. A failed read shows an inline error with *Try again*, never a toast.
  - Money is formatted by `money()` (`components/invoicing/invoices.ts`): rupees group the
    Indian way (₹1,55,000) whatever the browser's language, without paise in summaries.
  - **Your plan for today** (with **AI runs leads** on the ERP site, TBO Smart Settings): the
    person's follow-ups due, Call today and hot leads, each with the AI's next step and its
    day; a manager who picks an owner sees theirs. Its header counts the open leads the AI
    read as high intent, unhappy, and with a stage move waiting for a person; each count
    opens those leads.
- **New leads taken** (`LeadIntakeStrip.vue`, under the tabs on every tab): the owner wants
  each salesperson to take a number of new leads a day (Settings → CRM → Leads → *Daily
  new-lead target per salesperson*, `daily_lead_target`, 0 = no target). Two halves, Today
  and Yesterday: the total new leads (mono) and a chip per salesperson in the person's view,
  "Shahana 7 / 10" (just the count without a target), most first; someone who took none
  shows 0. Only the **sales team** gets a chip (the hub's enabled users with the Sales
  Employee role, set in Settings → Agents → Department wall → Sales team; the ERP site
  lists everyone with a sales role, which is every agent here), plus anyone else who took
  a lead that day. The header total stays the ERP site's real total. With no sales team
  yet, only people with leads show; with none, "No new leads yet today", and managers also
  see "Pick your salespeople in Settings → Agents → Department wall → Sales team"
  (`team_empty` in the answer). The filter runs after the cached ERP read. Reaching the target is a green check and green count with "target met" for
  screen readers; short of it stays neutral (no red: it isn't a failure to shame). Leads
  copied in from the old CRM don't count. The total and every chip open the list of exactly
  those leads (`metric=intake`, `period=today|yesterday`, `owner`). Skeleton while loading;
  left out quietly when the ERP site is older or the read fails.
- **Leads** list (the other tabs, `desk/src/pages/leads/Leads.vue`): views All, Mine, Call
  today and Follow-up; search (debounced) and stage, owner, segment and **Created** filters
  (Any time, Today, Yesterday, This week, This month, Custom with from and to dates; it is
  the `intake` metric with its period, so it replaces a number the Overview opened the list
  with; shown once the ERP site counts it); 20 a page with Previous and Next. View, search,
  filters and page are in the URL. Rows show the name, stage, **where the lead stands with
  the client** (one chip: the proposal's status, else the quotation's, with its value and how
  long ago it went, e.g. "Proposal sent · ₹1,55,000 · 3 days ago", "Viewed 2× · …";
  Accepted green, Declined, Rejected and Expired red, everything else gray, always as words),
  company, segment, mobile or email, the next follow-up (red with an icon once it's past),
  the owner and the score; on a phone they wrap into two-line cards. States:
  loading skeleton, error with Try again, "No leads match" when filtered to nothing, "No
  leads yet" on first use.
- **New lead** (`LeadFormDialog.vue`, the one primary action on the list): contact name
  (required), company, email, mobile, source, segment, territory, industry, owner (defaults
  to you on the ERP site) and next follow-up. Opens the new lead when it's created.
- **Lead** (`/helpdesk/leads/<name>`, `Lead.vue`): details, *Move stage* (the primary
  action; only `allowed_stages`, with an optional note), *Edit* (the same dialog, sending
  only changed fields), a note composer and the timeline, and the quotations read-only
  (`LeadQuotations.vue`).
- **AI suggests** on the lead page (`LeadAISuggests.vue`, its own component under Details):
  - the AI's summary, sentiment and intent (badges with icons; an unhappy customer amber),
    the phrases that show it, and the **next step** with its channel and day (already the
    follow-up when nothing else was planned);
  - a **stage to move to** with its reason: *Move to …* (a person's click; the ERP site
    records them) or *Dismiss*. The AI never suggests Won or Lost;
  - a **message to send**: the stored draft, or *Draft a message* (WhatsApp or Email). The
    person edits it, *Open in WhatsApp* / *Open in mail* opens their own app with the text,
    they press Send there, then *I sent it* logs it on the lead. **Nothing is sent from the
    hub or the ERP site;**
  - *Read the lead again* (once a minute), and when the lead changed since the last read the
    header says so;
  - **Lead health** (Healthy / Watch / At risk with the reasons) and **Maybe the same
    customer** (other leads with the same phone, email or company), which work with AI runs
    leads off too (the block is then titled *Lead health*).
  - States: loading lines, an error with Try again, "hasn't read this one yet" with *Read it
    now*, and a note when no AI provider is set up.
- **Call** (MyOperator, when `can_call`): a button in the lead's header (on a phone, Call and
  Edit show as icons, named by their `label`) and a phone button on each list row with a mobile
  (outside the row's link; all of them wait while one call is being placed). It toasts "MyOperator is calling your
  phone…", or the ERP site's reason (not set up, no number, MyOperator refused).
- **Calls on the timeline**: a MyOperator call shows "Incoming call" / "Outgoing call" with its
  talk time (mono), or "Missed call" / "Unanswered call" in red with the phone-missed icon; the
  direction is its icon. A recording plays in an audio player (`preload="none"`), streamed by
  `call_recording`. The AI summary is a collapsed `<details>` (its first line, "TBO AI"),
  opening to what was discussed, interest, intent, concerns, the next step and its day, and
  the language (`LeadCallEntry.vue`).
- **Settings → Telephony → MyOperator** (`MyOperatorSettings.vue`; the Telephony page opens
  on it when the telephony app isn't installed): the switch, company ID, IVR and caller ID,
  the three keys (`SecretField`: saved ones are never shown), *Test connection* (lists
  MyOperator's users, used to pick each person's MyOperator user), the **webhook URL with a
  copy button, the header and the events** to paste into MyOperator, *Make a new secret*
  (asks first; the new secret shows once, with Copy), the people mapping, unknown callers,
  recordings (days kept, the recording notice for the IVR greeting under the DPDP Act) and
  the AI call summary.
- The pickers' options (`get_options`) are fetched once per session (`leadOptions` in
  `desk/src/pages/leads/leads.ts`).
- Sidebar: *Leads* in Workspace (teal group), shown when `can_use_leads`.

## Daily report

The Leads page's **Daily report** tab (next to Overview; `LeadsDailyReport.vue`,
`DailyReportCard.vue`, `TargetRing.vue`) is the Sales Manager's Daily Sales Performance
Report, read live from TBO Smart's `get_daily_report` (`tbo_smart.api.hub_leads`, tbo_smart#49).
It shows **only when the ERP site has it**: `get_options` answers `has_daily_report` (and
`can_log_call`) from one probe, kept ten minutes once it is there, and the tab is left out
without a message until then. The ERP site counts the day; **the hub holds the targets and
compares**. Every metric's exact definition (what a call, a fresh lead, a follow-up lead, a
positive lead, a new quotation and a new lead are) is in TBO Smart's `docs/hub-leads-api.md`
§2.5.1 and §2.7.

- **Endpoint** `helpdesk.api.leads.get_daily_report(date, owner, fresh)`: one hub request,
  one ERP call, kept per person for 60 s like the Overview's reads (`fresh=1` skips it). It
  answers `{available, date, week_from, currency, people, targets, working_days, team_text}`;
  each person also gets `pace`, `behind`, `on_track` and `text`. `available: false` for an
  older ERP site (nothing queued for a toast, not remembered). A salesperson gets only
  themselves, a Sales Manager everyone; an `owner` out of scope is the ERP site's refusal.
- **Targets** (Settings → CRM → Leads, `HD CRM Settings`): `daily_lead_target` 10 qualified
  new leads a day, `weekly_meeting_target` 10, `weekly_proposal_target` 5 and
  `weekly_follow_up_target` 40 (0 = no target). The week's lead goal is the day's target
  times the week's working days.
- **Pace**: each weekly target is pro-rated by the working days gone, Monday to the day
  (`working_day_checker` in `helpdesk/recurrence.py`: the weekly off, Saturdays off and the
  hub's holidays are not working days; Monday to Saturday otherwise), of the week's working
  days. A person is *On track* when each metric is at or above that share, else *Behind by
  N meetings* (rounded up), one chip per metric behind. Quiet colour only: warning, never red.
- **Who is listed**: the same sales-team rule as the New leads strip
  (`content_team.only_sales_team`): sales-team members, plus anyone with a figure that day,
  plus the person picked (`owner`) and, for a non-manager, themselves. It also decides the
  team text and the 6 pm message. With no sales team the empty state tells managers where to
  pick one (`team_empty`).
- **Team view** (a manager, nobody picked): one row per salesperson: calls (and how many
  connected), fresh, follow-up, positive, quotations (count and value), new leads and the
  pace chips; a row opens that person's card. A salesperson, or anyone who picks a person,
  gets the **person card** in the owner's template order: header "Daily sales performance ·
  date · name"; Daily call performance (Total calls made, Fresh leads, Follow-up leads,
  Positive leads with names, New quotations with count, value and items, each opening the
  lead); New leads generated (total and a numbered list, each opening the lead); This week vs
  target (a ring per metric, with On track or Behind by N). The day (with previous and next
  day) and the person are in the URL (`date`, `person`). States: skeleton, error with Try
  again (a failed refresh keeps the last numbers), no salespeople in view.
- **Copy for WhatsApp** (and **Copy team report**) copies the plain text the hub writes
  (`helpdesk/daily_sales_report.py`, the same text the 6 pm message uses), with a
  fallback field when the browser refuses the clipboard. One person:

```
📊 DAILY SALES PERFORMANCE REPORT
📅 Date: 26 Oct 2026
👤 Employee Name: Shahana V K

📞 1. Daily Call Performance
• Total Calls Made: 32
• Fresh Leads: 8
• Follow-up Leads: 14
• Positive Leads: 3
• New Quotations: 2

🎯 2. New Leads Generated
• Total New Leads: 7
• Lead Names:
1. Asha Traders
2. ...
```

  An empty list is "—". The team text is one block per person, a line between them.
- **6 pm summary**: `helpdesk.daily_sales_report.run`, cron `0 18 * * *` (site time),
  behind *Send the Daily Sales Report at 6 pm* (`send_daily_sales_report`, on by default).
  On working days only, each enabled user with the Sales Manager or System Manager role who
  can use Leads gets **one message** with the team's day as they see it on the ERP site
  (chat when set up, else email, as the follow-up digest: `deliver_digest`). A manager the
  ERP site refuses is skipped, one failure doesn't stop the rest, and the whole run is
  silent while the ERP site is older.
- **Log call** (`LogCallDialog.vue`, `helpdesk.api.leads.log_call(lead, outcome, note)`,
  POST): a *Log call* button on the lead page beside Call, for calls made outside
  MyOperator: Connected, No answer, Busy or Voicemail and an optional note; the ERP site
  records an outgoing call as the signed-in person, which counts in the report. Shown only
  with `can_log_call`; the person's cached reads are cleared after it.
- **Colour**: this tab is colourful on the owner's request, an exception recorded in
  [ui-guidelines.md](ui-guidelines.md) §8.

## Proposals

The Lead page's **Proposals** section, the proposal builder and Settings → Rates and proposals
are specified in [proposals.md](proposals.md).

## Tests

`helpdesk/tests/test_leads.py` with `test_utils.FakeCRM` (`lead_answers`, `lead_calls`,
`lead_error`) and `test_utils.enable_leads`: off by default, `acting_user` on every call,
writes posted, view and page size checked, teams and inactive agents gated, and each error
mapped; the Overview's period checks and the metric with its period passed to the list; today and
yesterday sent as one-day custom ranges; the intake with the daily target (a negative one is
none); the money read for the period and owner; an older ERP site hides both quietly (no
message queued) while other errors still show; the
AI calls are the signed-in person's (POST for every change) and the channels checked.
The one-request Overview page (all parts, money or intake failing alone, cache hit, `fresh`,
per-person cache, a write clearing it) is tested there too.
`helpdesk/tests/test_sales_wall.py`: a Sales Employee outside the Leads teams lists, opens,
creates, moves and notes a lead as themselves.
`helpdesk/tests/test_daily_sales_report.py`: the report proxied as the person, targets and
pace (pro-rated by working days, zero targets left out), the exact WhatsApp text, the cache
(`fresh`, another day, a logged call clearing it), an older ERP site hiding it quietly,
`log_call`, and the 6 pm job (one message per manager, not on a day off, not when the setting
is off, silent on an older ERP site, a refused manager skipped).
`helpdesk/tests/test_lead_calls.py`: Call posted as the signed-in person to TBO Smart's
telephony API, the recording streamed (audio only) and a refusal refused, the MyOperator
settings for admins only and proxied.
