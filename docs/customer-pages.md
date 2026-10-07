# Customer pages: Customer report, Customers, Contacts

Pages about the people and companies TBO supports: the monthly report used for billing and
reviews, and the directory of customers and contacts with each one's page. They follow
[ui-guidelines.md](ui-guidelines.md) and reuse the shared pieces described in
[workspace-pages.md](workspace-pages.md) (`StatTile`, `SectionCard`, `TaskyState`,
`TaskyBadge`, `tone.ts`, `errorText`). Every figure comes from the server; nothing is
estimated in the browser.

## Customer report (`/customer-report`)

`desk/src/pages/work/CustomerReport.vue`; API `helpdesk.api.customer_report.get_customer_report(
month, customer)` and `download_customer_report(month, customer)` (CSV). Agent Managers and
project managers only (`canSeeCustomerReport`; the server checks the same).

- **Filters** in the URL: `month` (`YYYY-MM`; last month is the default and left out) and
  `customer`. The server narrows the rows to that customer, so the tiles, the table and the CSV
  all describe the same thing. The CSV is named `customer-report-<month>[-<customer>].csv`
  (the customer part keeps letters and digits only).
- **Tiles** (from the report's `totals`): Tickets opened, Tickets resolved (with the average
  rating when there is one), SLA met (with "kept X of Y"; red with a warning icon under 80%),
  Tasks done, Hours logged.
- **By customer** card: on `md` and up a table with right-aligned tabular numbers and a Total
  row (only when there are two or more rows); below `md` one block per customer with labelled
  figures. SLA under 80% is red and a rating under 3 amber, as before.
- **States**: loading skeletons, an error with Retry, "Nothing for <customer> in <month>"
  (Show all customers) and "Nothing in <month>".
- **Download CSV** is the page's primary action.

## Customers (`/customers`) and Contacts (`/contacts`)

`desk/src/pages/customer/Customers.vue` and `desk/src/pages/contact/Contacts.vue`, both built on
`desk/src/components/DirectoryList.vue` and `useDirectory()` in
`desk/src/composables/directory.ts`. APIs: `helpdesk.api.directory.get_customer_directory`
and `get_contact_directory(search, sort, start)`, agents only.

- **One page per call**: 50 rows plus `has_more` and `total`; "Show more" appends the next
  page. Search and sort live in the URL as `q` and `sort` (`name`, the default, or `newest`).
- **Counts respect permissions**: every read is a `frappe.get_list`, so open tickets and
  projects only count what the viewer may see (a plain agent sees the projects they are on).
- **Customer row**: logo, name, domain; Open tickets (Open and Paused), Active projects (not
  Completed or Cancelled) and ERP connection (the latest `HDS Support Connection` for the
  customer: Connected, Error, Disconnected or Pending, as a badge with an icon; "None"
  otherwise).
- **Contact row**: avatar, name, email (or phone); the customers they belong to (from the
  customers' member tables); Open tickets (tickets whose `contact` is them); Portal: Portal
  access (has a user), Invited or Invite expired (an open helpdesk `User Invitation`, read with
  `get_all` like `get_contact_info` does), else "No access".
- **Rows**: the whole row is one link (a stretched `RouterLink` with a focus ring). Below `md`
  the counts fold into the second line and the badge stays on the right.
- **Bulk delete** (Agent Managers and admins, `md` and up): checkboxes, "Select all N shown",
  and a confirm dialog naming how many. It calls `frappe.desk.reportview.delete_items` like
  the old list did: up to 10 are deleted at once and any that refuse (still linked elsewhere)
  are reported and stay selected; more than 10 are queued.
- **States**: loading skeleton, error with Retry, "No customers match …" (Clear search) and
  "No customers yet" (New customer); the same for contacts.
- **Primary action**: New customer / New contact (the same dialogs as before; the sidebar's
  New contact still opens it through `dialogState.ts`).

These two lists used to be the generic `ListViewBuilder`. They no longer offer its field filter
builder, column resizing or saved views (the customer and contact lists had no way to create
a view); search covers name, domain, email and phone instead.

## Customer page (`/customers/:id`)

`desk/src/pages/customer/Customer.vue`.

- **Header** (`components/PageInfo.vue`, shared with the contact page): logo, name, domain,
  email, phone, country and the ERP connection (badge, site host and when it was last
  checked). A connection in Error shows its last error under the header. Edit and the menu
  with Delete customer stay for Agent Managers and admins.
- **Support figures** (`components/customer/TicketStats.vue`, shared with the contact page):
  four `compact` `StatTile`s from `helpdesk.api.ticket_stats.get_ticket_stats(dt, dn, period)`: average
  first response, average resolution, SLAs failed (red with an icon when above zero), and the
  rating (all time, with how many). The period select offers the last 7, 30 or 90 days; each
  tile says in words how it compares with the days before ("+12% on the 30 days before"),
  with no colour. Shown on phones too.
- **Tabs** (hash in the URL: none, `#contacts`, `#projects`): Tickets (unchanged list with
  search, status, priority and contact filters; rows are links that open the ticket in a new
  tab, sortable headers are buttons), Contacts (cards; invite, set primary, manager role,
  remove), Projects (`components/customer/CustomerProjectsTab.vue`: the customer's projects the
  viewer may see, open first, with the end-date note from `projectEndNote()` in
  `pages/tasky/taskMeta.ts`, which the Projects page cards use too, and "Open in Projects").

## Contact page (`/contacts/:id`)

`desk/src/pages/contact/Contact.vue`: the same header (with the customers as links and the
invitation badge from `PORTAL_BADGE` in `composables/contact.ts`), the same support figures,
and the Tickets and Feedback tabs. Edit and the menu (invite as user, resend invite, reset
password, delete) stay for Agent Managers and admins.

## Removed

- `BarChartCard`, `LineChartCard`, `ChartCardBase` and `SkeletonLoader` (only the old support
  figures used them; their charts had hard-coded colours, gradients and a random placeholder
  chart), and `buildPercentageChange` in `utils.ts`.
- `helpdesk.api.ticket_stats.get_sla_violations`, `get_avg_first_response_time` and
  `get_avg_resolution_time`: only those cards called them; `get_ticket_stats` returns all
  four figures for a period.
