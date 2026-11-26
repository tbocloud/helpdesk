# AI models (Phase 31)

**AI models** (`/helpdesk/ai-models`, menu item "AI models") shows how each AI model does in
TBO Support and in the Copilot worker. It has three views: **Models** side by side, **One model**
(performance, errors, quality, benchmarks) and **Model settings** (which model each job uses).
Agent Managers and System Managers can read it. Only System Managers can change anything. No view
and no record shows a prompt or a customer's text.

Code: `helpdesk/ai_models.py`, `helpdesk/ai_gateway.py`, `helpdesk/api/ai_models.py`, and
`desk/src/pages/ai-models/`. Tests: `helpdesk/tests/test_ai_models.py`, `test_ai_review_engine.py` and
`test_ai_review_models.py`. (The plan is in TBO Copilot's
private design notes, Phase 31.) Providers, failover and models per job are described in
[ai-providers.md](ai-providers.md).

## What is recorded

**HDS AI Usage Log** now writes one row for every attempt, failed attempts included. A failed attempt's row is
written by a background job of its own (the `short` queue), so it stays even when the request that made the call
fails and rolls back:

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

Three numbered parts, top to bottom. Only System Managers change them.

**Applications and purposes** (`ai_engine.APPLICATIONS`): every application that uses AI, with its purposes.
Each purpose gets a model and a backup. A new application or purpose is one entry there; it then shows on the page.

| Application | Purposes | Without a model of its own |
|---|---|---|
| TBO Support | triage, draft, summary, task, chat | follows the sections, as before |
| Copilot worker | investigate, fix, review | follows the sections, as before |
| Desktop app | `desktop_simple`, `desktop_medium`, `desktop_hard`, `desktop_very_hard` (Simple … Very hard) | nothing: the gateway's own models answer (`OWN_MODEL_JOBS`) |
| Inbox | `inbox_reply`, `inbox_purpose`, `inbox_voice`, `inbox_files` | waits for phases 32–35 (`COMING_JOBS`); no model can be chosen yet |

- **Desktop levels:** a level takes only a model and a backup; the section settings don't apply to it. The desktop
  app follows its level only once the gateway connection is built (plan addendum 31.9, step 2, with DevOps):
  1. TBO Support writes each level to the gateway as `tbo-simple` … `tbo-very-hard`;
  2. each person's key allows them;
  3. the app shows them in its model picker.

  Until then the gateway's own models answer.
- **The older Settings → AI providers page** keeps the desktop levels when it saves.

**1. Providers and keys**
- Today's two sections, OpenAI and Anthropic-compatible, stay in HDS Hub Settings and show as
  the first two rows. Editing one here goes through `api.ai_settings.save_settings`.
- **HDS AI Provider** adds provider accounts: name, API style, address (https), encrypted key,
  on/off, whether the provider supports JSON mode and a token budget, and a note shown under its
  name, for example where its data goes. An account can be switched on or off in its row.
  - API styles: OpenAI, OpenAI-compatible, Anthropic or Anthropic-compatible.
  - Presets fill in the address and the note (there is no AWS Bedrock: the owner turned Bedrock
    off on 26 Nov 2026, and DeepSeek goes through its own API):
    - DeepSeek (`https://api.deepseek.com`; data goes to DeepSeek's servers in China);
    - Qwen (`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`; Alibaba Cloud's Singapore
      region, and keys work only in their own region);
    - Claude (the SDK's address);
    - GPT.
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
- **This month's use** (`ai_engine.month_tokens`) is the input, cached input and output tokens in
  the usage log since the 1st, TBO Support's calls and the worker's. It is cached for 5 minutes.
  A used-up first model stops its job even when its provider is switched off.
- **Allowed models:** a model a job uses can't be unticked or removed.
- **Removing:** a model that was never called and has no test-set run is deleted. Otherwise it
  only leaves the list, and its prices stay for the cost reports.
- **Candidate:** a listed model that no purpose uses.
- **Used by:** one line per application, with the purposes that use the model first and those it backs up, for
  example "TBO Support: draft, chat; backup for triage".
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

## Every AI call through the TBO AI gateway (Phase 37)

The TBO AI gateway is LiteLLM, running on the Copilot worker's server. It already carries the desktop app. With
**Use the gateway for every AI call** on (the TBO AI gateway card), TBO Support's calls go through it too.

**How calls go**
- `ai_engine.job_chain` turns each model a purpose would try (`chain_models`) into a gateway provider
  (`gateway_provider`): OpenAI's chat completions at `<gateway>/v1`, with TBO Support's own gateway key.
- The model, then the backup, as before. The provider's errors behind the gateway (429, 401, 5xx) come back with the
  same codes, so the error kinds on the page stay right.
- The worker is sent the same models under the provider name "TBO AI gateway". The worker reaches it at
  `http://127.0.0.1:4100/v1` with its own gateway key, `TBO_PROVIDER_GATEWAY_API_KEY`.

**When the gateway can't be used** (the owner's decision: an emergency key, and alerts)
- **When it counts as unusable:** the gateway doesn't answer its health check (`/health/liveliness`, asked again at
  most once a minute), or it refuses TBO Support's own key. In that case `_emergency` answers with TBO Support's
  sections: its own OpenAI key, kept for this alone.
