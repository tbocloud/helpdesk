# Customer health

One glance per customer: **Healthy**, **Watch** or **At risk**, with the reasons. Health is
worked out from records TBO already keeps (tickets, project tasks, support contracts,
sign-offs and the ERP connection); nothing is estimated and nothing new is stored. This page
is the source of truth for the rules; keep it current with `helpdesk/customer_health.py`.

## Signals

Each signal is judged **ok**, **watch** or **at risk** by a fixed rule, or **skipped** when the
customer has no data for it. A skipped signal never counts against the customer: a customer
without a support contract isn't penalised for it.

| Signal (`key`) | What it reads | Watch | At risk | Skipped when | Weight |
| --- | --- | --- | --- | --- | --- |
| SLA breaches (`sla`) | Tickets raised in the last 30 days with `agreement_status` Failed (first reply or resolution late; the SLA job keeps it current on open tickets) | 1 or more | 3 or more | no ticket with an SLA in the last 30 days | 3 |
| Waiting on us (`waiting`) | Tickets in an Open-category status whose last customer message (`last_customer_response`, else the ticket's creation) is over 3 days old | 1 or more | 3 or more | no open ticket | 2 |
| New tickets (`tickets`) | Tickets raised in the last 30 days against the 30 days before | 5 or more and 1.5× as many | 10 or more and 2× as many | no ticket in the last 60 days | 1 |
| Customer rating (`rating`) | Average rating of tickets resolved in the last 90 days, out of 5 | below 4 | below 3 | no rating | 2 |
| Project work (`work`) | Open tasks in the customer's projects that aren't Completed or Cancelled, judged like the Overview (`_task_item` in `helpdesk/api/work.py`): overdue, key and at risk | an overdue task, or a key task at risk | 3 overdue tasks, or an overdue key task | no open task | 2 |
| Support hours (`contract`) | The current period of the contract running today (`helpdesk/support_contracts.py`): % of hours used against % of the period gone | 50% or more used and 20 points ahead of the time gone | hours used up (100% or more) | no contract running today | 2 |
| Sign-offs (`signoff`) | Sign-offs in progress (Sent, In progress, Needs clarification, Ready to sign, Reopened) | one Needs clarification | an item Escalated | no sign-off in progress | 2 |
| ERP connection (`erp`) | The latest `HDS Support Connection` | Disconnected | Error | no connection | 1 |

## Status

A signal on watch scores its weight; at risk, twice its weight. The customer's points are
the sum:

- **At risk**: 6 points or more (e.g. SLA at risk alone, or two weight-2 signals at risk).
- **Watch**: 2 to 5 points.
- **Healthy**: under 2 points. One light signal on watch (new tickets, or the ERP
  connection Disconnected) isn't enough on its own; the Health tab still shows it.
- **No data**: every signal skipped (a new customer). Shown as a neutral "No data" badge and
  sorted after Healthy, rather than calling the customer healthy without evidence.

`reasons` are the labels of the signals with points, worst first.

## Computing and caching

`compute_all_health()` works out every customer at once: one grouped query for tickets, one
for ratings, one for open projects plus one for their open tasks (and the open dependencies
`_task_item` needs), the support hours of today's contracts (`contract_usage`, one hours
query), one for sign-offs with their escalated items, and one for connections. No query runs
per customer.

The result is cached in Redis (`helpdesk:customer_health`) for **10 minutes**. A change a
manager makes and expects to see at once clears it (`clear_health_cache`, `doc_events` in
`hooks.py`): a new, renamed or deleted HD Customer, and any change to an HD Support Contract,
HD Project Signoff or HDS Support Connection. Tickets, tasks and time logs change all day, so
they show within the 10 minutes instead of clearing the cache on every save.

The cache holds only facts and states; the words (labels, values, rules) are built per request
so they follow the reader's language.

**No snapshot doctype.** The ticket trend compares two windows of `creation` dates, which the
tickets already carry, so no daily snapshot is needed.

