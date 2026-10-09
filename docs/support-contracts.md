# Support contracts: AMC and support-hours tracking

Customers buy support from TBO as a number of hours per period: an AMC, a block of hours or a
retainer. For each customer TBO needs to see the hours included, used and left in the current
period, and to hear before they run out, because that drives billing. This page is the source
of truth for how it works; keep it current with the code.

## The contract (`HD Support Contract`)

`helpdesk/helpdesk/doctype/hd_support_contract/`. Named `SC-00001`…, titled by its name.

| Field | Notes |
| --- | --- |
| `contract_name` | What TBO and the customer call it, e.g. "ERPNext AMC 2026-27". |
| `customer` | HD Customer. |
| `contract_type` | AMC, Support block, Retainer. Only a label; it doesn't change the maths. |
| `status` | Active, Expired, Cancelled. The daily job sets Active contracts past their end date to Expired. |
| `account_manager` | Optional User, alerted with the others. HD Customer has no owner field, so it lives here. |
| `start_date`, `end_date` | Both required. |
| `billing_period` | Monthly, Quarterly, Yearly, One-off block. |
| `hours_per_period` | More than 0. For a block, the hours in the block. |
| `rollover_unused` | Unused hours are added to the next period. Cleared for a block. |
| `alert_threshold` | % used that triggers the first alert, 1 to 100 (default 80). |
| `rate_per_extra_hour`, `currency` | Optional. The rate an invoice draft bills this contract's hours at; without it, the default rate in Settings → CRM → Invoicing ([timesheet-invoicing.md](timesheet-invoicing.md)). |
| `notes` | Free text. |
| `alerted_period_start`, `alerted_stage` | Hidden: the period and stage (Threshold / Overage) the last alert was sent for. |

**One contract at a time, per day.** A customer may have several contracts, but Active ones may
not overlap in dates (`validate_no_overlap`). This was chosen over "one Active contract per
customer" so a renewal can be entered before the current contract ends. On any day at most one
contract counts the customer's hours, so hours are never counted twice.

Changing the dates, billing period, hours, roll-over or alert level clears the alert state, so
the alerts are re-judged against the new terms.

**Permissions.** System Manager, Agent Manager and Project Manager roles create, edit and
delete contracts (DocType role permissions; the UI writes through `frappe.client.insert` and
`set_value`, which check them). Agents have no DocType access; they read through the API below.

## Periods

`contract_periods(start, end, billing_period)` in `helpdesk/support_contracts.py`.

- Monthly, quarterly and yearly periods start on the contract's start date and repeat every 1,
  3 or 12 months. Each is computed from the start date (`add_months(start, n)`), so a contract
  from the 31st starts each period on the 31st or the month's last day without drifting.
- The last period ends with the contract (it may be short).
- A one-off block is one period from start to end.
- Only periods that have started are listed; a contract that hasn't started has none.

**Roll-over.** With `rollover_unused`, a period's hours are `hours_per_period` plus what was
left of the previous period's hours (which may itself include roll-over), never less than
zero: an overage isn't taken from the next period. Without it every period has
`hours_per_period`.

Each period (`period_usage`): `start`, `end`, `included`, `carried_in`, `allowance`
(included + carried in), `used`, `remaining` (negative when over), `percent`, `stage` and
`is_current`. Stage: `over` at 100% or more, `warning` at the alert level or more, else `ok`.

## What counts as used

`billable_logs()` / `daily_billable_hours()` in `helpdesk/support_contracts.py`. A time log
(`Timesheet Detail`) counts when:

- its timesheet isn't cancelled (Draft counts, like the customer report: a timesheet stays
  Draft when its submit fails, and the time was still worked);
- it is **billable** (`custom_billable`);
- it was logged in the period (by `from_time`, the day the work was done);
- it belongs to the customer: the customer of the time log's project, else of its task's
  project, else of the HD Ticket its task was raised from (`Task.hd_ticket`, set when a task is
  created from a ticket in `helpdesk/api/work.py`). Time isn't logged against tickets directly.

All contracts' hours come from one grouped query per call (customer and day), and are split into
periods in Python, so the Support hours page and the daily job don't query per contract.

### Billable flag

`Timesheet Detail.custom_billable`, a Check custom field defined in `get_custom_fields()`
(`helpdesk/setup/install.py`) with default 1, applied on install and every migrate. Adding the
column fills existing time logs with 1, so all time logged before this counts as billable.

- **Log time** (`create_timesheet(…, billable)`) has a Billable checkbox, on by default.
- Completing a task (`complete_task`) logs billable time.
- The timesheets CSV export has a Billable column.

## Alerts (daily job)

`send_support_hours_alerts()` in `helpdesk/support_contracts.py`, in the `daily` scheduler.

1. Active contracts whose end date has passed become Expired.
2. For each Active contract running today, the current period is judged (`alert_due`):
   - at or past the alert level, the **threshold** alert, once per period;
   - at 100% or more, the **overage** alert, once per period, also after a threshold alert. A
     period that goes straight past 100% gets only the overage alert.
3. Who: the contract's account manager, the managers, owners and leads of the customer's open
   projects and every enabled Agent Manager (`get_summary_recipients`, the same people as the
   weekly summary), through `notify_users` (notification panel plus email or Teams). The link
   opens the customer's Support hours tab.
