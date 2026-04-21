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

## Recommended next steps

1. prune weak, redundant, or too-gamey questions
2. define a scoring rubric for answer correctness and reasoning quality
3. add adapters for model providers
4. publish baseline results across a small model set

## License

MIT
