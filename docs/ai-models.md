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
- **Candidate:** it has no calls, and no job uses it.
- **Healthy:** none of the above.

## Model settings

- **Each job**, in HDS AI Job:
  - `primary_section` (blank means the settings' primary);
  - `allow_fallback` (On, Off, or blank for the settings' failover);
  - a model for each section.

  `ai_engine.provider_order(settings, job)` applies these, and `worker_models()` sends the same
  order to the worker.
- **Try:** one tiny call with the job's first model.
- **Change history:** HDS Model Change records who changed which setting of which job, and the
  old and new values.
- **Guard** (`ai_models.guard`): only for `investigate`, `fix` and `review`. It compares the newest
  test-set score of the first model after the change with that of the current one. If the new
  model has no score or a lower one, the page asks before saving. The guard itself saves nothing.
- **Candidates:** an HDS Model Pricing row with `candidate` ticked, added to be tested before a
  job uses it. When a candidate is removed, its row is deleted only if nothing ever used it.
  Otherwise only the tick goes.

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

- **Off:** a limit of 0 turns that alert off.
- **Repeats:** each model alerts at most once in 6 hours (cache key `ai_models:alerted:*`).
- **Who is told:** the System and Agent Managers, in the app and in the team's chat. The link
  goes to `/ai-models`.
- **Patch:** `helpdesk.patches.v16_0_3.model_alert_limits` sets the two defaults on sites that
  already have hub settings.

## The AI gateway (desktop app)

`ai_gateway.sync` runs every hour at :20 when switched on. It reads the gateway's
`/spend/logs/v2` with a read-only key and keeps totals per day, model and person in HDS Gateway
Usage Day. These models then appear beside TBO Support's own.

**Settings:** `gateway_url` (must be https), `gateway_viewer_key` and `gateway_sync`. A failed read
is noted on the settings and never raised.

## Known limits

- The gateway's field names come from the LiteLLM documentation. They have not yet been checked
  against our gateway.
- A draft counts only when the same agent sends the reply on the same ticket within 24 hours.
  The comparison uses word runs, not a full diff.
- Speed and errors exist only from the deploy day.