4. The contract records the period and stage sent, so a later run doesn't repeat it. The
   messages name the period, not running totals, so `notify_users` dedupes them too.
5. **Email the customer** (HD Work Settings `support_hours_email_customer`, off by default;
   Settings → Tasks → Support hours): the same two alerts are emailed to the customer's
   contacts and its own email (`portal_emails`), with the hours used and left.

One contract failing is logged and doesn't stop the others.

## API (`helpdesk/api/support_contracts.py`)

All agent-only. Managers are Agent Managers, System Managers and project managers
(`is_project_manager`).

- `get_customer_support_hours(customer, contract=None)`: the customer's contracts (newest start
  first) and, for the chosen one (default: today's Active contract, else the next to start,
  else the latest), its periods (newest first), the shown period (today's, or the last one
  for an ended contract) and that period's billable hours by project, by ticket and, for
  managers only, by person. `can_manage` says whether the viewer may edit. Allowed for managers
  and for agents who can read at least one of the customer's projects; others get a
  PermissionError. Hours per person are left out for non-managers because timesheets are
  private to their owner and the people who run the project. Non-managers also see names only
  for the projects and tickets they may read (`frappe.get_list`); the hours of the others are
  added up in one unnamed row (`other: 1`), so the totals still match. Each breakdown row is
  `{name, label, hours}`; `name` is empty for time outside any project.
- `get_support_hours(contract_type=None, stage=None)`: managers only. Every Active contract
  running today with its current period, most used first; `counts` of `warning` and `over`
  and `total` follow the type filter.
- `download_support_hours(contract_type=None, stage=None)`: the same rows as CSV (customer,
  contract, type, billing period, current period, hours included, rolled over, used, left,
  extra hours, % used, rate per extra hour, currency). Text cells pass through `csv_safe`
  (`helpdesk/utils.py`), so a name starting with =, +, -, @, a tab or a carriage return gets a
  leading quote and a spreadsheet won't run it as a formula; the customer report and
  timesheets CSVs use it too.

## UI

Shared pieces: `desk/src/composables/supportHours.ts` (types, `usageText` "32 of 40 h used ·
8 h left" / "· 4 h over", `periodText`, stage tone, icon and label) and
`desk/src/components/customer/SupportHoursMeter.vue` (a row's meter, `role="meter"` with the
usage as its text). Colour follows the stage: neutral under the alert level, warning at it,
danger at 100%, and always with the numbers and an icon.

### Customer page: Support hours tab (`#support-hours`)

`desk/src/components/customer/CustomerSupportHoursTab.vue`.

- **Current period**: a `StatTile` with the % used, the meter and the usage text, then the
  period's hours (with what rolled over) and when the period ends. A contract that hasn't
  started says when it starts.
- **Where the hours went**: by project (links to the project), by ticket (links to the
  ticket) and by person (managers only), each with a neutral share bar.
- **Contract**: type, billing period, dates, hours, roll-over, alert level, account manager,
  extra-hour rate and notes, with its status badge.
- **Periods**: every period so far, newest first (a table from `md`, two-line rows below).
- **Contract picker** when the customer has more than one; the chosen one is `?contract=` in
  the URL.
- **Manage** (managers): Edit contract and New contract open
  `SupportContractDialog.vue` (labelled fields, Combobox for the account manager and currency so
  Escape and outside clicks still close the dialog, inline errors from the server such as an
  overlapping contract, "Create contract" / "Save changes").
- **States**: loading skeleton, error with Retry, no access ("You can't see these support
  hours"), no contract (New contract for managers).
- **Invoicing** (Agent Managers and System Managers): **Create invoice draft** and the
  customer's **Invoices**, also for customers without a contract. Only the hours beyond the
  contract's included hours are billed by default. See
  [timesheet-invoicing.md](timesheet-invoicing.md).

### Support hours page (`/support-hours`)

`desk/src/pages/work/SupportHours.vue`, in the Workspace sidebar after Customer report, for the
same people (`canSeeCustomerReport`: Agent Managers and project managers; the server checks).

- Tiles: Running today, Running low, Used up. The last two are toggles that filter the list
  (`stage` in the URL).
- Type filter (`type` in the URL).
- List, most used first: customer (opens its Support hours tab), contract and type, current
  period, meter, % used (with an icon when low or used up), used / hours, left or over.
  A table from `md`, two-line rows below.
- **Download CSV** is the primary action and follows the filters.
- States: loading skeleton, error with Retry, nothing matching the filters (Show all
  contracts), no contracts running (Open customers).
- **Invoicing** (Agent Managers and System Managers): an **Invoice** button per contract
  opens the invoice draft dialog for its customer, and an **Invoices** section lists every
  draft created from the hub. See [timesheet-invoicing.md](timesheet-invoicing.md).

Billed time logs carry `custom_billed_invoice`; they still count as used hours here (the
work was done), so invoicing doesn't change any usage figure on this page.

## Tests

`helpdesk/tests/test_support_contracts.py` (helpers `make_support_contract` and
`make_timesheet(…, billable)` in `helpdesk/test_utils.py`; `hold_commits`): monthly, quarterly,
yearly and block periods; roll-over; stage; billable, cancelled, ticket-task and other-customer
time; threshold alert once; overage after threshold; nothing below the threshold; expiry;
overlapping contracts; agent and manager access; the managers' list order and stage filter.
