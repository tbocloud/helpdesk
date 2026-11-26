# Divisions: one hub for every country

**Status:** built 2026-11-16 (TeamBackOffice multi-division brief, phases 2–5). This document is
the living source of truth for the feature; update it with every change.

TeamBackOffice works in several countries (India, KSA, UAE, more later). Each is a **division**
with its own people, ERP site and records. The hub at **teams.teambackoffice.com** is the
central administration: Super Admins see and compare every division; everyone else works in
their own.

## Why it works this way

- **Each division's ERP is its own Frappe site, and stays one.** india.teambackoffice.com
  (tboindia: ERPNext + TBO Smart) and erp.teambackoffice.com (KSA) already serve the divisions'
  ERP sites, so those hostnames can't also serve hub workspaces. The owner chose (2026-11-16)
  to keep the ERP sites on their subdomains: the hub is the central portal, and a division's
  "workspace" inside the hub is chosen by membership and the switcher. Its *Workspace URL* links
  to the division's own site. Nothing is shared at database level: the hub reads and writes the
  ERP sites only through their REST API with an API key (Frappe permissions apply there).
- **ERP data is isolated by the sites themselves.** Leads, customers and quotations live in each
  division's ERP. The hub calls the ERP of the person's *active division*, so a KSA user's Leads
  page talks to the KSA site and never sees India's leads.
- **Hub data is isolated by a `division` field.** Projects live in the hub, so they carry a
  division, and server-side permission hooks keep each division's projects (and their tasks) to
  its members. Hiding things in the page is never the protection.
- **Super Admin is the hub's existing full access.** System Managers and Agent Managers
  (`is_tasky_admin`) already see every project, task and report; about 40 server paths rely on
  that. Making them the Super Admins keeps all those paths correct, with no second "see
  everything" rule. The other roles of the brief are per-division membership roles.
- **One connection per site, no copied secrets.** A division points at an `HD CRM Source` (its
  ERP site, Settings → Divisions → ERP sites), which holds the site's URL, API key, secret,
  currency and rate, or reuses the CRM connection in Settings → CRM.
- **Until the first division exists, nothing changes for anyone.**

## Data model

| DocType / field | What it is |
| --- | --- |
| `HD Division` | Name, code (2–10 capitals or digits; the record's name, can't change), status (Active / Inactive), country, workspace URL (unique host), currency, time zone (IANA), default language, division administrator (added to the members as Division Admin), ERP site (`crm_source` → `HD CRM Source`, unique), members. Tracks changes. Created on = `creation`. |
| `HD Division Member` | Child: user and their role in the division. A user may be in several divisions, with a role in each. |
| `HD Division.weekly_lead_report` | The division keeps Sales → Weekly lead report (KSA's weekly sheet of the leads each salesperson worked; [weekly-lead-report.md](weekly-lead-report.md)). Super Admins set it on the profile. |
| `Project.division` | The project's division. New projects take the maker's active division. Empty = visible as before divisions. |
| `HD Team.division`, `HD Department.division` | Which division a team or department belongs to (set in Settings → Divisions). |

## Roles

| Role | Where | What it allows |
| --- | --- | --- |
| Super Admin | System Manager or Agent Manager | Every division: create, edit, deactivate, delete; move teams and projects between divisions; the audit log; the consolidated overview and reports; switch to any division or "All divisions". |
| Group Admin | membership | Runs that division like a Division Admin. Given and taken away only by Super Admins. With several divisions, sees their overview consolidated. |
| Division Admin | membership | Their division's time zone, language, people (any role but Group Admin), teams and departments; its overview and reports. |
| Division Manager, Sales Manager, Project Manager | membership | Their division's overview and reports. |

Every membership role from Group Admin to Project Manager above is a **manager role**
(`OVERVIEW_ROLES`): someone who holds one in several divisions switches between those divisions
(see The active division).
| Division Sales User | membership | A salesperson in that division: their own and allocated leads on the division's ERP site (it becomes a Sales User there), with proposals and the client documents; none of the team's figures. |
| Sales Executive, Employee | membership | Their division's records only. |

What each membership role may do *inside* a module (leads, quotations) is still decided where the
data lives: the ERP site's own roles for leads and quotations, the project roles for projects.

### Lead access by division role

The owner's request (2026-11-17): per division, a **Division Admin** sees every lead of the
division and a **Division Sales User** only their own. Each division has its own ERP site, so
"the division's leads" are the leads on that site, and the site's lead rules (TBO Smart's
`sales/permissions.py`) already draw the line: a **Sales Manager** there sees every lead, a
**Sales User** what they own, were given or created. The hub therefore sets the ERP role
rather than filtering leads itself, so every Leads screen keeps the site's one rule.

