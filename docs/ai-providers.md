# AI providers and failover

Every cheap, always-on AI call in the hub goes through `helpdesk.ai_engine.call_haiku`:
triage, the Home action plan, reply suggestions and drafts, KB drafts, AI task descriptions
and estimates, repeat-issue titles, the team dashboard analysis, team insights, work
summaries, content topics and captions, and the TBO Chat bridge. This page describes how
that call picks a provider, fails over and recovers.

Code: `helpdesk/ai_engine.py` (providers, failover, status), `helpdesk/api/ai_settings.py`
(the settings page), `desk/src/components/Settings/AI/AIProviderSettings.vue`,
`desk/src/components/AIProviderBanner.vue`. Tests: `helpdesk/tests/test_ai_engine.py`,
`helpdesk/tests/test_ai_settings.py`.

## Why

From 2026-10-12 15:49 every AI call failed with HTTP 429: the Anthropic-compatible
provider account (Kimi) was suspended for insufficient balance. Triage, the action plan,
task descriptions, repeat-issue titles, KB drafts and reply suggestions all stopped, and
nobody was told. The owner chose OpenAI as the main provider, with the old one kept as a
fallback.

## Providers

HDS Hub Settings has two provider sections. Each needs an API key and a model; a section
without both is left out.

| Section | Fields | API |
| --- | --- | --- |
| **OpenAI** | `openai_base_url` (default `https://api.openai.com/v1`), `openai_api_key`, `openai_model` (default `gpt-5.6-luna`) | Chat Completions, `Authorization: Bearer` |
| **Anthropic-compatible** | `ai_base_url` (empty: Anthropic), `anthropic_api_key`, `default_triage_model`, `ai_provider` | Messages API through the `anthropic` SDK (Kimi/Moonshot, GLM, Anthropic) |

