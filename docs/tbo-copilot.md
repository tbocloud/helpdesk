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
