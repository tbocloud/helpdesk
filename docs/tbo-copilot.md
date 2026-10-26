# TBO Copilot (hub side)

TBO Copilot is the AI support engineer: a customer's ticket comes in, a worker investigates it on a sandbox, the hub routes the result (explain, fix, hand over, ask), one person approves a change, and the customer is kept informed on their own ticket. The design and the build plan live in the `tbocloud/tbo-copilot` repository (`docs/tbo/system-design.md`, `build-plan.md`, `phases/`). This page describes what is implemented in `helpdesk`.

Code: `helpdesk/copilot/` (one module per concern), `helpdesk/api/copilot*.py` (endpoints). Doctypes are prefixed `HDS Copilot …` and named `TBO-<KIND>-.YYYY.-.#####` like the other hub doctypes.

## Settings (`HDS Copilot Settings`)

| Field | Meaning |
|---|---|
| Enabled | A Copilot run starts for every new ticket of a customer with **Copilot enabled** (HD Customer) |
| Shadow mode | On by default. Copilot investigates and notes its diagnosis for the team only: the customer sees no stages and no portal question, no hand-over Task is created, and agents rate each diagnosis (see **Shadow mode** below). Switch it off only when the ratings show Copilot is right often enough |
| Hand-over project | Tasks for hand-overs go here when the customer has no project of their own |
| Lease minutes | A worker keeps a run alive by heartbeat; after this long without one the run is given back to the queue (default 5) |
| Max lease losses | After this many lost leases the run fails and a person is told (default 3) |
| Min confidence | An investigation below this confidence (0 to 1) is treated as unclear (default 0.6) |
| Messages to the customer | One row per stage (Received, Working on it, Fix scheduled, Resolved, With our team, Waiting for you); an empty or missing row uses the built-in text in `helpdesk/copilot/settings.py`. Placeholders: `{date}`, `{resolution}` |
| Press URL, API key and secret, team | Copilot's own Press user in TBO's Press team, for deploys (see **Deploying through Press**). Without them Deploy is refused and Mark deployed stays the way |
| Deploy window starts, ends, timezone | Deploy Tonight goes out in this window (default 21:00 to 06:00, Asia/Riyadh) |
| Wait for Press (minutes) | How long a deploy waits for Press (another deploy running, the merged commit not yet on the bench) before it moves to the next window (default 60) |
| Check after deploy (minutes) | How long the check after a deploy may keep asking a site that does not answer (default 30) |
| Skip Press's backup | Test benches only (off by default): Press updates the sites without a backup first, so a failed update cannot be restored from one. The Deploy dialog says so. Leave it off for customers' live sites |
| Auto-deploy categories | Empty in the pilot. Root-cause categories or risk levels, one per line, whose approved fixes are scheduled for the window by themselves |

`helpdesk/copilot/settings.py`: `get_settings()`, `is_enabled()`, `is_shadow()`, `template_for(stage)`.

On HD Customer: **Copilot enabled** opts the customer in; **Assigned developer** receives the task when Copilot hands a ticket over to a person.

## Site registry (`HDS Site Registry`)

One row per customer site and environment (Production, UAT, Sandbox): the customer, the connection it is reached through, the site URL, and its apps (`HDS Site App`: app, GitHub repository, branch, deployed commit, drift status). A customer and connection have one Production row.

`helpdesk/copilot/registry.py`: `registry_for_ticket(ticket)` finds the Production site by the ticket's connection, else by its customer; `apps_for(registry)` hands the apps to a worker as plain dicts.

A row is created by hand; then **Refresh from the site** on the form (`helpdesk.api.copilot.refresh_site_card`, System Manager) reads every app the site runs through its connection (`get_code_identity`): the repository (from the git remote; an app reported without one keeps the repository already on the card), the branch, the deployed commit, and Drift when the site's code has uncommitted changes. A sandbox copy needs all of them. For a site on TBO's Press, its Press site name and release group (the bench) are typed in once. **Refresh from Press** (`helpdesk.api.copilot.refresh_site_card_from_press`, write access to the card) then reads the bench from Press: an app whose Press commit differs from the one the site reported is marked Drift (the site's own commit stays), and **Other sites on the bench** lists the sites that share its code. A card the site already filled keeps exactly the site's apps: a shared bench holds every site's apps, so Press's other apps are only listed (`bench_only` in the answer), never added. An empty card is filled from Press.

**Before every run the card is read again** (`registry.refresh_for_run`, when a worker claims a run or a fix job): a deploy made outside Copilot, from Press's dashboard for example, would otherwise leave the card behind, and the worker would read older code than the site runs. It is one quick read through the connection (8 seconds, no retry), skipped when the card was read in the last 2 minutes. The run records what changed (`site_refreshed`, each app's old and new commit), or that the site did not answer (`site_not_refreshed`), in which case the worker reads the commits the card had; the run context says when they were read (`site.apps_read_at`).

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
| Preparing Fix | Awaiting Approval | hub | the fix's pull request is ready for review (see **The fix**) |
| Awaiting Approval | Approved | agent | the one approval |
| Awaiting Approval, Approved | Preparing Fix | agent, hub | rejected with a reason; the pull request went back to draft or was closed |
| Approved | Awaiting Approval | hub | new commits arrived after the approval |
| Approved | Merged | hub | the hub merged it |
| Preparing Fix, Awaiting Approval | Merged | hub | merged on GitHub without the approval (recorded, the Agent Managers told) |
| Merged | Resolved | agent | Mark deployed, after an engineer deployed it |
| Merged | Deploying | hub | Press started the deploy (or the bench already runs the merged commit) |
| Deploying | Verifying | hub | Press updated every site |
| Verifying | Resolved | hub | the check after the deploy passed |
| Merged, Deploying, Verifying | Escalated | hub | the deploy or the check failed |
| Resolved | Closed, Escalated | customer, agent | the customer confirmed, or reopened |
| any active state up to Approved | Cancelled | agent | Cancel |

An undo is a run of its own (`kind` revert, `reverts` the run it undoes); see **Deploying through Press**.

A run started while **Shadow mode** is on is a shadow run (`shadow`) for its whole life, whatever the setting says later. `base_app` and `base_commit` (set with `start_run(..., base_commit=, base_app=)`) make the worker read that app at that commit instead of the deployed code; the evaluation uses them to put Copilot in front of the code as it was before a known fix.