- **Model is free text.** The OpenAI model's only default is the doctype default
  (`gpt-5.6-luna`, the owner's choice). It could not be checked against OpenAI offline, so
  the page says it must match the model ID in the OpenAI dashboard exactly, and Test
  connection proves it. It is not hard-coded anywhere else.
- **`ai_provider`** (Anthropic / Anthropic Compatible / OpenAI Compatible) is the existing
  field. The page sets it from the base URL (empty → Anthropic, set → Anthropic
  Compatible). An older `OpenAI Compatible` value is kept as it is and still speaks Chat
  Completions, but new OpenAI-compatible endpoints belong in the OpenAI section.
- `primary_ai_provider` (OpenAI or Anthropic-compatible) is tried first; with
  `ai_failover` on (default), the other section is tried next.
- **Keys** live only in HDS Hub Settings Password fields, encrypted. They never reach the
  browser, logs, errors or alerts: provider error text is passed through `redact`, which
  removes the key and anything shaped like `sk-…` (OpenAI's 401 echoes part of the key).
  `frappe.conf.anthropic_api_key` still works as the Anthropic-compatible key.
- Investigation sessions (`session_manager`, tool use) are unchanged: they always use the
  Anthropic SDK with `investigation_provider` or the Anthropic-compatible section.

### Request mapping

| | OpenAI | Anthropic-compatible |
| --- | --- | --- |
| System prompt | `messages[0]`, role `system` | `system` block with `cache_control: ephemeral` |
| Token budget | `max_completion_tokens` (reasoning models count thinking in it) | `max_tokens` |
| JSON | `response_format: {"type": "json_object"}` when the system prompt mentions JSON (all current callers do; OpenAI requires the word) | prompt only; `parse_json_answer` reads fences and prose |
| Temperature | never sent: newer OpenAI models refuse anything but the default | not sent |
| Timeout | 120 s per attempt (`REQUEST_TIMEOUT`) | 120 s per attempt; the SDK's own retries are off (`SDK_MAX_RETRIES = 0`): failover replaces them |

One `call_haiku` has 240 seconds in all (`CALL_SECONDS`), both providers included: each
attempt gets the smaller of 120 seconds and the time left, and none starts with under 5
seconds left. That keeps the whole failover inside triage's 300-second job timeout, so a
killed job never hides it.

Both get the thinking-model budget retry: 4096 tokens, then 8192 once when the first answer
ran out of tokens with no text (`finish_reason: length` / `stop_reason: max_tokens`). A legacy
`OpenAI Compatible` endpoint gets neither the budget nor JSON mode, since such servers may
not know them. Chat Completions was chosen over the Responses API because it is what
OpenAI-compatible servers implement too, and the hub already spoke it; there is no `openai`
SDK dependency (`requests` only).

## Failover

`call_haiku` tries the providers in order and skips a paused one. Each failure is an
`AIProviderError` with a `kind`:

| HTTP / error | Kind | Fail over | Pause 30 min | Alert and "failing" status |
| --- | --- | --- | --- | --- |
| 402; 400, 403 or 429 whose message says balance, quota, billing, credit, payment, insufficient or suspended (Anthropic sends "credit balance is too low" as a 400) | `billing` | yes | yes | yes |
| 401, 403 | `auth` | yes | yes | yes |
| 404; 400 saying the model doesn't exist | `config` | yes | yes | yes |
| other 429 | `rate_limit` | yes | no | no (passes in seconds) |
| 5xx; a 200 whose body has no `choices[0].message` or isn't JSON | `server` | yes | no | yes |
| 408, 504, connection error, timeout | `timeout` | yes | no | yes |
| other 4xx (400 validation) | `invalid` | **no**: raised and logged ("AI request rejected by …") | no | no |

A wrong model id is treated as a configuration failure, not a validation error, so a
mistyped OpenAI model fails over to the other provider and tells the managers.

- **Circuit breaker:** `ai_engine:circuit:<section>` in `frappe.cache`, 30 minutes
  (`CIRCUIT_SECONDS`). While it is set the section is skipped. If every provider is paused,
  `call_haiku` raises at once (kind `paused`) instead of calling them.
- **Status:** `ai_engine:down:<section>` = `{kind, reason, since, model}` for 24 hours or
  until that section answers again.
- **Alert:** on a section's first failure, one notification to the enabled System and
  Agent Managers (`github_sync.admin_users`) through `notify_users(..., escalate=True)`, so
  it also reaches the team's Teams/Slack channel. Deduplicated for 6 hours per section with
  an atomic `SET NX` on `ai_engine:alerted:<section>` (a Redis flush can at worst repeat
  one alert). Sent from a background job, so a request that rolls back after the failure
  doesn't lose it. Text, e.g. "AI provider Anthropic-compatible (kimi-k2.6) failing since
  12 Oct, 15:49: insufficient balance or quota. Using OpenAI (gpt-5.6-luna)." or, with no
  fallback, "… No other provider is set up, so AI features are paused until it's fixed in
  Settings → AI providers." The time keeps each incident's text unique, since chat posts
  are sent once per text. It links to Home.
- Callers call `call_haiku(system_prompt, user_message, ticket_name=None, job=None)` and get
  `{response, usage, cost}`; each names its job (below). Triage catches `AIProviderError`
  (it used to catch the SDK's `anthropic.APIError`) and marks the ticket Failed.

## Models per job

A job can use its own model in each section; the order, the failover, the pauses and the
alerts stay as above. **HDS Hub Settings → Models per job** (child table `HDS AI Job`: job,
OpenAI model, Anthropic-compatible model; one row per job, both models optional) and the
same list on Settings → AI providers. A blank model, or no row, is the section's own model,
so with an empty table every job runs as before. A change applies from the job's next call.

| Job | Who calls it |
|---|---|
| `triage` | `triage.py`, `api/ticket_ai.py`, the Chatwoot chat answer |
| `draft` | `ai_suggestion.py`, `kb_drafts.py`, `content_topics.py`, `api/content.py` |
| `summary` | `work_summary.py`, `team_dashboard.py`, `team_insights.py`, `home_plan.py`, `repeat_issues.py`, `standup.py`, the Chatwoot transcript summary |
| `task` | `task_descriptions.py`, `task_estimates.py` |
| `chat` | the staff assistant (Teams and the Copilot panel) and the customer chat (the ERP chat and TBO Chat's bot) |
| `investigate`, `fix`, `review` | the TBO Copilot worker (below) |

- `get_providers(job)` gives each section with the job's model. A provider with its own
  model has `override` set, and its pause, failure and alert keys are `<section>|<model>`
  (`AIProvider.key`), so a mistyped job model pauses only that job, not its section.
- `HDSHubSettings.validate` refuses a second row for the same job (`check_job_rows`).
- **The worker's jobs:** `run_context.models` (`ai_engine.worker_models()`) lists, for
  `investigate`, `fix` and `review`, each set-up section in the hub's order with the job's
  model and its HDS Model Pricing prices per million tokens. It never holds a key: the worker
  keeps its own addresses and keys and uses only the sections it has a key for.

## Recovery

- When every provider fails, `ai_engine:outage` is set. The next successful call clears it
  and queues `helpdesk.tasks.retry_pending_triages` (job id `ai-retry-pending-triages`,
  deduplicated).
- A successful **Test connection** also unpauses that section and queues the same job, so
  tickets whose triage failed before this feature (nine on the hub on 2026-10-14) are
  re-run as soon as the owner adds and tests the OpenAI key.
- `retry_pending_triages` (also daily) re-queues up to 20 open tickets with triage
  Pending or Failed through `run_triage_now(ignore_cooldown=True)`: the 30-second cooldown
  is for people clicking Re-run (a triage that failed seconds before the recovery must run
  too), while the limit of 2 retries per ticket still holds.
- Saving the settings forgets every pause and failure (`reset_provider_state`), so a fixed
  key or model is tried at once.
- The Home action plan and repeat-issue titles keep their own 15-minute back-off after a
  failure; they recover on their own.

## Settings → AI providers

In the helpdesk app (Integrations group), for System Managers and Agent Managers.
`helpdesk.api.ai_settings` checks the roles (`is_tasky_admin`) and saves HDS Hub Settings
with `ignore_permissions`; the doctype stays writable by System Managers only.

- **Banner** (`AIProviderBanner`): the primary is failing (warning when the other one
  answers, danger when none can, with the provider's reason and since when), or the primary
  isn't set up yet (info).
- **Order:** Primary provider (select) and Fall back to the other provider (switch).
- **OpenAI** and **Anthropic-compatible** sections: badges (Primary / Fallback / Not used,
  and Answering, Failing, Paused or Not set up), Model, Base URL, API key
  (`SecretField`: masked `sk-proj-…` / `sk-…`, Replace, Remove) and **Test connection**
  (`SettingsAction`, uses the saved settings so it waits for Save).
- `get_settings` returns `{settings, secrets: {field: {set, masked}}, status}`.
  `save_settings(values)` keeps a key that isn't sent, stores a sent one trimmed and
  removes it for "". `HDSHubSettings.validate` refuses a base URL that isn't `https://`
  (the message starts with the field label, so it shows under the field).
- `test_connection(provider)` (POST): one call with a 64-token budget ("Reply with the
  single word OK."), returns `{ok, message, details: Model, Endpoint, Time}` or the
  provider's own error with its HTTP status, never the key.

## Home

For admins, `helpdesk.api.home._systems().ai.providers` is `provider_status()`. Home shows
the same banner under the follow-up strip while the primary fails, with **Open AI
providers**. The Systems card's AI triage row names the provider that answers now.

## Usage log and pricing

- **HDS AI Usage Log** has `provider` (the section; investigation calls log
  Anthropic-compatible) next to `model`, for every attempt, plus `job`, `fallback` (the
  answer came from a section other than the first) and `copilot_run`.
- **The worker's spend:** `submit_investigation` and `submit_change` carry the run's `cost`
  with a `stages` list (one entry per job and model: tokens, cached tokens, dollars, section,
  fallback). `log_worker_usage` turns each entry into a usage row with the run and its
  ticket, keyed by `stage_key` (`<run>:<job>:<attempt>`, plus `:fallback`), so a report sent
  again adds nothing. A ticket's hub and worker AI cost are then in the same log.
- **HDS Model Pricing** `provider` options: Anthropic, Anthropic-compatible, OpenAI.
  `ensure_model_pricing` adds a row priced 0 with a TODO note for a newly configured OpenAI
  model (on save and in the patch), so cost reports list it at $0 until a System Manager
  enters OpenAI's price. The weekly `sync_model_pricing` reminder flags it because it was
  never reviewed.

## Patch

`helpdesk.patches.v16_0_2.set_ai_provider_defaults`: a Single's defaults only reach new
sites, so it fills `primary_ai_provider` (OpenAI), `ai_failover` (on), `openai_base_url` and
`openai_model` from the doctype defaults where never saved, and adds the pricing row. It
never touches a key: until the OpenAI key is entered, the OpenAI section is left out and
the Anthropic-compatible provider keeps answering as before.

## After deploy (owner)

1. Settings → Integrations → **AI providers**.
2. OpenAI: check **Model** is the exact model ID from the OpenAI dashboard, paste the
   **API key** (Replace), leave **Base URL** as `https://api.openai.com/v1`. Save changes.
3. **Test connection** under the OpenAI key. OK re-runs the failed triages.
4. Primary provider OpenAI and Fall back on are the defaults. Top up Kimi (or remove its
   key) when convenient; until then it is the paused fallback.
5. Enter OpenAI's price for the model in HDS Model Pricing.
6. Optional: a job that needs another model gets a row under **Models per job**; its
   OpenAI model gets a pricing row priced 0 to fill in, as in step 5.

## Known limits

- Investigation sessions have no OpenAI path: their tool-use loop is Anthropic-shaped.
- No streaming, and no OpenAI prompt-cache accounting (OpenAI caches automatically; its
  cached tokens are billed inside `prompt_tokens`).
- The circuit, status and alert keys live in Redis: a cache flush forgets a pause (the
  provider is simply tried again) and may repeat one alert.
