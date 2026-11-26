# Lead report (KSA)

**Status:** built 2026-11-25. This document is the living source of truth for the feature;
update it with every change.

The KSA sales team reported their week in an Excel sheet: one row per lead, with the company,
contact, requirement, whether it was quoted, its chances, the visits that week, a follow-up
plan and remarks. **Sales → Lead report** is that sheet in the hub, for the divisions that
keep it (KSA). It is a report, not a visit log (owner, 2026-11-25), with filters; it was
called *Weekly lead report* until the owner renamed it (2026-11-26). The code keeps the
`weekly_lead_report` names.

## Why it works this way

- **Everything is on the lead, on the KSA ERP site** (erp.teambackoffice.com). The owner asked
  for the sheet's fields on the Lead, for KSA only; the KSA site is KSA's alone, so fields made
  there are KSA's only. The hub keeps nothing: the report reads and writes the leads.
- **A row is a lead created or updated in the period** (owner's choice, 2026-11-25; the
  period filter replaced the week picker on 2026-11-26). Filling in a lead's visits or
  remarks updates it, so it shows that day. Changing a lead from an older period's report
  updates it too, so it also shows today. There is no *Tomorrow*: nothing is updated
  tomorrow, so it would always be empty.
- **No salesperson column**: the template has none (owner, 2026-11-26). Managers still pick
  one salesperson's leads with the Salesperson filter.
- **What the lead already had is reused**: Designation is `job_title`, Requirement the KSA
  site's Lead Segment, Remarks the lead's *Comment*.
- **Switched on per division, not by name.** A Super Admin ticks *Weekly lead report* on the
  division (Settings → Divisions → the division's profile, under ERP site; labelled *Lead
  report*). Only KSA keeps it.
- **A week runs Sunday to Saturday** (This week, Last week, and the period when none is given):
  KSA works Sunday to Thursday (`week_start`).

## On the KSA ERP site

Custom Fields made directly on erp.teambackoffice.com on 2026-11-25 through the hub's API key
(the owner's choice over shipping them in `tbo_ksa`), so they are in no app's source:

| Lead field | Type | Where |
| --- | --- | --- |
| `custom_conversion_possibility` (Conversion Possibility) | Select: High, Medium, Low, Not Possible; a standard filter | after Lead Segment |
| `custom_visits_this_week` (Number of Visits This Week) | Int, not negative | after Conversion Possibility |
| `custom_follow_up_plan` (Future Follow-up Plan) | Select: Yes, No | after Number of Visits This Week |

A visit log (a `KSA Lead Visit` table on the lead) was made first the same day and removed
before anything was logged, when the owner asked for a report instead.

## Who sees what

The page opens (`weekly_lead_report.report_division`) when the person's **active division**
keeps the report, they are its member (or a Super Admin), and its Leads are open to them
(`can_use_leads`, the division has an ERP site, the site gives them a sales role).
`get_user` sends it as `has_weekly_lead_report`: the Sales menu item and the route follow it.

| Who | Sees | Changes |
| --- | --- | --- |
| A salesperson (Division Sales User, or any other member with Leads) | the leads they own | the sheet fields of their leads |
| Division managers (`overview_divisions`: Group Admin, Division Admin, Division Manager, Sales Manager, Project Manager) and Super Admins | every owner's rows, or one person's (Salesperson filter); leads with no owner as *No owner* | the sheet fields of the leads the site shows them |

- **Every write first reads the lead on the ERP site as the person** (`get_lead` with
  `acting_user`), so only a lead the site shows them is changed. The write itself goes with
  the hub's key (the site's Administrator), since TBO Smart's `update_lead` takes only its
  own fields; the lead's *Last modified by* shows that user.
- **Reading** goes with the hub's key: the period's leads (`modified` in it, `lead_owner`
  the salesperson for a salesperson) and their quotations.
- The server enforces all of this; the page only hides what isn't theirs.

## The columns

| Template column | Where it comes from |
| --- | --- |
| Name | Lead `company_name` (else `lead_name`) |
| Contact Number | `mobile_no`, else `phone` |
| Email | `email_id` |
| Nature of Business | `industry`, else TBO Smart's `tbo_business_type` |
| Contact Name | `lead_name` |
| Contact Designation | `job_title` |
| Requirement | `custom_lead_segment` (Erpnext → ERPNext, Digital → Digital Marketing), else `tbo_lead_type` |
| Quoted (Yes/No) | Yes when the lead has a quotation that isn't cancelled (`quotation_to` Lead) |
| Quoted (Value), Quotation Number | The latest of those (by date): its grand total and currency, and its number; *latest of N* when there are several |
| Conversion Possibility | `custom_conversion_possibility` |
| Number of Visits This Week | `custom_visits_this_week` |
| Future Follow-up Plan | `custom_follow_up_plan` |
| Remarks | The lead's `custom_comment`, as plain text (written back escaped, lines as `<br>`) |

