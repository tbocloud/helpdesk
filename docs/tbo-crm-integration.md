# TBO CRM integration

Status: users and customers both ways are implemented (missing records only), billable
time becomes draft Sales Invoices in the CRM site's ERPNext, and the CRM site's holidays and
approved leave are read into the hub.
This document is the source of truth for the feature and changes with it.

## What it connects

- **TBO Support**: this hub (Frappe Helpdesk fork, tbocloud/helpdesk).
- **TBO CRM**: a Frappe CRM site (fork tbocloud/crm), e.g. https://tboindia.tbocloud.in.

The hub calls the CRM's REST API. The connection lives in **Settings → CRM**
(HD CRM Settings): site URL, API key and API secret of a System Manager user on the
CRM site. The secret is a Password field and never comes back to the browser.

Code: `helpdesk/integrations/crm/client.py` (REST client), `helpdesk/integrations/crm/users.py`
(user sync), `helpdesk/api/crm.py` (settings page actions),
`desk/src/components/Settings/CRM/CRMSettings.vue`.

## Users, both ways (implemented)

Only what's missing is created; existing accounts keep their roles and details.

- **Helpdesk → CRM** (*Add helpdesk agents missing in the CRM*): active HD Agents with an
  enabled desk user, except Administrator and the TBO AI automation user.
  - not on the CRM site → create the User (welcome email if that setting is on);
  - disabled on the CRM site → enable it;
  - no CRM role (Sales User, Sales Manager or System Manager) → give the role from settings
    through Frappe CRM's own `crm.api.user.add_existing_users`.
- **CRM → helpdesk** (*Add CRM users missing in helpdesk, as agents*): users Frappe CRM lists
  as CRM users (`crm.api.session.get_users`) without a helpdesk account get a User and an
  active HD Agent (HD Agent adds the Agent role). Existing helpdesk users are not changed.
- **Leaving** (*Disable CRM users who leave helpdesk*): users this connection created on the
  CRM site (remembered in HD CRM Settings, hidden field `created_in_crm`) are disabled there
  once they're disabled or deactivated in helpdesk. People created directly in the CRM are
  never touched, and nobody is deleted.

## Customers, both ways (implemented)

*Sync customers both ways*: helpdesk **HD Customer** ↔ the CRM's customers, matched by
name ignoring case and extra spaces. On the CRM site a customer is a **CRM Organization**,
or an ERPNext **Customer** (not disabled) when that site runs ERPNext too; both are read.

- An HD Customer missing in the CRM becomes a CRM Organization (with its domain as website);
  it isn't created as an ERPNext Customer, which needs a group and territory.
- A CRM Organization or ERPNext Customer missing in helpdesk becomes an HD Customer
  (website as domain).
- Existing records on either side are never changed or deleted. Contacts are not synced yet.

Code: `helpdesk/integrations/crm/customers.py`.

## Invoicing (implemented)

Billable time becomes a **draft Sales Invoice in ERPNext on the CRM site**, over the same
connection. Settings → CRM → **Invoicing** picks the company, service item, optional taxes
template, income account and cost center from lists read live from that site
(`get_invoicing_options`), plus a default hourly rate and currency; they are checked against
the site when saved. The invoice's customer is the ERPNext Customer with the HD Customer's
name (matched like the customer sync). Details: [timesheet-invoicing.md](timesheet-invoicing.md).

The CRM API user therefore also needs to read Company, Item, Sales Taxes and Charges
Template, Account, Cost Center and Customer, and to create, read and delete draft Sales
Invoices (System Manager or Accounts Manager on that site).

## Holidays and leave (implemented, read only)

The owner's request (2026-10-10): TBO's holidays live in ERPNext on tboindia.tbocloud.in, so
the hub shows and uses those. Nothing is ever written to the CRM site.

Code: `helpdesk/integrations/crm/holidays.py` (the sync), `helpdesk/work_calendar.py` (the
readers everything else uses), `helpdesk/helpdesk/doctype/hd_leave/`, Settings → CRM →
**Holidays and leave**.

### Holidays

- **Which lists**: the Holiday Lists ticked in Settings → CRM (a live list from the CRM site,
  `get_holiday_options`, stored one per line in `holiday_lists`). None ticked: the
  `default_holiday_list` of the invoicing company, or of the only company on the site.
  ERPNext lists are often per year (or per financial year), so tick next year's list once HR
  has made it. Rows from 1 January this year to 31 December next year are read.
- **Where they're stored**: as rows of **every enabled SLA's holiday list** (HD Service
  Holiday List, child HD Holiday), with `synced_from_crm` set. Why there: that is the store
  the SLA clock (`HDServiceLevelAgreement.get_holidays`), the follow-ups and working-day
  counts (`work_calendar.company_holidays`, `recurrence.working_day_checker`), capacity
  (`api.capacity.holidays`) and the Saturdays-off sync already read, so they all count a
  synced holiday as a day off with no other change, and there's no second holiday store.
  `work_calendar.save_holidays` is shared with the Saturdays-off sync.
