# AI models (Phase 31)

**AI models** (`/helpdesk/ai-models`, menu item "AI models") shows how each AI model does in
TBO Support and in the Copilot worker. It has three views: **Models** side by side, **One model**
(performance, errors, quality, benchmarks) and **Model settings** (which model each job uses).
Agent Managers and System Managers can read it. Only System Managers can change anything. No view
and no record shows a prompt or a customer's text.

Code: `helpdesk/ai_models.py`, `helpdesk/ai_gateway.py`, `helpdesk/api/ai_models.py`, and
`desk/src/pages/ai-models/`. Tests: `helpdesk/tests/test_ai_models.py`. Plan:
`design/phases/phase-31.md`. Providers, failover and models per job are described in
[ai-providers.md](ai-providers.md).

## What is recorded

**HDS AI Usage Log** now writes one row for every attempt, failed attempts included:

| Field | Meaning |
|---|---|
| `status` | Success or Failed |
| `duration_ms` | timed with `perf_counter` |
| `source` | TBO Support, or Copilot worker |
| `error_class` | `rate_limit`, `timeout`, `server`, `billing`, `auth`, `config` or `bad_answer` |
| `error_message` | the HTTP status and the provider's clipped message, with any key masked |

Rows written before the deploy have only the cost. The pages show this as "recorded since".

## Status of a model

- **Paused:** its circuit is open after a key, billing or model failure.
- **Degraded:** 5% or more of its calls failed, with at least 20 calls in the period.
- **Not used:** it has no calls in the period.
- **Candidate:** it is allowed for jobs, has no calls, and no job uses it.
- **Healthy:** none of the above.

## Model settings

Three parts, top to bottom. Only System Managers change them.

**1. Providers and keys**
- Today's two sections, OpenAI and Anthropic-compatible, stay in HDS Hub Settings and show as
  the first two rows. Editing one here goes through `api.ai_settings.save_settings`.
- **HDS AI Provider** adds provider accounts: name, API style, address (https), encrypted key,
  on/off, and whether the provider supports JSON mode and a token budget.
  - API styles: OpenAI, OpenAI-compatible, Anthropic or Anthropic-compatible.
  - Presets fill in DeepSeek (`https://api.deepseek.com`), Qwen
    (`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`; keys work only in their own
    region), Claude (the SDK's address) and GPT.
  - A provider may not take a section's name.
- **Keys:** a key is sent only to replace the saved one. The page and the API return only
  whether one is saved.
- **Test:** one tiny call with the provider's first model (`ai_models.test_provider`).

**2. The model list** (HDS Model Pricing)
- Each model in the list has:
  - `ai_provider`: a section or a provider account;
  - `listed`: allowed for jobs;
  - `monthly_token_limit`: in millions, 0 means none;
  - its prices.
- **This month's use** (`ai_engine.month_tokens`) is the input plus output tokens in the usage
  log since the 1st, TBO Support's calls and the worker's. It is cached for 5 minutes.
- **Allowed models:** a model a job uses can't be unticked or removed.
- **Removing:** a model that was never called and has no test-set run is deleted. Otherwise it
  only leaves the list, and its prices stay for the cost reports.
- **Candidate:** a listed model that no job uses.
- **Patch:** `v16_0_3.ai_model_list_from_sections` starts the list with the models today's
  sections use, allowed and called through their section.

**3. Model and backup per job** (HDS AI Job `model`, `backup_model`)
- **With a model set,** `ai_engine.job_chain` calls the model and then the backup, each through
  its provider (`model_provider`, `account_provider`). A model whose provider is off or has no
  key is skipped.
- **With both empty,** the job follows the sections as before: `primary_section`,
  `allow_fallback`, and a model per section.
- **When the backup answers:** only for the failures that fail over today (balance, key, model
  missing, rate limit, server error, timeout).
- **A used-up monthly limit:** a model past its limit is never called
  (`ai_engine.within_limits`). When it is the job's first model, the job stops with a clear
  message and the backup is not used, so the limit really caps spending.
- **Saving:** the backup needs a model and must be another model. Clearing the model clears the
  backup too. The older Settings → AI providers page keeps both (`ai_settings.JOB_CHOICES`).
- **The worker:** `worker_models()` sends the worker each job's providers by name and model,
  never a key. The worker uses only the providers it holds its own key for:
  - `TBO_PROVIDER_DEEPSEEK_API_KEY`, `_QWEN_`, `_CLAUDE_` and `_GPT_` (tbo-worker `config.ts`),
    so DevOps adds the same providers' keys there;
  - a model whose provider the worker has no key for goes to the backup.

**Also on this view**
- **Try:** one tiny call with the job's first model.
- **Change history:** HDS Model Change records the job, the setting, the old and new values, and
  who changed it.
- **Guard** (`ai_models.guard`): only for `investigate`, `fix` and `review`. If the job's new
  first model has no test-set score, or a lower one than the current model, the page asks before
  saving.

## Quality signals

| Signal | Where it comes from |
|---|---|
| Fixes approved, root cause rated right or wrong, explanation edited | HDS Copilot Run and HDS Copilot Approval |
| Customer said it is still broken | the run's ticket: `custom_customer_confirmation` Reopened ÷ (Confirmed + Reopened) |
| Chat answered, handed over, unsupported answer, safety cut, broken format | HDS AI Quality Event, from `copilot/conversation.py` |
| Missing references | the worker checks the files, lines and doctypes a report cites (`references` in `submit_investigation`); the result lands on HDS Copilot Run, plus one event per missing item |
| Draft replies | see below |

**Draft replies**
1. When an agent asks for an AI draft (`api/ticket_ai.draft_reply`), `ai_models.note_draft` keeps
   the draft as checksums of its three-word runs, for 24 hours, under the ticket and the agent. It
   also records "Draft made". A redraft while one is waiting counts as the same draft.
2. When that agent's reply is sent (`ai_models.on_communication_insert`, Communication
   `after_insert`), the reply is compared with the draft:

   | Share of the draft in the reply | Recorded as |
   |---|---|
   | 90% or more | Draft used |
   | 40% to 89% | Draft changed |
   | less than 40% | not sent |

   The comparison never blocks the reply.

