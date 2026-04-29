# AGENTS.md

This file provides guidance to AI coding agents (Codex, etc.) when working with this repository.

## Commands

```bash
# Run all tests
python3 -m unittest discover tests

# Run a single test file
python3 -m unittest tests.test_scoring

# List benchmark questions from the default 94-question auto-scored slice
python3 scripts/run_benchmark.py --list

# List available suite manifests
python3 scripts/run_benchmark.py --list-suites

# Generate a blank run template for the default slice (use --suite for other slices)
python3 scripts/run_benchmark.py --sample-run

# Export a JSONL prompt pack for the default slice
python3 scripts/run_benchmark.py --emit-prompts runs/prompts.jsonl

# Restrict list/sample/export commands to a suite selector
python3 scripts/run_benchmark.py --list --suite starter

# Score a completed run
python3 scripts/score_run.py --input runs/example-run.json --output runs/example-run.scored.json
```

No dependencies to install — the codebase uses Python stdlib only.

## Architecture

Pure-Python reasoning benchmark. No framework, package manager, or external dependencies.

### Data flow

1. **Dataset** — `data/questions.json`, 144 questions with `id`, `category`, `prompt`, `expected_answer`, `accepted_variants`, `common_wrong_answer`, `rationale`, `failure_mode`.
2. **Suite manifests** — `data/suites/<name>.json`, ordered case selections loaded by `scripts/suites.py`. `starter.json` and `holdout.json` are calibrated 14-case default slices spanning the seven auto-scored task families.
3. **Run files** — `runs/*.json`, model answers against the dataset. Canonical shape: top-level `results` list (also accepted: `runs`, `items`, `answers`, or a bare list).
4. **Scorer** — `scripts/score_run.py` reads a run file + dataset, writes a scored artifact.

### Adapter layer

- `scripts/benchmark_contract.py` — shared prompt/JSON contract
- `scripts/benchmark_adapters.py` — shared adapter library (Codex CLI, Claude CLI, OpenCode CLI, Ollama)
- `scripts/api_adapter.py` — direct/provider entrypoint
- `scripts/cli_adapter.py` — subscription-CLI entrypoint

### Scoring

V1 conservative: automatic scoring covers final answer correctness only (`score_answer`). Manual fields (`score_reasoning`, `score_constraint_extraction`, `penalties`, `notes`) are preserved but never auto-filled.

See `docs/scoring.md` for the full normalization and matching contract.

### Runs directory

`runs/` is gitignored except for `example-run.json` and `example-run.scored.json`. New run files follow the same shape as `example-run.json`.