**Leases.** A claim gives the worker a token for **Lease minutes**; `heartbeat` extends it, and every later call must carry it. The cron `*/5` (`expire_stale_leases`) sends a run whose lease ran out back to the queue, or fails it after **Max lease losses**. A cancelled run keeps its token so the worker's next heartbeat is answered with `cancel`.

**Router** (`helpdesk/copilot/router.py`). `submit_result` with `kind: investigation` is validated (`root_cause_category` among the nine, `confidence` 0–1, bounded strings and lists) and routed by the table above; a confidence below **Min confidence** is treated as `unclear`, with the reported category kept in the run's investigation JSON.

## Worker API (`helpdesk/api/copilot_worker.py`)

POST only, for users with the role **Copilot Worker** (created on migrate, no desk access; give it to a worker user with API keys).

| Call | Does |
|---|---|
| `claim_job(worker_id, free_slots=1, capabilities="", run="")` | the oldest queued run, or the named one when it is queued (an evaluation claims exactly the runs it started): `{run, lease_token, lease_expires, context}`, or `{}` |
| `heartbeat(run, lease_token, stage="")` | keeps the lease; `{ok, action: continue or cancel}` |
| `post_events(run, lease_token, events)` | stores `[{seq, type, payload}]`; a repeated `seq` is ignored; payloads over 16 KB are cut and marked |
| `submit_result(run, lease_token, result)` | `{kind: investigation, root_cause_category, confidence, summary, evidence[], proposal{}, customer_message, questions[], cost{tokens_in, tokens_out, usd, model}}` or `{kind: failure, reason}`; the run keeps the tokens and the model |

