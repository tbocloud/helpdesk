# GitHub sync

GitHub talks to TBO Support through one webhook,
`https://<hub>/api/method/helpdesk.api.github.webhook` (`helpdesk/api/github.py`). Settings
live in **HD GitHub Settings**. It has no helpdesk settings page yet, so a System Manager
edits it in the desk form (known debt).

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

**Settings** (HD GitHub Settings → Org merge bot):

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
   - Payload URL: `https://<hub>/api/method/helpdesk.api.github.webhook`
   - Content type: `application/json`
   - Secret: the same value as HD GitHub Settings → Webhook Secret
   - Events: Pull requests, Pull request reviews, Check suites, Workflow runs

   If a repository already has its own webhook to the hub, remove it once the org webhook
   is in place, or each event arrives twice. A second copy of an event does no harm,
   because of the debounce and the task sync's checks, but it doubles the delivery log.
   teambackoffice repositories are only used by the merge bot trigger; their deliveries are
   logged as Ignored unless `teambackoffice/*` is added to Allowed Repositories.
2. **Token.** Create a fine-grained personal access token whose resource owner is tbocloud,
   limited to the `ai-review` repository, with the single permission **Actions: Read and
   write**. Paste it into "Merge bot token". Without it, the GitHub Token is used, and that
   token then needs the same permission on `ai-review`.
3. **Switch on.** With "Enabled" already on (the webhook refuses everything while the sync
   is off), tick "Trigger the org merge bot" and save. Check "Last result" after the
   next approval or within 10 minutes. A `Failed (HTTP 403)` or `404` means the token can't
   dispatch on that repository.
