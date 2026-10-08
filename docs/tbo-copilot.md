# TBO Copilot (hub side)

TBO Copilot is the AI support engineer: a customer's ticket comes in, a worker investigates it on a sandbox, the hub routes the result (explain, fix, hand over, ask), one person approves a change, and the customer is kept informed on their own ticket. The design and the build plan live in the `tbocloud/tbo-copilot` repository (`docs/tbo/system-design.md`, `build-plan.md`, `phases/`). This page describes what is implemented in `helpdesk`.

Code: `helpdesk/copilot/` (one module per concern), `helpdesk/api/copilot*.py` (endpoints). Doctypes are prefixed `HDS Copilot …` and named `TBO-<KIND>-.YYYY.-.#####` like the other hub doctypes.

## Settings (`HDS Copilot Settings`)

| Field | Meaning |
|---|---|
| Enabled | A Copilot run starts for every new ticket of a customer with **Copilot enabled** (HD Customer) |
| Hand-over project | Tasks for hand-overs go here when the customer has no project of their own |
| Lease minutes | A worker keeps a run alive by heartbeat; after this long without one the run is given back to the queue (default 5) |
| Max lease losses | After this many lost leases the run fails and a person is told (default 3) |
| Min confidence | An investigation below this confidence (0 to 1) is treated as unclear (default 0.6) |
| Messages to the customer | One row per stage (Received, Working on it, Fix scheduled, Resolved, With our team, Waiting for you); an empty or missing row uses the built-in text in `helpdesk/copilot/settings.py`. Placeholders: `{date}`, `{resolution}` |

`helpdesk/copilot/settings.py`: `get_settings()`, `is_enabled()`, `template_for(stage)`.

On HD Customer: **Copilot enabled** opts the customer in; **Assigned developer** receives the task when Copilot hands a ticket over to a person.

## Site registry (`HDS Site Registry`)

One row per customer site and environment (Production, UAT, Sandbox): the customer, the connection it is reached through, the site URL, and its apps (`HDS Site App`: app, GitHub repository, branch, deployed commit, drift status). A customer and connection have one Production row.

`helpdesk/copilot/registry.py`: `registry_for_ticket(ticket)` finds the Production site by the ticket's connection, else by its customer; `apps_for(registry)` hands the apps to a worker as plain dicts.

Rows are entered by hand for the pilot. Press deployment (Phase 2) fills `press_site` and `press_release_group` and syncs the apps from Press; the client's code identity (Phase 1b) fills `deployed_commit` and the drift status.

## Runs (`HDS Copilot Run`, `helpdesk/copilot/runs.py`)

A run is Copilot's work on one ticket. It starts when a ticket of a customer with **Copilot enabled** is created (settings **Enabled** on), or when an agent starts one; a ticket has one active run at a time (`custom_copilot_run` points at the latest). Every change of state writes an `HDS Copilot Event`, mirrors the stage on the ticket (`custom_copilot_stage`, `custom_root_cause`) and publishes `helpdesk:copilot-run` with the ticket and run names to the ticket's room, nothing more.

| From | To | Who | When |
|---|---|---|---|
| — | Queued | hub, agent | the ticket arrives; Start Copilot; a follow-up after the customer's reply |
| Queued | Investigating | worker | `claim_job` |
| Investigating | Queued | hub | the lease expired (fewer than **Max lease losses** times) |
| Investigating | Failed | worker, hub | `submit_result(failure)`; too many lost leases (the Agent Managers are told) |
| Investigating | Explaining | hub (router) | question, not_allowed_request, customer_mistake, unclear |
| Investigating | Preparing Fix | hub (router) | wrong_setting, bug, data_damaged_by_bug |
| Investigating | Handed Over | hub (router) | core_issue |
| Explaining | Answered | hub, agent | the agent sent the reply |
| Answered, Handed Over | Closed | customer, agent, hub | the customer confirmed |
| Answered, Preparing Fix, Handed Over | Escalated | customer, agent | the customer reopened; a person takes over |
| any active state | Cancelled | agent | Cancel |

Later phases add Awaiting Approval, Approved, Merging, Merged, Deploying, Verifying, Resolved and Rejected.

**Leases.** A claim gives the worker a token for **Lease minutes**; `heartbeat` extends it, and every later call must carry it. The cron `*/5` (`expire_stale_leases`) sends a run whose lease ran out back to the queue, or fails it after **Max lease losses**. A cancelled run keeps its token so the worker's next heartbeat is answered with `cancel`.

**Router** (`helpdesk/copilot/router.py`). `submit_result` with `kind: investigation` is validated (`root_cause_category` among the eight, `confidence` 0–1, bounded strings and lists) and routed by the table above; a confidence below **Min confidence** is treated as `unclear`, with the reported category kept in the run's investigation JSON.

## Worker API (`helpdesk/api/copilot_worker.py`)

POST only, for users with the role **Copilot Worker** (created on migrate, no desk access; give it to a worker user with API keys).

| Call | Does |
|---|---|
| `claim_job(worker_id, free_slots=1, capabilities="")` | the oldest queued run: `{run, lease_token, lease_expires, context}`, or `{}` |
| `heartbeat(run, lease_token, stage="")` | keeps the lease; `{ok, action: continue or cancel}` |
| `post_events(run, lease_token, events)` | stores `[{seq, type, payload}]`; a repeated `seq` is ignored; payloads over 16 KB are cut and marked |
| `submit_result(run, lease_token, result)` | `{kind: investigation, root_cause_category, confidence, summary, evidence[], proposal{}, customer_message, questions[], cost{tokens, usd}}` or `{kind: failure, reason}` |

The context holds the ticket, its triage fields, the customer, the registered site and its apps, the last 20 messages, the file list and earlier runs; never credentials. Events are kept 90 days.

**Trying it without a worker:** `bench --site <site> execute helpdesk.test_utils.run_fake_worker --kwargs "{'category': 'bug'}"` claims the oldest queued run and reports that root cause with demo text (`abandon: True` claims and stops, to watch the lease expire; `ticket: '0042'` starts a run for that ticket first).