- **On save** (Settings → Divisions → People, `set_members`, for every member, so someone
  whose user was made on the site later is set by the next save; and `save_division` when the
  division's ERP site or its Division Admin changes), each Division Admin gets **Sales
  Manager** on the division's ERP site (a role already there isn't written again), and each
  Division Sales User
  gets **Sales User** and loses Sales Manager there (taken off first, then Sales User added: the
  removal writes back the roles it read). `HDDivision.apply_erp_roles`; their other roles stay.
- **Not undone:** moving someone off Division Admin to another role, or out of the division,
  leaves their ERP roles as they are; take Sales Manager off on the site if they shouldn't see
  every lead any more. Group Admins and the other roles are not sent to the site.
- **What can't be done is shown, not hidden:** the save goes through and the People section
  lists each person the site couldn't set (no enabled user there; a Role Profile that puts a
  role back; a Division Sales User who is a **System Manager** there and so still sees every
  lead; the site unreachable).
- **The Leads page** opens for a Division Admin or Division Sales User of the active division
  (`divisions.leads_role`, in `can_use_leads`), on top of the Leads teams and Sales Employees.
- **Their screens** (owner, 2026-11-17): both roles are on the sales wall like a Sales Employee
  (`content_team.is_sales_employee`: sales screens only, no tasks, projects, tickets or
  content). A **Division Admin** gets Add a lead, My leads, Leads, Commission, Overview and the
  Scoreboard, Assign sales targets and Team targets for their division's people
  (docs/sales-targets.md, owner 2026-11-26), and Reports → Business overview, Lead status and
  Division reports (plus Business,
  Assign leads and Today's calls where the ERP site allows them): they
  are never a BD, so they get the team's view, and, as a Sales Manager on the division's site,
  pick many leads on the list to set their category or merge them (the site checks it again).
  A **Division Sales User** is a salesperson (owner, 2026-11-24): no BD (`content_team.
  is_sales_bd_role` is false for both roles), so their lists hold every lead the ERP site's Sales
  User rule gives them, the ones they own, are allocated or created, and they open each of
  those; but none of the team's figures: no Overview, Business or Team dashboard
  (`divisions.is_division_sales_user`; `api.leads.refuse_team` refuses them on the server,
  `authStore.isDivisionSalesUser` leaves them out of the menu and the Leads tabs, and the Leads
  page opens on All). They keep Add a lead, My leads, Commission (their own), Daily report (the
  site shows them their own) and the Scoreboard. On their leads they make proposals,
  quotations, agreements, BRDs, SRSs and implementation plans as far as the ERP site lets a
  Sales User. The Project and UAT steps stay with the project team: both roles are on the
  sales wall, so they neither make nor open projects.
- **Scoreboard** (`divisions.scoreboard_people`, in `api.team_dashboard.get_team_dashboard`): a
  Division Admin sees only their division's members, a Division Sales User only themselves
  (`team_dashboard.only_people` keeps their rows; a task shared with others counts for them
  only), and their sales numbers come from the division's ERP site (`sales_scoreboard.activity`
  with the division, cached per division). The team-wide parts (the stored champions, last
  period's champion, the year's champions, the month table and the AI analysis) are left out
  for them; everyone else's Scoreboard is unchanged.
- **A division without an ERP site has no leads in the hub** (`division_without_site`): its
  members' Leads page stays closed and says so, and `crm_client` refuses instead of falling back
  to the CRM connection, which holds another division's (India's) leads; the lead copy isn't
  used for it either (`on_crm_connection`). With "All divisions" (a Super Admin) or no divisions
  the CRM connection is used, as before.
- The hub's API key on the division's site needs to change Users' roles there (System Manager).

## Who sees what (server side)

`helpdesk/divisions.py` is the one home of these rules.

- **Projects** (`tasky.permissions.project_query` / `project_has_permission`): a non-Super Admin
  sees a project only when it has no division or one of their *active* divisions (on top of the
  existing rules: owner, lead, member, assigned task, department walls).
