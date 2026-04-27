# Reasoning Benchmark

A small benchmark for short natural-language questions that expose weak LLM reasoning in places where the prompt looks easy but the model still misses the actual point.

## What it tests

This benchmark is aimed at failure modes like:
- goal grounding
- world-state tracking
- social pragmatic inference
- pronoun/reference resolution with commonsense grounding
- physical commonsense and test-condition reasoning
- instruction ambiguity and clarification judgment
- overfitting to familiar riddle templates

These are deliberately short prompts. The whole point is to catch models that sound fluent while missing simple real-world constraints.

## Repo layout

- `data/questions.json` — canonical machine-readable dataset
- `data/questions.csv` — spreadsheet-friendly export
- `docs/benchmark.md` — human-readable benchmark overview
- `scripts/run_benchmark.py` — minimal local runner scaffold
- `scripts/run_baselines.py` — baseline runner for first-class baseline models
- `scripts/benchmark_contract.py` — shared prompt/JSON contract for adapters
- `scripts/benchmark_adapters.py` — shared adapter library
- `scripts/api_adapter.py` — direct/provider adapter entrypoint
- `scripts/cli_adapter.py` — CLI/harness adapter entrypoint
- `scripts/report_summary.py` — v2 report-summary builder from scored artifacts and bundle manifests
- `runs/` — saved benchmark runs

## Dataset schema

Each question currently includes:
- `id`
- `category`
- `category_label`
- `provenance`
- `prompt`
- `expected_answer`
- `accepted_variants`
- `common_wrong_answer`
- `rationale`
- `failure_mode`

## Current status

- 100 questions total
- good enough for pruning and early model evals
- not yet a polished public benchmark release

## Framework spec

The v2 framework direction is captured in [`docs/framework-v2.md`](docs/framework-v2.md). It defines the intended scope, non-goals, core contract boundaries, and extension points for runner, scorer, artifact, and reporting work.

The canonical v2 entity and artifact shapes are captured in [`docs/contracts-v2.md`](docs/contracts-v2.md). They define suites, task families, benchmark cases, run configs, artifact bundles, score records, and report summaries.

The v2 dataset schema extension is captured in [`docs/dataset-schema-v2.md`](docs/dataset-schema-v2.md). It defines ambiguity metadata, cooperative-intent expectations, accepted interpretations, evaluator modes, and calibration fields that are present on migrated cases and additive for the rest of the dataset.

## Usage

Preview the dataset:

```bash
python3 scripts/run_benchmark.py --list
```

Export a light run template:

```bash
python3 scripts/run_benchmark.py --sample-run
```

The template preserves legacy `question_count` and `results[].id` fields while also emitting
v2-compatible `schema_version`, `suite_id`, `case_count`, and `results[].case_id` fields for scorer
and reporting consumers.

Create a JSONL prompt pack for another tool or model runner:

```bash
python3 scripts/run_benchmark.py --emit-prompts runs/prompts.jsonl
```

## Baselines

Run baseline runs for three starter models:

- `gpt-5.4`
- `sonnet-4.6`
- `qwen3.5-9b`

Smoke run (first 5 dataset rows) with dry-run payloads:

```bash
python3 scripts/run_baselines.py --mode smoke
```

Full run (all questions) with dry-run payloads:

```bash
python3 scripts/run_baselines.py --mode full
```

Run from a v2 RunConfig:

```bash
python3 scripts/run_baselines.py --config runs/baseline/run-config.json
```

