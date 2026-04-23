# Reasoning Benchmark

A small benchmark for short natural-language questions that expose weak LLM reasoning in places where the prompt looks easy but the model still misses the actual point.

## What it tests

This benchmark is aimed at failure modes like:
- goal grounding
- world-state tracking
- social pragmatic inference
- pronoun/reference resolution with commonsense grounding
- physical commonsense and test-condition reasoning
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

- 50 questions total
- good enough for pruning and early model evals
- not yet a polished public benchmark release

## Usage

Preview the dataset:

```bash
python3 scripts/run_benchmark.py --list
```

Export a light run template:

```bash
python3 scripts/run_benchmark.py --sample-run
```

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

Full run (all 50 questions) with dry-run payloads:

```bash
python3 scripts/run_baselines.py --mode full
```

Raw artifacts are written under `runs/baseline/` as one JSON per model, plus scored files with `.scored.json`.

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
5. use the scored artifact format from `scripts/score_run.py` as the long-term run manifest

## License

MIT
