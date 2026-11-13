# CRM dashboards

**Status:** built 2026-11-12 (requirement section 16, "Configuration-driven dashboard"). This
document is the living source of truth for the feature; update it with every change.

Configurable lead reporting across companies: admins connect each company's CRM site, map its
lead fields and statuses, shape the organisation, and build dashboards from templates. Nothing
about a company, branch, team, person or status is in the code.

## Why it works this way

- **Leads live on other sites.** The hub has no ERPNext; each company's leads are on its own
  ERPNext (or Frappe CRM) site. TBO Smart's hub API (docs/leads.md) is TBO-specific and isn't
  in this repo, so the dashboards read any site through Frappe's standard REST API with an API
  key, the same `CRMClient` the CRM connection uses.
- **A reporting copy, not live calls.** Every filter change would otherwise be a round of calls
  to several sites. The hub copies only the mapped fields of each lead into
  `HD CRM Report Lead` and counts there with SQL. The source stays the master.
- **Not the lead mirror.** `HD Lead Mirror` (docs/lead-mirror.md) is the Leads page's copy of
  the TBO ERP, fed by TBO Smart's change feed, keyed by lead name and carrying TBO fields. The
  dashboards need any site, several of them, and mapped fields (company, branch, money,
  closing date) the mirror doesn't have. Joining the two would tie the mirror to the mapping;
  they stay separate.
- **Derived, not stored, organisation.** A lead often names only its owner. Its team,
  department, branch and company come from the organisation (`HD CRM Org Unit`) and are worked
  out again locally whenever a mapping or relationship changes, so moving a person to another
  team needs no re-read of any site.

## Data model

| DocType | What it is |
| --- | --- |
| `HD CRM Source` | One site's leads: connection (its own URL, key and secret, or *Use the CRM connection* in Settings → CRM), lead doctype (Lead / CRM Lead), company for leads without one, currency and rate to the reporting currency, the field mapping, the status mapping (`HD CRM Status Map`), sync interval and health. Tracks changes. |
| `HD CRM Status Map` | Child: a status → Open / Won / Lost / Converted / Other, optionally for one company of the source. |
| `HD CRM Report Lead` | The reporting copy: `raw` (the mapped fields as sent) plus the columns counted by (company, branch, department, team, employee, lead owner, status, category, lead source, expected revenue and won value in the reporting currency, created on and its month, closed on, days to close, `excluded`). Named `<source>::<lead>`. Read-only; written in bulk by the sync. |
| `HD CRM Org Unit` | A company, branch, department, team or employee of a source, by the name its leads carry: display name, active, parents (company, branch, department, team), the employee's user, the team's leader, and origin (Synced / Added here). Tracks changes. |
| `HD CRM Dashboard` | One dashboard: name, description, active, default, roles (`HD CRM Dashboard Role`), scope, covered units (`HD CRM Dashboard Unit`), default period, money format, filters (`HD CRM Dashboard Filter`, with defaults), KPI cards (`HD CRM Dashboard KPI`) and charts (`HD CRM Dashboard Chart`), each list in display order. Tracks changes. |
| `HD CRM Settings.dashboard_currency` | The reporting currency of every dashboard. |

The registry (`helpdesk/crm_dashboard/registry.py`) is the one home of the categories,
metrics, groupings, filters, periods, scopes, chart presets and templates. The doctypes
validate against it and the settings page reads it from `get_settings`.

## Sync (`helpdesk/crm_dashboard/sync.py`)

- **Every 15 minutes** `sync_due_sources` queues each enabled source whose interval (15 minutes,
  hour, 6 hours, day) has passed; a failed run keeps its last good time, so it is retried at the
  next tick. **Nightly** `full_sync_all` reads every lead of every source, which drops the ones
  deleted there.