`record_event` never raises. Its `detail` is a short code or a file or field name, never a
customer's text.

## Benchmarks

HDS Model Eval Run and HDS Model Eval Result keep each run of the private test set as scores per
case number only. `store_eval` drops the case text, the ticket, the expected answer and Copilot's
summary.

**How scores arrive**
- **The worker:** `eval --cases FILE --to-hub [--request NAME]` sends them to
  `api.copilot_worker.report_eval`. The command also writes `<report>.scores.json` beside its
  report.
- **Bring in a report** (System Managers): the page reads that scores file, or the full report
  `.json`, in the browser. It sends only the case number, right, confidence, the number of files
  found, tokens, cost, minutes and outcome to `api.ai_models.import_eval`.

**Requests** (HDS Model Eval Request)
- **Ask for a run** records a request. A model can have only one open request.
- A report that arrives for the model answers its open requests (`close_requests`).
- **Take back** deletes a request that hasn't been answered.
- The live worker doesn't run the test set by itself, because the cases' tickets exist only on
  the test hub.

**Public benchmarks** (HDS Public Benchmark) are dated entries with a source link, shown for
reference only.

## Alerts

`ai_models.watch` runs every hour at :20 (`hooks.py`) and reads the last 60 minutes of the usage
log:

| Alert | When |
|---|---|
| A model is failing | a model with 10 or more calls has an error rate at or above `model_alert_error_rate` (default 20) |
| The fallback is answering | of 10 or more answered calls, the share answered by the fallback is at or above `model_alert_fallback_rate` (default 30) |
| A monthly limit | a model reaches 80%, and then 100%, of its monthly token limit (each once a month) |

- **Off:** a limit of 0 turns that alert off.
- **Repeats:** each model alerts at most once in 6 hours (cache key `ai_models:alerted:*`).
- **Who is told:** the System and Agent Managers, in the app and in the team's chat. The link
  goes to `/ai-models`.
- **Patch:** `helpdesk.patches.v16_0_3.model_alert_limits` sets the two defaults on sites that
  already have hub settings.

## The AI gateway (desktop app)

`ai_gateway.sync` runs every hour at :20 when switched on. It reads the gateway's
`/spend/logs/v2` with a read-only key and keeps totals per day, model and person in HDS Gateway
Usage Day.

The desktop app sees only TBO's names for its models, for example `tbo-default` for GPT-5.6
Luna and `tbo-deepseek` for DeepSeek V3.2 on AWS Bedrock (the gateway's `litellm-config.yaml`).
TBO Support keeps the real model (`model`, without the provider's prefix) and puts the gateway's
name beside it (`gateway_alias`, `gateway_provider`). So the desktop app's calls add up with TBO
Support's own calls to the same model, and the pages say "Desktop app calls it tbo-default".
Which real model is behind each name is still set in the gateway's own settings.

**Settings:** `gateway_url` (must be https), `gateway_viewer_key` and `gateway_sync`. A failed read
is noted on the settings and never raised.

## Known limits

- The gateway's field names come from the LiteLLM documentation. They have not yet been checked
  against our gateway.
- A draft counts only when the same agent sends the reply on the same ticket within 24 hours.
  The comparison uses word runs, not a full diff.
- Speed and errors exist only from the deploy day.
