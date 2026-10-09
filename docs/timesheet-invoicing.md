# Timesheet invoicing: billable time → a draft Sales Invoice

TBO bills support time from its own ERPNext, which runs on the CRM site
(tboindia.tbocloud.in). The hub has no ERPNext, so it creates the invoice there over REST,
through the CRM connection ([tbo-crm-integration.md](tbo-crm-integration.md)), always as a
**draft**: somebody in accounts checks and submits it in ERPNext. This page is the source of
truth for the feature; keep it current with the code.

Code: `helpdesk/integrations/crm/invoices.py` (the rules), `helpdesk/integrations/crm/client.py`
(the ERPNext calls), `helpdesk/api/invoices.py` (the dialog and lists),
`helpdesk/api/crm.py` `get_invoicing_options` (the settings pickers), doctype
`HD Customer Invoice`, UI in `desk/src/components/invoicing/`.

## Settings → CRM → Invoicing

Which company and item to bill with wasn't decided, so they are settings (HD CRM Settings),
picked from lists read live from ERPNext on the CRM site:

| Field | From the CRM site |
| --- | --- |
| `invoice_company` | Company. Empty means invoicing is off. |
| `invoice_item` | Item: enabled, a sales item, not stocked (a service item). One item for every line; each line's description says what the hours were. |
| `invoice_taxes_template` | Optional Sales Taxes and Charges Template of the company; its rows are copied onto the invoice. |
| `invoice_income_account`, `invoice_cost_center` | Optional, the company's leaf Income accounts and cost centers; else ERPNext's defaults. |
| `invoice_hourly_rate`, `invoice_currency` | The default rate, for customers without a contract rate per extra hour. Currency is the hub's Currency list. |

**Checked on save.** When an invoicing field changes, `HDCRMSettings.validate_invoicing`
asks the CRM site whether the company, item, template, account and cost center exist (and
belong to the company). An unknown one, a missing item or rate, or an unreachable site stops
the save with what to fix. Saving other CRM settings doesn't call the CRM site. Changing the
company clears the template, account and cost center in the form and takes the company's
default currency when none is set.

## What is billed

The time that counts is the support hours rule (`billable_logs()` in
`helpdesk/support_contracts.py`, see [support-contracts.md](support-contracts.md)): billable
time logs of timesheets that aren't cancelled, for the customer's projects and ticket tasks,
by the day the work was done. Invoicing adds one condition: **not yet billed**
(`Timesheet Detail.custom_billed_invoice` empty).

**Period.** The dialog offers the customer's contract periods so far (newest first, up to
12) and the last six calendar months. It opens on the latest contract period that has
ended (else today's), or last month for a customer without a contract.

**Mode** (only for a contract period):

- **Only the hours beyond the contract** (default). The period's included hours (with
  roll-over, as the Support hours tab shows them) cover the **earliest** work first; only the
  time after them is billed, at the contract's rate per extra hour. Hours earlier invoices of
  the same period already counted as included (`hours_covered`) are taken off first, so a
  second invoice for late time in the same period bills it in full.
- **All billable hours**: every hour, the included ones too.

A calendar month always bills all billable hours. Asking for "beyond the contract" on dates
that overlap a contract but aren't one of its periods is refused: the included hours belong
to a contract period.

**Rate.** The matched contract's `rate_per_extra_hour` (and its currency) when it has one, in
both modes; else the default rate and currency from settings. The dialog says which.

**Lines.** One per project (time outside projects is one "Support work outside projects"
line), or with **One line per task**, per project and task. Each line: the configured item,
description "<project · task>: support hours, <period>", qty = hours (2 decimals), rate.
Most hours first.

## Creating the draft

`create_invoice_draft(customer, start, end, mode, by_task, expected_hours)`:

1. The preview is worked out again on the server; nothing the browser sends is trusted but
   the choices. If the hours to bill differ from `expected_hours` (time was logged since the
   preview), it stops and asks to check the preview again.
2. The time logs are locked (`SELECT … FOR UPDATE`). If another invoice took any of them
   meanwhile, it stops. A second request for the same time waits for the first and then
   finds them billed.
3. The ERPNext **Customer** on the CRM site is found by name, ignoring case and extra spaces,
   as the customer sync matches. If there is none, it stops with
   `CustomerNotInERPNext` and says to create the customer in ERPNext (or convert its CRM
   organization). The customer sync can't fix this: it creates CRM Organizations, not ERPNext
   Customers, which need a group and territory.
4. The draft Sales Invoice is inserted (`docstatus` 0, never submitted): customer, company,
   posting and due date today, currency, remarks, items, and the template's taxes.