A division that keeps the report must have these fields on its site's Lead (KSA's has them).

## The page

`desk/src/pages/weekly-lead-report/WeeklyLeadReport.vue`, route `/lead-report` (`LeadReport`,
on the sales wall's routes).

- The header has **Export to Excel** (the primary action). Under it, the **period**: Today,
  Yesterday, This week (the default), Last week, This month, or *Between dates…* with From
  and To (`periodRange`; until both dates are picked the card asks for them), and, for
  managers, the Salesperson filter (Everyone first). The server takes up to 366 days and
  refuses a From after the To.
- **Filters** under them: a search (any part of the company, contact, number or email) and
  Requirement, Conversion possibility and Follow-up plan (each a value, or *Not set* for
  leads with it empty) and Quoted (Yes / No), with *Clear filters* while any is on. The
  server applies them (`filter_rows`), so the summary and the Excel file match the table;
  the Salesperson picker still lists the whole period's people. The selects apply at once, the
  search after a pause. The period, person and filters are in the URL.
- One card: the dates, and *N leads · N visits · N quoted*. The table follows the template,
  grouped for the screen: Name (with the nature of business), Contact (name · designation,
  number, email), Requirement, Quoted (Yes/No, value, number), then Conversion possibility,
  Visits this week, Follow-up plan and Remarks, which save to the lead at once (the selects
  on pick, visits and remarks when the field is left; a failure puts the old value back and
  says so). It scrolls sideways inside the card on a phone. The company links to the lead.
- States: dates still to pick, loading, an empty period, no lead matching the filters (with *Clear filters*), the
  ERP site failing (the error and Try again).

## On the hub's lead screens

For the people the report is open to (`has_weekly_lead_report`, so KSA only):

- **New lead / Edit lead** (`LeadFormDialog.vue`): Designation, Requirement, Conversion
  possibility, Visits this week and Follow-up plan, after Next follow-up. TBO Smart's
  `create_lead` / `update_lead` take only their own fields, so these go to
  `weekly_lead_report.update_lead` once the lead is saved; a failure there says so without
  undoing the lead. Editing loads them with `get_lead_sheet`; only what changed is sent, and
  an edit of only these skips TBO Smart. (The dialog's own *Remarks* on a new lead stays the
  lead's first note.)
- **Lead page** (`LeadSheetCard.vue`, after Details, titled *Lead report*): the sheet fields
  read only, with *Open report*. Saving the Edit dialog reloads it.

## Excel

`export_report` sends the rows as the page shows them (the same period and filters) in the
template's columns and order, titled *Lead report*, with the division, the dates, whose rows
they are and the filters used above the table (`lead-report-<from>-to-<to>.xlsx`). A salesperson's file is always their own. Every export is in the audit log
(Settings → Divisions → Audit log). Reuses `division_overview.send_xlsx`.

## API (`helpdesk.api.weekly_lead_report`)

| Method | HTTP | Arguments | Returns |
| --- | --- | --- | --- |
| `get_report` | GET | `from_date, to_date` (this week when both are empty; one alone is that day), `salesperson` (managers), `search, requirement, conversion, follow_up, quoted` (`not_set` for an empty field) | `{division, division_name, from_date, to_date, sees_team, people, rows}`; a row is the lead's columns (`lead_columns`) plus `salesperson_name` |
| `get_lead_sheet` | GET | `lead` | the lead's columns |
| `update_lead` | POST | `lead, values` (`designation, requirement, conversion, visits, follow_up, remarks`) | `{saved}` |
| `export_report` | GET | as `get_report` | an .xlsx file |

## Data model

Nothing in the hub but `HD Division.weekly_lead_report` (Check): the division keeps the report.
The data is the KSA site's Lead (above).

## Files

- `helpdesk/weekly_lead_report.py`: the period, who may use it, reading leads from the site.
- `helpdesk/api/weekly_lead_report.py`: the endpoints above.
- `desk/src/pages/weekly-lead-report/`: the page, the Lead page's card (`LeadSheetCard.vue`),
  types and helpers; `pages/leads/LeadFormDialog.vue` and `Lead.vue` use them.
- Tests: `helpdesk/tests/test_weekly_lead_report.py` (the site: `FakeWeeklyLeadERP` and
  `weekly_report_lead` in `helpdesk/test_utils.py`).

## To set up on a site

1. Migrate (the division field).
2. Settings → Divisions → KSA: tick **Weekly lead report** and save.
3. Add the KSA salespeople to the KSA division as **Division Sales User** (Settings → Divisions →
   People). Only members get the report; their rows are the leads they own on the KSA site.
