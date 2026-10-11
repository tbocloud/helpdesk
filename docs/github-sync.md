# GitHub sync

GitHub talks to TBO Support through one webhook,
`https://<hub>/api/method/helpdesk.api.github.webhook` (`helpdesk/api/github.py`). Settings
live in **HD GitHub Settings**, edited in the helpdesk at **Settings → Integrations → GitHub**
(see [The settings page](#the-settings-page) below).

Every delivery is checked against the webhook secret (HMAC SHA-256 over the raw body) and
refused while the sync is off. It's then logged once per `X-GitHub-Delivery` in **HD GitHub
Delivery**, and the log is cleared daily by `clear_old_deliveries`. After that, two
independent things happen:

1. **Task sync** (`helpdesk/github_sync.py`). Pull requests, reviews and workflow runs from
   the allowed repositories move the tasks they name. The module docstring describes the
   rules. Other events, and other repositories, are logged as Ignored.
2. **Merge bot trigger** (`helpdesk/merge_bot.py`), described below.

## Merge bot trigger

The org-wide merge bot, `tbocloud/ai-review` → `.github/workflows/merge-bot.yml`, merges
every open PR in tbocloud and teambackoffice that CodeRabbit approved and whose checks are
green. GitHub doesn't reliably fire its `schedule`, so the hub asks GitHub to run it. The hub
only asks: every merge rule stays in the bot.

**When the hub asks.** The trigger is off by default ("Trigger the org merge bot"). When it's
on, the hub asks in these cases:

- **Approval:** a `pull_request_review` arrives with action `submitted`, state `approved`,
  by `coderabbitai[bot]`.
- **Green CI:** a `workflow_run` or `check_suite` arrives with action `completed`,
  conclusion `success`, on a commit with a PR (non-empty `pull_requests`). Runs without a
  PR, such as pushes to main and the bot's own `workflow_dispatch` runs, are skipped, and so
  is anything from the merge bot repository. Otherwise a finished bot run would ask for the
  next one.
- **Fallback:** the scheduler job `helpdesk.merge_bot.scheduled_run`, every 10 minutes at
  :02, :12 and so on (cron `2-59/10 * * * *`). It catches events the webhook never got,
  e.g. CI for PRs from forks.

The trigger is checked for every signed delivery, whatever the allowed-repositories list
says, since that list only limits the task sync.

**Debounce and rate limit.** A request takes a Redis key with `SET NX EX 120`
(`helpdesk:merge_bot_dispatch`). Only the request that takes the key queues the dispatch,
so any number of events and scheduler ticks within 2 minutes cause one dispatch.

- A green-CI event that arrives inside the window of an earlier dispatch is picked up by the
  next scheduler run, at most 10 minutes later.
- The workflow's `concurrency: merge-bot` group keeps a single run going.

**The dispatch.** The background job `helpdesk.merge_bot.dispatch` sends
`POST https://api.github.com/repos/<repo>/actions/workflows/<workflow>/dispatches` with
`{"ref": "main", "inputs": {"dry_run": "false"}}`.

- `dry_run` is sent as a string, the way `gh workflow run -f` sends it; GitHub reads it into
  the boolean input. It must be sent, because the workflow defaults `dry_run` to true.
- The token is "Merge bot token" if set, else "GitHub Token".
- The outcome, `Dispatched (HTTP 204)` or `Failed (HTTP 403)` for example, and its time are
  stored on the settings ("Last run requested", "Last result"). Failures also go to the
  Error Log. The token is never logged.
- Nothing in the trigger can fail a webhook response: errors are caught and logged.

**Settings** (Settings → GitHub → Org merge bot):

| Field | Default | Notes |
| --- | --- | --- |
| Trigger the org merge bot | off | Nothing is requested while off. |
| Merge bot repository | `tbocloud/ai-review` | `owner/repo`. |
| Merge bot workflow | `merge-bot.yml` | The workflow file name. |
| Merge bot token | empty | Optional; falls back to GitHub Token. |

The validation fills an empty repository or workflow with its default. A Single's JSON
defaults only reach new sites, so this is how an existing hub gets them. Both values go into
the dispatch URL, so they must look like `owner/repo` and `name.yml`.

### Owner steps

1. **Org-level webhooks.** The hub only hears from repositories where the webhook is
   configured. To cover every repository, add it at organization level in **both** tbocloud
   and teambackoffice (Organization → Settings → Webhooks → Add webhook):
   - Payload URL: `https://<hub>/api/method/helpdesk.api.github.webhook` (the page shows
     it for this site, with Copy)
   - Content type: `application/json`
   - Secret: the same value as Settings → GitHub → Webhook Secret
   - Events: Pull requests, Pull request reviews, Check suites, Workflow runs

   If a repository already has its own webhook to the hub, remove it once the org webhook
   is in place, or each event arrives twice. A second copy of an event does no harm,
   because of the debounce and the task sync's checks, but it doubles the delivery log.
   teambackoffice repositories are only used by the merge bot trigger; their deliveries are
   logged as Ignored unless `teambackoffice/*` is added to Allowed Repositories.
2. **Token.** Create a fine-grained personal access token whose resource owner is tbocloud,
   limited to the `ai-review` repository, with the single permission **Actions: Read and
   write**. Paste it into "Merge bot token", save, and use **Test merge bot token**. Without
   it, the GitHub Token is used, and that token then needs the same permission on
   `ai-review`.
3. **Switch on.** With "Enabled" already on (the webhook refuses everything while the sync
   is off), turn on "Trigger the org merge bot", save, and use **Request a merge bot run
   now**. A `Failed (HTTP 403)` or `404` means the token can't dispatch on that repository.

## The settings page

Settings → Integrations → GitHub (`desk/src/components/Settings/GitHub/GitHubSettings.vue`),
backed by `helpdesk.api.github_settings`.

**Who.** System Managers and Agent Managers, the same as Chat & Teams: the API checks the
roles itself (`is_tasky_admin`) and saves with `ignore_permissions`, while the doctype stays
writable by System Managers only. Agent Managers run the team's GitHub flow (tasks, reviews,
the merge bot), and they can replace or remove the tokens but never read them back.

**Sections.**
- **Header:** Enabled and Save changes.
- **Webhook:** the Payload URL for this site (`frappe.utils.get_url`) with Copy, the content
  type and the four events, and Webhook Secret.
- **Task sync:** Allowed Repositories, Complete the task when a closing PR is merged,
  Project for PRs without a task, and GitHub Token with **Test GitHub token**.
- **Org merge bot:** the trigger switch, repository, workflow, Merge bot token with **Test
  merge bot token**, Last run requested and Last result (green with a check when GitHub
  accepted it, red with an alert otherwise), and **Request a merge bot run now**. The colour
  comes from the hidden "Last outcome" (`Dispatched` or `Failed`), which `merge_bot.record`
  stores next to the result because the result itself is translated; a result recorded
  before that field existed stays neutral.
- **Last webhook delivery:** time, event and action, repository and status of the newest HD
  GitHub Delivery (never its payload or error text).
- **Setting up GitHub:** the organization webhook and the fine-grained token, step by step.

**Secrets** (Webhook Secret, GitHub Token, Merge bot token) work as on Chat & Teams, with the
same `SecretField`: `get_settings` returns `secrets[field] = {set, masked}`, the mask being
the token's kind (`ghp_…`, `github_pat_…`) or `…`, never any of the key. `save_settings`
keeps a secret whose key isn't sent, stores a sent value trimmed and removes it for "".
`HDGitHubSettings.validate` refuses Enabled without a Webhook Secret (the form's
`mandatory_depends_on` isn't checked on the server) and starts each message with the field's
label, so the page shows it under that field as well as in a toast.

**Test a token** (`test_token(field)`, POST): uses the saved token, so it waits for unsaved
changes. It calls `GET /user` and returns the account, a classic token's scopes
(`X-OAuth-Scopes`) and the expiry when GitHub sends it; fine-grained tokens don't list their
permissions. The token the dispatch uses (the merge bot token, or the GitHub Token when there
is none) is also checked with `GET /repos/<merge bot repository>`. Hints: 401 means mistyped,
expired or revoked; 403 on `/user` means SSO authorisation or the rate limit; 403 or 404 on
the repository means the token can't see it. A network error shows only its kind.

**Request a run now** (`request_merge_bot_run`, POST): needs the trigger on and saved, takes
the same debounce as the events (`merge_bot.take_debounce`; within 2 minutes of the last
request nothing is sent and the page says so), then runs `merge_bot.dispatch` in the request
and shows its result, which is also stored as Last result.

Tests: `helpdesk/tests/test_github_settings.py`.