The context holds the ticket, its triage fields, the customer, the registered site and its apps, the last 20 messages, the file list and earlier runs, whether the run is a shadow run, the base app and commit when set, and `models`: for `investigate`, `fix` and `review`, each AI provider section in the hub's order with that job's model (Models per job, else the section's model) and its price per million tokens. Never credentials: the worker holds its own provider addresses and keys and uses only the sections it has a key for ([AI providers](ai-providers.md#models-per-job)). Events are kept 90 days.

**The worker's AI cost.** The `cost` in `submit_investigation` and `submit_change` may carry `stages`: one entry per job and model (a stage that moved to its fallback model has two). Each becomes an HDS AI Usage Log row with the run, its ticket, the job and `fallback`, once per run, job, attempt and model, so a ticket's hub and worker AI cost show in one report.

**Trying it without a worker:** `bench --site <site> execute helpdesk.test_utils.run_fake_worker --kwargs "{'category': 'bug'}"` claims the oldest queued run and reports that root cause with demo text (`abandon: True` claims and stops, to watch the lease expire; `ticket: '0042'` starts a run for that ticket first).

## After the worker reports (`helpdesk/copilot/router.py`, `customer.py`)

| Root cause | Run | The customer sees | What else happens |
|---|---|---|---|
| question, not_allowed_request, customer_mistake | Explaining → Answered when the agent sends | Working on it → **Resolved** ("please confirm, or reopen") | the worker's `customer_message` lands in the agent's suggested-reply card; nothing goes out by itself |
| unclear (or confidence below the setting) | Explaining → Answered when the agent sends | Working on it → **Waiting for you** | the questions land in the card; the customer's reply (email, portal or their site) starts a **follow-up run** |
| wrong_setting, bug, data_damaged_by_bug | Preparing Fix | **Working on it** | continues in the next phases (sandbox, pull request, approval) |
| customization_request | Explaining → Answered when the agent sends | Working on it → **With our team** | the explanation says it is a change, not a fault, and offers an estimate; **Start estimate** in the Copilot dialog makes the ticket a Customization with Copilot's hours (`helpdesk.api.copilot.start_estimate`), and the agent sends the estimate from the estimate card |
| core_issue | Handed Over | **With our team** | a Task for the customer's **Assigned developer** in the customer's open Project (else the hand-over project); without a project the Agent Managers are told |

Every diagnosis is an internal note on the ticket (category, confidence, summary, evidence, proposal), credited to the hub's automation user.

**Stages on the customer's site.** A stage is delivered once per run, stage and text: to a connected site whose client advertises `hub_api_v1` as an update row on its Support Ticket (the raiser is notified there), and as an internal note on the hub ticket; `custom_copilot_stage` mirrors it. An older client gets no stage (its status is still pushed as before). The texts come from HDS Copilot Settings. A site that cannot be reached is logged once an hour per ticket; the stage still shows on the hub.

**Confirm and reopen.** On the customer portal the ticket page shows "Is this solved?" while the stage is Resolved (`helpdesk.api.copilot.get_resolution` / `decide_resolution`); on a connected site the customer presses the same buttons on their own ticket and the sync relays the answer. Confirmed closes the ticket (through the controller) and the run. Reopened needs a note, reopens the ticket, escalates the run, creates the hand-over Task and tells the developer (or the managers); the customer sees **With our team**.

**Shadow mode.** A shadow run does everything above for the team and nothing for the customer:
- stages are recorded as events only (`shadow: true`, `pushed: false`), with no note on the ticket and no `custom_copilot_stage`, so the customer's site, the portal question and follow-up runs stay untouched;
- the diagnosis note is marked "(shadow)" and asks the agent to rate it;
- explanations and questions still land in the suggested-reply card, where the agent decides;
- a core issue is not handed over (an event `hand_over_skipped` records it).

**Rating a diagnosis.** On a run with a diagnosis, the agent presses **Rate diagnosis** in the Copilot dialog and chooses **Right**, **Partly** or **Wrong**; Wrong needs the root cause the agent found, and a note is optional (`helpdesk.api.copilot.review_diagnosis(ticket, verdict, root_cause, note)`, agents with read access to the ticket). The run keeps the latest rating (`review_verdict`, `reviewed_root_cause`, `review_note`, `reviewed_by`, `reviewed_at`); every rating is also an event. The ratings measure Copilot before shadow mode is switched off.

**The agent's Copilot button** (HD Form Script "Helpdesk Copilot Actions", installed with the AI one by `helpdesk/setup/form_scripts.py`): start a run, see the state, root cause, diagnosis, evidence, model and tokens and latest events, rate the diagnosis, cancel it, start again. API: `helpdesk.api.copilot.start_run`, `get_run`, `review_diagnosis`, `cancel_run` (agents).

**Connections** record `client_version` and `client_capabilities` from registration and the daily health check (`helpdesk/client_api.py`: `call`, `hub_api`, `supports`).

## The fix (`helpdesk/copilot/fixes.py`, `approvals.py`, `risk.py`, `github.py`)

A run at Preparing Fix needs a code change. Until the worker can open pull requests (Phase 1c-2), a developer makes the change; the hub holds it, asks one person to approve it, merges it, and tells the customer once it is deployed.

1. **The fix task.** A live run gets a Task "Copilot fix: <subject>" in the customer's open project (else the hand-over project), assigned to the customer's **Assigned developer**, with the diagnosis and the instruction to open a pull request that says `Closes TASK-…`. A shadow run gets it from **Create fix task** in the Copilot dialog. With no project at all the run says so on the ticket.
2. **The pull request.** The GitHub sync links it to the task and calls `fixes.on_pull_request`. The hub puts the **hold label** (`no-auto-merge`, a setting) on it: the org merge bot and the repository's auto-merge workflow skip pull requests with that label, so nothing merges it before the approval. A draft waits; when it is ready, an **HDS Copilot Approval** is opened for its head commit, with the changed files, the risk and the checks, and assigned. One pull request per fix: while the run's own is open, another that closes the same task is left alone (an event says so) and is followed once the first is closed.
3. **The risk** (`risk.py`, fixed rules on the changed files): accounting and tax, stock, payroll, permissions, migrations, `hooks.py`, doctype JSON, raw SQL writes, dependencies or CI make it **high** and **sensitive**; more than 300 changed lines make it high; no test makes it medium; otherwise low. Each reason is listed on the card.
4. **Who approves.** HDS Copilot Settings → **Approvers** (user, senior, active). The customer's developer when allowed, else the approver with the fewest pending approvals; a sensitive fix only a **senior** (with no senior listed, the Agent Managers act as seniors); never the people the fix task is assigned to. The approver hears it by chat or email with a link to the ticket; a sensitive one, and any approval that waits past **Escalate after**, also goes to the team's channel.
5. **Deciding** (`approvals.decide`, row lock): the first decision wins. **Approve** with the planned deploy date: the hub re-reads the pull request, and if new commits arrived the approval is superseded and a new one opened. **Reject** needs a reason, which goes to the task and the pull request; the run goes back to Preparing Fix, and the rejected commit is not asked again: the developer's next push opens a new approval.
6. **The merge** (`fixes.try_merge`): when the head is still the approved commit, every check run passed (success, neutral or skipped) with the commit status green or absent, and GitHub calls the merge clean, the hub merges with the approved commit pinned (GitHub refuses with 409 if the head moved), using the repository's own method as the org merge bot chooses it (merge commit where allowed, else squash, else rebase). It retries on every check webhook and the 10-minute refresh. A lasting block (failing checks, merge conflicts, a branch behind its base, a review GitHub requires) is told to the approver and the developer once, in plain words; GitHub still settling the merge state (`unknown`, `unstable`) is a quiet wait. Each finished workflow also updates the checks on the card. After merging, the hub replays the merged pull request through the task sync, so the fix task completes at once; GitHub's own webhook arriving later changes nothing, because the sync acts once per change of state. The customer then sees **Fix scheduled** with the planned date.
7. **Merged elsewhere.** A pull request merged on GitHub without the approval moves the run to Merged too, with a note on the ticket, an event and the Agent Managers told.
8. **Deploy, or Mark deployed.** A site on TBO's Press is updated with **Deploy** (see **Deploying through Press**). Otherwise, after an engineer deploys the merged fix by hand, **Mark deployed** in the dialog resolves the run; the customer is asked to confirm (Resolved), as in Phase 1a. Mark deployed is refused while a deploy is waiting or running.

The GitHub token in Settings → GitHub needs, on the repositories Copilot fixes: Contents read and write (to merge), Pull requests read and write (the pull request, labels, comments), Commit statuses read, and Checks read. GitHub gives no fine-grained personal token Checks read; with one, give it Actions read instead: the hub then reads the commit's GitHub Actions workflow runs, the card says that only those were seen, and GitHub's own merge state still has to be clean. Those repositories must also be allowed in the sync. Copilot follows pull requests only while the GitHub sync is on: switched off, the refresh says so and nothing acts on GitHub's events. Crons: `fixes.refresh_open` every 10 minutes (reads every open fix's pull request from GitHub and replays it as its webhook would have; finds one that says `Closes TASK-…` but never reached the hub, and moves on to a new pull request when the run's was closed), `approvals.remind_and_escalate` every 15 minutes (a reminder after **Remind after** hours, then a senior or the Agent Managers after **Escalate after** hours). API (agents): `helpdesk.api.copilot.create_fix_task`, `decide_fix(ticket, approve, note, deploy_date)`, `refresh_fix`, `mark_deployed`; `get_run` returns the fix card (deploys: see below). When the Task of a Copilot fix completes on the merge, its note on the ticket says to deploy and press Mark deployed instead of "Reply to the customer".

## Copilot's own fix (Phase 1c-2: `fixes.request_copilot_fix`, `github_app.py`)

Copilot can write the fix itself instead of a developer. It does so only when asked: **Copilot writes fixes** in HDS Copilot Settings (off by default) asks it for every live bug diagnosis; **Let Copilot fix it** in the Copilot dialog asks it for one run, live or shadow.

1. **The fix job.** Asking queues a fix job on the same run, still at Preparing Fix (`fix_requested`, `fix_status` Queued). It also makes sure the fix task exists, because the pull request must say `Closes TASK-…`. A worker that can fix (`claim_job(..., capabilities="fix")`) claims it with a lease, as for an investigation. Its context adds the diagnosis and `fix`: the task, the branch to push (`copilot/TASK-…-r<run>-a<attempt>`), the site's repositories, the dollar cap and Copilot's commit email.
2. **The push key.** `copilot_worker.repo_token(run, lease, repository)` gives the worker a GitHub App key for **one repository of the run's site card**, valid an hour, allowed only to push and open the pull request. Any other repository is refused.
3. **The report.** The worker opens the pull request and reports it with the MCP tool `submit_change`: repository, number, head commit, and what it tested on the sandbox copy (each check pass, fail or not run). The hub keeps it on the run (`change`), ends the lease and follows the pull request at once, so the approval opens with the results. The card shows them under "Tested by Copilot", and says when they belong to an older commit than the pull request's head.
4. **Who approves.** When the GitHub App opened the pull request and every commit carries Copilot's commit email, nobody on the fix task wrote it, so the customer's developer may approve it. If a person added commits, the 1d rule applies again.
5. **When it fails.** A failure report (`submit_result` with `kind: failure`) sets the fix to Failed. The run stays at Preparing Fix, and the reason goes to the fix task and to its developer. A worker that stops reporting is tried again until **Fix attempts per run** (2) are used, then the same happens.

**The GitHub App** (HDS Copilot Settings: App ID and private key): when it is set up, every Copilot call to GitHub uses an installation key for the repository in question, and the search for an unlinked pull request asks each owner of the site's repositories. Without it, the personal token in Settings, GitHub is used as before. It also lets the hub read check runs, which a fine-grained personal token cannot.

## Deploying through Press (Phase 2: `press.py`, `deploy.py`, `verify.py`)

After the merge, a person presses **Deploy** on the ticket's Copilot card: **Tonight** (the next deploy window; inside the window, at once) or **Now**. The approvers and the Agent Managers may deploy Tonight; only senior approvers and Agent Managers may deploy Now. If other customers' sites share the bench, only a senior may deploy, and they stay on their old code: Press's normal update moves only the sites it is given, and keeps every other app at its last deployed commit. TBO Support's own site may share the bench too (TBO's demo bench does): it is not another customer, it never moves (a site card naming it is refused), and its code stays as it is. The Deploy dialog lists the exact sites it updates before it is pressed, and pressing it approves that set: the deploy request keeps them as a fixed list (a change to it is refused), and only those rows go to Press. The card lists the sites left on the bench under **Not moved**; until they move, Press runs the old and the new bench side by side.

**What moves.** The Press site of each of the customer's Production site cards on that bench, with the merged commit of the app whose repository the fix changed. The request (`HDS Deploy Request`, `TBO-DEP-.YYYY.-.#####`) lists the sites, the app with its old and new commit, and the other sites on the bench.

**The steps** (the cron `deploy.run_due`, every 5 minutes):

1. **Scheduled** until its time.
2. **Starting.** One Copilot deploy at a time across TBO's Press (a lock, freed after 3 hours at the latest), none while Press is deploying that bench, and the merged commit must be Press's next release for the app (else the hub asks Press to fetch it and waits). While it cannot start it is **Waiting for Press**; after **Wait for Press** minutes it moves to the next window. A bench that already runs the merged commit goes straight to the check.
3. **Deploying.** `deploy_and_update` for those sites only, with Press's backup first (unless **Skip Press's backup** is on) and Press's check that the update will not fail; the run is Deploying. The hub follows each site's Site Update. Failure, Fatal, Recovered or Recovery Failed (Press puts the site back on its old code), or no answer in 2 hours, fails the deploy. It also reads the bench's newest Deploy Candidate Build (Deploy Candidate itself has no status on TBO's Press): a build in Failure fails the deploy at once, with a link to the build, since Press then updates no site. Agent Jobs are not read: some fail by design on TBO's Press ("Add User to Proxy" on every new bench) without the deploy failing. With Press's new deploy flow on (Release Pipelines, as on TBO's Press) the hub follows the same Site Updates.
4. **Checking.** The run is Verifying, and the hub checks the site through the customer's connection: it runs the merged commit; no error signature since the deploy began that the week before did not have (the connector's own left out); the scheduler is on and maintenance mode off; the documents the diagnosis names still open. A site that does not answer is asked again for **Check after deploy** minutes. A ticket without a connection is not checked, and the card says so.
5. **Succeeded.** The run is Resolved, and the customer sees Resolved ("The fix is live") and is asked to confirm.

