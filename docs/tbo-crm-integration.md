# TBO CRM integration

Status: users and customers both ways are implemented (missing records only), and billable
time becomes draft Sales Invoices in the CRM site's ERPNext.
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
- The CRM API user needs System Manager (to create users) on the CRM site.
- The hub only creates, enables and (for users it created) disables records. The one
  deletion is a draft Sales Invoice it created itself, when recording it in the hub failed.
