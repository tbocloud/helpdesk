# Leads

Status: Phase 1 implemented (list, new lead, lead page with stage, notes, edit and read-only
quotations), the **Overview** (2026-10-19), and proposals with the segment rate card in
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
  System Managers and Agent Managers (and Administrator) always do.
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
| `list_leads` | GET | `search, stage, owner, segment, source, temperature, metric, period, from_date, to_date, view, start, page_length` | `{rows: [{name, lead_name, company_name, email_id, mobile_no, tbo_stage, segment, lead_owner, owner_name, score, next_follow_up, modified}], total}` |
| `get_overview` | GET | `period, from_date, to_date, owner` | the Overview's figures (TBO Smart's `hub-leads-api.md` §2.4) |
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

- `metric` (`new`, `contacted`, `meetings`, `quotations`, `won`, `lost`, `stale`, `overdue`,
  `hot`, `open`, and the AI's `high_intent`, `unhappy`, `stage_suggested`) keeps the leads one Overview number counts; `period` (`week`, `month`, `quarter`,
  `custom` with `from_date` and `to_date`) goes with it and is sent only with a metric.
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
| `click_to_call` | POST | `lead, number` (one of the lead's own numbers; blank: its mobile) | `{ok, message, number, reference_id}`: MyOperator rings the person's phone, then the lead |
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
`list_leads`, `get_overview`, `get_lead`, `get_lead_ai`, `refresh_lead_ai`, `apply_ai_stage`,
`dismiss_ai_stage`, `draft_lead_message`, `log_message_sent`, `create_lead`, `update_lead`,
`set_stage`, `add_note`, `click_to_call`, `call_recording`. They check
`can_use_leads`, validate the view and page size, trim notes, and pass `acting_user`. The
client is `CRMClient.call` in `helpdesk/integrations/crm/client.py`; the call and error
mapping live in `helpdesk/integrations/crm/leads.py`. The API key and secret never reach the
browser.

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
ValidationError, so the page shows the message with *Try again*).

## The pages

- **Overview** (the first tab, where `/helpdesk/leads` opens; `LeadsOverview.vue`): one calm
  page for the person's leads (their own, their team's or everyone's, as the ERP site's sales
  rules give them). Its job: see where the pipeline stands and what needs a person now.
  - **Period** (This week, This month, This quarter, Custom with from and to dates) and, for
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
  - **Your plan for today** (with **AI runs leads** on the ERP site, TBO Smart Settings): the
    person's follow-ups due, Call today and hot leads, each with the AI's next step and its
    day; a manager who picks an owner sees theirs. Its header counts the open leads the AI
    read as high intent, unhappy, and with a stage move waiting for a person; each count
    opens those leads.
- **Leads** list (the other tabs, `desk/src/pages/leads/Leads.vue`): views All, Mine, Call
  today and Follow-up; search (debounced) and stage, owner and segment filters; 20 a page
  with Previous and Next. View, search, filters and page are in the URL. Rows show the
  name, stage, company, segment, mobile or email, the next follow-up (red with an icon once
  it's past), the owner and the score; on a phone they wrap into two-line cards. States:
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
- **Call** (MyOperator, when `can_call`): a button in the lead's header and a phone button on
  each list row with a mobile (outside the row's link). It toasts "MyOperator is calling your
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

## Proposals

The Lead page's **Proposals** section, the proposal builder and Settings → Rates and proposals
are specified in [proposals.md](proposals.md).

## Tests

`helpdesk/tests/test_leads.py` with `test_utils.FakeCRM` (`lead_answers`, `lead_calls`,
`lead_error`) and `test_utils.enable_leads`: off by default, `acting_user` on every call,
writes posted, view and page size checked, teams and inactive agents gated, and each error
mapped; the Overview's period checks and the metric with its period passed to the list; the
AI calls are the signed-in person's (POST for every change) and the channels checked.
`helpdesk/tests/test_lead_calls.py`: Call posted as the signed-in person to TBO Smart's
telephony API, the recording streamed (audio only) and a refusal refused, the MyOperator
settings for admins only and proxied.