- **Upsert by date**: a date the list doesn't have yet is added; a synced row whose
  description changed upstream is updated; a synced date that disappeared upstream (inside
  the window) is removed. Rows people entered in the hub are never changed or removed, and a
  date they already have isn't added a second time. Synced rows are read-only in Settings →
  Business holidays ("From TBO CRM", no edit or delete); anything changed there by other means
  is put back on the next sync.
- **Weekly offs** (ERPNext rows with `weekly_off` set) **map onto the hub's own weekly-off
  rule** (HD Work Settings: Weekly Off and Saturdays Off) instead of becoming hundreds of
  dated rows. A weekly off the rule already skips is not stored; one it doesn't (say the CRM
  site has every Saturday off and the hub only the 2nd and 4th) is stored as a dated synced
  row, so it still counts as a day off, and the result says the two disagree. The rule is
  **not** changed by the sync: it also drives task due dates and estimates, and a nightly job
  silently moving those would surprise people. Fix it in Work settings if the CRM site is
  right; the extra dated rows then disappear on the next sync.
- The count shown is the dated holidays read in the window (named holidays plus the weekly
  offs the hub's rule doesn't cover), including dates a hub holiday already covers.

### Approved leave

On by default (*Sync approved leave*).

- **What**: Leave Applications with `status = Approved` and `docstatus = 1` overlapping 30
  days ago to 60 days ahead.
- **Who**: the Employee's `user_id`, else `company_email`, else `prefered_email`, matched
  ignoring case to a hub desk user. Leave of someone without a match is skipped and counted
  ("N couldn't be matched to a person here").
- **Stored** in **HD Leave** (user, employee name, leave type, from, to, half day, half-day
  date; named after the Leave Application), read-only; System Managers and Agent Managers can
  read it. Leave that is no longer approved upstream (cancelled, or outside the window) is
  removed.
- **Used by**: the follow-ups (nobody on leave is nudged or escalated to; see
  [follow-ups.md](follow-ups.md#leave)), capacity (a day of leave has no available hours, a
  half day half), the Calendar, Home, the Team page and the assignee pickers. The leave type
  stays in HD Leave; the pages show only dates.
- **No access**: when the API user can't read Leave Application or Employee (HTTP 403),
  holidays still sync and Settings → CRM shows "Leave sync needs read access to Leave
  Application and Employee on tboindia.tbocloud.in". That message is not written to the Error
  Log, since it's a setting to fix rather than a failure.

### When and errors

- Daily at **06:15** (`helpdesk.integrations.crm.holidays.sync_holidays_job`, cron
  `15 6 * * *` in `hooks.py`), before the working day, when the connection is enabled and
  either switch is on; and with **Sync holidays now** (System Managers and Agent Managers,
  `helpdesk.api.crm.sync_holidays_now`).
- Settings → CRM shows when it last synced, how many holidays and leave it holds, the result
  (including the weekly-off comparison) and any problem with a way forward.
- A timeout, a refused key or a missing list never breaks the hub: the run returns the
  problem, records it (`holiday_sync_error`), writes a short Error Log ("CRM holiday sync
  failed") and tries again the next morning. What was synced before stays in use. Holidays
  and leave are independent: one failing doesn't stop the other.

Tests: `helpdesk/tests/test_crm_holidays.py` (with `test_utils.FakeCRM`) and the leave cases in
`helpdesk/tests/test_follow_ups.py`.

## When it runs

Every hour (users, then customers), soon after an agent is added, re-activated or
deactivated (HD Agent hook, queued once), and with **Sync now** in Settings → CRM. One
failing record is listed in Last Sync Result and the rest continue; the hourly job logs
connection errors instead of raising.

Tests: `helpdesk/tests/test_crm_user_sync.py` and `helpdesk/tests/test_timesheet_invoicing.py`
(with `test_utils.FakeCRM`).

## Possible next steps

- Contacts of a customer, both ways.
- A CRM Deal marked Won creating the customer's project in helpdesk.
- A webhook from the CRM site for new organizations, instead of waiting for the hourly run.

## Security

- Keys are entered only in Settings → CRM, never sent in chat or email; rotate any key
  that was.
- The CRM API user needs System Manager (to create users) on the CRM site. For holidays
  and leave it needs read access to **Holiday List**, **Company**, **Leave Application** and
  **Employee** (System Manager has it; with a narrower role, add read in Role Permissions).
- The hub only creates, enables and (for users it created) disables records. The one
  deletion is a draft Sales Invoice it created itself, when recording it in the hub failed.
  Holidays and leave are only read.
