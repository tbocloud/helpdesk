# AI customization pipeline

Status: phase 1 (estimates in TBO Support) is implemented; phases 2–4 are the plan for
TBO Copilot (PROJ-0006). This document is the source of truth for the feature and is
updated with every change to it.

## Goal

A customer asks for a change to their ERPNext ("add a status filter to the Daily Sales
report"). Today a developer estimates, builds, tests and deploys it by hand. The goal:

- the customer gets an estimate and a delivery date within hours, not days;
- an AI agent builds the change on the customer's **staging** site;
- people approve twice before anything reaches production;
- delivery is measured against the date we agreed, not a fixed SLA.

Nothing reaches a customer's production site without a person clicking Deploy.

## Why customizations need their own SLA

The support SLA (HD Service Level Agreement) gives each priority a fixed first-reply and
resolution time. That works for issues and questions, but a customization can be 2 or 40
hours of work. So for customizations:

| | Support (issue, question) | Customization |
|---|---|---|
| First reply | Per priority (the normal SLA) | The normal SLA: the estimate is the first real reply |
| Resolution | Per priority | The **delivery date agreed** with the customer when they approve the estimate |

Once the estimate is approved the ticket waits on a task ("Waiting on Task" is a Paused
status, so the SLA resolution clock stops) and the task's due date is the agreed date.
Task reminders and the morning brief chase it; nothing new is needed for that.

## The flow

```
Ticket ──▶ AI triage ──▶ Estimate ──▶ Customer ──▶ AI builds ──▶ Checks ──▶ Developer ──▶ Customer ──▶ Deploy
           (type +       (agent       approves      on staging    (tests,    approves     tests on      (person
            hours)        sends)      [gate 1]                    review)    [gate 2a]    staging       clicks)
                                                                                          [gate 2b]
```

1. **Triage.** AI triage classifies the request (`request_type`: issue, question,
   customization) and, for a customization, estimates developer hours.
2. **Estimate.** An agent checks the AI estimate, adjusts it and sends it with a delivery
   date. Hours become working days at HD Work Settings → Development Hours per Day.
3. **Gate 1: customer approval** of scope, hours and date (portal button, or the agent
   records an email or phone approval).
4. **Build on staging.** The AI agent makes the change on the customer's staging site:
   configuration through the hub's MCP connection, code through a pull request.
5. **Checks.** Tests, the CodeRabbit review, lint, and running the
   changed report or form on staging data.
6. **Gate 2a: developer approval** of the diff or configuration.
7. **Gate 2b: customer acceptance** on staging (portal button).
8. **Deploy.** A person clicks Deploy: the same configuration is applied to production
   through MCP, or the pull request is merged and the bench deployed in Press. The
   previous version is kept for rollback.
9. **Close.** The ticket resolves; the timesheet records the AI build and the people's
   review time; the report compares estimate with actual hours and the agreed date with
   the delivery date.

## Two kinds of customization

| Kind | Examples | How the agent builds it | Deploy |
|---|---|---|---|
| **Configuration** | Report filters and columns (Script/Query Report), Print Formats, Custom Fields, Property Setters, Client/Server Scripts, Workflows | Generates the documents (JSON) and creates them on **staging** through the helpdesk_client MCP tools (the hub already pushes content approvals this way) | Apply the same documents to production through MCP, after export of the current versions |
| **Code** | Logic in the customer's custom app | Writes the change in the custom app's repo and opens a pull request | Merge after review, deploy the bench in Press |

Start with configuration: most small requests (report and print format changes) are
configuration, and the AI does these well. Accounting, stock and integration logic stays
with developers; the agent may draft, a developer finishes.

## Phases

### Phase 1: estimates in TBO Support (implemented)

- Ticket type **Customization** (created on install and by patch
  `v16_0_2.customization_estimates`).
- AI triage returns `request_type`, `estimate_hours` and `estimate_note`; a customization
  gets the type and the AI estimate (status *Estimated*) once. An estimate an agent has
  worked on is never overwritten. Code: `helpdesk/triage.py`,
  `helpdesk/api/customization.py` (`record_triage_estimate`).
- HD Ticket fields: `custom_estimate_hours`, `custom_estimate_status`
  (Estimated, Sent, Approved, Declined), `custom_agreed_delivery`, `custom_estimate_note`,
  `custom_estimate_sent_on`, `custom_estimate_decided_on`, `custom_estimate_decided_by`.
- HD Work Settings → **Development Hours per Day** (default 6) turns hours into working
  days, skipping the weekly off.
- Agent: the **Customization estimate** card on the ticket (hours, ready-by date, note,
  Send estimate; Customer approved / declined for answers by email or phone; Create task
  once approved).
- Customer: an **Approve estimate / Decline** banner on their ticket in the portal; the
  estimate email links to it.
- An approval made after the proposed date moves the date by the days that passed. The
  agents on the ticket are notified when the customer decides.
- **Create task** on an approved estimate fills the task's due date and estimated hours
  from the estimate (`create_task_from_ticket`).
- Tests: `helpdesk/tests/test_customization_estimates.py`.

### Phase 2: staging and connections (DevOps + TBO Copilot)

- A staging site per customer in Press, refreshed from production on demand.
- A second helpdesk_client connection per customer for staging, marked as staging, so
  the agent can never write to production by mistake.
- An allow-list of what the agent may create or change through MCP (Report, Print
  Format, Custom Field, Property Setter, Client Script, Server Script, Workflow) and an
  audit log of every call.

### Phase 3: the build agent (TBO Copilot)

- Picks up approved customizations, reads the ticket, triage and estimate, inspects the
  customer's staging schema through MCP, and proposes the change.
- Configuration: creates the documents on staging and records what it created.
- Code: opens a pull request on the custom app; CI and the AI review run as usual.
- Posts a summary and a staging link on the ticket, and logs time on the task.
- Stops and asks a developer when the change touches accounting, stock valuation,
  permissions or an integration, or when its own check fails twice.

### Phase 4: approvals, deploy, rollback and reporting

- Developer review and customer acceptance buttons (gates 2a and 2b) on the ticket and
  in the portal.
- Deploy button: applies the configuration to production (or merges and deploys), after
  exporting the current versions for rollback.
- Report: estimate vs actual hours, agreed vs delivered date, per customer; AMC hours
  used and left (if AMC tracking is wanted).

## Security and safety rules

- The agent never writes to production. Production changes happen only from the Deploy
  button, pressed by a person, after both approvals.
- The agent's MCP access is limited to the allow-listed doctypes, on staging only.
- Every agent action is logged on the ticket (what, where, when).
- Customer data stays on the customer's site; prompts carry schema and the request, not
  bulk records.
- Rollback: the previous version of every changed document is exported before deploy.

## Open decisions

- Track AMC / billable hours per customer per month?
- Which customer pilots phase 2–3 (suggested: Galom), and which kinds first (suggested:
  report filters and print formats)?
- Should estimates above a threshold (for example 16 hours) need a lead's approval before
  they're sent?
