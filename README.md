# Reasoning Benchmark

### Does the model actually understand the question, or just the words in it?

A small benchmark of short natural-language prompts that look easy but expose weak reasoning — goal grounding, world-state tracking, social pragmatics, modified-riddle templates, and instruction ambiguity.

The point is to catch models that sound fluent while missing simple real-world constraints. 100 questions in the dataset, with the default benchmark set focused on 50 auto-scored questions. Instruction-ambiguity cases are kept as opt-in/manual-review cases. No dependencies, pure stdlib Python.

- **Short by design** — most prompts are one or two sentences. The failure isn't comprehension, it's reasoning.
- **Failure-mode labelled** — every case carries a `failure_mode` tag so you can see *where* a model breaks, not just *that* it broke.
- **Calibrated suites** — `starter` (12 cases, two per default family) for fast iteration, `holdout` (12 disjoint cases) for clean cross-model comparison, plus an optional `instruction-ambiguity` pack.
- **Conservative scoring** — automatic answer scoring only; reasoning quality and constraint extraction stay human-review fields.

## Quick Start

```bash
# Preview the dataset
python3 scripts/run_benchmark.py --list

# Generate a blank run template (fill in answers, then score)
python3 scripts/run_benchmark.py --sample-run > runs/my-run.json

# Score a completed run
python3 scripts/score_run.py --input runs/my-run.json --output runs/my-run.scored.json

# Run all tests
python3 -m unittest discover tests
```

No `pip install` — stdlib only.

## What it tests

| Code | Failure mode | Cases |
|------|--------------|------:|
| `GG` | Goal grounding / means-end reasoning | 8 |
| `SP` | Social / pragmatic reasoning | 9 |
| `PR` | Pronoun / reference resolution with commonsense grounding | 7 |
| `MC` | Classic-riddle override / anti-pattern matching | 8 |
| `TW` | Temporal or world-state tracking | 8 |
| `CR` | Physical constraint / practical reasoning | 10 |
| `IA` | Instruction ambiguity / clarification judgment | 50 |

These are deliberately short prompts. The whole point is to catch models that sound fluent while missing simple real-world constraints.

## How it works

```
┌──────────────────────────────────────────────────┐
│ 1. Dataset (data/questions.json, 100 cases)      │
│    id, prompt, expected_answer,                  │
│    accepted_variants, failure_mode, rationale    │
└──────────────────────┬───────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────┐
│ 2. Suite manifest (optional)                     │
│    starter / holdout, or RunConfig.matrix.suites │
└──────────────────────┬───────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────┐
│ 3. Runner — produces raw run artifact            │
│    run_benchmark.py    (template / prompt pack)  │
│    run_baselines.py    (live or dry-run)         │
└──────────────────────┬───────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────┐
│ 4. Scorer — score_answer + manual review fields  │
│    score_run.py                                  │
└──────────────────────┬───────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────┐
│ 5. Report summary (per-bucket breakdowns)        │
│    report_summary.py                             │
└──────────────────────────────────────────────────┘
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `run_benchmark.py --list` | Print default questions |
| `run_benchmark.py --list-suites` | Show available suite manifests |
| `run_benchmark.py --sample-run` | Emit a blank run template |
| `run_benchmark.py --emit-prompts <file>` | Write a JSONL prompt pack for an external runner |
| `run_baselines.py --mode smoke` | Dry-run baseline against the first 5 default questions |
| `run_baselines.py --mode full` | Dry-run baseline against the 50 default auto-scored cases |
| `run_baselines.py --config <file>` | Run from a v2 RunConfig (supports matrix) |
| `score_run.py --input <run> --output <scored>` | Score a run artifact |
| `report_summary.py --input <scored>` | Build a report summary from a scored artifact |
| `report_summary.py --bundle <manifest>` | Build a report summary from a v2 bundle manifest |

Add `--suite default` to any `run_benchmark.py` command to select the 50-question default auto-scored slice explicitly. You can also use `--suite starter` or `--suite holdout` for calibrated default manifests, or `--suite instruction-ambiguity` for the optional ambiguity pack.

Instruction-ambiguity cases (`IA-*`) are intentionally excluded from default baseline modes for now because they use hybrid/manual-review scoring. To opt in, either run the optional suite directly for inspection:

```bash
python3 scripts/run_benchmark.py --suite instruction-ambiguity --sample-run
```

or copy selected `IA-*` ids into a RunConfig `suite.case_ids` list on top of the default starter/holdout ids. See `examples/configs/starter-with-instruction-ambiguity.config.json` for that pattern.

## Dataset schema

Each case carries:

`id`, `category`, `category_label`, `provenance`, `prompt`, `expected_answer`, `accepted_variants`, `common_wrong_answer`, `rationale`, `failure_mode`

Migrated v2 cases additionally carry ambiguity, cooperative-intent, accepted-interpretation, evaluator-mode, and calibration metadata. See [`docs/dataset-schema-v2.md`](docs/dataset-schema-v2.md).

## Baselines

Three first-class baseline models are wired in:

| Model | `cli_adapter.py` | `api_adapter.py` |
|-------|------------------|------------------|
| `gpt-5.4` | Codex CLI | stubbed |
| `sonnet-4.6` | Claude CLI | stubbed |
| `qwen3.5-9b` | local Ollama via shared adapter layer | local Ollama |

Two entrypoints are shipped:

```bash
# CLI / subscription-backed harness path
python3 scripts/run_baselines.py --mode smoke \
  --provider-command python3 scripts/cli_adapter.py

