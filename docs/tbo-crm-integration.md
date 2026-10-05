# TBO CRM integration

Status: phase 1 (users) is implemented; phase 2 (customers from the CRM) is planned.
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

## Phase 1: every helpdesk agent is a CRM user (implemented)

- Who: active HD Agents with an enabled desk user, except Administrator and the TBO AI
  automation user.
- For each person:
  - not on the CRM site → create the User (welcome email if the setting is on, so they
    can set a password);
  - disabled on the CRM site → enable it;
  - no CRM role (Sales User, Sales Manager or System Manager) → give the role from
    settings through Frappe CRM's own `crm.api.user.add_existing_users`.
- People who leave the helpdesk are **not** removed or disabled on the CRM site; that is
  a manual decision there.
- When: every hour, when an agent is added or re-activated (HD Agent hook), and with
  **Sync users now** in Settings → CRM. The result is kept in Last Sync Result.
- A failure for one person is recorded and the rest continue; the hourly job logs
  connection errors instead of raising.
- Tests: `helpdesk/tests/test_crm_user_sync.py` (with `test_utils.FakeCRM`).

## Phase 2: customers from the CRM into helpdesk (planned)

Customers created on the CRM site are fetched into helpdesk as HD Customers (with their
contacts), so support can start the moment a deal is won. Open questions before
building it:

- Which record on tboindia is "a customer": a **CRM Organization**, a **CRM Deal** marked
  Won, or an ERPNext **Customer** (if ERPNext runs on tboindia)?
- One-way (CRM → helpdesk) only, or should helpdesk changes go back?
- Match existing HD Customers by name, or by a stored CRM ID (recommended: a
  `crm_reference` field on HD Customer)?
- How fast: every few minutes (pull) or a webhook from the CRM site?

## Security

- Keys are entered only in Settings → CRM, never sent in chat or email; rotate any key
  that was.
- The CRM API user needs System Manager (to create users) on the CRM site.
- The hub only creates and enables users and assigns CRM roles; it never deletes.