## Permissions

Health is a property of the customer, the same for everyone who may see the customer. It is
computed once for all customers (with `get_all`) so it can be cached, and every endpoint only
returns it for customers the viewer can read (`frappe.get_list("HD Customer")` /
`frappe.has_permission`), and only to agents (`agent_only`). It shows counts, never the titles
of records; the links open lists that apply the viewer's own permissions. Agents can read every
customer today (HD Customer `permission_query`), so they see every customer's health; managers
see all.

## API

- `helpdesk.api.customer_health.get_customer_health(customer)` (GET, agents who may read the
  customer): `status`, `points`, `reasons`, `thresholds` (`watch`, `at_risk` points) and
  `signals`, each with `key`, `state`, `weight`, `points`, `label`, `value`, `rule` and `link`
  (none when skipped). `null` for a customer newer than the cache (cleared on insert, so only
  in a race).
- `helpdesk.api.directory.get_customer_directory(search, sort, start, health)`: each row has
  `health` (`status`, `points`, `reasons`). `sort=health` orders worst first (status, then
  points, then name); `health` filters to `at_risk`, `watch`, `healthy` or `attention` (at risk
  or watch). Health isn't a column, so with either the list reads every matching customer
  (one query) and pages in Python.
- `helpdesk.api.home.get_home`: `company.customer_health` (`count`, `at_risk`, and up to 5
  `items` with the customer, status, points and reasons), worst first, only customers the
  viewer may read.

Links (`link.kind`): `tickets` (a `?filters=` tickets list: the customer plus the signal's
conditions; for Waiting on us, the customer's Open-category tickets, since the "last customer
message or creation" rule can't be one filter), `work` (the Overview filtered to the customer
for people who can see it, else the customer's Projects tab), `tab` (Support hours or
Projects tab), `signoff` (the project's Sign-off page when one project has the problem).

## UI

Shared: `desk/src/composables/customerHealth.ts` (types, `healthBadge` for the status badge
with text and icon, `signalLook`, `HEALTH_FILTERS`, `signalRoute`). Colour always comes with
an icon and a word: At risk red with a warning triangle, Watch amber with an alert circle,
Healthy green with a check, No data neutral with a dashed circle.

- **Customers list** (`pages/customer/Customers.vue`): a Health column (badge, and the reasons
  on one truncated line from `md`), a health filter (`health` in the URL) and "Health, worst
  first" sort (`sort=health`), through `useDirectory(url, { sorts, filterKey })`. On phones
  the health badge is on the right, with the ERP badge under it only when the connection is
  failing. Filtered to zero: "No customers with this health" with Show all customers.
- **Customer page** (`pages/customer/Customer.vue`): the health badge in the header links to
  the **Health** tab (`#health`, `components/customer/CustomerHealthTab.vue`): a summary (badge
  and "N points from: …"), then every signal, worst first and skipped last, with its state in
  words, its points, value, rule and weight, and a link to the underlying list. Loading
  skeleton, error with Retry, and "No health yet" for a brand-new customer.
- **Home** (`pages/home/components/HomeSide.vue`): "Customers at risk", first in the side
  column for people who see the company section, only when a customer is at risk or on watch:
  "N at risk, M to watch", the 5 worst with their badge and reasons (each opens the customer's
  Health tab) and "See all" to `/customers?health=attention&sort=health`.

## Tests

`helpdesk/tests/test_customer_health.py` (helpers `make_customer_ticket` and
`make_customer_project` in `helpdesk/test_utils.py`; `hold_commits`): each signal's rule and
thresholds, the status from points, skipped signals not counting and No data, reasons worst
first; from records: ticket signals, an overdue key task, support hours used up, an escalated
sign-off and a failing connection; the page payload (labels, rules, links); agents only, and
an agent limited to one customer sees only that one on Home, the Customers list and the
page; the Customers list's health filter and sort; the cache reused and cleared by a change.