- A run reads the leads changed since the last one (`modified` from a minute before the newest
  copied, on the source's own clock), in pages of 500, then:
  1. adds the units it finds: ERPNext's Company, Branch, Department and Employee on the source
     (skipped when the source has none or may not read them), and every org value on the leads.
     An employee record becomes a unit only when a lead names that person. Units are added top
     down; a new unit takes the closest parent seen next to it on a lead. **The sync never
     changes what an admin set**: it only fills empty fields and never switches a unit off;
  2. recounts the leads it read from their `raw` fields, or every copied lead of the source when
     it added or changed a unit (a new parent can move any lead), and writes only the rows
     that changed.
- One run per source at a time (a file lock); a recount waits for a running sync. A sync, a full
  sync and a recount are separate queued jobs, so a full read asked for while a sync runs is
  queued after it, never dropped.
- A site that has no lead doctype (or won't let the key read it) fails the sync; the copy is
  kept. Only a successful full read drops leads.
- Changing the connection, lead doctype or field mapping clears the cursor and queues a full
  sync; changing the status mapping, rate, company label or any unit queues a recount (no site
  is read).
- A failure is recorded on the source (status Failed and the reason, shown in Settings and on
  the dashboards) and logged to the Error Log once per outage.
- **Offset paging caveat:** a lead changed while a run pages through could be skipped by that
  run; the nightly full sync picks it up.

### How a lead is counted

- **Employee** is the mapped employee field, else the lead owner.
- Empty levels fill from the units below them, closest first: the employee's team, the team's
  department, its branch, its company. What the lead carries itself always wins. A lead with no
  company at all goes under the source's *company for leads without one*.
- **Category** is the status mapping for the lead's company, else the one for every company,
  else none. A lead with no category counts in Total leads only and the dashboard says how
  many there are and which statuses (it never guesses).
- **Money** is the mapped amount times the source's rate, in the reporting currency.
- **Days to close** is closing date minus creation date, for closed leads (won, converted,
  lost) only.
- A lead any of whose units is inactive is left out of every dashboard.

## What a dashboard counts (`helpdesk/crm_dashboard/report.py`)

In order: leads of enabled sources without an inactive unit → what the dashboard covers (the
leads of any of its units, so a company and a branch of another company cover both; none covers
all, new ones included) → the viewer's scope → the filters picked (only ones the dashboard
offers) → the period, by the day each lead was created. A unit always counts with its own
source: two sites may use one name (a "North" branch, an employee ID) for different things, and
one site's unit never opens the other's leads.

| Metric | Calculation |
| --- | --- |
| Total, open, won, lost, converted leads | Leads in that category. A lead has one category, so won and converted never count one lead twice. |
| Conversion rate | (won + converted) ÷ all leads, or ÷ closed leads (won + converted + lost). |
| Total won sales value | Won value (or expected revenue) of the won and converted leads; total or average per lead with an amount. |
| Expected revenue | Expected revenue of all leads; total or average. |
| Pending sales value | Expected revenue of the open leads; total or average. |
| Average deal value | Won value (or expected revenue) ÷ won and converted leads with an amount. |
| Average lead closing time | Days to close of the won and converted leads, or of all closed leads. |

A metric whose field no enabled source maps shows "—" and what to map. A card left unlabelled
that shows an average says so ("Total won sales value, average per lead"), so two cards of one
metric never read alike. Charts group by company,
branch, department, team, employee, lead owner, lead source, status category, status or
month. A month chart shows every month of its period up to this month, an empty one as 0 for a
count or amount and as a gap for a rate or average. A table shows leads, open, won, lost,
converted, conversion rate and won value (when mapped) per group, sorted by its metric.

Filters list the values there are leads for, over all time, given the other filters: so a
company narrows the branches, a branch its departments and teams, a team its employees. On the
page, changing a filter clears the ones below it.

## Who sees what

- **Configure:** System Managers and Agent Managers only (`require_admin` in
  `helpdesk.api.crm_dashboard_settings`). They also open every dashboard, inactive ones
  included, with no scope.
- **View:** anyone else needs the dashboard active, one of its roles, and Leads access
  (`can_use_leads`, so the Digital team never sees leads through a dashboard).
- **Scope** keeps each viewer to their part: everything the dashboard covers, or their
  company, branch or department (from the employee unit linked to their user, or named by
  their email), their teams (teams they lead or are in), or their own leads (owner or
  employee). Someone the organisation doesn't place sees nothing and is told to ask an admin.
  Filters only narrow; configuration never widens what a viewer sees.
- A source's API secret never leaves the server: the page gets whether one is set and a masked
  hint, and sends a secret only to replace or remove it.
- `get_user` sends `can_view_crm_dashboards` (someone who may open at least one), which shows
  the sidebar item and lets the router open `/helpdesk/crm-dashboards`. Admins may open the page
  before any dashboard exists, to see its set-up prompt.
- A unit or a source that a dashboard is kept to can't be deleted (the dashboard is named):
  taking a dashboard's last unit away would widen it to every lead.

## Settings → CRM dashboards

`desk/src/components/Settings/CrmDashboards/`, System Managers and Agent Managers.

- **Dashboards:** list with Default and Inactive badges, an active switch (saves at once) and a
  ⋯ menu (Duplicate, which starts inactive; Delete, confirmed). **New dashboard** picks a
  template (Executive management, Company administrator, Branch manager, Department manager,
  Sales team leader) and a name; it starts inactive.
- **Dashboard editor** (sub-page, Active and *Open dashboard* in the header): details and
  default; who sees it (roles, scope); what it covers (units, default period, money full or
  short); filters with defaults; KPI cards (label, period, calculated from, shown as, show);
  charts (title, type, group by, metric, compare with, calculated from, shown as, period, sort,
  how many, width, show), each list reorderable; history.
- **Data sources:** list with sync health. **Source editor** (sub-page, Enabled in the header):
  details; connection (or the CRM connection) and *Test connection*; money (currency, rate);
  field mapping (pickers of the site's own lead fields of a fitting type, or typed names when
  they can't be read); status mapping (rows, with the statuses on the copied leads and in a
  Select status field's choices that have no category yet); sync (interval, health, last error,
  *Sync now*, *Read every lead again*); history; delete (confirmed).
- **Organisation** (sub-page): per source and kind of unit, the units with where they sit,
  their lead count and an active switch (saves at once); add or edit a unit (name on the leads,
  display name, parents, the employee's user or the team's leader). Only a unit added here
  with no leads can be deleted; a synced one is switched off instead.
- **Reporting currency** saves with Save changes.

### Validation (on save)

- Source: a URL and key with a secret, or the CRM connection (one source per site, so no lead
  counts twice); field names that are names; the status and creation date fields set; no field
  for two different values (except employee with lead owner, and expected revenue with won
  value); no status mapped twice for the same company; a rate above 0. When the connection or
  mapping changes, the mapped fields are checked against the site's own lead fields (exist, of
  a fitting type); a site that can't be reached saves with a warning.