- **The managers are told** once in 6 hours (`ai_gateway.mark_down`). The alert says whether an emergency key
  answers.
- **Every 5 minutes** `ai_gateway.watch` checks the gateway and says when it answers again.
- **The switch** turns on only once the gateway answers and accepts TBO Support's key. While it is on, a new
  address or key is checked the same way before it is kept.
- **Switching off** is refused while a TBO Support or worker job uses a model whose account's key lives only in the
  gateway: TBO Support no longer has that key. To switch off, point those jobs at other models, switch off, enter
  the keys again, then point the jobs back. Desktop levels don't stop it: the desktop app always calls the gateway.

**The AI models page writes into the gateway** (admin API, with TBO Support's admin key or TBO Desktop Settings'
one)

| What | Where it goes in the gateway |
|---|---|
| A provider's key | a gateway credential (`/credentials`) under the provider's name; TBO Support then forgets the key (`key_on_gateway`) |
| An allowed model | `/model/new` with the id `tbo-support:<model>` |
| An unticked or removed model | `/model/delete` |
| A model of today's OpenAI section | the gateway's own `OPENAI_API_KEY` |

- **Write all to the gateway** writes everything again: the keys still held here, and every model. A key is
  forgotten here only while the switch is on; with it off, the key is copied and kept, and **switching on later**
  moves every key still kept here to the gateway and forgets it here (a refusal leaves the switch off).
- **With the switch off,** the gateway's copies of keys and models change only with "Write all": after changing a
  key, an address or a model the desktop levels use, run it again. Removing a model or a provider still takes its
  copies off the gateway when it answers. Desktop levels are always written to the gateway (with the admin key),
  and switching on runs "Write all" first.
- **A provider's credential** is changed in place on the gateway (PATCH), so a refused change leaves the working one;
  one without an address of its own drops an earlier address explicitly. It is written new only when the gateway has
  none yet.
- **While the switch is on,** a change the gateway can't take isn't saved. A model or desktop level the gateway
  refuses keeps what it had (the old one is written back); if even that fails, the message says to use "Write all".
- **A provider test** through the gateway tests only that account's own models.

**Usage:** TBO Support keeps its own log of its calls and the worker's. From the gateway's usage it reads only the
desktop app's keys (aliases starting with `desktop:`), so nothing is counted twice.

**Checked on 26 Nov** against a local LiteLLM, the same image the gateway runs:
- the switch;
- a credential, and a model referring to it;
- a test call with TBO Support's key;
- the usage alias `tbo-support`;
- removing a model;
- the emergency path with the gateway stopped.

DevOps's steps (the gateway's settings, its salt key, Bedrock off, the worker's key) are in tbocloud-infra:
`docs/copilot-gateway.md`, "Every AI call through the gateway", and operator action 39. They were applied on
26 Nov 2026.

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
- **A worker claims** the oldest waiting request with a locking read, so two workers never take the same one.
- **A report** answers the request it names, or else the model's open request for the same job. A report for
  another model or job is refused. A worker's run takes the place of a manager's import that answered the request
  first, and a copy of a report sent again is stored once.
- **A run never reported** within 24 hours is given up (Failed, with a note) the next time a worker asks for one;
  a late report still answers it.
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

The desktop app sees only TBO's names for its models: `tbo-default` for GPT-5.6 Luna (the
gateway's `litellm-config.yaml`) and the levels `tbo-simple` … `tbo-very-hard`, which this page
writes. (Older usage rows may show `tbo-deepseek`, DeepSeek V3.2 on AWS Bedrock, removed on 26 Nov
2026.)
TBO Support keeps the real model (`model`, without the provider's prefix) and puts the gateway's
name beside it (`gateway_alias`, `gateway_provider`). So the desktop app's calls add up with TBO
Support's own calls to the same model, and the pages say "Desktop app calls it tbo-default".
Which real model is behind each name is still set in the gateway's own settings.

**Settings:** `gateway_url` (https; plain http only for a gateway on this machine, `localhost` or `127.0.0.1`),
`gateway_viewer_key` and `gateway_sync`. A failed read
is noted on the settings and never raised.

## Known limits

- The gateway's field names come from the LiteLLM documentation. They have not yet been checked
  against our gateway.
- A draft counts only when the same agent sends the reply on the same ticket within 24 hours.
  The comparison uses word runs, not a full diff.
- Speed and errors exist only from the deploy day.