- **Tasks** (`task_query` / `task_has_permission`): follow their project's division.
- **Inactive division**: its records are hidden from its members; Super Admins still see them.
- **Assignment** (`check_assignment_department`, ToDo validate): a task of a division's project
  goes only to that division's members (new assignments; closing an older one still works).
- **A project's people**: its lead and members must be members of its division; nobody moves a
  project into a division they aren't in.
- **A division whose ERP site decides access**: when its source has *Access follows this
  site's roles* on (see ERP sites, Users and roles), the site's roles decide its CRM parts.
  Its overview and reports open to the site's managers (a mapped Manager role, matched by
  email) and to its Group and Division Admins, whatever their membership; its Leads page opens
  only to people with a mapped role there. Projects and tasks still follow membership.
- **Leads, quotations, call batches and the rest of the Leads page**
  (`integrations/crm/leads.call` / `download`): sent to `divisions.crm_client()`, the ERP of the
  person's active division (its source's own connection, or the CRM connection when its site is
  that one). A division with no site gets none (see Lead access by division role); with no
  active division the CRM connection is used. The Leads cache key carries the
  division. The lead mirror (docs/lead-mirror.md) holds only the CRM connection's leads, so a
  division on another site never falls back to it.
- **Not divided (yet):** tickets and HD Customers (the support desk is shared), timesheets (own
  and managed projects' time, as before), and the scheduled jobs that read the ERP (stale-lead
  follow-ups, daily sales report, WhatsApp outreach, lead mirror, user, customer and holiday
  sync, invoicing): they run on the CRM connection in Settings → CRM only. The Scoreboard reads
  a division's site only for its Division Admins and Sales Users (above).

## The active division and the workspace URL

`active_division(user)`, in order: the division whose workspace URL host the request came in on
(when the hub itself is served there); then the one they last picked (user default
`hd_active_division`) when they may still switch to it; else, for a Super Admin, "All
divisions" (none), and for everyone else their first division (by name).

**Who switches** (owner, 2026-11-23, replacing "only Super Admins" of 2026-11-17):

- **Super Admins**: any active division, or "All divisions".
- **Managers of several divisions** (a manager role, see Roles, in more than one): between the
  divisions they hold a manager role in (`switchable_divisions`), never "All divisions" and
  never one where they only work (Employee, Sales Executive, Division Sales User).
- **Everyone else** works in their first division; `switch_division` refuses them, and a pick
  saved for them doesn't move them. Their projects and tasks still follow all their
  memberships. To move them, a Super Admin changes their membership.

`switch_division` saves the pick and writes the audit log; the page reloads so every list,
cache, the Leads page's ERP site and the overview follow.

The **switcher** sits under the workspace name in the menu panel (`DivisionSwitcher.vue`),
shown when `can_switch_division`: a menu of the divisions they may switch to ("All divisions"
first, for a Super Admin), and *Open … workspace* when the division has a URL. Hidden for
everyone else and when there are no divisions.

