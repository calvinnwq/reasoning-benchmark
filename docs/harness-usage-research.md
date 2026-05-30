# Harness Usage And Cost Telemetry

Last checked: 2026-05-30.

This note records the current telemetry assumptions used by the benchmark before adding more
subscription-backed harness reruns.

## Codex CLI

Codex CLI run output exposes token telemetry, including input, cached input, output, and reasoning
output tokens. The benchmark adapter captures those fields from `turn.completed` events.

OpenAI's Codex rate card now maps Codex usage to token-based credits for most Plus, Pro, Business,
Enterprise, Edu, Health, and Gov customers. The rate card gives credits per 1M input, cached input,
and output tokens, not provider-reported USD per question:

- <https://help.openai.com/en/articles/20001106-codex-rate-card>

For USD reporting, the benchmark can only produce an API-equivalent estimate from OpenAI API
pricing unless Codex starts emitting provider-reported dollars in the run stream:

- <https://developers.openai.com/api/docs/models/gpt-5.5/>

Current benchmark rule:

- Preserve raw Codex `usage`.
- Treat Codex `input_tokens` as already including cached input for normalized context.
- Split `input_tokens - cache_read_input_tokens`, `cache_read_input_tokens`, and `output_tokens`
  for API-equivalent dollar estimates.
- Also emit estimated Codex credits from the pinned Codex rate card.
- Mark those derived values as estimates, not provider-reported dollars.

## Claude Code / Claude Agent SDK

Claude's agent SDK reports per-step usage, per-model cost, and cumulative result cost. The benchmark
Claude adapter already captures `usage`, `modelUsage`, `duration_ms`, and `total_cost_usd`.

- <https://code.claude.com/docs/en/agent-sdk/cost-tracking>

Current benchmark rule:

- Preserve raw Claude `usage` and `modelUsage`.
- Normalize input as `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`.
- Use `total_cost_usd` as provider-reported cost.

## OpenCode

OpenCode JSON streaming exposes step-finish usage events with token counts. The benchmark adapter
already parses `input_tokens`/`inputTokens`, `output_tokens`/`outputTokens`, cache read/write fields,
reasoning output, and `cost_usd`/`costUSD` when present.

References:

- <https://docs.cub.tools/docs/guide/harnesses/opencode/>
- <https://dev.opencode.ai/docs/config/>
- <https://github.com/sst/opencode/issues/1634>

Current benchmark rule:

- Preserve raw OpenCode event usage.
- Normalize input as `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`.
- Use `cost_usd`/`costUSD` as provider-reported cost when the event includes it.
- Otherwise leave dollars unknown until we add an explicit model-pricing table for that provider.

## Pi Coding Agent

Pi exposes live token/cache usage, cost, context usage, and current model in its interactive footer.
It also supports JSON mode and RPC APIs for usage/cost statistics. Custom models can declare
per-million-token costs in `models.json`, including input, output, cache read, and cache write.

References:

- <https://pi.dev/docs/latest/usage>
- <https://pi.dev/docs/latest/rpc>
- <https://pi.dev/docs/latest/models>
- <https://pi.dev/docs/latest/providers>

Current benchmark rule:

- A future Pi adapter should prefer JSON/RPC usage stats if they include per-turn usage.
- Normalize Pi like Claude/OpenCode when cache fields are separate.
- Use Pi-reported cost if available.
- If Pi only reports tokens, use the model's configured cost table when available and mark the
  result as an estimate.

## Accounting Contract

Every scored row should preserve raw `usage` and add:

- `normalized_usage`: comparison view for charts and summaries.
- `billing_usage`: audit view for uncached input, cache read/write, output, included reasoning,
  provider-reported cost, estimated cost, pricing version, and pricing source.

`reasoning_output_tokens` is included in output. It is never added on top of `output_tokens`.