**When it fails**, the request is Failed with Press's reason or the failed check, the run is Escalated, a note goes on the ticket, and the approver, the person who pressed Deploy and the Agent Managers are told. **Cancel deploy** works while the request has not started.

**Undo the fix.** On a run whose merged fix went wrong (Escalated or Resolved), an approver or Agent Manager presses **Undo the fix** with a reason. The hub asks GitHub for its own revert of the merged pull request (`revertPullRequest`; with the GitHub App when it is set up) and starts a revert run with its own task ("Copilot revert: …"); the revert pull request says `Closes` that task and goes through the one approval and the merge like any fix, then Deploy (Now, for a senior). The ticket's card follows the revert run. The customer hears nothing from it: its stages are recorded as events only. One undo per run. A database restore from Press's backup stays a person's decision.

**Automatic deploys.** With **Auto-deploy categories** filled (empty in the pilot), a fix whose root cause (for example `bug`) or risk level (`low`, `medium`) is listed is scheduled for the window by itself when it merges, on its approver's behalf. Never a sensitive or high-risk fix, an undo, or a bench other customers' sites share; whatever stops it is an event (`auto_deploy_skipped`) and Deploy stays with a person.

**The Press client** (`press.py`) posts `{Press URL}/api/method/<method>` with `Authorization: token <key>:<secret>` (and `X-Press-Team` when set) and shows Press's own message on a refusal. The key goes only to an `https://` Press URL, with certificate checks, and a redirect is refused, never followed. Press has no narrower role for an API user, so keep the key on the hub and, where Press's web server allows, accept it only from the hub's address.

API (agents): `helpdesk.api.copilot.request_deploy(ticket, when)`, `cancel_deploy(ticket)`, `undo_fix(ticket, reason)`; `get_run` adds the deploy to the fix card (status, time, sites, other sites on the bench, the check, the error).

**When a deploy goes wrong (runbook)**

1. Read the card: Press's reason, or the check that failed.
2. **Press failed the update** (Recovered): Press put the site back on its old code from its own backup. Open the site to confirm, read Press's Site Update for the step that failed (often a patch), then fix forward with a new fix, or Undo.
3. **The check failed after a good update:** the site runs the new code. If the customer is hurt, Undo and deploy the revert Now (a senior); otherwise fix forward.
4. **Data changed by a failed patch:** only a person restores from Press's backup (the site's Backups on Press), after telling the customer.
5. A deploy stuck in Deploying fails by itself after 2 hours; a lock left by a crash frees itself after 3 hours.