`get_user` sends `divisions` (each with the person's `role` and `can_switch`),
`active_division`, `overview_division`, `is_super_admin`, `can_switch_division`,
`can_manage_divisions` and `can_view_division_overview` (`divisions.division_info`).

## Settings

**Central administration** group of the Settings modal (`components/Settings/Divisions/`):

- **Divisions** (`can_manage_divisions`): Super Admins see every division and the central URL,
  create divisions, and can put every project without a division into one (projects whose
  people aren't that division's members stay out and are counted). A division's own admins see
  only the divisions they run. The editor has Profile (central fields read only for division
  admins), People (add, change role, remove), Teams and Departments; one Save sends what changed
  (`save_division`, `set_members`, `set_units`). Deleting is refused while projects, teams or
  departments are in the division.
- **ERP sites** (Super Admins, a section of the Divisions page): every source with the divisions
  on it and its sync health, *Add ERP site*, and the reporting currency (saves when picked). The
  division editor's ERP site row has *Edit ERP site* (or *Add ERP site* when it has none); a
  site added there is picked for the division, saved with it. The source editor opens over the
  Divisions page and Back returns where it came from; the division editor stays open behind it,
  so nothing typed there is lost. See ERP sites below.
- **Audit log** (Super Admins): newest first, up to 100: changes to divisions (their Versions:
  profile, people, ERP site), projects moved between divisions (Project Versions), division
  switches and report exports (Activity Log, `divisions.log_activity`).

### Agents of a division (owner, 2026-11-17)

A division's own admins (Division Admin, Group Admin) who aren't Super Admins get **Agents** and
**Invite Agents** under Central administration (`DivisionAgents.vue`, `DivisionInvite.vue`, a
division picker when they run several); Super Admins keep the hub-wide Agents and Invite Agents.

- **Agents** (`get_division_agents`): the division's members with their name, picture, whether
  their agent is active and their role in it, and its pending invites. Roles are changed in
  Divisions → People; a division admin can't make anyone a Manager or Admin of the hub.
- **Invite Agents** (`invite_to_division`): emails and a division role (the roles they may give:
  never Group Admin). Someone who is already an active agent joins the division at once (and
  gets its ERP site's role, as a People save does); anyone else gets a hub invite as **Agent**
  that carries `division` and `division_role` (custom fields on User Invitation) and joins the
  division with that role when they accept (`hooks/user_invitation.join_division`). Already in
  it, already invited and disabled accounts are listed, not invited again.
- A division admin holds no inviting role of their own: only an invite made by
  `invite_to_division` (flag `division_invite`, after `require_manager`) passes
  `HelpdeskUserInvitation._validate_roles`, and only as Agent. Their own invites can be
  cancelled (`cancel_division_invite`); the audit log records who was brought in.
- **Lead setup** (Division Admins of their active division, while Leads is on;
  `DivisionLeadSetup.vue`, `auth.isActiveDivisionAdmin`): the same **Lead departments** and
  **Referral (Lead Bank)** sections as Settings → CRM, on the active division's own ERP site, so
  a KSA admin makes the KSA department and picks it for KSA without a Super Admin. No new
  server code: `helpdesk.api.leads.save_lead_department` and
  `helpdesk.api.lead_bank.save_referral_settings` already call the active division's site as
  the person, and a Division Admin is a Sales Manager there (`ERP_SALES_ROLES`); that site
  decides. Department people are picked from the division's members (`get_division_agents`),
  not every hub agent. A Group Admin doesn't get it: they hold no sales role on the site.

How the brief's settings list maps onto the hub: General Settings, User Management (Agents,
Invite agents), Department Management, Team Management, Global CRM Settings (CRM),
Integration Settings (the Integrations group) and Notification Settings stay where
they were; Domain Management is the Workspace URL of each division plus the central URL shown on
the Divisions page; Division Profile, Division Users, Departments, Teams and Currency and
Localization are the division editor; Lead and Quotation Settings live on each division's ERP
site. Role & Permission Management is the membership roles above plus Frappe's own roles.

## Overview and reports

`helpdesk/division_overview.py` computes every figure; `helpdesk/api/division_overview.py`
serves it. Open to Super Admins and members with Group Admin, Division Admin, Division Manager,
Sales Manager or Project Manager (`overview_divisions`); each sees only those divisions. A
division whose ERP site decides access opens instead to the managers on its site and its Group
and Division Admins (see Who sees what).

- **Scope**: one division, or every division the person may see (consolidated). The page always
  says which in words ("Consolidated: India, KSA" / "India division only").
- **Period**: this month, last 3 months, this year (default), last 12 months or custom; kept in
  the URL with the division, so a view can be shared.
- **Where it opens**: with no division in the URL, on `overview_division`, the active division
  (the switcher's) when its figures are the person's to see, else every division they may see.
  So a manager who switches to KSA opens on KSA, and a Super Admin on "All divisions" opens
  consolidated. Picking "All divisions" on the page puts an empty division in the URL.
- **Where each figure comes from:**
  - Employees: distinct members of the divisions.
  - Projects, active projects (Open), on hold, completed: `Project.status` by division.
  - Pending activities: open tasks (not Completed, Cancelled or Template) of the divisions'
    projects; overdue = past their end date. Tasks done = completed in the period.
  - Employee performance: per member, tasks given to them (ToDo) done in the period, open and
    overdue, and hours they logged on the division's projects in the period.
  - Leads, won (Won + Converted), lost, open, conversion (won ÷ leads) and monthly trend: the
    reporting copy (`HD CRM Report Lead`) of the division's ERP site, created in the period.
  - Customers: enabled ERPNext Customers on the division's ERP site.
  - Quotations (dated in the period, not cancelled), quoted value, ordered (Ordered, Partially
    Ordered) and their value (= **Sales value**), lost (Lost, Expired), conversion: read from the
    ERP site's Quotations in pages of 500 (at most 20,000 per period), `base_grand_total` times
    the source's rate, in the reporting currency (Settings → Divisions → ERP sites). The customer
    count's filter is sent as JSON text: a GET's dict parameter would reach the site as its
    keys alone, which the site can't parse (a 500).
- **ERP reads are cached** 10 minutes per site and period. A site that can't answer (or a
  division with no site) is named in a notice, and its customers and quotations show "—", never
  0; consolidated totals then count the sites that answered.
- **The page** (`/helpdesk/business-overview`, Reports → Business overview): ten stat tiles,
  charts drawn by `DashboardChart` (leads and won leads by division, sales by
  division, quoted value by month, lead conversion by month, business growth, projects by
  division, employee performance) and, for several divisions, a comparison table.
- **Reports** (`/helpdesk/division-reports`): division-wise leads, country-wise customers,
  division-wise quotations, sales performance, project status, employee productivity, monthly
  business performance, lead conversion and pending activities. Each exports to **Excel**
  (`make_xlsx`) or **PDF** (wkhtmltopdf; where it isn't installed, a page that prints itself), and
  every export is written to the audit log.

## Divisions home and a division's dashboard

Owner, 2026-11-24: a page with every division side by side, each opening its own dashboard.
Same access and scope as the overview (`scope`): Super Admins every division, managers
theirs, nobody else.

- **Divisions home** (`/helpdesk/divisions`, Reports → Divisions, `DivisionsHome.vue`,
  `DivisionCard.vue`; `get_division_cards` → `division_overview.division_cards`): one card
  per division with who runs it (its Group and Division Admins), its people, its ERP site's
  sync in words (danger when the last sync failed, warning with no site or sync off), and for
  the period its leads, conversion and open leads (the reporting copy), open projects,
  pending and overdue tasks. Period filter only. *Compare* opens the Business overview of
  every division.
- **A division's dashboard** (`/helpdesk/divisions/<code>`, `DivisionDashboard.vue`;
  `get_division_dashboard` → `division_dashboard`): the profile (who runs it, ERP site, time
  zone, language, workspace URL), tiles (people, leads, conversion, won value, open projects,
  pending and overdue tasks), leads by status group and its top statuses (*All lead status*
  opens the Lead status page on the division), its people with their role, leads, won leads
  and tasks open, overdue, done and hours in the period (`productivity` plus the lead status
  people, matched by email), its open and on-hold projects (to 50, soonest due first) and its
  teams and departments. The division picker switches dashboards; "All divisions" goes back to
  the cards. Leads show "—" for a division with no ERP site, never 0.

## Lead status

`/helpdesk/lead-status` (Reports → Lead status, `DivisionLeads.vue`), served by
`helpdesk.api.division_overview.get_lead_status` (`division_overview.lead_status`). Same
access and division scope as the overview (`scope`): Super Admins every division, managers
theirs, nobody else. A Division Admin, who is on the sales wall, reaches it too
(`DivisionLeads` is in `SALES_EMPLOYEE_ROUTES`, owner, 2026-11-26); a Division Sales User has
no overview role, so it stays hidden from them.

- **What it counts**: the reporting copy (`HD CRM Report Lead`) of each division's ERP site,
  leads created in the period, by their own status on the site (Lead, Replied, Interested,
  Quotation, Do Not Contact, ...). Each status sits in its group from the source's status
  mapping: Open, Won, Converted, Lost, or **Not grouped** when the mapping leaves it out (it is
  counted and shown, never dropped, so a gap in the mapping is visible).
- **Filters** (in the URL with the division and period, so a view can be shared): status
  group, status, salesperson (the lead's mapped employee, else its owner; named from the hub
  user when there is one) and lead source. Their choices are every value of the period, so
  picking one never hides the others. Clicking a status, salesperson or source filters to it.
- **The page**: tiles (leads, open, won or converted, lost, conversion, open pipeline = the
  expected revenue of open leads in the reporting currency, and not grouped when there are
  any); charts (by status group, by status, by month with won, and open/won/lost by division
  for several); the status × division table with each status's share; by salesperson and by
  lead source (top 10, then *Show all*).
- **Freshness**: the copy is as fresh as the sources' last sync, said on the page ("Leads
  synced from the ERP sites 3 hours ago", the oldest of the divisions). A division with no
  ERP site is named: it has no leads.

## ERP sites

Each division's ERP site is an `HD CRM Source`. The hub keeps a reporting copy of its leads
(for the overview's lead figures), reads its users and roles (for access that follows the
site), and calls it live for customers, quotations and the Leads page. Settings → Divisions →
ERP sites, Super Admins only (`helpdesk/api/erp_sites.py`).

The CRM dashboards that first used these sources were removed on 2026-11-17 (owner: "remove the
CRM dashboard, just need the division-wise data source working"), with their organisation
units. Patch `v16_0_2.remove_crm_dashboards` deletes their doctypes and tables. The sources,
their sync and the reporting currency stayed.

### Data model

| DocType / field | What it is |
| --- | --- |
| `HD CRM Source` | One site: connection (its own URL, key and secret, or *Use the CRM connection* in Settings → CRM), lead doctype (Lead / CRM Lead), company for leads without one, currency and rate to the reporting currency, the field mapping, the status mapping (`HD CRM Status Map`), *Access follows this site's roles* and its role mapping (`HD CRM Source Role`), sync interval and health. Tracks changes. |
| `HD CRM Status Map` | Child: a status → Open / Won / Lost / Converted / Other, optionally for one company of the source. |
| `HD CRM Report Lead` | The reporting copy: `raw` (the mapped fields as sent) plus columns (company, branch, department, team, employee, lead owner, status, category, lead source, expected revenue and won value in the reporting currency, created on and its month, closed on, days to close). Named `<source>::<lead>`. Read-only; written in bulk by the sync. |
| `HD CRM Source User` | A desk user of the site as the last sync read them: email, name, enabled there, their roles there and the access those give (Manager / Executive / none). Named `<source>::<email>`. Read-only. |
| `HD CRM Source Role` | Child of a source (`role_map`): a role on its site → Manager or Executive. |
| `HD CRM Settings.dashboard_currency` | The reporting currency of the division overview (the field kept its name). |

`helpdesk/crm_dashboard/registry.py` holds the categories and the mapped fields (the package
kept its name so the scheduled job paths didn't change).

### Sync (`helpdesk/crm_dashboard/sync.py`)

- **Every 15 minutes** `sync_due_sources` queues each enabled source whose interval (15
  minutes, hour, 6 hours, day) has passed; a failed run keeps its last good time and is retried
  next tick. **Nightly** `full_sync_all` reads every lead of every source, which drops the ones
  deleted there.
- A run reads the leads changed since the last one (`modified` from a minute before the newest
  copied, on the site's own clock), in pages of 500, recounts them from their `raw` fields and
  writes only the rows that changed; then it reads the site's users.
- One run per source at a time (a file lock); a sync, a full sync and a recount are separate
  queued jobs, so none swallows another.
- A site with no lead doctype (or that won't let the key read it) fails the sync; the copy is
  kept. Only a successful full read drops leads. A failure is recorded on the source (shown in
  its editor) and logged to the Error Log once per outage.
- Changing the connection, lead doctype or field mapping queues a full sync; changing the
  status mapping, rate or company label queues a recount (no site is read).
- **How a lead is counted:** category is the status mapping for the lead's company, else the
  one for every company, else none (counted in total leads only). Money is the mapped amount
  times the source's rate. A lead with no company goes under the source's *company for leads
  without one*. Employee is the mapped employee field, else the lead owner. Days to close only
  for closed (won, converted, lost) leads.

### Users and roles (`helpdesk/crm_dashboard/erp_roles.py`)

- After its leads, every sync reads the site's desk users and their roles
  (`CRMClient.users_with_roles`) into `HD CRM Source User`. Users gone from the site go from the
  copy; a site that won't list them keeps the last copy and the reason in `users_error`.
- With *Access follows this site's roles* on, each mapped role gives *Manager* or *Executive*;
  a user's access is the highest their roles give, none when disabled there. Switched on with no
  rows, a source starts with Sales Manager and Sales Master Manager → Manager, Sales User →
  Executive. Changing the mapping applies at once without reading the site.
- A hub user is matched by email; hub admins (System Managers and Agent Managers) count as
  Manager everywhere. What the access decides is in Who sees what above.

### The editor and validation

The source editor (`components/Settings/Divisions/SourceEditor.vue`, Enabled in the header):
details; connection and *Test connection*; money (currency, rate); field mapping (pickers of
the site's own lead fields of a fitting type, or typed names when they can't be read); status
mapping (rows, with the statuses that have no category yet offered); sync (interval, health,
*Sync now*, *Read every lead again*); users and roles; history; delete (refused while a
division is on it).

On save: a URL and key with a secret, or the CRM connection, with one source per site; field
names that are names; the status and creation date fields set; no field for two values (except
employee with lead owner, and expected revenue with won value); no status or role mapped twice;
a rate above 0. When the connection or mapping changes, the mapped fields are checked against
the site's own lead fields; a site that can't be reached saves with a warning. Sources and the
reporting currency track changes, shown newest first with secrets masked.

### API

`helpdesk.api.erp_sites` (Super Admins): `get_sources` (currency, CRM connection, registry,
each source's health and the divisions on it), `set_currency`, `get_source` (without the
secret; with the statuses on its copied leads and its users), `save_source`, `delete_source`,
`test_source`, `get_remote_fields`, `sync_source_now`, `get_history`.

## Known limits

- The Leads page works per division only where the division's ERP runs TBO Smart's hub APIs
  (India today). On a site without them the page says the ERP needs the latest TBO Smart.
- Project budgets aren't tracked in the hub (Project has no budget), so the overview has none.
- Quotation numbering and currency are the ERP site's own (each site numbers and prices its own
  quotations); the hub doesn't renumber them.

## Code

- Backend: `helpdesk/divisions.py` (access, active division, ERP client, audit),
  `helpdesk/division_overview.py` (figures and reports), `helpdesk/api/divisions.py`,
  `helpdesk/api/division_overview.py`, `helpdesk/helpdesk/doctype/hd_division/`,
  `hd_division_member/`, `helpdesk/templates/division_report_pdf.html`; hooks in
  `tasky/permissions.py`, `doctype/project/project.py`, `integrations/crm/leads.py`,
  `api/leads.py`, `api/auth.py`.
- Frontend: `desk/src/pages/divisions/` (overview, reports, lead status (`DivisionLeads.vue`,
  `LeadBreakdown.vue`, `LeadGroupLabel.vue`, `leadStatus.ts`), divisions home and dashboard
  (`DivisionsHome.vue`, `DivisionCard.vue`, `DivisionDashboard.vue`), filters, `divisions.ts`),
  `components/layouts/DivisionSwitcher.vue`, `components/Settings/Divisions/`.
- ERP sites: `helpdesk/api/erp_sites.py`, `helpdesk/crm_dashboard/` (registry, sync,
  erp_roles), doctypes `hd_crm_source`, `hd_crm_status_map`, `hd_crm_source_role`,
  `hd_crm_source_user`, `hd_crm_report_lead`; frontend `ErpSites.vue`, `SourceEditor.vue`,
  `ConfigHistory.vue`, `erpSites.ts`; charts `pages/divisions/DashboardChart.vue` and
  `chartLook.ts`.
- Tests: `helpdesk/tests/test_erp_sites.py` (the sync, the source's validation and settings, the
  site's roles, against `FakeCRMSite` with `make_crm_source` and `fill_crm_site`);
  `helpdesk/tests/test_divisions.py` (helpers `make_division`, `FakeERPSales` in
  `test_utils.py`); `TestDivisionSiteRoles` covers a division whose ERP site decides access,
  `TestDivisionSalesRoles` the ERP roles given on save (with `FakeCRM.remove_role`), the Leads
  page and sales screens for the two roles, `TestDivisionLeadsConnection` a division without a
  site, `TestDivisionAgents` a division's agents and invites, `TestDivisionDashboards` the
  Divisions home, a division's dashboard and the Lead status page (helper
  `make_report_lead`),
  `TestDivisionSalesRoles.test_a_division_admin_sets_up_lead_departments_on_their_divisions_site`
  the Lead setup saves;
  `test_sales_scoreboard.TestDivisionScoreboard` the division's Scoreboard.