- Unit: no two of the same kind and name in a source; every parent an existing unit of the
  source; parents that agree (a team's branch is its department's); an employee user linked
  once; no deleting a unit others sit under or a dashboard covers (nor its source).
- Dashboard: a scope and period; no filter twice; each card and chart's metric, calculation
  source and aggregation ones it supports; a line chart grouped by month; a donut of a count or
  amount; a comparison measured like its metric; 1 to 50 items; at least one card or chart.
- **History:** sources, units, dashboards and the reporting currency track changes; editors show
  who changed what, newest first, with secrets masked.

## The dashboard page

`/helpdesk/crm-dashboards/:dashboardId?` (`desk/src/pages/crm-dashboard/`), in the sidebar under
Sales → Team as **CRM dashboards**. The header has a dashboard switcher (when there is more than
one) and **Configure** for admins. The period, dates and filters live in the URL. The period
and the first two filters show in one light row of outlined selects, with when the figures were
read at its end; **More filters (N)** opens the rest, which stay open while one of them is
picked. The page sits on a faint grey, and the compact cards carry a coloured left edge. The page is
colourful by the owner's exception ([ui-guidelines.md](ui-guidelines.md), "the CRM dashboards
are colourful"): each metric has one icon, tone and series colour (`METRIC_LOOK`). KPI cards are
`StatTile`s with their metric's icon. The first three cards are the headline, shown large,
filled with their tone (leads teal, won value green, conversion blue) with a mini trend under
the figure (`Sparkline.vue`: the figure in each of the last
six months up to the end of the period, from one grouped query, in the metric's chart colour,
with each month and figure read out to screen readers; four cards or fewer all lead); the rest follow as a compact strip in as many columns
as leave no card alone on its row (8 cards: 4 and 4). Each card says how it changed against the
stretch just before its period ("+33 vs the 90 days before"): a month, quarter or year against
the same days of the one before (to date, so a half month meets a half month), any other period
against as many days before it, all time against nothing. The change is green when it is good
news, amber when it isn't (never red), and neutral for a figure where neither (open leads,
pending value). Templates put leads, won sales value and conversion rate first. A half-width
chart with no half-width partner next to it takes the whole row, so no row has a hole; a chart
card has a heading strip in its metric's tone; charts use frappe-ui ECharts with the shared `chartTheme` and its validated
palette, a value at each bar's end and a line's last point, a soft flat wash under a trend line, and
a screen-reader table behind each; a table's columns carry their metric's colour dot, and each
row a bar under its name with its share of the largest. Tables turn into two-line rows on a
phone.
States: loading skeleton, load error with Try again, no access, no dashboards yet, no source
connected, viewer not placed, custom period without both dates, empty charts, notices for
unmapped statuses and failing sources.