## Releases of every merge (Phase 7: `releases.py`)

Every merge into a branch a customer's site runs reaches the site the same way as Copilot's fixes, whoever wrote it. Off by default: HDS Copilot Settings → **Releases** → **Release every merge**, and **Repositories in the pipeline** (one `owner/repo` per line; add a repository once its CI is green).

**A release** is an `HDS Deploy Request` without a Copilot run. Every 10 minutes (`releases.watch`) the hub reads the tip of each branch that a Production site card deploys through Press (the hub's own site never counts). Commits the bench does not run yet (Press's running commit, else the card's) become a release per repository, branch and bench, holding each commit with the pull request that merged it, the task it closes (`Closes TASK-…`; the task's ticket too) and the customers' sites. **Source** is Pull request, or **Push** when a commit came without one. Later commits join a release until it is approved; after that they start a new one. Commits that are only Copilot's merged fixes are left to the fix's own Deploy; a release that contains one resolves its run when it succeeds. A branch GitHub cannot read is logged once every 6 hours.

**The steps** (`releases.run_due` every 5 minutes, then `deploy.run_due`):

1. **Waiting for CI.** CI runs on a pull request's last commit, not on the merge, so each pull request is judged there; a push by its own commit; the branch tip too when CI ran on it. Every check must be green, and a commit with no check at all fails: nothing deploys unchecked. Red CI tells the people who wrote it once; a fix arrives as new commits. A **senior** may let it through with a reason (**Let through without green CI**), kept on the release.
2. **Staging** (on unless **Stage before the approval** is off). When one of the customers has a **UAT** site card that runs the same branch on Press, the release first deploys there in the next window (a UAT deploy request, `staging_for` the release) with the check after. Otherwise a worker that offers `release_check` builds a fresh site with the card's apps at their commits and this app at the release's commit, then runs migrate, the app's tests and the new-errors check (`copilot_worker.claim_job` hands it out; `release_check_result` takes the evidence; 60-minute lease). A check no worker takes within **Hours a sandbox check may wait** is marked not run, and the seniors are told. A failed or missing check waits for a fix, or a senior lets it through.
3. **Waiting for approval.** One approver who wrote none of it: not an assignee of the tasks it closes, nor a user with a commit's email. A **senior** for a push, a sensitive diff (`risk.py` on the release's changed files), several customers, or another customer's site on the bench. The release's card goes to them in Teams (else the Copilot panel), with **Approve for tonight**, **Deploy now** (seniors and Agent Managers) and **Reject** (a reason, sent to the people who wrote it). The card is bound to what the approver saw: new commits, or a decision someone already made, refuse it. Reminders after **approval_reminder_hours**. The same buttons are on the release's form in the desk.
4. **Scheduled**, then the deploy as for a fix (window, lock, Press, Site Updates). **The nightly train:** approved requests due on the same bench go out in one Press deploy (one build), each app once; the others wait for the next train.
5. **Checking** through each site card's own connection: the merged commit, no new errors, the scheduler. **Succeeded** tells the people who wrote it, the approver and the ticket.

**When it fails**: Press's failure (the site is put back on its old code) is reported with Press's links. When the site ran the new code and the check after failed, each pull request of the release is **reverted** with GitHub's own revert, newest first; the reverts are ordinary pull requests that come back as the next release. A push has nothing to revert: the people are told.

**The weekly pilot email** gets a Releases section: releases made (from pushes, let through), live and checked, failed and reverted, rejected, the median wait for an approval, and the deploys on these benches that went around TBO Support (Press builds no deploy request asked for).

API (agents): `helpdesk.api.copilot.get_release(release)`, `decide_release(release, approve, note, when, expected_hash)`, `override_release_ci(release, reason)`, `cancel_release(release, reason)`. Worker: `claim_job(..., capabilities="release_check")`, `release_check_result(release, lease_token, evidence, tested_on)`.

## Corrections to settings and data (Phase 3: `changes.py`, `approval_key.py`)

When the cause is a wrong setting (`wrong_setting`) or data a bug damaged (`data_damaged_by_bug`), the worker's report can carry a **change set**: each record with its new values and why, how the records were found, a note for the customer, and the records it leaves to a person. The worker reports it in `submit_investigation` (`change_set`) or `submit_result`. A change set has at most 1,000 records; each one updates fields (and existing table rows, or adds rows) or creates a missing record. Deletes are refused, and so are users, roles and permissions, system and email settings, scripts and scheduled jobs, custom fields, property setters, workflows and print formats.

1. **The check.** The hub keeps the change set (`HDS Copilot Change Set`, `TBO-CHG-.YYYY.-.#####`) and, in the background, asks the customer's site about every record with the connector's `check_change`. The site writes nothing and runs none of its own code; it says whether its guard would allow the change, what is wrong with the fields or values, and what the record holds now (the old values). A submitted document is set aside for a person (cancel and amend, or a return or credit note where e-invoicing forbids cancelling). A wrong setting with a change set needs no developer, so no fix task is made.
2. **The approval.** When any record is ready, an approval opens (kind **Config Change** or **Data Fix**) for a **senior** approver, always. The card lists the first 20 records with old → new, the records set aside and why, the note the customer will get, and **Download all (CSV)**. The approval stands for exactly the checked content: if the change set is checked again with other old values, the approval is superseded. A shadow run's change set is checked and shown, never approved.
3. **Applying.** **Approve and apply** applies it at once, in the background (the run goes Approved → Applying). The hub signs one approval per batch of 200 records with the site's **approval key** and sends each record with `apply_change` and the old values it was approved for. The site refuses a record whose changed fields no longer hold those values (someone edited it since): that record is skipped and listed. The first other refusal stops the change set: the records not applied stay as they were, the run is Escalated and the Agent Managers are told. When it is done, the run is Resolved and the customer sees Resolved with the approved note.
4. **Applied by hand.** A senior may apply the records by hand on the site instead and press **Applied by hand**. That counts as their approval; the hub reads every record back and marks those that hold the new values.
5. **Rejected** with a reason: the run goes back to Preparing Fix and nothing is changed.