# Direct/provider path
python3 scripts/run_baselines.py --mode smoke \
  --provider-command python3 scripts/api_adapter.py
```

Optional OpenCode preference for subscription-backed models:

```bash
python3 scripts/run_baselines.py --mode smoke \
  --provider-command python3 scripts/cli_adapter.py --prefer opencode
```

Run a matrix baseline from the starter config:

```bash
python3 scripts/run_baselines.py --config examples/configs/matrix-baseline.config.json
```

Raw artifacts land under `runs/baseline/` as one JSON per model, alongside scored sidecars (`*.scored.json`) and report-summary sidecars (`*.summary.json`). Matrix runs additionally write `matrix.index.json` at the configured bundle root; failed cells are recorded in the index while later cells continue, and the command exits nonzero if any cell errors.

`--skip-scoring` (or `execution.skip_scoring` in a RunConfig) writes only raw artifacts and removes any stale manifest for that model/mode.

If you have a local model adapter, you can execute live by providing a command that accepts `MODEL` and `PROMPT` as positional args and returns JSON with `answer` and `reasoning` fields. Adapter arguments are redacted in persisted artifacts as `program '[arguments omitted]'` so secrets are not stored.

RunConfig and bundle-manifest validation rules (fingerprints, `case_count` reconciliation, matrix suite constraints, allowed adapter values, `extensions` namespacing) are documented in [`docs/contracts-v2.md`](docs/contracts-v2.md).

## Scoring

Scoring is **V1 conservative** — only final-answer correctness is automatic.

- automatic: `score_answer` (0/1), `scoring_status` (match reason + heuristic flags), `score_answer_normalized` (debug fields)
- manual review: `score_reasoning`, `score_constraint_extraction`, `penalties`, `notes`
- yes/no answers use a strict first-6-tokens extractor with polite/brief variants
- blank or missing answers score `0` with `missing_answer`
- short-answer fallback marks heuristic matches with `is_heuristic: true`
- summary breaks results into `auto_scored`, `manual_only`, `manual_review`, per-bucket breakdowns, and `heuristic_flags`

Build a report summary from saved scored artifacts or v2 bundle manifests:

```bash
python3 scripts/report_summary.py --input runs/example-run.scored.json --output runs/report.summary.json
python3 scripts/report_summary.py --bundle runs/gpt-5-4.smoke.manifest.json --output runs/report.summary.json
```

When scored inputs already contain `summary.source_bundles`, the rebuilt report preserves those bundle references; explicit `--bundle` manifests are recorded directly.

See [`docs/scoring.md`](docs/scoring.md) for the full normalization and matching contract.

## Repo layout

```
data/
  questions.json        canonical dataset (100 cases)
  questions.csv         spreadsheet export
  suites/               named suite manifests (starter, holdout, optional instruction-ambiguity)
docs/
  benchmark.md          human-readable benchmark overview
  framework-v2.md       v2 framework spec
  contracts-v2.md       canonical entity/artifact shapes
  dataset-schema-v2.md  v2 dataset schema extension
  scoring.md            scoring contract and normalization rules
scripts/
  run_benchmark.py      runner scaffold (preview, template, prompt pack)
  run_baselines.py      baseline runner for first-class models
  suites.py             suite manifest loader
  benchmark_contract.py shared prompt/JSON contract for adapters
  benchmark_adapters.py shared adapter library
  api_adapter.py        direct/provider adapter entrypoint
  cli_adapter.py        CLI/harness adapter entrypoint
  score_run.py          scorer
  report_summary.py     v2 report-summary builder
runs/                   saved benchmark runs (gitignored except examples)
examples/configs/       example RunConfig files
```

## Spec

- [`docs/framework-v2.md`](docs/framework-v2.md) — scope, non-goals, contract boundaries, extension points
- [`docs/contracts-v2.md`](docs/contracts-v2.md) — canonical shapes for suites, task families, benchmark cases, run configs, artifact bundles, score records, and report summaries (including all manifest fingerprint and `case_count` validation rules)
- [`docs/dataset-schema-v2.md`](docs/dataset-schema-v2.md) — ambiguity metadata, cooperative-intent expectations, accepted interpretations, evaluator modes, calibration fields

## Status

- 100 questions
- Good enough for pruning and early model evals
- Not yet a polished public benchmark release

## License

MIT
