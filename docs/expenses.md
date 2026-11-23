# Expenses: claim and approve in the hub

**Status:** built 2026-11-18. This document is the living source of truth for the feature;
update it with every change.

The owner's request (2026-11-18): salespeople claim their work expenses in the hub, and the
person who approves them (Faris for India) sees and approves those claims there, instead of
going to the ERP site or the Frappe HR app.

## Why it works this way

- **The claims stay on the division's ERP site.** Expense Claim is HRMS's, on the ERP site
  (india.teambackoffice.com for India), where Accounts pays it. The hub keeps no copy: like
  Leads, every read and write goes to the ERP site of the person's active division
  (`divisions.crm_client`, docs/divisions.md) through TBO Smart's
  `tbo_smart.api.hub_expenses` (its `docs/hub-leads-api.md` §2.35), with `acting_user` the
  person signed in here. The ERP site runs the call as them, so its own roles, approvers,
  workflow and User Permissions decide everything.
- **One rule with the TBO Smart app.** `hub_expenses` wraps the TBO Smart app's own expense
  paths (`api/mobile/ess.py`, `api/mobile/manager.py`), so a claim made in the hub, the app or
  the desk is the same draft, routed to the same approver, and approved the same way.
- **Who opens the page:** the people who may use Leads (`can_use_leads`), because the ERP
  site only acts for a user with a sales role there (`hub_leads.hub_user_problem`): Sales
  User, Sales Manager or System Manager.

## What each person sees (`/expenses`, sidebar: Sales → Expenses)

- **My claims:** their own claims, newest first (50 at a time, "Show older claims"), each with
  its type and note, date, number, approver, a status (Pending / Approved / Rejected / Paid,
  always with its icon and word), the amount and the receipt.
- **New claim** (only when they're linked to an employee): type (the site's Expense Claim
  Types), amount, the day it was spent (not in the future), what it was for, and a receipt (a
  photo, scaled to a JPEG of at most 2000 px as Lead photos are, or a PDF of at most 10 MB).
  It is saved as a draft claim on the ERP site, routed to their expense approver (Employee,
  else Department), and the toast names who it went to.
- **To approve** (only for approvers, the ERP site's `approve_expense`: HR Manager / HR User,
  a named expense approver of an employee or department, or a role that can approve in the
  Expense Claim workflow): the claims waiting for them, as HRMS lists them (their own left
  out), with the person, the type, the date, the amount and the receipt. **Approve** applies
  the workflow's approve action (or, without a workflow, sets Approved, sanctions the amounts
  and submits); **Reject** asks for a reason, which the claimant sees as a comment. The tab's
  count is how many wait. `?view=approve` opens it.
- **Receipts** open in a new tab, streamed through the hub (`expense_receipt`); the ERP site
  serves one only to people who may read the claim.

## What the ERP site needs (set up there, not in the hub)

- Each claimant: the **Employee** role and an active **Employee** record whose **User ID** is
  their email. Without one the page says so and offers no New claim.
- Each Employee (or their Department): an **Expense Approver**, so the claim is routed and
  the approver is notified.
- **Expense Claim Types** with a default account for the company.
- The approver: **Expense Approver** (or HR Manager / HR User), and no **User Permission**
  on Employee that applies to all document types, or they see only that employee's claims.
  (Faris had one, Employee 1000004, on the local copy of tboindia on 2026-11-18.)
- TBO Smart with `hub_expenses` (v1.34 of its hub API). An older one: the page says it needs
  the latest TBO Smart (`available` false).

## API (`helpdesk/api/expenses.py`)

Thin proxies, nothing cached; each checks `require_leads` and calls `hub_expenses` as the
person.

| Method | Verb | Does |
| --- | --- | --- |
| `get_expenses(page=1)` | GET | `{available, employee, can_approve, currency, types, claims: {data, page, has_more}, approvals}`; `available` false on an older ERP site |
| `create_expense_claim(expense_type, amount, expense_date, description?, receipt_filename?, receipt_base64?)` | POST | the new claim |
| `decide_expense(name, approve, reason?)` | POST | approve (1) or reject (0, with a reason) |
| `expense_receipt(name, filename?)` | GET | the receipt's bytes; PDFs and pictures open in the browser (`leads.send_file`, shared with lead files) |

A refusal from the ERP site is an error the person can read (`friendly_error`); an older TBO
Smart on a write says so (`LeadsUnavailableError`).

## Files

- Backend: `helpdesk/api/expenses.py`; `helpdesk/api/leads.py` (`send_file`, shared with
  `lead_file`).
- Frontend: `desk/src/pages/expenses/` (`Expenses.vue`, `ClaimApprovals.vue`,
  `NewClaimDialog.vue`, `expenses.ts`); route `Expenses` in `desk/src/router/index.ts`; the
  sidebar item in `components/layouts/navigation.ts` (`leadsOnly`); `Expenses` in
  `SALES_EMPLOYEE_ROUTES` (`pages/content/contentTeam.ts`), so salespeople reach it.
- Tests: `helpdesk/tests/test_expenses.py` (against `FakeCRM`: read live as the person, an
  older ERP site, the claim and the decision as POSTs, refusals, the receipt streamed, people
  without Leads refused). The ERP side is tested in TBO Smart (`tests/test_hub_expenses.py`).
