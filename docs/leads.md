# Leads

Status: Phase 1 implemented (list, new lead, lead page with stage, notes, edit and read-only
quotations). This document is the source of truth for the feature and changes with it.

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
| `get_options` | GET | | `{stages: [{name, label, type, color}], sources, segments, owners: [{email, full_name}], territories, industries}` |
| `list_leads` | GET | `search, stage, owner, segment, view, start, page_length` | `{rows: [{name, lead_name, company_name, email_id, mobile_no, tbo_stage, segment, lead_owner, owner_name, score, next_follow_up, modified}], total}` |
| `get_lead` | GET | `name` | `{lead: {...}, timeline: [...], quotations: [...], allowed_stages: [...]}` |
| `create_lead` | POST | `data` | the lead (at least `name`) |
| `update_lead` | POST | `name, data` | the lead |
| `set_stage` | POST | `name, stage, note` | the lead |
| `add_note` | POST | `name, note` | the note |

- `view` is `all`, `mine`, `call_today` or `follow_up`. The hub sends `page_length` 20
  (at most 100) and `start` from 0.
- `data` (create and update) uses these keys: `lead_name, company_name, email_id, mobile_no,
  source, segment, territory, industry, lead_owner, next_follow_up` (date, `YYYY-MM-DD`).
  An update sends only the fields that changed; an empty string clears a field.
- `allowed_stages` may be stage names or stage objects; the hub offers only those (minus the
  current stage).
- Timeline entries are TBO Smart's `{kind, at, who, who_name, text, ref}` (kind: note, call,
  activity, meeting, stage, quotation), newest first; each kind has its own icon and a screen
  reader label, and `text` is shown as sent (a stage move reads "Contacted → Proposal Sent").
- Quotations are read as `{name, transaction_date, tbo_quote_status, grand_total, currency}`.
- `next_follow_up` on create or update schedules a Sales follow-up for the lead owner on the
  ERP site (tbo_smart#25); clearing it adds nothing and doesn't close the open one.
- Stage colours from the ERP site are not used, to keep the hub's one-accent rule: a stage
  whose `type` is `Won` is green, `Lost` red, every other stage gray, always with its label.

## Hub endpoints

`helpdesk/api/leads.py`, thin typed proxies (writes are POST only): `get_options`,
`list_leads`, `get_lead`, `create_lead`, `update_lead`, `set_stage`, `add_note`. They check
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
| 403 saying only the hub's integration user may act for someone else | The hub's API user on (host) isn't the site's integration user: it needs the role in TBO Smart Settings → Hub integration role there (blank: Hub Integration). Ask an admin to check that field and add the role it names to the API user on (host). |
| 403, 404 or 417 saying the method isn't there or isn't whitelisted | Leads need the latest TBO Smart on the ERP site (host). |
| Any other 403 | You don't have a sales account on the ERP site yet. Ask an admin to give (email) the Sales User role on (host). |
| Any other 404 | That lead isn't on the ERP site any more, or you can't see it. |
| Other 4xx with a message | The ERP site's own message (e.g. a missing field, a stage it refuses); never its exception text. |
| 5xx, or a 4xx with only an exception | The ERP site ran into a problem (status). Try again; if it keeps happening, tell an admin. |

Setup and reach problems are `LeadsUnavailableError`, the rest `LeadsError` (both
ValidationError, so the page shows the message with *Try again*).

## The pages

- **Leads** (`/helpdesk/leads`, `desk/src/pages/leads/Leads.vue`): views All, Mine, Call
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
- The pickers' options (`get_options`) are fetched once per session (`leadOptions` in
  `desk/src/pages/leads/leads.ts`).
- Sidebar: *Leads* in Workspace (teal group), shown when `can_use_leads`.

## Next phases

- Phase 3/4: proposals and quotations made from the lead page. `LeadQuotations.vue` is the
  place: it gets the actions, and `get_lead`'s `quotations` the extra fields. No placeholder
  UI is shown until then.

## Tests

`helpdesk/tests/test_leads.py` with `test_utils.FakeCRM` (`lead_answers`, `lead_calls`,
`lead_error`) and `test_utils.enable_leads`: off by default, `acting_user` on every call,
writes posted, view and page size checked, teams and inactive agents gated, and each error
mapped.
