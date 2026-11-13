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
- Staff who may not see Leads still get the Lead Bank (`can_use_lead_bank`, [lead-bank.md](lead-bank.md)): Add a lead and My leads only.
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
| `get_options` | GET | | `{stages: [{name, label, type, color}], sources, segments, owners: [{email, full_name}], territories, industries, org_sizes, states, kerala_districts, districts_by_state, can_call, departments: [{name, lead_type, is_active, is_head, is_member}], lead_types}` (the last two from the departments release of TBO Smart) |
| `list_leads` | GET | `search, stage, owner, segment, department, industry, state, district, org_size, product, last_call_result, last_reply_class, source, temperature, metric, period, from_date, to_date, view, start, page_length` | `{rows: [{name, lead_name, company_name, email_id, mobile_no, tbo_stage, segment, lead_owner, owner_name, score, next_follow_up, modified, latest_quotation, latest_proposal, tbo_department, tbo_lead_type, product, industry, state, district, org_size}], total}` |
| `get_category_counts` | GET | | `{industry, state, district, org_size, product}`, each `{value: leads}` (TBO Smart v1.14, `hub-leads-api.md` §2.14) |
| `add_industry` | POST | `name` | `{name, created}`; managers only |
| `bulk_set_lead_category` | POST | `leads, values` | `{updated, skipped}`; managers only (a department head may set `product`) |
| `get_overview` | GET | `period, from_date, to_date, owner` | the Overview's figures (TBO Smart's `hub-leads-api.md` §2.4) |
| `get_lead_intake` | GET | `from_date, to_date` (the hub sends yesterday and today) | new leads taken each day by owner, imports left out, and the scope's salespeople (§2.4.1) |
| `get_overview_page` | GET | `period, from_date, to_date, owner` | the Overview, its money, the intake and the analysis in one request (see *How the Overview loads*) |
| `get_proposal_money` | GET | `period, from_date, to_date, owner` | proposals sent, won, advances and every payment split still to collect (§2.8) |
| `get_daily_report` | GET | `date, owner` | each salesperson's day and week to date (§2.5.1) |
| `log_call` | POST | `lead, outcome, note, callback_at` | `{name, status, outcomes, stage}` (§2.7, §2.16) |
| `get_my_calls`, `get_next_batch`, `record_call_outcome`, `get_call_batches_report` | GET, POST, POST, GET | see [Today's calls](#todays-calls) | TBO Smart's `hub-leads-api.md` §2.13 |
| `get_call_plans`, `save_call_plan`, `get_department_leads`, `assign_leads`, `unassign_leads` | GET, POST, GET, POST, POST | `department, users, product, industry, district, sizes, clear` (save); `department, owner, product, industry, district, search, start, page_length`; `department, user, leads or count + product, industry, district`; `department, leads` | see [Assign leads](#assign-leads), TBO Smart's `hub-leads-api.md` §2.23 (v1.23) |
| `estimate_prospect_run`, `start_prospect_run`, `get_prospect_runs`, `get_prospect_run` | POST, POST, GET, GET | `values: {industry, state, districts, provider, max_results, department, require_phone}`; `name` | a run and its price, the started run, the runs, one run with its leads; see [Find prospects](#find-prospects), TBO Smart's `hub-leads-api.md` §2.15 |
| `get_lead_ai` | GET | `name` | what the AI proposes, the lead's health and likely duplicates (TBO Smart's `hub-leads-api.md` §2.6) |
| `refresh_lead_ai`, `apply_ai_stage`, `dismiss_ai_stage` | POST | `name` | as above, or the lead (apply) |
| `draft_lead_message` | POST | `name, channel (whatsapp / email), language` | `{channel, subject, text, to?, url?}`; nothing is sent |
| `log_message_sent` | POST | `name, channel, text` | the timeline entry |
| `get_sales_activity` | GET | `from_date, to_date`, **no** `acting_user` | each salesperson's activity, for the Scoreboard ([team-dashboard.md](team-dashboard.md#sales)) |
| `get_lead_departments` | GET | | `[{name, department_name, lead_type, is_active, assignment, stale_after_days, heads: [{user, full_name}], members: [{user, full_name}]}]` |
| `save_lead_department` | POST | `values: {department_name, lead_type, is_active, assignment, stale_after_days, heads: [user], members: [user]}, name` (edit) | the saved department; only System Manager / Sales Manager on the ERP site, others get PermissionError |
| `set_lead_department_active` | POST | `name, active` | the department |
| `get_lead` | GET | `name` | `{lead: {...}, timeline: [...], quotations: [...], proposals: [...], allowed_stages: [...]}` |
| `find_duplicate_leads` | GET | `email, phone, company, exclude` | `[{name, lead_name, company_name, email_id, mobile_no, lead_owner, owner_name, tbo_stage, matched_on: ["email" / "phone" / "company"]}]`, only leads the person may see |
| `get_merge_preview` | GET | `first, second` | `{leads: [Summary, Summary]}`: both leads' name, company, email, numbers, stage, owner, creation and what sits on each (`counts`, `new_numbers`) |
| `merge_leads` | POST | `keep, merge` | the kept lead as `get_lead`; the other lead is deleted. A Sales Manager, System Manager or the head of the leads' department |
| `get_stale_leads` | GET | `days` | `[{name, lead_name, company_name, lead_owner, tbo_department, tbo_stage, last_activity_on, idle_days}]` idle for `days` or more, scoped to the acting user's visibility |
| `create_lead` | POST | `data, allow_duplicate` (1 only after the person confirmed) | the lead (at least `name`); an email another lead has is refused with DuplicateEntryError "Possible duplicate of <lead> (<owner>)" unless `allow_duplicate`; a number another lead has always ("... it already has the number <number>, and a number belongs to one lead.", [One lead per number](#one-lead-per-number)) |
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
- `view` is `all`, `mine` (owned or created), `call_today`, `follow_up` or `called` (called at
  least once, last called first; `from_date` / `to_date` without a `metric` keep the leads last
  called in those days). `mine` keeps any view to the leads the person owns or created, and
  `created_by_me` to the ones they created (whoever owns them now; the ERP site lets them read,
  not change, those). An older TBO Smart ignores both and has no `called`. Each row also brings
  `created_by` and `call_count`. The hub sends `page_length` 20 (at most 100) and `start` from 0.
- `data` (create and update) uses these keys: `lead_name, company_name, email_id, mobile_no,
  source, segment, territory, industry, state, district, org_size, lead_owner, next_follow_up` (date, `YYYY-MM-DD`), and `tbo_department` (a department's name).
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

## Lead departments

Departments (GrowthX, ...) are created in the hub, kept on the ERP site and put on leads:
each has a **lead type** (`ERP / Software` or `Content / Digital Marketing`), **heads** and
**members** (users, by the email both sites share) and an active switch. A head sees every
lead in the department, a member the leads they own; **the ERP site enforces that**, the hub
only filters and shows. The department's type is the lead's type (`tbo_lead_type`).

- **Settings → CRM → Lead departments** (`LeadDepartments.vue`, only for System Managers and
  Agent Managers, once Leads is on): list with type, heads, member count and an active
  switch, and an add/edit dialog (name is fixed once saved; type; heads and members are
  pickers of the hub's agents). If the ERP site refuses (only its System Manager or Sales
  Manager may), its reason shows in the dialog.
- **Leads list:** a Department filter (`department` in the URL) and, on each row, the
  department and its type as plain text.
- **New lead / Edit lead:** a Department picker. A new lead starts in the person's only
  department (they are a head or member of exactly one active department). Once a
  department is picked, its heads and members come first in the Owner picker.
- **Older TBO Smart:** without departments on the ERP site, `get_options` has no
  `departments`, `get_lead_departments` answers `available: false`, and the Settings section,
  the filter and the pickers stay out without an error. Writes then say the ERP site needs
  the latest TBO Smart.
- Hub endpoints: `get_lead_departments` (cached 60 s per person, key part `departments`),
  `save_lead_department`, `set_lead_department_active`; a change clears the signed-in
  person's cached reads (including `get_options`, which carries `is_head` and `is_member`).
  `list_leads` takes `department`. The Overview and Daily report don't filter by department
  yet.

## Products / brands under a department

A department such as GrowthX has sub-teams that sell different things (PhoebiX for solar,
BillaX, WilpeX, PrintagX, Foamia, Avera). Managers list them on the department; each lead can
carry one; callers see which name they are calling under. A department with no products works
exactly as before. TBO Smart holds and enforces everything
([lead-departments.md](https://github.com/tbocloud/tbo_smart/blob/main/docs/lead-departments.md) §10,
`hub-leads-api.md` §2.20); the hub shows and edits it.

- **Settings → CRM → Lead departments → Products / brands**
  (`DepartmentProducts.vue`): add a product, give it a name and one short line to say on the
  call, switch it off. A saved product is switched off, never removed (its leads keep the name);
  renaming it moves its leads. Names are unique in the department. Under *Daily call batches*, a
  **Calls for product** picker gives the next batches only that product's leads (follow-ups due
  still come).
- **Lead form and Details card:** a *Product* picker when the department has products, shown only
  to managers and the department's head (`canSetProduct`; the ERP site refuses anyone else). The
  owner sees the product in Details. Changing the department clears a product it doesn't have.
- **Leads list:** a *Product* filter with counts (`?product=PhoebiX` in the URL, repeatable) and a
  small neutral chip with the product name on each row. Managers' *Set category* has a *Product*
  choice (a lead only takes a product of its own department; the others are listed as left out).
- **Today's calls:** every call shows **Calling for: PhoebiX** with the intro line underneath
  (a lead with no product shows its department's name). The batch header shows *Calls for:
  PhoebiX* while a campaign product is set.
- **Messages:** AI drafts and the WhatsApp first message use the product's name and intro. The
  template's blanks can be `product` and `product_intro` as well as `name`, `company` and
  `why_call` (Settings → TBO Chat); a lead with no product gets TBO and a neutral line.
- **Older TBO Smart:** without products the sections, filter, chip and picker stay out; the
  campaign product is sent only when the ERP site's departments carry `products`.

### How to use (staff)

*Managers*
1. Settings, CRM, Lead departments, pick GrowthX (the pencil).
2. Under **Products / brands** press **Add product**. Type the name (PhoebiX) and a short line
   to say on the call ("PhoebiX – solar ERP for installers"). Add BillaX, WilpeX, PrintagX,
   Foamia, Avera and Solar the same way. Press **Save changes**.
3. To call for one product tomorrow, open the department again and set **Calls for product** to
   PhoebiX, then save. The next batches give each caller only PhoebiX leads.
4. To tag leads: on **Leads**, press **Select**, tick the leads, press **Set category**, choose
   the **Product** and apply. Or open a lead, press Edit and pick the **Product**.
5. To stop using a name, switch it **off**. Its leads keep it; nobody can pick it any more.

*Callers (BDs)*
- Open **Today's calls**. Each call says **Calling for: PhoebiX** and the line to say. A lead with
  no product shows the department's name. Say that name when you introduce yourself.
- You can see a lead's product but only a manager changes it. Ask your manager.

### Wave 1: assignment, duplicates, quiet leads, website form

All of it comes with the wave 1 release of TBO Smart and stays out (no error, no message)
on an older one; every hub proxy asks through `call_if_deployed`.

- **Assignment** (department dialog): *Manual* (the creator picks the owner) or *Round robin*
  (a lead created with no owner is given to the department's next member by the ERP site),
  with a one-line explanation under the select, and *Follow-up alert after N days*
  (`stale_after_days`, default 3). The assignment shows in the department list. In the lead
  form, a Round robin department lets the Owner stay empty, with the hint "Assigned
  automatically (round robin)". The fields show when the ERP site's departments carry
  `assignment`, or when there are no departments yet.
- **Duplicates** (lead form): on leaving the Email or Mobile field (debounced 300 ms) the form
  calls `find_duplicate_leads` and lists matches under the fields: name (opens the lead in a
  new tab), company, owner, stage and what matched. On a new lead, an email match turns the
  button into **Create anyway**, which sends `allow_duplicate=1`; a phone match stops the
  form instead ([One lead per number](#one-lead-per-number)); a company-only match is shown
  but doesn't block. Pressing Create lead before leaving the field checks first and stops to
  show the match. If the ERP site still refuses ("Possible duplicate of ..." about a lead the
  person can't see, so none was listed), the button becomes Create anyway, unless the refusal
  is about the number ("... a number belongs to one lead."). On an edit the matches are only
  shown (`exclude` is the lead itself), except a changed Mobile that another lead has, which
  stops the save.
- **No activity chip** (Leads list): `get_stale_leads` (cached 60 s per person, key part
  `stale`) gives the person's quiet leads; a row shows a warning-toned "No activity N days"
  chip with a clock icon. The hub asks the ERP site for the shortest department threshold
  (the default 3 days for leads with no department) and keeps each lead only when its idle
  days reach its own department's `stale_after_days` (`helpdesk.api.leads.read_stale_leads`).
  The same rows drive the follow-up rule in [follow-ups.md](follow-ups.md#lead-rules).
- **Website lead form** (Settings → CRM, System Managers only, once Leads is on;
  `WebsiteLeadForm.vue`): read-only. It shows the endpoint
  `https://<ERP site>/api/method/tbo_smart.api.hub_leads.submit_website_lead` (guest-callable;
  the hub never calls it) and a copyable HTML form snippet, and a note that emails BCC'd to the
  logging address are filed on the lead's timeline. That address is set on the ERP site, not
  here.

## The lead page and the lead list (2026-11-12 redesign)

Presentation only. **The lead page** (`Lead.vue`): a header with back, `id · department ·
product`, the name, a temperature pill (when the lead carries one), **WhatsApp** (`wa.me`),
**Log call**, **Edit** and the primary **Call**; under it the stage row. Every stage in one row
(sixteen on TBO Smart) left the names too narrow to read, so the row shows only the main path as
steps (`STAGE_PATH` in `leads.ts`): New Lead → Contacted → Meeting → Proposal Sent → Negotiation →
Closed – Won. **Meeting** is one step for Meeting Scheduled and the First, Second and Third Meeting
Completed; while the lead is in one of them the step shows that stage's name. Done steps are
`brand-soft` with a check, the current one `brand` (`aria-current="step"`), later ones gray. Every
other stage (Not Responding, Positive / Interested, Follow-up Required, On Hold, Closed – Lost, Not
Interested, Wrong Number, and any stage the ERP site adds) is a side stage: **Move to…** at the end
of the row lists the ones the ERP site allows from here, and a lead in a side stage shows it as a
"Now" pill (the list's stage tone and icon). Only what the ERP site allows from here moves the
lead: a step opens the Move stage dialog with its first allowed stage picked (the current Meeting
step, the next meeting), and the others stay dimmed but focusable (`aria-disabled`) with the reason
as a tooltip. The dialog itself is unchanged: an optional note, and the ERP site's message when it
refuses a move. A path stage the ERP site doesn't have is left out. On a phone the row is one
**Stage: Contacted** button that opens the same dialog. Left: the AI suggests and WhatsApp cards
and the **Activity** timeline with the add-note box. Right (first on a phone): the duplicate
notice (unchanged: Open and Merge), **Next step** (the follow-up date), **Numbers**
(`LeadNumbers.vue`, old and wrong numbers struck through), **Details**, then place, photos, why
call, quotations and proposals.

**The list tabs** (All, My leads, Call today, Follow-up, Called): one toolbar row of Search,
Stage, Owner, Product (and Created by or Last called where they apply), **More filters** (a
dialog with Segment, Department, Created, Industry, State, District, Organisation size, Last call
and Replied) and **Select leads**. What narrows the list beyond the toolbar shows as removable
chips with **Clear all**. The leads are a table: lead (name, company, department, segment,
category, number, score), stage, owner, product, last call, next follow-up, updated, and the call
button; on a phone the stage, follow-up and owner fold in under the name. Every filter and URL
parameter works as before.

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

## Today's calls

Salespeople used to see every lead at once and cherry-picked, skipping many. For a department
that switches it on (Settings, CRM, Lead departments, *Hand out daily call batches*), each member
is handed a **batch** of leads per time slot and must call them within it. TBO Smart builds the
batches and keeps the outcomes ([call-batches.md](https://github.com/tbocloud/tbo_smart/blob/main/docs/call-batches.md));
the hub shows them. Nothing is stored here.

**The tab.** *Today's calls* is the first tab of Leads for people in a department that hands out
batches, and the page opens on it for Sales Employees. It **replaces Call today** for those people
(an old `?view=call_today` link lands on it): both answer "who do I phone now", so they would be two
places for one job. People without batches keep Call today. Managers who are not members see
neither; they have the batch table on the Daily report.

**The screen (2026-11-12 redesign; presentation only, the data and calls are unchanged).** A
header with the title, the **Calling for** switch (`CallingFor.vue`, a button that opens the same
picker) and a red *N overdue* pill. Left: the batch card (slot, time left, progress bar, called,
contacted, call backs, the product it calls for), then the queue: pending calls first, then the
overdue ones (red pill), each with its number, name, place and reason; picking a row makes it the
current call, and the first one is current by default. Right: the **current call** (`CallRow.vue`):
name and place, a big **Call +91...** button (MyOperator, or the phone's dialler), **WhatsApp**
(a `wa.me` link on the main number), "+N more numbers", the **Say first** block (the product's
intro line, under *Calling for*), the six outcomes in a 3-column grid (2 on a phone) and an optional
note. The note is saved with Not Responding, Busy and Wrong Number, and starts filled in the dialog
the other three open. On a phone the batch card comes first, then the current call, then the queue.
Loading, error ("Try again"), empty ("Nothing left to call in this batch") and a failed refresh
that keeps the last queue are all shown.

**One name for a call and its stage.** The six call answers are labelled with the lead stage they
move the lead to: **Contacted** (Connected), **Not Responding** (Not answered), **Busy**,
**Follow-up Required** (Call back), **Not Interested** and **Wrong Number**: on Today's calls, the
call sheet, Log call, the Last call filter and each lead's last-call chip
(`callBatches.OUTCOMES`). Busy keeps its own name; like Not responding it makes the lead Not
Responding. Only the labels changed: the values the ERP site takes (Connected, Not answered, Call
back, Not interested, Wrong number) are the same, so the names in brackets below are those values. The counts say **contacted** for the answered calls too (Today's calls, the Call batches table, the Daily report, Your calls and the Teams summary; the data keeps `connected`), and a lead moved by hand to a stage that means they spoke (for example Not answered, then Move stage to Contacted) counts as contacted (TBO Smart's `call-batches.md` §5).

**What it shows** (`desk/src/pages/leads/TodaysCalls.vue`):
- the batch header: slot name, time left (a live countdown, a warning icon under 15 minutes),
  *37 / 50 called* with a progress bar, and the day's total;
- the calls to make now, best priority first. Each row has a big **Call** button (MyOperator
  click-to-call when set up for the person, otherwise a `tel:` link), the lead's company, industry,
  district, phone, last note, the AI's next step, why it is in the batch, and six outcome chips;
- **Connected** opens a quick sheet (what was said, the stage to move the lead to, an optional next
  follow-up); **Call back** asks for a date and time (with quick choices); **Not interested** asks
  for a reason (the ERP site moves the lead to Not Interested, no second step). *Not answered*, *Busy* and *Wrong number* save
  at once. The counter drops the moment an outcome is chosen and is put back with the reason if the
  ERP site refuses;
- calls that come back later (a retry two hours after Not answered or Busy, or a call back) wait
  under the list and join it at their time;
- **Get next batch**, disabled with the ERP site's reason in words under it (calls still pending,
  too many overdue, the day's limit reached, no slot open);
- **Overdue** at the bottom: calls of a slot that ended, with a danger icon and the word
  *Overdue*. They stay, and are still callable. The ERP site lists a lead once (its latest missed
  call), so the count is leads, not missed days. A lead comes first in a batch only for a
  follow-up a person set; one the TBO AI scheduled after a call does not bring it back.

States: loading skeleton, error with retry (and a banner that keeps the last queue when an update
fails), an older ERP site, a department without batches, no batch right now (with the next slot),
and nothing left to call. The queue is read again every minute and when the tab comes back, so a
call made through MyOperator or the Log call dialog counts without a tap. It is never cached.

**The Daily report.** For managers and department heads, the team view of the Daily report ends
with a *Call batches* table: per person, the batches (slot called/size), called, connected and
overdue. `get_call_batches_report`; it stays out for anyone else and for an older ERP site. The 6 pm
message lists the same, one line per person and a total, when the ERP site has it.

**Settings.** The department dialog has a *Daily call batches* box: the switch, the slots (name,
from, to, calls; add and remove), calls a day per person, a limit for one person, overdue calls that
block the next batch, pull unassigned leads, and an optional campaign filter (industry, state,
district). The same rules are validated here (no overlaps, an end after the start) and by the ERP
site.

Code: `helpdesk/api/call_batches.py` (proxies; `report_lines` for the 6 pm text),
`desk/src/pages/leads/callBatches.ts` (types, outcome list, optimistic update, rules helpers),
`TodaysCalls.vue`, `CallRow.vue`, `CallOutcomeDialog.vue`, `CallBatchesTable.vue`,
`desk/src/components/Settings/CRM/CallBatchRules.vue`.

## Assign leads

The department's slots hand every member the same number (by default Morning 40, Afternoon 30, Evening 30). On
**Assign leads** (Sales, Team; `/leads/assign`, `AssignLeads.vue`) a manager or department head
plans each person instead: the **product** they are handed and the **calls per slot**. The ERP
site keeps the plan on the member's row and the call batches follow it from the next slot
(TBO Smart's `call-batches.md` §11). Nothing is stored here.

**What the page shows.** A **Department** field first (the departments with call batches on;
`?department=` in the URL). The **People** list and the **Product** choices are that
department's own. The **People** list has each member's product ("Any product" without one), their calls per
slot (gray: the department's size, no plan of their own) and today's *called / handed*. On a phone
each row is the name with "PhoebiX · 50 + 50" under it. The **Assign** panel (beside the list on a
wide screen, under it on a phone) has the product, one number per slot, the day's total ("100
calls a day each, 300 together"), how many unassigned leads of that product are ready (with a
warning icon and words when it is fewer than the plan; each batch starts with the person's own
leads anyway), one primary **Assign leads** button and, for people who have a plan, **Back to
department sizes**. A department's campaign product is the only product (the picker is locked
and says why).

**A department without products gives leads by industry.** When a department has no products
(TBO) and the ERP site sends its industries, Assign leads uses **Industry** where it would use
Product (`callPlans.byIndustry`): the department line says *no products: leads are given by
industry*, the people table's column and each plan show the industry, the picker counts the
unassigned leads of each industry (*Hospitality · 120 unassigned*), and See leads, Give now and
the plan are sent with `industry` (`save_call_plan`, `assign_leads`, `get_department_leads`;
TBO Smart keeps it as the member's `call_industry`, and the batches and the 11:00 auto-assign
follow it). The leads window filters and gives by industry too and hides Set product. An older
TBO Smart sends no industries, so the page stays as it was.

**A district narrows it all.** When the ERP site sends a department's districts (those its open
leads are in; `callPlans.hasDistricts`), the Assign panel has a **District** under Product (or
Industry): *Any district* or one district, each with its unassigned leads of the product chosen
(*Malappuram · 40 unassigned*), and the product's counts follow the district chosen. The box says
*40 unassigned PhoebiX leads in Malappuram*; **See leads** opens the Unassigned window on that
product and district, **Give now** gives the next leads of both, and **Assign leads** saves the
district with the plan, so the batches, *Calling for* and the 11:00 auto-assign take only that
district's new leads (TBO Smart keeps it as the member's `call_district`; `save_call_plan`,
`assign_leads`, `get_department_leads` send `district` only when one is chosen). The people
table's plan column reads *PhoebiX · Malappuram* (*Product · District*). A department's campaign
district is the only one: the field is locked and says why. The leads window gets a **District**
filter with counts (*All districts*, each district, *No district*), each lead shows its district
next to the stage, and *Give the next* takes an **In district** too. An older TBO Smart sends no
districts, so the field stays out instead of filtering nothing.

**The product's unassigned leads, there and then.** Each product in the picker says how many
unassigned leads with a phone it has (*PhoebiX · 120 unassigned*; *Any product* the total). With
people picked, a box under it says *120 unassigned PhoebiX leads* with **See leads** (the
Unassigned window, already on that product; with one person picked it opens on their pool, ready
to give picked leads to them) and **Give now** (*Give each now* for several people): that many of
the next unassigned leads of the product go to each person at once (`assign_leads` with `count`
and `product`, one call per person, as *Give the next 25* in the window). Given leads are theirs
straight away and their next batch can call them; the plan below still sets the calls a day.

**Auto-assign when nobody did.** Under the panel, a clock line says when the department hands
out leads on its own: *At 11:00, anyone with a plan who wasn't given leads here today is topped up
to their plan automatically. Not on Sundays or the 2nd Saturday.* The ERP site does it (TBO Smart's
`call-batches.md` §14): once a day at the department's time, each member with a plan of more than
0 calls who was not handed a lead here by hand today and is not on leave or a holiday gets the
next unassigned leads of their plan's product, up to their plan minus the leads of that product
they still have and never called. It is set per department in **Settings → CRM → Lead
departments**, under the call-batch rules (`CallBatchRules.vue`): **Auto-assign leads nobody
handed out** (on), **Auto-assign at** (11:00), **Saturdays** (every one a work day / not the 2nd /
not the 2nd and 4th / none) and **Not on Sundays** (on). While the ERP site's departments don't carry
these fields yet (`auto_assign`), the block shows disabled with *Auto-assign needs the latest TBO
Smart on the ERP site*, none of them is sent, and the Assign leads line stays out.

**Each person's leads, and the unassigned ones.** Every row ends with *1,219 leads* (their
open leads in the department); it opens a window (`MemberLeadsDialog.vue`) with **Their leads** and
**Unassigned**, a Product filter and a District filter with counts and a search (name, company,
phone):
- tick leads and **Move to** another member, **Unassign** them (back to the department's pool),
  or **Set product** (the existing `bulk_set_lead_category`, which a head may do for their
  department);
- under Unassigned, tick leads and **Assign to** the person, or **Give the next 25 of PhoebiX**
  without picking (the ERP site takes the next unassigned leads with a phone, hot then newest);
- the header's **Unassigned leads** button opens the pool on its own.

**Made hard to get wrong.** *Send N back to the pool* is a quiet secondary button and asks first
("Send 71 leads back to the pool? Shahana V K will no longer see them or their notes. They go to
the next person's call batch."); *Keep them with X* is the primary button of that question. Under
Unassigned, *Give N to X* is the solid button. Every action leaves a plain result line in the
window ("71 leads given to Fidha V P", "71 leads are now in the pool") and the list says who owns
what it shows ("owned by X" / "no owner yet"). When leads wait in a department's pool and nobody
will be handed them, the page shows a warning above the people: every member's plan is 0 (with a
*Set the plan* button that picks everyone) or the department doesn't pull unassigned leads
(`poolStuck` in `callPlans.ts`).

The owner, the ToDo assignment and a waiting call in the previous owner's running batch move with
the lead (TBO Smart's `call-batches.md` §12). At most 500 leads at a time; 50 a page with **Show
more**. Never cached. `get_department_leads`, `assign_leads`, `unassign_leads` in
`helpdesk/api/call_batches.py`.

**Who.** The item shows for anyone who is not a BD once a department hands out batches; the ERP
site decides: Sales Managers and System Managers plan every department, heads theirs. Anyone else
sees *Assign leads isn't available to you* (`LeadsForbiddenError`, no retry button). Only members
can be planned; the page says to add people in Settings, CRM, Lead departments.

**States.** Loading skeleton; an error with Try again; an older ERP site (*The ERP site can't
assign leads yet*); no department with batches (turn them on in Settings); a department with no
members; the save's own error under the button.

**What a plan does on the ERP site.** The slot's batch holds the person's number (0: none in
that slot), the day's cap is at least the plan's total, new leads are only the plan's product, the
person's *Calling for* offers only that product in the department, and their batches there open
even when they focus on another department. Calls already handed out stay.

Code: `helpdesk/api/call_batches.py` (`get_call_plans`, `save_call_plan`; a 403 becomes
`LeadsForbiddenError` with the ERP site's reason), `desk/src/pages/leads/callPlans.ts` (types,
`leadsReady`), `AssignLeads.vue`; the nav item `assign-leads` (`callPlannerOnly` in
`useNavigation.ts`).

### How to use (managers and heads)

1. Open **Sales → Assign leads** and pick the **Department**. The list shows its people.
2. Tick the people (or the box at the top for everyone).
3. Choose the **Product** and, to call one place only, the **District**. Type the calls for each
   slot, for example Morning 40, Afternoon 30, Evening 30.
4. Check the line under it: if fewer unassigned leads are ready than you plan, the batches give
   what there is.
5. Press **Assign leads**. It counts from the next slot.
6. To see or move someone's leads, press **N leads** on their row. Tick leads to **Move to**
   someone else, **Unassign** or **Set product**. Under **Unassigned**, tick leads and assign them,
   or type how many to give (and of which product and district) and press **Give to**.
7. To remove someone's plan, tick them and press **Remove plan · use (department) default
   (50 + 50)**; the button shows the department's slot sizes. It asks first ("Remove Fidha V P's
   plan? From the next slot they get GrowthX's default: Morning 50 + Afternoon 50, any
   product."), naming the campaign product instead of "any product" when the department has one.

**Viewers (read-only).** A department's **Viewers** (Settings → CRM → Lead departments, next to
Heads; shown once the ERP site's TBO Smart has them) open Assign leads for it but change nothing:
`get_call_plans` lists the department with `can_edit: false`, and the page then hides the tick
boxes, the plan form and the Remove plan button, and shows a **View only** card instead. **N leads**
still opens the person's leads and the unassigned ones, without tick boxes or actions. A Sales
Manager listed as a viewer only watches that department. The sidebar shows Assign leads to a
viewer even when they are a BD (`is_viewer` in `get_options`' departments).

**A person's Today's calls, read-only.** On Assign leads, each person's **Today** count
(`12/50`) opens `MemberCalls.vue` (`/leads/assign/calls/<user>`): their Today's calls as they see
it (`TodaysCalls.vue` with `member`, reading `get_member_calls`), the batch, time left, counts,
the calls waiting, coming back later and overdue, without the Call button, the answer buttons,
Get next batch or the calling-for switch, and the lead name is not a link. Below it, **Called
today** lists the calls they already made, newest first, with the answer, the time and the note.
It reads again every 15 seconds. Managers, heads and the department's viewers may open it; the ERP
site refuses anyone else ("Only managers, department heads and viewers can see someone's calls.").

**Live.** Assign leads reads the plans again every 15 seconds while the page is in view, and at
once when it comes back into view, so today's calls, plans and lead counts follow what others
change. The view-only card says when it last updated.

**Follow-up cards.** On *Follow-up*, five number cards (`FollowUpCards.vue`): **Overdue** (in red
with its icon when there are any), **Due today**, **Tomorrow**, **Next 7 days** (2 to 7 days on)
and **Later**, counting the leads whose earliest open follow-up is due then (a BD's own or
created; else the Owner filter's, or everyone they see). Picking a card lists its leads (`due`
on `list_leads`, kept in the URL); picking it again goes back to the list as before, overdue
and due today. `helpdesk.api.leads.get_follow_up_counts` (cached 60 seconds per person) reads TBO
Smart's `get_follow_up_counts`; the cards stay out while an older TBO Smart can't count.

**Your calls on My leads.** At the top of *My leads*, a strip (`MyCallCounts.vue`) shows the
person's own calls **Today**, **This week** (from Monday), **This month** and **All time**, each
with how many connected; **By day** opens every day with calls in the last year, newest first
(day, calls, connected). They are counted as the Daily report counts calls: every call the
person made or took (Today's calls, Log call, MyOperator), answered ones as connected; calling a
lead twice is two calls. `helpdesk.api.leads.get_my_call_counts` (cached 60 seconds per person)
reads TBO Smart's `get_my_call_counts`; the strip stays out while an older TBO Smart can't count.

## BD view, calling for, and recording results

A **BD** is a Sales Employee who is not a System Manager, Agent Manager or Sales Manager and
heads no department. Another BD may be calling the same lead, so a BD sees only what comes to
them.

**Tabs.** *Today's calls* (the default; *Call today* in its place while their departments have no
batches), *My leads* (what they own or created; renamed from *Mine* for everyone), *Follow-up*,
*Called* and their own *Commission*. No Overview, Daily report, Business, All, Outreach or *Find prospects*, and no
Owner filter. Managers and department heads keep everything.

**Only their own leads, and the ones they created.** The ERP site also shows a lead to whoever it
is assigned to (a follow-up given to them on someone else's lead). For a BD the hub sends `mine`
on every `list_leads` (All becomes My leads; Follow-up, Call today and Called are their own or
created leads only), and `get_lead` refuses a lead they neither own nor created (*This lead is
someone else's*, PermissionError). A lead they created and handed on shows *Created by you* and
opens read only.

**On the list** (everyone): a **Created by** filter on My leads (*Owned or created* / *Created by
me*); the **Called** tab with a **Last called** filter (Any time, Today, Yesterday, This week, This
month); and on every row, next to the last call, how many calls the lead has had.

**On the server too** (`helpdesk.api.leads.is_bd`; `auth.get_user` sends `is_sales_bd` for the
role, `get_options` sends `is_bd` once the department heads are known): `list_leads` with view *All*
returns *My leads* and ignores the owner filter; `get_overview`, `get_overview_page`,
`get_lead_intake`, `get_proposal_money`, `get_business_overview`, `get_daily_report` and the
Find-prospects endpoints answer *This is for managers* (PermissionError). If the ERP site cannot say
whether the person heads a department, they are treated as a BD.

**Calling for** (`CallingFor.vue`, top of Today's calls; the ERP side is `call-batches.md` §10).
A card says what they call for now (*Hotels (StayVeX)*, *PhoebiX (GrowthX) in Kochi*, *All my
departments*) with a **Change** button when there is anything to switch. The picker lists their
departments that hand out batches, each product, *All my departments* and an optional district;
**Start calling** saves it and the answer says in plain words what happens (*Your next 30 calls are
ready*, or why the next batch has to wait). A department with call batches off is not listed:
in Settings, Lead departments the box says *Turn on daily call batches so its members can call from
Today's calls.* `helpdesk.api.call_batches.set_calling_focus`; the choice is remembered per person on
the ERP site, and `get_my_calls` carries `focus` and `focus_options`.

**Recording results** (`helpdesk/api/pending_calls.py`, `PendingCalls.vue`, `CallResultSheet.vue`).
Tapping **Call** on a lead (a row in Today's calls, the lead page's Call button or its phone number)
remembers the lead. The cache holds it per person for 3 days, at most 50. When the person comes back
to the page (`visibilitychange` or window focus; for MyOperator, 45 seconds later) the **result
sheet** opens for it: six big buttons (Connected, Not answered, Busy, Call back, Not interested,
Wrong number), an optional note; Call back asks *In 1 hour / In 2 hours / Tomorrow 10:00*, Not
interested asks why in one tap. A small banner, *You have N calls without a result*, stays on every
screen for Sales Employees with **Add results**, which opens them one by one. The result goes to
`record_call_outcome` (a call from Today's calls) or `log_call` (any other); both take the lead off
the list. A call can only leave without a result with a reason: *I didn't call* or *Tapped by
mistake* (`dismiss_pending_call`). Endpoints: `start_call`, `get_pending_calls`,
`dismiss_pending_call`, `resolve` (internal).

### How to use (BDs)

1. Open **Leads**. You see **Today's calls**: only your own calls, nobody else's.
2. Check **Calling for** at the top. Tap **Change** to call for another department or product (a
   district too, if you like), then **Start calling**.
3. Tap **Call** on a lead and make the call.
4. Back on the page, tap how it went: Connected, Not answered, Busy, Call back, Not interested or
   Wrong number. That is all.
5. If you forget, the banner *You have N calls without a result* waits. Tap **Add results**.
   If you did not make the call, tap *I didn't call*.

## More than one number per lead

Leads arrive with one number; on a call the person often gives another (the decision-maker's, the
office's). A lead keeps all of them, and the old one is never lost. TBO Smart stores them
(`docs/lead-numbers.md` and `hub-leads-api.md` §2.24 there); the hub shows and edits them.

**How to use it (telecallers and BDs):**

- On a call they give a new number: open the lead, tap **+ Add number**, type it, **Save**. The
  old number stays in the list. Pick *Decision-maker* or *Office* if you know whose it is, and
  type their name if you have it.
- It is the number to call from now on: tick **Make this the main number**. The old one moves to
  **Old numbers** (tap it to see it); nothing is deleted.
- After a call, the result sheet has **Got another number?**: the same form, so it takes seconds.
- A number is wrong: pick **Wrong number** as the call's result. That number is greyed out and the
  next one becomes the main number; the lead is only a Wrong Number lead when none is left. Or use
  the **...** menu on a number: Make main, Not reachable, Wrong number, Old number, Back in use.
- The number is already on another lead? The form says whose lead it is and won't save it: a
  number belongs to one lead ([One lead per number](#one-lead-per-number)). Work that lead, or
  ask a manager to merge the two.
- Only managers remove a number (it is in the **...** menu for them); everyone else marks it Old
  or Wrong number.

**Where it shows** (`LeadNumbers.vue`, `AddNumberDialog.vue`):

- *Lead page, Details card:* a **Numbers** list: each number with its **Main** tag, label, name and
  note, a *Not reachable* chip, a **Call** button for that number (MyOperator click-to-call when set
  up, otherwise the phone's `tel:` link), a WhatsApp link, and the **...** menu. Old and Wrong
  numbers are greyed and struck through under **Old numbers (n)**. An older TBO Smart, which sends no
  list, keeps the single Mobile line.
- *Today's calls:* the row shows the main number and, when the lead has more in use, **+1 more**;
  tap it to call one of the others. The result is recorded against the number that was dialled
  (`number` on `record_call_outcome`).
- *Log call:* a **Number called** choice appears when the lead has several numbers in use.
- *Calls without a result:* the pending call remembers the number that was dialled
  (`pending_calls.start_call`'s `number`), and the result sheet sends it with the outcome.
- *Duplicates:* the Add number form and the lead form ask `find_duplicate_leads`, which now covers
  every number of every lead (`DuplicateLeadsNotice.vue` shows the matches); a phone match stops
  the save ([One lead per number](#one-lead-per-number)).

Hub endpoints: `add_lead_number`, `update_lead_number`, `remove_lead_number` (thin proxies; every
write clears the person's cached reads), and a `number` argument on `log_call` and
`record_call_outcome`. An ERP site without them answers "needs the latest TBO Smart".

## One lead per number

The same phone number never makes a second lead. Two leads with one number split the calls, the
notes and the follow-ups between two people, so the ERP site (TBO Smart, `lead-departments.md` §6
there) refuses it however the lead comes in: the hub, the mobile app, the desk, a Data Import, the
website form, the Lead Bank, prospecting or Meta lead ads. A number is the same when its last 10
digits are (`+91 98470 12345`, `098470-12345` and `9847012345` are one number), on any of a lead's
numbers, old and wrong ones too.

**What people see:**

- *New lead (hub):* typing a mobile number that a lead has shows that lead under the field
  ("This number is already on a lead: work that one instead") and the Create button is off. There
  is no Create anyway for a number; an email match still has it.
- *Edit lead:* changing the Mobile to a number another lead has stops the save the same way. The
  lead's own number, even one it shares with an old duplicate, saves as before.
- *Add number:* a number another lead has is shown with that lead and Save is off.
- *A lead the person can't see:* nothing is listed before saving; the ERP site's refusal names
  the lead and its owner ("Possible duplicate of LD-… (Anil): it already has the number …, and a
  number belongs to one lead.").
- *Website form and Meta lead ads:* the enquiry goes on the lead that has the number (or email) as
  a note, and its owner (or the department's heads, when it has no owner) is notified. The Meta
  Lead Log says Duplicate and links that lead.
- *Mobile app:* the 409 comes even with *Create anyway*, with `number_taken: 1` so the app can
  hide that button.

**Numbers many businesses share.** A lead portal (IndiaMART, JustDial) sometimes gives every
business it forwards the same virtual number. Such a number goes in TBO Smart Settings, section
*One lead per number*, field *Numbers many businesses share* (one per line, on the ERP site);
it may then be on any number of leads.

**Duplicates made before the rule** stay as they are and can still be edited; merge them
([Merge duplicate leads](#merge-duplicate-leads)). On 2026-11-13 ten numbers were on two leads
each, nine of them the same number typed differently (`+91…` and `0…`). One of them,
08047808605 on LD26101623 and LD26101628, looks like a portal's shared number: put it under
*Numbers many businesses share* rather than merging. Two pairs include a Closed – Won lead
(LD26101145 / LD26101210, LD26101020 / LD2610560): keep the won one.

**How it is built.** The ERP site is the rule (`refuse_taken_numbers` on Lead validate, so no path
can skip it); the hub only says it early. `LeadFormDialog.vue` and `AddNumberDialog.vue` check
with `find_duplicate_leads` before saving and stop on a `phone` match (`blockedByPhone`,
`numberTaken`); `create_lead` sends `allow_duplicate` only for an email match. A refusal
mentioning "belongs to one lead" never turns into Create anyway.

## Merge duplicate leads

The same person sometimes comes in twice (two companies, one phone). A manager or the head of the
lead's department merges them into one; the ERP side moves everything
(`hub-leads-api.md` §2.26 in TBO Smart).

### How to use (managers and heads)

1. Open a lead. When another lead has the same email or number, a box says **This may be the same
   person as another lead**, with a **Merge** button next to it. (Not seeing it means no lead
   matches, or you are not a manager or head.)
   From the leads list: **Select leads**, tick exactly two, **Merge**.
2. The dialog shows both leads side by side. The one further along in the pipeline (else the
   older one) is ticked **Keep this one**; tap the other to keep that instead.
3. It says what moves, in words: "12 notes, 4 calls, 2 numbers will move to Ashraf." Check it,
   then **Merge into Ashraf**. The other lead is removed and cannot be brought back; if you were
   looking at it, the page opens the kept lead.

The kept lead's timeline records "Merged LD-… (Ashraf, Amana UAE) into this lead by <you>".
Numbers the kept lead lacks are added (never as the main number), empty fields are filled from
the merged lead, and nothing the kept lead already has is overwritten. Two leads of different
departments are merged by a manager only; the kept lead's department stays.

### How it is built

`LeadDuplicates.vue` (on `Lead.vue`, only while `lead.can_merge`) asks `find_duplicate_leads` for
the lead's email and up to three numbers and lists the matches with `DuplicateLeadsNotice.vue`
(its `can-merge` prop adds the Merge button). `MergeLeadsDialog.vue` reads `get_merge_preview`,
picks the lead to keep (further stage, else older), and posts `merge_leads`; the list's Select
mode opens the same dialog for two ticked leads. Hub tests: `helpdesk/tests/test_lead_merge.py`.

## Find prospects

TBO sells mainly by phone. Managers and department heads find businesses by industry and district
(for example Resorts in Idukki) and drop them into a department's **unassigned pool**; the call
batches ([Today's calls](#todays-calls)) hand them out. The ERP site does everything (providers,
prices, the monthly spend cap, the search, the import, the duplicate check and reading each
business's own website); the hub only asks and shows. TBO Smart's `docs/prospecting.md` is the
spec.

**Who.** `get_options` carries `can_find_prospects` (System Manager, Sales Manager or a department
head, while TBO Smart Settings → Prospecting → Enable Find prospects is on) and `prospecting`
(providers with `available`, the default department, the largest run, the monthly cap and spend).
Everyone else gets neither: no button, and the page says it is not available. The ERP site
refuses the calls too.

**The page** `/leads/prospects` (button *Find prospects* in the Leads header, only with the flag).
One purpose, one primary action. On the left the search: Industry, State, District(s) (a multi
select from the ERP site's district lists, or comma separated text without them), Provider (each
with its coverage, one that is switched off or has no key is listed as "not set up" and cannot be
used), Max results, Department and "Only businesses with a phone number". The primary action is
**Estimate**; it prices the run (nothing is searched or bought), shows the cost, the number of
businesses (OpenStreetMap: how many the map holds; a paid provider: "up to" the maximum) and the
coverage note, and the button becomes **Start run**. Changing any field drops the estimate. A paid
run over the monthly cap is refused with the ERP site's words. On the right the runs, newest first,
each with its status (icon and word), counts (found, new, duplicates) and cost; a running one
refreshes every 5 seconds. A run opens in a dialog: counts, the leads it created (each links to its
lead page and shows its Why call line, or "In the pool" while it has no owner), the log, and a link
to the Leads list filtered by the source `Prospecting – <provider>`.

**On the lead page.** A lead found by a run (or any lead whose website was read) shows **Why call**
above the AI suggestions: the one-line reason and four chips, each with an icon and words in both
states (Website / No website, Online booking / No online booking, WhatsApp / No WhatsApp, Hiring /
Not hiring). Neutral styling, no colour meaning. Nothing shows while the site was not read or could
not be read.

**Errors.** An older ERP site: the runs list is empty with "The ERP site can't find prospects yet";
estimate and start say "needs the latest TBO Smart". A refusal says only managers and department
heads can find prospects, or the ERP site's own reason.

## Outreach

Phase 2 of Find prospects (TBO Smart's `docs/prospecting.md` §10 and §11 is the spec): the AI
writes a first message for each lead of a prospect run, **a person reads, edits and approves it**,
and the replies are sorted by the ERP site. The hub proxies `tbo_smart.api.hub_outreach` through
`helpdesk/api/outreach.py` (`get_outbox`, `draft_outreach`, `update_outreach`,
`regenerate_outreach`, `approve_outreach`, `cancel_outreach`, `mark_outreach_sent`); the ERP site
holds the outbox, the daily cap, the send window and sends the email. The hub sends nothing.

**Who and when.** `get_options` carries `outreach` (TBO Smart Settings → Outreach → Enable
Outreach, off by default). While it is on, everyone who uses Leads gets the **Outreach** tab and
sees their own messages; a department head also sees the department's, a manager everyone's (the
ERP site decides). An older TBO Smart: the tab stays out; the endpoints answer "needs the latest
TBO Smart". The options are cached for ten minutes, so the tab can take that long to appear after
the switch is turned on.

**The tab** (`LeadsOutreach.vue`, `OutreachRow.vue`). One purpose: review and approve. A status
switch (Draft, Approved, Sent, Failed, Cancelled, each with its count; Draft first), today's email
count against the daily limit, and the sending hours when they are closed. Each row shows the
company, the status (icon and words, "Approved, waiting to go" for an email held for the window or
the limit), the lead's last reply class, the recipient, the owner (when other people's messages
show) and the subject or the start of the text; it opens to an editable subject and text with
**Approve** (the one primary action), **Save changes**, **Regenerate** and **Cancel message**, the
opt-out line the email will carry, and an error in words on a Failed message. Approving saves any
edit first. Select rows (Draft, Approved, Failed) to **Approve selected** or **Cancel selected**.
A WhatsApp row shows how it will go (the approved template with the lead's details filled in, or
the person's own words inside 24 hours of the lead's reply) and, once the WhatsApp inbox is set,
goes by itself after Approve (Sending on WhatsApp, Sent, Delivered, Read;
[whatsapp-outreach.md](whatsapp-outreach.md)). Without an inbox or a template an approved WhatsApp
row shows **Open WhatsApp** (the `wa.me` link with the text filled in) and **Mark sent**, which
the person presses after sending it by hand.
Results are told in words (sent, approved, a message that was held and why); approving an email
with no outgoing email account on the ERP site shows "Set up an outgoing email account first".
The list refreshes by itself while drafts are being written.

**Drafting.** In Find prospects, a Done run offers **Draft first messages** on its row and in its
dialog (only while Outreach is on): pick Email or WhatsApp, and the ERP site drafts in the
background, skipping and explaining the leads that unsubscribed, are lost, have no address, are
not the person's to edit or already have a first message. Nothing is sent. The ERP site writes the
message from the lead's website findings and Why call line, and throws away a draft that has a
number that is not in them.

**Replies.** The lead page's AI card shows the last reply's class (Interested, Question,
Objection, Not now, Not interested, Unsubscribe, Out of office, or New reply when the AI could
not sort it) with when it came and what the ERP site did about it. The Leads list has a
**Replied** filter (any of the classes, with counts) beside Last call; `list_leads` takes
`last_reply_class`, which is validated here and sent as a JSON list.

**WhatsApp on the lead page** (`LeadWhatsApp.vue`, backend `helpdesk/api/whatsapp.py`): the
conversation appears in the Timeline (“The lead, on WhatsApp”); a WhatsApp card has **Open in TBO
Chat** and a reply box that is enabled only within 24 hours of the lead's last message, otherwise
it says why and offers the approved template. The card is absent on an older TBO Smart. A lead's
WhatsApp reply is sorted like an email reply (the ERP site does it). Owner setup, the staff steps
and the decisions are in [whatsapp-outreach.md](whatsapp-outreach.md).

Tests: `helpdesk/tests/test_outreach.py` (the outbox read live as the person and never cached,
status filters, an older ERP site, the ERP site's refusals reaching the person, drafting posted
with its channel, the names checked before the ERP site is asked, edits trimmed, no leads access,
the reply-class filter).

## Commission

Commission is a percentage of the money **collected** on a project, per month, in progressive
slabs with a higher rate above a target. The ERP site holds the plans, the project set-ups and the
statements and works the money out from its customer receipts (TBO Smart's `docs/commission.md` is
the spec, `docs/hub-leads-api.md` section 2.18 the contract). The hub proxies
`tbo_smart.api.hub_commission` through `helpdesk/api/commission.py` (`get_commission`,
`generate_statements`, `approve_statement`, `mark_paid`, `get_commission_plans`,
`save_commission_plan`, `get_project_commission`, `save_project_commission`). Nothing is cached;
an older TBO Smart answers `available: false` (reads) or "needs the latest TBO Smart" (writes).

**Where it lives, and why.** A **Commission** tab on Leads, not a Scoreboard section. It needs a
month, a person-then-project drill-down and approval actions, and the Scoreboard is a live
activity count; the tab sits beside Business and the Daily report, which are the other
"report for a period" views, and it reads as one purpose: who earns what this month.

**The tab** (`LeadsCommission.vue`, `CommissionPayments.vue`). A month picker (this month and the
12 before) and, for managers, **Generate drafts** (the one primary action; approved statements are
left as they are and the toast says how many). Tiles: collected and commission (for a salesperson
"My collected" and "My commission", with the target reached and the slab), people, and, for managers,
**Unattributed**. One card per person: collected with an achievement bar against the target (the
percentage is always written; the bar turns green at 100%), the slab reached, commission and the
status (Draft, Approved, Paid, or "Not drafted"). A manager sees **Approve** on a Draft and **Mark
paid** on an Approved statement. A card opens to the projects (collected, share, commission), the
slab breakdown (each slab's part of the money, its rate, whether it was above target) and the
payments. An approved or paid statement is shown as approved and says so. What a person may see is
decided on the ERP site: a salesperson only themselves (their card opens by itself), a department
head their department, a manager everyone. **Unattributed** explains in words that it is money that
could not be followed to a project and a person (an advance not matched to an order or invoice, an
order with no project, a lead with no owner), lists the reasons with amounts and opens to the
payments. States: loading skeletons, an error with Try again (and a banner over stale figures), "needs
the latest TBO Smart", and an empty month that says what makes commission appear.

**Commission plans** (Settings → CRM, `CommissionPlans.vue`, `CommissionSlabs.vue`; System Manager and
managers). A plan has optional conditions (department, lead type, project type, person), a basis
(Project collected: each project's money through the slabs on its own, target per project; Collected
(all): the person's whole month once, target per person), a monthly target, an above-target rate and
slabs (from, to blank for no limit, rate). The dialog checks the slabs as you type and shows a live
example, "On Rs 3,00,000 collected: Rs X", with the slab pieces under it; the maths is the same as the
ERP site's (`previewCommission` in `commission.ts`), which has the last word on save. The plan whose
conditions all hold and match the most wins: person, then project type, lead type, department.

**Project page** (`ProjectCommission.vue`, a **Commission** tab for managers). Who earns on the
project with their shares (they must add up to 100), the plan (or "Match by rules") or the project's
own slabs, what was collected on the project so far and the commission credited in statements. With
no earners the owner of the lead behind each payment earns all of it. The project name defaults to
the hub project; type the ERP Project name when the invoices use another.

Tests: `helpdesk/tests/test_commission.py` (reads live as the person and never cached, filters
trimmed, an older ERP site hidden quietly, refusals, writes as POSTs, plan and project values sent as
JSON). The ERP site's own tests cover the maths, attribution and statements.

## Lead Bank (staff collect leads, referral commission)

Every active agent, whatever their team or wall, can add a lead from a photo and earns a referral
when it is won and paid. It is a separate path from Leads: `can_use_lead_bank` (Leads switched on in
Settings → CRM, and an active agent) opens only **Add a lead**, **My leads** and, for managers,
**Team**; it never opens the CRM, so designers, developers and the Digital team still do not see
Leads. Specs: [lead-bank.md](lead-bank.md) here, TBO Smart's `docs/lead-bank.md` and
`docs/commission.md` section 7, the contract `docs/hub-leads-api.md` section 2.21. The hub proxies
`tbo_smart.api.hub_lead_bank` through `helpdesk/api/lead_bank.py`, and reads the photos with its
own AI (`helpdesk/lead_bank.py`).

Referral shows in **Commission** like any other line: a statement line of kind Referral, labelled
"Referral: <lead>" in a person's projects, and the statement's `referral` is the part of its
commission that is referral. The rates, the cap and the department of each region are set in
Settings → CRM → **Referral (Lead Bank)** (`ReferralSettings.vue`), under the commission plans.

## Hub endpoints

`helpdesk/api/leads.py`, thin typed proxies (writes are POST only): `get_options`,
`list_leads`, `get_overview_page`, `get_overview`, `get_business_overview`, `get_lead_intake`, `get_proposal_money`, `get_lead`, `get_lead_ai`, `refresh_lead_ai`, `apply_ai_stage`,
`dismiss_ai_stage`, `draft_lead_message`, `log_message_sent`, `create_lead`, `update_lead`,
`set_stage`, `add_note`, `get_category_counts`, `add_industry`, `bulk_set_lead_category`, `find_duplicate_leads`, `get_stale_leads`, `get_lead_departments`, `save_lead_department`, `set_lead_department_active`, `add_lead_number`, `update_lead_number`, `remove_lead_number`, `get_merge_preview`, `merge_leads`, `click_to_call`, `call_recording`, `get_daily_report`, `log_call`, `get_lead_photos`, `upload_lead_photo`, `delete_lead_photo`, `lead_photo`. Find prospects has its own `helpdesk/api/prospects.py`: `estimate_prospect_run`, `start_prospect_run`, `get_prospect_runs`, `get_prospect_run`; Outreach has `helpdesk/api/outreach.py` (see [Outreach](#outreach)). They check
`can_use_leads`, validate the view and page size, trim notes, and pass `acting_user`. The
client is `CRMClient.call` in `helpdesk/integrations/crm/client.py`; the call and error
mapping live in `helpdesk/integrations/crm/leads.py`. The API key and secret never reach the
browser.

### How the Overview loads

One request: `get_overview_page` reads the overview, the proposals and money, the intake and the
calling/quality analysis (`get_lead_analysis`, TBO Smart `hub-leads-api.md` §2.25) from the ERP
site one after another and answers `{overview, money, intake, analysis, errors}`. Money, intake
and analysis are optional: one that fails (or an ERP site too old to have it) leaves the overview
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
copy and renews it; on the list tabs Refresh also renews the Follow-up cards and the *Your calls*
strip. Creating or updating a lead, moving its stage (by hand or the AI's suggestion), and
creating or sending a proposal clear the signed-in person's copies; other people's age out within
a minute. A department change also clears everyone's `get_options` copy, as it says who heads a
department: a new head gets the managers' screens at once, not after 10 minutes.

A list request starts only after the previous one is aborted (`leads.abort()`), so a slow answer
for an old tab or filter never lands over the new one; *Created by me* is sent only on the tabs
that show it (My leads, and every tab for a BD).

### Errors people see

| What happened | Message |
| --- | --- |
| No connection saved | Leads aren't connected yet. Ask an admin to set up Settings → CRM. |
| ERP site unreachable or timed out | Couldn't reach the ERP site (host). Try again in a minute. |
| 401 | The ERP site refused the hub's API key. Ask an admin to check Settings → CRM. |
| 403 saying only the hub's integration user may act for someone else | The hub's API user (email, when the ERP site says who the key belongs to) on (host) isn't the site's integration user: it needs the role in TBO Smart Settings → Hub integration role there (blank: Hub Integration). Ask an admin to add the role that field names to that user. |
| 403, 404 or 417 saying the method isn't there or isn't whitelisted | Leads need the latest TBO Smart on the ERP site (host). |
| 403 saying the person has no sales role or isn't an enabled user, or a 403 with no message | You don't have a sales account on the ERP site yet. Ask an admin to give (email) the Sales User role on (host). |
| Any other 403 with a message (a refusal of the lead, e.g. "No permission for Lead …") | The ERP site's own message: the person has an account, just not that lead. |
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
  - **This period** (one bordered row of five cells: New leads, Contacted, Meetings held,
    Proposals sent, Won with its value; each opens its leads). The second row holds **Needs
    attention** now and Lost. **Needs attention** now: Overdue follow-ups (red), Gone quiet (no touch for
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
  - **Calling performance** and **Lead quality** (`LeadsAnalysis.vue`, at the bottom, part of
    the same request; hidden while the ERP site is older than TBO Smart v1.25, an inline error
    with *Try again* if it fails). How to read it:
    - *Calling performance*, one row per person, most called first. **Given**: leads on their
      daily call lists in the period. **Called**: those they logged an answer for. **Done**:
      called out of given. **Reached**: the person at the other end picked up (Connected,
      Call back or Not interested). **Reach rate**: reached out of called. **Overdue**: left
      uncalled when their list ended (red when above 0). **Calls** and **Missed** are the call
      log (MyOperator and logged calls), **Talk time** the time on answered calls. A
      salesperson sees their own row, a team lead the team's, a manager everyone's.
    - *Lead quality*: the leads that *came in* during the period, grouped by Source, Industry,
      District, Department or Product (the buttons above the table; a grouping the ERP site
      lacks is not offered). **Called**, **Wrong number** and **Not interested** are shares of
      the leads; **Picked up** is the share of the called leads who answered; **Moved on** is
      how many reached a meeting, a proposal or a win; **Won** how many are won now.
      The line above the table names the group that picks up most and the one that picks up
      least, and marks them in the list; it appears only when at least two groups have 10 or
      more leads called, so a few calls never name a winner. Use it to decide where to spend
      calls: a source with a high Picked up and many Moved on is worth more of the list.
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
  shows 0. Only the **sales team** gets a chip
  (the hub's enabled users with the Sales Employee role, set in Settings → Agents →
  Department wall → Sales team; the ERP site lists everyone with a sales role, which is
  every agent here); nobody else is shown, whatever they took, and each day's total is the
  sum of the chips shown. With no sales team yet: "No new leads yet today", and managers
  also see "Pick your salespeople in Settings → Agents → Department wall → Sales team"
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
  to you on the ERP site), next follow-up and remarks. Opens the new lead when it's created.
  Remarks aren't a lead field: the ERP site's `create_lead` takes only the `data` keys above,
  so the dialog saves them with `add_note` once the lead exists (they're the first entry on
  its timeline). If that note fails the lead stays created, a warning says so, and the
  remarks are kept per person and lead (`keepUnsavedNote` in `leads.ts`): in `localStorage`
  under `hd-lead-unsaved-note:<user>:<lead>`, and in memory as well so blocked or full
  storage still hands them over (the warning then says a reload would lose them). The lead's
  page opens with them in its note box, and they stay through reloads until a note sent from
  them (edited or not) is added; a fresh note typed after clearing the box leaves them
  stored. Logout clears them (`stores/auth.ts`), so the next person on a shared browser
  never sees them, and a failure landing after logout began stores nothing. A save (or its
  duplicate check) that finishes after the dialog was closed and opened again keeps those
  remarks but leaves the reopened form alone, and a note added on the lead page clears the
  box only if it's still that lead and the text wasn't changed meanwhile. Edit lead has no
  Remarks; the lead page's note composer does that.
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
- **Place and Photos** (needs TBO Smart's hub leads API v1.11, `hub-leads-api.md` §2.11; both
  cards stay out while the ERP site is older: no `place` on `get_lead`, and `get_lead_photos`
  answers `available: false` through `call_if_deployed`), under Details in the left column, for
  a BD who is about to visit:
  - **Place** (`LeadPlace.vue`): the location note, **Get directions** (Google Maps
    `dir/?api=1&destination=<lat,lng>`, which opens the Maps app on a phone; only with a pin),
    **Open in Maps** (the pasted map link, when there is no pin), **Google profile** (opens the
    client's Business Profile), and **Show map** (Google's key-free embed
    `maps?q=<lat,lng>&output=embed`, loaded only when asked, to spare mobile data). The
    coordinates show in mono. Empty: a line saying what to add and an *Add place* button (read
    only: "No place has been saved"). *Edit* (anyone who can write the lead) saves through
    `update_lead` with the links, the pin and the note; **Use my current location** asks the
    browser for one fix (needs https and permission) and says plainly when it is denied, can't
    be found, times out or isn't supported; a long Google Maps link fills the pin when it is
    empty. Latitude and longitude go together and are range-checked before they are sent; the
    ERP site checks the links are Google's.
  - **Photos** (`LeadPhotos.vue`): a grid of thumbnails (square, lazy), **Take photo** (camera
    on a phone: `accept="image/*" capture="environment"`) and **Add photos** (several, from the
    gallery). Chosen pictures open a dialog with previews and one optional caption for them;
    each is scaled to 2000 px as a JPEG in the browser (so a phone upload is quick, HEIC works
    where the browser decodes it, and the GPS in EXIF is dropped) and uploaded one at a time with
    a status line per file, a named error for a refused one and a toast when done. At most 20
    per lead (the buttons disable, with the reason). Tapping a thumbnail opens the shared
    `MediaLightbox` (arrow keys, buttons and a swipe, Esc to close); *Remove* asks once. The
    ERP site lets only the uploader, the lead's owner or a manager delete and says so.
  - The images are private on the ERP site. The browser loads them from
    `helpdesk.api.leads.lead_photo?lead=&file=&thumb=`, which streams the ERP bytes as the signed-in
    person (only PNG, JPEG or WebP are passed on, `Content-Disposition: inline`) and, through the
    `after_request` hook `cache_lead_photo`, `Cache-Control: private, max-age=3600`.
- The pickers' options (`get_options`) are fetched once per session (`leadOptions` in
  `desk/src/pages/leads/leads.ts`).
- Sidebar: *Leads* in Workspace (teal group), shown when `can_use_leads`.

## Lead categories (industry, state, district, organisation size)

Each lead says what kind of client it is, so the list can be filtered and counted by it.
The four fields are ERPNext's own (`industry`, `state`, `no_of_employees`) plus TBO's
`tbo_district`; the hub's names are `industry`, `state`, `district`, `org_size`. The contract
is TBO Smart's `hub-leads-api.md` §2.14.

- **Lead form** (`LeadCategoryFields.vue`, inside `LeadFormDialog.vue`): Industry and State
  are searchable lists. A manager who types an industry that isn't there gets "Add as a new
  industry" (`add_industry`; the ERP site refuses anyone else). District is a combobox that
  accepts any text: with State Kerala it suggests the 14 districts, with another state the
  districts leads there already use, with no state all of those. Organisation size is
  ERPNext's employee band. The lead page's Details card shows all four.
- **Filters** (`LeadCategoryFilters.vue`, under the other filters): four multi-selects (any of
  the picked values; different fields all apply). They are in the URL as repeated keys
  (`?industry=Resorts&industry=Hotels…&state=Kerala`), clear with "Clear filters", and apply
  with every view and with an Overview number's list. Each value shows how many of the
  person's leads have it (`get_category_counts`, cached a minute; no counts on an older ERP
  site). District lists only the districts in use.
- **Rows** show "Industry · District" (the state when there is no district) after the segment.
- **Bulk set** (managers): "Select leads" turns on checkboxes (this page, or one by one across
  pages), and "Set category" opens a form for the four values. A field left as it is changes
  nothing; "Clear" empties it on every selected lead. Up to 500 leads per call; leads the
  person may not write come back as `skipped` and are listed.
- **Overview and dashboards are not filtered by category**: the ERP site builds their figures
  per owner and period (`hub-leads-api.md` §2.14). Opening a number's list and then filtering it
  by category works.
- Needs TBO Smart v1.14 on the ERP site; before that the pickers show empty lists and the
  filters send nothing it understands.

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
  (`content_team.only_sales_team`): sales-team members only, plus the person picked
  (`owner`) and, for a non-manager, themselves. It also decides the team text and the 6 pm
  message. With no sales team the empty state tells managers where to pick one
  (`team_empty`).
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
- **Log call** (`LogCallDialog.vue`, `helpdesk.api.leads.log_call(lead, outcome, note,
  callback_at)`, POST): a *Log call* button on the lead page beside Call, for calls made outside
  MyOperator. The six outcomes are the ones Today's calls has (Connected, Not answered, Busy,
  Call back with a time, Not interested, Wrong number), each with its icon, and a line says
  what it does to the stage. The ERP site records an outgoing call as the signed-in person
  (which counts in the report), sets the lead's last call result and moves its stage (below).
  Shown only with `can_log_call`; the person's cached reads are cleared after it, and the
  lead page reloads. `No answer` and `Voicemail` are still accepted by the proxy and read as
  Not answered.

## Call outcomes: stages and the last call

Owner's problem: stages were only progress ones, so every call became "Contacted" plus a note
and positive and negative calls could not be told apart. TBO Smart now has the stages **Not
Responding** (called, not answered: call again), **Not Interested** and **Wrong Number** (both
lost, reason filled in), and keeps each lead's **last call result**
(`hub-leads-api.md` §2.16; the ERP site moves the stage, the hub only shows it).

- **Stage picker** (Move stage on the lead page) lists them from `get_options` like any stage.
  The call stages carry an icon next to the label and the colour the ERP site gives them
  (`stageTone`/`stageIcon` in `leads.ts`): Not Responding warning, Not Interested danger, Wrong
  Number neutral. Setting Not Interested or Wrong Number needs no reason.
- **Last call chip** (`lastCall` in `leads.ts`): "Not answered · 2d ago" on each list row and in
  the lead page's Details header, with the outcome's icon (`OUTCOME_LOOK` in `callBatches.ts`,
  shared with Today's calls). Colour only where it means something: Connected success, Not
  answered and Busy warning, Call back info, Not interested danger, Wrong number neutral. A lead
  never called shows none.
- **Last call filter** (`LeadCategoryFilters.vue`): a fifth multi-select next to the categories,
  any of the picked outcomes, kept in the URL (`?last_call_result=Busy&last_call_result=…`),
  cleared with "Clear filters", with each outcome's count from `get_category_counts`. It is
  left out until the ERP site has it.
- Needs the TBO Smart release with §2.16. Before it the stages, chips and filter simply do not
  appear.
- **Colour**: this tab is colourful on the owner's request, an exception recorded in
  [ui-guidelines.md](ui-guidelines.md) §8.

## Business (management only)

The Leads page's **Business** tab (`LeadsBusiness.vue`, `business/`) is the owner's meeting
view: how many clients are in the pipeline and what they are worth, proposals given,
onboardings (clients won, projects started) and the revenue that came in. It is company-wide,
not the signed-in person's sales scope, and it can be taken to a meeting.

**Who can see it, and how to grant it.** One place decides: the ERP site. A person sees the tab
and gets the figures when they are a **System Manager** or have the **TBO Management** role
there (created by TBO Smart's migrate; it is given to nobody). To grant it, add the role to the
person's user on the ERP site (User → Roles). The hub keeps no list of its own. The tab shows
when `get_options` answers `can_view_business` (kept up to 10 minutes per person, so a new
grant may need a refresh); the figures are checked again on every read, so a link or API call by
anyone else is refused (403: "Only management can see the Business overview"), and a role taken
away stops the figures within the 60-second cache. The person still has to be a hub user who
can open Leads (System Manager, Agent Manager, or an active agent in the Leads teams).

`helpdesk.api.leads.get_business_overview(period, from_date, to_date, department, include_profit,
fresh)` proxies TBO Smart's `get_business_overview` (hub-leads-api.md §2.11 in the tbo_smart repo),
through `call_if_deployed` (an older ERP site answers `available: false` and the page says so),
cached per person for 60 seconds, `fresh=1` skips it. Periods: this month, last month, this
quarter, this FY (from 1 April) and custom (at most two years); the hub works the dates out.

**The page:** a period picker, a department filter (shown when the ERP site has departments),
a Show profit switch, then a headline row (clients in pipeline, pipeline value, proposals sent,
onboarded, revenue invoiced, collected, outstanding, each saying whether it is the period or
now), revenue by month, the funnel, pipeline by stage, proposals and onboarding facts, the last six
months, top clients, profit (when asked and available) and a department table. Charts are plain
SVG (`BusinessBars`) and bar rows (`BusinessRows`); no chart library is added. The pipeline value is
the open clients' latest quotations, **unweighted** (lead stages have no probability) and says so.
Outstanding is what customers owe today, not the period's.

**Downloads:** *Download data (CSV)* writes the page's numbers as rows (section, item, count, amount,
note) with a byte-order mark for Excel. *Download as slides (PDF)* prints `BusinessSlides.vue`: a
title slide (logo, "Sales & Business overview", period, generated date) and six 16:9 landscape slides
(headline numbers, pipeline and funnel, proposals and onboarding, revenue, last six months,
departments and clients) in fixed light colours, through the browser's Save as PDF. The slides sit on
`<body>` and add their `@page { size: 297mm 167mm }` rule only while the tab is open, so printing any
other page is unchanged; turn "Background graphics" on in the print dialog for the bars.

## Proposals

The Lead page's **Proposals** section, the proposal builder and Settings → Rates and proposals
are specified in [proposals.md](proposals.md).

## Content and Digital Marketing leads

A lead whose `tbo_lead_type` is Content / Digital Marketing runs a different chain on the ERP
site: a **6-month strategy proposal** → the client accepts → the **credentials handover** →
the content calendar → the project and team. When the ERP site's next action is
`create_project` for such a proposal (`next.source_type == "Proposal"`), the lead's documents
strip calls `helpdesk.api.proposals.create_project_from_proposal(proposal)`; plans keep
`create_project_from_plan`. Both share `ensure_project`.

- The project is in the **Digital** department (looked up by name; none when it is missing or
  inactive), has the project type **Content Calendar** (so the client's posts find it, see
  [content-calendar.md](content-calendar.md#which-project-the-tasks-go-to)), the proposal's
  dates and client, and the deliverables summary as its notes.
- It carries `custom_crm_lead` and the new `custom_crm_proposal` (protected like the plan
  link), and the ERP site is told with `hub_proposals.link_project(lead, project, proposal,
  url)`. A second call finds the project already made.
- **Assumed ERP contract** (not final): `hub_proposals.get_accepted_proposal(name)` answers
  `proposal, lead, customer, tbo_lead_type, tbo_department, start, end, project_name,
  deliverables, hub_project`. It is read in one function, `proposals.accepted_proposal`, through
  `call_if_deployed`: an older ERP site gets a plain "needs the latest TBO Smart" message.
- The project's **Credentials** tab holds the client's logins and the hand-back when the client
  leaves: [client-credentials.md](client-credentials.md).

## Tests

`helpdesk/tests/test_bd_view.py`: who is a BD (a manager, a head, an admin and a support agent
are not), *All* turned into *My leads*, the team screens refused, the calling-for switch and
queue passed through, and the calls without a result (remembered once per lead, per person, cleared
by a result from Today's calls or Log call, kept when the result fails, dismissed only with a
listed reason, forgotten after 3 days, capped at 50). Helpers `bd_options` and
`clear_pending_calls` in `test_utils.py`.
`helpdesk/tests/test_lead_numbers.py`: a number posted as the signed-in person with trimmed details, a
blank number refused, a write clearing the cached reads, removal refused for non-managers, an older
ERP site, the dialled `number` passed with `log_call` and `record_call_outcome` (none for the main
number), and a pending call remembering it. Helper `lead_number` in `test_utils.py`.
`helpdesk/tests/test_lead_bank.py` (the Lead Bank, see [lead-bank.md](lead-bank.md)).
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
`helpdesk/tests/test_lead_categories.py`: the filters (and the last call result, checked) sent as JSON lists (none when empty), a lead
saved with its categories, the counts (empty on an older ERP site), `add_industry` and
`bulk_set_lead_category` proxied as the person, a refusal naming who may, empty picks refused.
Products: `test_lead_categories.py` (the product filter sent as a JSON list, a lead saved with its
product, the options' products, bulk set with a product and its refusal naming the head),
`test_leads.py` (products and the campaign product saved as given, `previous_name` for a
rename), `test_call_batches.py` (`product`, `intro_line`, `calling_for` and `campaign_product`
reach the person) and `test_whatsapp_outreach.py` (a template naming the product and its intro,
and the lead page's facts).
`helpdesk/tests/test_lead_place.py`: the photo list (and the card staying out on an older ERP
site), an upload passed on with a trimmed caption, an empty or oversize upload kept at the hub,
the ERP site's refusal reaching the person, delete, the image streamed (and only image types),
no access without leads, and the private cache header.
`helpdesk/tests/test_stale_leads.py`: wave 1: the duplicate check proxied as the person (and skipped
quietly on an older ERP site), `allow_duplicate` sent only when confirmed, the quiet leads kept
per department threshold and cached per person, and the follow-up rule (owner at L0, heads at
twice the days, one notice per person and lead, off switch, older ERP site and ERP errors add
nothing).
`helpdesk/tests/test_leads_business.py`: the period dates, the proxy as the signed-in person,
the 60-second per-person cache (and `fresh`), a refusal from the ERP site shown and never kept, an
older ERP site, and the tab flag passed through `get_options`.
`helpdesk/tests/test_sales_wall.py`: a Sales Employee outside the Leads teams lists, opens,
creates, moves and notes a lead as themselves.
`helpdesk/tests/test_daily_sales_report.py`: the report proxied as the person, targets and
pace (pro-rated by working days, zero targets left out), the exact WhatsApp text, the cache
(`fresh`, another day, a logged call clearing it), an older ERP site hiding it quietly,
`log_call` (the six outcomes and `callback_at`, a call back needing its time), and the 6 pm job (one message per manager, not on a day off, not when the setting
is off, silent on an older ERP site, a refused manager skipped).
`helpdesk/tests/test_call_batches.py`: the queue read live as the person (never cached; an older
ERP site and a department without batches told apart), an outcome posted with a trimmed note, a
made-up outcome and a call back without a future time refused before the ERP site is asked, the ERP
site's reason reaching the person, the next batch's reason passed on, the manager report, and the
6 pm message's batches section (and its absence on an older ERP site), and the call plans (read
as the manager, an older ERP site, a refusal as `LeadsForbiddenError`, a plan sent with its people,
trimmed product and sizes, clearing, no people refused before the ERP site is asked).
`helpdesk/tests/test_lead_calls.py`: Call posted as the signed-in person to TBO Smart's
telephony API, the recording streamed (audio only) and a refusal refused, the MyOperator
settings for admins only and proxied.
`helpdesk/tests/test_outreach.py`: see [Outreach](#outreach).
`helpdesk/tests/test_whatsapp_outreach.py`: see [whatsapp-outreach.md](whatsapp-outreach.md).
`helpdesk/tests/test_prospects.py`: an estimate and a start proxied as the person (POST, the values as a set of fields), the runs read live, a refusal naming who may, an older ERP site (the list hides quietly, estimate and start say so), and no access without leads.
