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