## API

`helpdesk.api.crm_dashboard`: `get_dashboards`, `get_dashboard(name, filters)`.

`helpdesk.api.crm_dashboard_settings` (admins): `get_settings`, `set_currency`, `get_source`,
`save_source`, `delete_source`, `test_source`, `get_remote_fields`, `sync_source_now`,
`get_units`, `save_unit`, `set_unit_active`, `delete_unit`, `get_dashboard_config`,
`save_dashboard`, `create_dashboard`, `duplicate_dashboard`, `set_dashboard_active`,
`delete_dashboard`, `get_history`.

`CRMClient` gained `get_page` (a page of a list in a fixed order) and `doctype_fields` (a
doctype's fields on the site, custom ones included).

## Requirement coverage (section 16)

| Part | Where |
| --- | --- |
| 16.1 Settings | Settings → CRM dashboards; dashboard editor (name, description, units covered, default period and filters, cards, charts, order, money format, enable/disable each). |
| 16.2 Organisation | Org units synced from ERPNext records and the leads, added and edited here; relationships, leaders, active switch; no duplicates. |
| 16.3 Field mapping | Per source, picked from the site's own fields, checked on save. |
| 16.4 Status mapping | Per source and optionally per company; unmapped statuses flagged, never guessed. |
| 16.5 KPI cards | Eleven metrics; show, order, period, calculation source, aggregation. |
| 16.6 Charts | The ten named presets plus blank charts; type, group by, metric, comparison, period, sort, count, show, width, order. |
| 16.7 Filters | Generated from the leads and organisation; dependent; everything refreshes. |
| 16.8 Multi-company | One source per site with its own credentials (server only), test, sync settings and errors; company-level status mapping; currency and rate; consolidated or one company by filter. |
| 16.9 Templates | Five templates; create, edit, duplicate, activate, deactivate; own filters, cards, charts and scope. |
| 16.10 Validation | See Validation; change history. |
| 16.11 Permissions | Admin-only configuration; role and scope for viewers; never wider than Leads access. |
| 16.12 No developer needed | New companies, branches, departments and teams appear with their leads or are added here; people move teams; new statuses are flagged and mapped. |

## Known limits

- Field mapping is per site: companies on one site share it (status mapping can differ per
  company). A site whose companies use different lead fields needs those fields unified there.
- One currency per source; a lead-level currency field isn't read.
- Periods count leads by creation date; a lead created last quarter and won this month counts
  in last quarter.
- Filters offer units that have leads; a new unit with no leads yet shows only in Settings.
- Viewers whose position isn't in the organisation see nothing until an admin links them.

## Tests

`helpdesk/tests/test_crm_dashboard.py`, against `FakeCRMSite` (helpdesk/test_utils.py) with
`make_crm_source`, `make_crm_org_unit` and `make_crm_dashboard`: the copy and its categories,
incremental and full syncs, recounting without reading, failures, units from ERPNext and leads,
team moves, inactive units, source / unit / dashboard validation, the remote field check, the
secret, templates and copies, history, admin-only settings, every KPI on a known set, missing
mappings, unmapped statuses, tables, month trends, dependent filters, periods, two sources in
two currencies, roles, team scope, unplaced viewers and own scope; and since review, deletes a
dashboard depends on, a missing lead doctype, a full read during a sync, recounting only what a
sync read, coverage across kinds of unit, names two sites share and average labels.
