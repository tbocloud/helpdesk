# AI providers

Where TBO Support's AI calls go, and what happens when a provider fails. The code is `helpdesk/ai_engine.py`; the settings are in **HDS Hub Settings → API**.

## Main provider

| Setting | Meaning |
|---|---|
| Provider | `Anthropic`, `Anthropic Compatible` (Kimi/Moonshot's Anthropic endpoint, GLM) or `OpenAI Compatible` (Moonshot International `https://api.moonshot.ai/v1`, OpenAI, Poolside, Qwen) |
| Base URL | Required for the compatible providers |
| AI API Key | The key for that provider; it lives only on the hub |
| Triage Model | The model for one-shot jobs: triage, suggested replies, KB drafts, task descriptions, summaries |
| Investigation Provider / Key / Model | The tool-using investigation loop; Anthropic or Anthropic Compatible only |

## Fallback provider

A second provider for the one-shot jobs only. It is used when the main provider:
- refuses the key (401, 403) or has no credit (402);
- rate-limits (429) or times out (408, connection errors);
- fails with a server error (5xx);
- is not configured at all.

A `400` is our own request's fault and is not retried. When the fallback answers, the **HDS AI Usage Log** row names the fallback model, `call_haiku` returns `model` = that model, and an Error Log entry "AI main provider failed; the fallback provider answered" is written at most once an hour, so someone notices the main provider is down.

The investigation loop has no fallback: it needs Anthropic-style tool use, and TBO Copilot's worker takes over investigations.

## Today's setup

Main: OpenAI Compatible, Moonshot International, `kimi-k2.6`. Fallback: OpenAI Compatible, `https://api.openai.com/v1`, the GPT model TBO chooses. Keys are entered in the settings form, never in chat or code.