**Code and data together.** For `data_damaged_by_bug` the code fix goes first: the fix task and the pull request as in Phase 1d. The change set is checked when it arrives, and the pull request's approval carries it (kind **Code + Data**, one approval, by a senior). After the deploy's check passes (or **Mark deployed**), the run goes to Applying and the change set is applied with the old values it was approved for, then the run is Resolved ("The fix is live" and the note). Records the bug damaged after Copilot looked are found by starting Copilot again on the ticket: the worker sees the earlier corrections and prepares only the new ones, under their own approval.

**Undo the change.** On a run whose correction was applied, an approver or Agent Manager presses **Undo the change** with a reason. Copilot starts a revert run with the reverse change set (the stored old values), checked and approved by a senior like any correction; the customer hears nothing from it. Records the correction created, and table rows it added, are listed for a person to remove.

**Customer mistakes.** Copilot explains the ERP way, as before. When the customer asks TBO to correct it, an agent presses **Let Copilot prepare the correction** (after the explanation was sent): a follow-up run asks the worker for a change set, which goes through the same check and senior approval.

**The approval key.** The customer's site makes it when its System Manager connects the site (`connect_to_hub`) and hands it over with `pair_client`; the hub keeps it on the HDS Support Connection (`approval_key`, Password). The hub's own API key can never set it. A site connected before this version connects once more to get one; until then a Production site takes no correction (the change set stops and says so). A signed approval names the change set, the ticket (the customer's own ticket number when known), who approved it and when, its expiry (2 hours), and each record with the digest of its exact new and old values. The older write path of the AI support sessions (HDS Support Action Request) signs its approved actions the same way.

**On the customer's site** (helpdesk_client): the site checks every write itself: its write switch, its **Write List** (doctypes and actions), the never list, and on Production the signed approval. Every write, applied or refused, is a row in its **HDS Change Log**, and each changed record gets a note on its timeline. The write list starts empty.

API (agents): `helpdesk.api.copilot.decide_fix` (also for corrections), `change_set_applied_by_hand(ticket)`, `download_change_set(change_set)` (CSV), `undo_change(ticket, reason)`, `prepare_correction(ticket)`; `get_run` adds the change set to the fix card.

**When a correction goes wrong (runbook)**

1. Read the card: the record that was refused and the site's reason, or the check's findings.
2. **Refused while applying:** the records before it are changed, the rest are not. Fix the cause (often the site's write list, or a validation of the site), then start Copilot again on the ticket for the rest, or apply them by hand.
3. **Wrong values applied:** **Undo the change** prepares the reverse; a senior approves it.
4. **Submitted documents set aside:** a person corrects them the ERP way. Copilot does not touch them.
5. **No approval key:** the customer's System Manager connects the site again with a connection code from TBO Support.

## Pilot (Phase 4: `settings.level_of`, `pilot.py`, report Copilot Pilot)

**Copilot level per customer** (HD Customer **Copilot Level**; blank uses **Default Copilot level** in HDS Copilot Settings). Each level allows what the ones before it do:

| Level | Copilot may |
|---|---|
| Diagnose only | investigate; every run is a shadow run (the team sees the diagnosis, the customer nothing) |
| Explain | the customer sees the stages and the explanations agents send; bugs get the fix task and the one approval as before |
| Fix | Copilot also writes fixes (**Let Copilot fix it**, or **Copilot writes fixes**); below Fix both are refused |
| Correct | a senior may also approve setting and data corrections; below Correct a correction is checked and shown on the card (event `change_set_held`) but never sent for approval, approved or applied, even if the level is lowered after the approval was asked |

**Shadow mode** holds everyone at Diagnose only, and so does a ticket with no customer. The patch `copilot_pilot_defaults` sets the default level to Correct on a site where Copilot already ran live (shadow mode off), so nothing changes there, and to Diagnose only otherwise. The Copilot dialog shows the customer's level.

**The instant stop.** With **Copilot enabled** off, no run starts, `claim_job` hands out no work, and a worker mid-run is answered `cancel` at its next heartbeat (within 30 seconds): an investigation is Cancelled, a fix job is marked Failed (event `fix_stopped`), and the team takes the ticket as before Copilot.

**Monthly AI budget** (HDS Copilot Settings → Pilot). The month's spend is the AI usage log rows with a Copilot run (the worker's stages; the hub's own AI features are not counted). At 80% the Agent Managers are told once a month; at 100% `claim_job` hands out no work until the next month or a larger budget (0: no budget). **Dollar cap per diagnosis** goes to the worker in the run context (`limits.max_usd`); a fix has **Dollar cap per fix** in `fix.max_usd`.

**Worker watch** (every 10 minutes, `pilot.watch_workers`): runs queued, or fixes asked for, more than 15 minutes ago with no worker claiming them → the Agent Managers are told, once an hour while it lasts (not while the budget holds the work).

**Text that tries to instruct the AI** (`suspicious.py`; the red team of 18 Oct 2026 found the model reports it only sometimes). When a diagnosis arrives, the hub looks at the ticket's subject, description and the customer's messages; the worker looks at everything its tools return (files, error logs, records). Lines such as "ignore your previous rules", "note to the AI assistant", "you are now in maintenance mode" or "paste the contents of the .env file" become `suspicious_instruction` events (source and line, at most 5 a run from the worker), and the Copilot dialog shows them in a warning box: Copilot is told to ignore such text, and the agent reads it before sending anything. The patterns leave ordinary requests alone (tested).

**Copilot Pilot** (Script Report, System and Agent Managers; filters dates and customer): per week and customer, tickets, diagnoses, ratings (Right, Partly, Wrong; rated right % counts Partly half), root causes, explanations sent and the median **edit** (how much agents changed Copilot's explanation before sending it: 0 as drafted, 100 rewritten; kept on the run as `explanation_edited`), fixes asked, opened, approved, merged, deployed and undone, corrections applied, records skipped and corrections undone, refused approvals, escalations and hand-overs, median approval wait and time to resolve, AI cost (hub and worker) per ticket, and the runs rated Wrong.

**Weekly pilot email** (hourly check, sent once on Monday from 08:00 Riyadh time): last week's rows, the cost, links to the runs rated Wrong and to the report, to the **Weekly pilot email to** addresses and the Agent Managers.

## Staff assistant (Phase 6: `assistant.py`, `teams.py`, `api/copilot_teams.py`, `api/copilot_chat.py`)

One engine for the **TBO Copilot bot in Teams** (personal chat) and the **TBO Copilot panel** in the agent app (sidebar → TBO Copilot). Chats and messages: **HDS Copilot Chat** and **HDS Copilot Chat Message** (kept 90 days, `assistant.prune` daily).

**How it works.** The model only reads what the person wants: `call_haiku(job="chat")` returns one intent as JSON (`question`, `approve`, `reject`, `change_request`, `new_work`, `waiting`, `snooze`, `help`, `unclear`) with the ticket, task, reason, customer or summary it names. The code then:

| Intent | What happens |
|---|---|
| question | Answered from the run's own record only (diagnosis, evidence, proposal, the fix card, events), with links; "The run does not say" otherwise. Refused for a ticket the person cannot read |
| approve | The fix's card: problem, change, files, checks, site, risk, with **Approve**, **Reject** (the reason box), **Remind me later** |
| reject | A confirmation card; Yes rejects with the reason |
| change_request | A confirmation card; Yes notes the words on the ticket (an HD Ticket Comment, which the worker reads), rejects a pending fix with them (so `fix.guidance` carries them to the next fix job) and asks Copilot for a new fix when the customer's level allows; on a finished run, a follow-up run |
| new_work | The customer from the site cards (buttons when several match); a confirmation card; Yes raises the ticket for the customer's contact (no acknowledgement email: a person replies first), attaches the files and starts Copilot. The diagnosis comes back in the same chat |
| waiting, snooze, help | What waits for the person; snooze an approval's reminders (hours, or until 09:00 Riyadh); what it can do |

Every action runs **as the person** (their permissions), only after **Yes** (a proposal older than 24 hours expires), and is logged in HDS Copilot Call Log with kind `Teams` or `Web`. Approve and Reject call the same `approvals.decide` as the ticket page (`decided_via` Teams or Web). Messages with text that tries to instruct the AI get the warning card first. 30 messages a minute per person.

**In Teams** (`helpdesk.api.copilot_teams.messages`, guest by design): Bot Framework sends its token as `Authorization: Bearer …`, which Frappe takes for its own credentials and refuses before any endpoint runs. So the auth hook `teams.authenticate` checks it first, for a POST to this endpoint only, and lets a valid one through as the bot's own user `teams.bot@tbo-copilot.internal` (a website user without roles, made on migrate); any other Bearer request is left to Frappe as before. The endpoint then checks the Bot Framework token again (signature from the published keys, issuer, audience = our bot's app ID, the service URL), then the tenant. People are **HDS Teams User** rows (Microsoft user ID, email, the agent with that email, their personal chat); the agent is found by the Microsoft email Bot Framework gives, and when it gives none (its member lookup can be refused) or nobody has that email, the bot answers with a **Link my Teams account** card: a one-time link (30 minutes, single use) that the person opens signed in to TBO Support as themselves (`helpdesk.api.copilot_teams.link`), and joins their Teams account with **Link** (`confirm_link`, a POST with their CSRF token). It refuses a non-agent, a Teams account already linked to someone else, an agent already linked to another Teams account, and a Microsoft email that is not the agent's; after linking, the bot sends its help card. Messages are answered in the background; card buttons are Adaptive Card Universal Actions (`Action.Execute`) answered with the updated card. Pictures and files sent to the bot are saved privately on the chat and go to the ticket on new work. Settings: HDS Copilot Settings → **Teams bot** (enabled, app ID, client secret, tenant; blank tenant = HD Settings').

**The fix's card, news and the digest.** When an approval opens (and at every reminder), `approvals.announce` sends the fix's card to the approver: by the bot when it can reach them (then only the panel notice, no second message), else into their panel chat plus the usual chat message or email. **Remind me later** sets `snoozed_until` on the approval: reminders wait, escalation does not. After any decision every copy of the card shows who decided (`refresh_cards`). A run reaching Merged, Resolved, Closed, Escalated or Failed is news for the approver, the ticket's assignees and whoever started it from a chat (`tell_news`). At 09:00 Riyadh time each person with a pending approval or a fix task gets one digest (`send_digest`). With the bot set up, helpdesk reminders (HD Notification) reach people through the bot instead of the Workflows webhook.

**The worker sees the pictures** (W9): `copilot_worker.ticket_file(run, lease_token, file_url)` gives the worker a picture or video of the run's ticket (png, jpg, gif, webp, mp4, webm, mov, mkv; up to 50 MB) while the lease holds (event `file_read`); the worker turns videos into frames. `fix.guidance` carries the reasons earlier fixes of the run were rejected.

**Setting up the bot (TBO's Microsoft 365 admin, once per hub):**
1. Azure portal → create an **Azure Bot**: handle `tbo-copilot`, pricing tier F0, type **Single Tenant**, a new Microsoft App ID.
2. The bot's Configuration → **Messaging endpoint**: `https://<the hub>/api/method/helpdesk.api.copilot_teams.messages`.
3. Channels → **Microsoft Teams** → enable.
4. The bot's app registration (Microsoft Entra) → Certificates & secrets → a new client secret. In TBO Support → HDS Copilot Settings → Teams bot: the App ID, the secret, the tenant ID (if HD Settings has none); enable.
5. As a System Manager, download the Teams app: `/api/method/helpdesk.api.copilot_teams.app_package`. Teams admin center → Teams apps → Manage apps → **Upload new app**; then Setup policies → Installed apps → add **TBO Copilot** for the support staff (so reminders can reach everyone).
6. In Teams, write `help` to TBO Copilot.

**When the bot does not answer.** Anyone who installs or messages the bot appears in **HDS Teams User**, even someone it does not know. If nobody appears, Teams' messages are not reaching the hub, or the hub refuses them. A refused call that carries a Bot Framework token is written to the **Error Log** once an hour per reason, as "Copilot Teams bot refused a call: …", with the bot Teams sent it to next to ours, the tenant it came from next to ours, and what the token says (issuer, audience, service URL), never the token:
- **bad Bot Framework token** with another audience: the Azure Bot's Microsoft App ID is not the App ID in Teams bot settings;
- **another tenant**: the Tenant ID in Teams bot settings is not the Microsoft 365 tenant the message came from;
- **messages arrive, replies fail** (an HDS Teams User appears or `answer_message` fails with "401 Authorization has been denied"): Bot Framework refused the bot's own key. The hub asks for it from the bot's tenant first (a Single Tenant bot) and, when Bot Framework refuses that one, once more from Bot Framework's own tenant (a Multi Tenant bot), and remembers which worked. When both are refused, compare the Azure Bot's Microsoft App Type and App Tenant ID with the Tenant ID in Teams bot settings;
- **could not handle a call**: the endpoint failed on a message from Teams; the Error Log has the traceback. A refusal at sign-in and a failure like this are saved straight away, because Frappe undoes everything else the request wrote;
- **nothing at all**: the Azure Bot's messaging endpoint does not point at the hub, or its Teams channel is off. In the Azure portal, the bot's **Test in Web Chat** shows the hub's answer: *Forbidden* means it reached the hub with the right App ID (Web Chat has no Teams tenant), *Unauthorized* a wrong App ID, a timeout a wrong address. The bot's Channels → Microsoft Teams page lists Teams' own delivery errors.

## MCP server (`helpdesk/api/copilot_mcp.py`, `helpdesk/copilot/mcp/`)

TBO staff use tickets, tasks and the knowledge base from the TBO Copilot desktop app, or any MCP client, **as themselves, with their own permissions** (TASK-2026-00013).

- **Endpoint:** `POST /api/method/helpdesk.api.copilot_mcp.handle`. Streamable HTTP without sessions or event streams: every request is a POST and carries its own credentials; GET and DELETE answer 405. Replies are raw JSON-RPC (`initialize`, `ping`, `tools/list`, `tools/call`, batches; notifications get 202). Protocol versions 2025-11-25, 2025-06-18 and 2025-03-26.
- **Who:** an enabled agent (Agent or Agent Manager role, or an HD Agent) with their own API key, `Authorization: token <key>:<secret>`, which Frappe checks before the endpoint runs. Administrator, non-agents and requests without the header are refused (403, 403, 401). The key is checked on every request.
- **Switch and limit:** HDS Copilot Settings **MCP Server On** and **MCP Calls per Minute** (per person, default 120; over it a call is refused as "Rate limited").
- **Log:** every tool call is an **HDS Copilot Call Log** row (user, kind, tool, status OK / Refused / Error / Limited, time, ticket, task, run, arguments, the start of the result), kept 90 days.
- **Results:** compact JSON as text. Ticket text written by people is wrapped in `<untrusted_ticket_content>`. Conversations keep the last 15 messages (2,500 characters each) and notes (1,500), the description 6,000; anything over 100,000 characters is cut. A refusal (permission, missing record, bad argument, rate limit) is an `isError` result whose first words say why, and is not written to Error Log.

| Read tool | Wraps |
|---|---|
| `my_work` | `helpdesk.api.work.get_my_work` |
| `get_ticket` | `hd_ticket.api.get_one`, `support_hub.get_triage`, `api.ai_suggestion.get_suggestion` |
| `search_tickets` | `api.search.search` for words, `frappe.get_list("HD Ticket")` for status, priority, customer, assigned to me |
| `get_task`, `list_projects`, `list_project_tasks` | `tasky.api.get_task_detail`, `get_projects`, `get_kanban_tasks` |
| `search_knowledge_base`, `get_kb_article` | `api.article.search`, `api.knowledge_base.get_article` |
| `get_fix_brief`, `get_possible_duplicates`, `get_session_replay` | `api.fix_brief`, `api.duplicates`, `api.session_replay` |
| `get_calendar`, `get_copilot_run` | `api.calendar.get_calendar`, `api.copilot.get_run` |

Ticket numbers may be written as people write them (`236`, `#236`, `HD-0236`).

**TBO Copilot desktop:** Settings → MCP → Add → HTTP endpoint, the URL above and the header `Authorization: token <key>:<secret>`, then Test connection. The tools appear as `mcp_<server id>_<tool>`; the app asks before each call in Ask mode and hides MCP tools in Plan and Goal mode. The header is stored in plain text in `~/.agents/servers/<id>.json`, so use your own key, never an admin's.

| Write tool | What it does (never sends anything to a customer) |
|---|---|
| `add_ticket_comment` | An internal note as the person, with the comment box's guard (ticket read + agent). Text is shown as text, never run as HTML |
| `draft_ticket_reply` | Saves the text in the ticket's suggested-reply card for the person to edit and send, with Regenerate's guard (ticket write, open ticket) |
| `update_task_status` | Open, Working, Cancelled through the task board's API; On Hold needs one of the task's hold reasons; Completed needs the hours worked (it may become Pending Review); a held task is resumed first |
| `create_kb_article_draft` | A Draft HD Article in General as the person (their own create permission), Markdown content, optionally linked to a ticket they can read; never published |

**The worker's run token.** `claim_job` returns a lease token and records the claiming user as the run's `worker_user`. The run's agent sends `X-Copilot-Run-Token: <run>:<lease token>` (and no Authorization header, which Frappe would check as a key). The request then runs as that worker user, sees only the worker tools, and is scoped to that run; the token stops working when the lease ends (a result, a cancel, an expiry). The agent never holds the worker user's API key.

| Worker tool | Does |
|---|---|
| `get_run_context` | The run's context (as `claim_job` gives it) |
| `post_event` | An event for the run; a repeated `seq` is ignored |
| `submit_investigation` | The root cause, confidence, evidence, proposal; routed as `submit_result` does, and the lease ends |
| `customer_erp_read` | One read tool on the ticket's customer site through the hub (`MCPClient`, logged in HDS Remote Audit Log too): `get_doc`, `get_list`, `get_count`, `get_meta`, `get_error_log`, `execute_report`, `get_installed_apps`, `get_site_info`, `get_code_identity`, `get_customizations`, `get_deploy_status`, `get_version_history`. Never a write tool; results over 64,000 characters are cut |

**Permission fixes in the support hub API.** `get_connections` lists all connections only to managers (Administrator, System Manager, Agent Manager); other agents see the connections of customers whose tickets they can read. `get_session_detail` needs read access to the session's ticket. `start_investigation` needs read access to the ticket, and an agent may only investigate the ticket's own customer site (managers may choose another).