Raw artifacts are written under `runs/baseline/` as one JSON per model, plus scored files with `.scored.json`
and report summary sidecars with `.summary.json`.
Bundle manifests used for report-summary regeneration must include `artifacts` as a JSON object,
point to raw and scored artifacts with exact, unpadded `artifacts.raw_results` and
`artifacts.scored_results` paths, use exact, unpadded `schema_version: "2.0.0"`,
preserve the exact `benchmark: "reasoning-benchmark"` identity, and include an exact, unpadded
non-empty `id` and `suite_id`, include the `run_config` field (which may be `null` for
legacy CLI runs, or an exact, unpadded, non-empty string for config-driven runs), plus a non-empty `models` list whose entries are exact,
unpadded strings, a non-negative integer `case_count`, and an exact, unpadded non-empty
`created_at`; when present, `completed_at` must be `null` or an exact, unpadded non-empty
string. Manifests must include `fingerprints`, `fingerprints.dataset`,
`fingerprints.scored_results`, and `fingerprints.raw_results` as JSON objects, use exact, unpadded
`fingerprints.dataset.algorithm: "sha256"` with an exact, unpadded, non-empty `fingerprints.dataset.value`, use exact, unpadded
`fingerprints.scored_results.algorithm: "sha256"` and
`fingerprints.raw_results.algorithm: "sha256"`, and include an exact, unpadded, non-empty
`fingerprints.scored_results.value` that matches the scored artifact bytes, plus a non-empty
exact, unpadded `fingerprints.raw_results.value` that matches the raw artifact bytes. When the
raw artifact is consumed, it must be a JSON object with a `results` list whose entries are JSON objects; the scored artifact must also be a JSON object with a `results` list whose entries are JSON objects. When the raw artifact embeds top-level `case_count`, `dataset.case_count`, or legacy
`dataset.question_count`, manifest `case_count` must match it; manifest `case_count` must also match the raw `results` list length; when the scored artifact embeds
`summary.overall.case_count` or
`summary.overall.question_count`, manifest `case_count`
must match it; when the scored artifact embeds a `results` list, manifest `case_count` must
match the actual scored record count; every raw and scored result record must expose an exact,
unpadded string `id` or `case_id`, records that expose both aliases must use the same value, and
paired raw/scored case identifiers must match in order; raw and scored result `model` values must be listed
in manifest `models`; when the raw artifact embeds `dataset.path_hash`, `fingerprints.dataset.value` must match it. When
`artifacts.report_summary` is present, its path must also be exact and unpadded, and
`fingerprints.report_summary.value` must match the summary sidecar bytes.
They emit top-level `schema_version: "2.0.0"` while preserving `runner_version` for the runner
implementation version. They also preserve legacy `run_mode` and `dataset.question_count` fields
while emitting v2-compatible `suite_id`, top-level `case_count`, and `dataset.case_count`
aliases for report and bundle consumers.
Embedded prompt contracts include the v2 response-shape metadata (`response_format` and `required_fields`)
used by config-driven runners and external adapter harnesses.
When a v2 RunConfig supplies `prompt_contract`, the baseline runner preserves that configured contract
in the raw artifact; legacy CLI runs continue to emit the built-in contract from `scripts/benchmark_contract.py`.
When a v2 RunConfig supplies `dataset.fingerprint` with a SHA-256 value, the runner verifies the
configured hash against the dataset file before writing artifacts; fingerprint algorithms and values
must be exact and unpadded.
Config-driven runs also reject RunConfig files whose `benchmark` is not the exact, unpadded
`reasoning-benchmark` value, so artifacts are not accidentally produced from a config intended for another benchmark.
They also require exact, unpadded `schema_version: "2.0.0"` so legacy or partial config shapes fail before artifact
generation, require exact unpadded non-empty `id` and `suite_id`, `dataset.path`, and model id fields so saved artifacts
remain traceable to a named execution request, suite, dataset, and model set, and reject configs that
omit the required `prompt_contract` or `execution` objects. Configured prompt contracts must declare an
exact, unpadded, non-empty `version` string, use the exact, unpadded supported value `response_format: "json_object"`, and include a
non-empty `required_fields` list with exact, unpadded string entries that include the adapter-facing
`answer` and `reasoning` fields.
Configured output directories must also
provide an exact, unpadded, non-empty `output.bundle_dir`, configured execution timeouts must be numeric, finite, and
positive, configured `max_cases` values must be whole positive integers, and configured
`skip_scoring` values must be booleans. Configured execution modes and model adapter names must be exact, unpadded,
non-empty strings, string seeds must be exact, unpadded, and non-empty, configured `suite.case_ids` entries must be exact, unique, unpadded case ids, and
`adapter_command` and `execution.provider_command` string values and list entries must be exact, unpadded, and non-empty.
Without `suite.case_ids`, configured modes must be `smoke` or `full`; explicit `suite.case_ids`
preserve their order and allow custom mode names. `seed` shuffles only mode-derived selections, and
`max_cases` truncates the selected suite after selection. Configured model ids must be one of
`gpt-5.4`, `sonnet-4.6`, or `qwen3.5-9b`.
Supported RunConfig adapter values are `api`, `cli`, and `provider-command`; model-level
`adapter_command` overrides adapter selection, while `execution.provider_command` supplies the
default command for models without their own command.
Live provider-backed raw result records include v2 audit metadata for the captured provider response,
adapter command/exit details, and per-prompt start/completion timestamps.

If you have a local model adapter, you can execute live by providing a command that accepts
`MODEL` and `PROMPT` as positional args and returns JSON with `answer` and `reasoning` fields.

This repo now ships two entrypoints:

**CLI / subscription-backed harness path**

```bash
python3 scripts/run_baselines.py \
  --mode smoke \
  --provider-command python3 scripts/cli_adapter.py
```

Optional OpenCode preference for subscription-backed models:

```bash
python3 scripts/run_baselines.py \
  --mode smoke \
  --provider-command python3 scripts/cli_adapter.py --prefer opencode
```

**Direct/provider path**

```bash
python3 scripts/run_baselines.py \
  --mode smoke \
  --provider-command python3 scripts/api_adapter.py
```

Current behavior:
- `cli_adapter.py`
  - `gpt-5.4` → Codex CLI by default
  - `sonnet-4.6` → Claude CLI by default
  - `qwen3.5-9b` → local Ollama through the shared adapter layer
- `api_adapter.py`
  - `qwen3.5-9b` → local Ollama now
  - `gpt-5.4` / `sonnet-4.6` are intentionally stubbed until direct API transport is wired

Scoring uses `scripts/score_run.py` automatically and writes a second artifact with the same model/mode
suffix for each raw run.

## Scoring

Score a run output with:

```bash
python3 scripts/score_run.py --input runs/example-run.json --output runs/example-run.scored.json
```

Build a report summary from saved scored artifacts or v2 bundle manifests with:

```bash
python3 scripts/report_summary.py --input runs/example-run.scored.json --output runs/report.summary.json
python3 scripts/report_summary.py --bundle runs/gpt-5-4.smoke.manifest.json --output runs/report.summary.json
```

When scored inputs already contain `summary.source_bundles`, the rebuilt report preserves those
bundle references; explicit `--bundle` manifests are recorded directly.

Scoring is **V1 conservative**:
- automatic scoring only affects final-answer correctness (`score_answer`)
- reasoning quality, constraint extraction, penalties, and notes remain manual review fields
- yes/no answers are handled explicitly, including polite/brief explanation variants
- blank or missing answers are scored as `0` with `missing_answer`
- heuristic matches are marked with `is_heuristic: true` in `results[].scoring_status.heuristic_flags`
- summary includes separate `auto_scored` and `manual_only` sections

See [`docs/scoring.md`](docs/scoring.md) for the full contract and normalization rules.

## Recommended next steps

1. prune weak, redundant, or too-gamey questions
2. define a scoring rubric for answer correctness and reasoning quality
3. add adapters for model providers
4. publish baseline results across a small model set
5. use v2 `RunArtifactBundle` manifests as durable run manifests

## License

MIT