5. Only after the CRM site created it, in the same transaction: an **HD Customer Invoice**
   record (invoice name and link, period, mode, contract, hours logged / covered / billed,
   amount before tax) and every time log of the preview marked with it
   (`custom_billed_invoice`, `custom_billed_on`). The covered logs are marked too, so the
   period's included hours are settled.
6. If the CRM site refuses, nothing is marked. If marking fails after the invoice was
   created, the hub deletes the new draft again (and logs an error if it can't).

The dialog then shows **Open in ERPNext** (the CRM site's `/app/sales-invoice/<name>`, new
tab).

### Custom fields

In `get_custom_fields()` (`helpdesk/setup/install.py`), re-applied on every migrate:
`Timesheet Detail.custom_billed_invoice` (Link to HD Customer Invoice, read only, no copy,
indexed) and `custom_billed_on` (Date, read only, no copy).

## Invoices list and unlinking

**HD Customer Invoice** (`BILL-00001`…): status `Linked`, or `Unlinked` once its time was
freed. Read-only in the desk; only the API writes it.

The **Invoices** section lists them newest first, 10 at a time (Show more): on the Support
hours page everyone's, on a customer's Support hours tab that customer's. The ERPNext status
is read **after** the list shows (`get_invoice_statuses`, one call for the page, cached five
minutes per invoice): Draft, Unpaid, Partly Paid, Overdue, Paid, Cancelled…, or "Deleted in
ERPNext" when the CRM site answers 404. Each status has an icon and a label.

**Unlink** (`unlink_invoice`) appears when the invoice was deleted or cancelled in ERPNext.
The hub fetches it again; if it still exists and isn't cancelled, it refuses. Otherwise it
clears the marks on its time logs, sets the record `Unlinked` (kept for the record) and the
time can be invoiced again, with the period's included hours back.

## Permissions

**Agent Managers and System Managers** (`is_tasky_admin`) preview, create, list and unlink;
everyone else gets a PermissionError, project managers included. An invoice is a document in
the company's books, and these are the people who own the invoicing settings; project
managers manage contracts and see the hours, but don't bill. The buttons and lists are shown
only to them (`auth.isAdmin || auth.isManager`); the server checks. Settings → CRM is limited
to the same roles (`require_admin`).

## API (`helpdesk/api/invoices.py`)

- `get_invoice_preview(customer, start=None, end=None, mode="extra", by_task=False)`: the
  preview (period label, mode applied, contract and its included hours left, rate and where
  it came from, currency, hours logged / covered / billed, amount, lines) and the period
  choices.
- `create_invoice_draft(…)` (POST): see above; returns the new record.
- `get_invoices(customer=None, limit=20)`: `{rows, has_more}`, at most 100.
- `get_invoice_statuses(names)` (POST, the body carries a list): `{record: status}`.
- `unlink_invoice(name)` (POST).

A CRM site problem comes back as a message saying the CRM site couldn't be used and why.

## UI

- **Support hours page** (`/support-hours`): an **Invoice** button on each contract row
  (Create invoice draft on small screens) and the Invoices section under the contracts.
- **Customer → Support hours tab**: **Create invoice draft** next to the contract buttons,
  for customers with or without a contract, and the customer's Invoices section.
- **Dialog** (`InvoiceDraftDialog.vue`): period select, One line per task, the mode as two
  explained choices (contract periods only), three figures (Unbilled time, Covered by
  contract, To bill), the lines table with right-aligned numbers and the total before tax (a
  list on small screens), the rate note, then **Create invoice draft**. States: loading
  skeleton, error with Try again, nothing to bill (all covered, or no unbilled time), create
  error inline. After creating: what was created and **Open in ERPNext**.

## Tests

`helpdesk/tests/test_timesheet_invoicing.py`, with `FakeCRM` (companies, items, taxes
templates, accounts, cost centers, ERPNext customers, sales invoices) and `enable_invoicing`
in `helpdesk/test_utils.py`; `hold_commits`. Beyond-the-contract and all-hours maths, contract
and default rate, no contract, beyond-the-contract outside a contract period, non-billable time,
lines per task; create (draft, items, marks), taxes template, customer missing in ERPNext,
failed remote create, changed hours, no double billing (and late time in a billed period),
unlink only once gone or cancelled, list and statuses, permissions; settings: valid, unknown
records, required item and rate, other changes don't call the CRM site, the pickers.

## Known limits

- One item for all lines; different items per kind of work would need a mapping.
- An invoice in a currency other than the customer's billing currency in ERPNext is refused
  by ERPNext; the message is shown as it comes.
- Time logged on a timesheet that stays Draft counts (as for support hours).
