# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
python3 -m unittest discover tests

# Run a single test file
python3 -m unittest tests.test_scoring

# List all benchmark questions
python3 scripts/run_benchmark.py --list

# Generate a blank run template (fill in answers, then score)
python3 scripts/run_benchmark.py --sample-run

# Export a JSONL prompt pack for external model runners
python3 scripts/run_benchmark.py --emit-prompts runs/prompts.jsonl

# Score a completed run
python3 scripts/score_run.py --input runs/example-run.json --output runs/example-run.scored.json
```

No dependencies to install — the codebase uses Python stdlib only (`unicodedata`, `json`, `re`, `argparse`, etc.).

## Architecture

This is a pure-Python reasoning benchmark with no framework, package manager, or external dependencies.

### Data flow

1. **Dataset** lives in `data/questions.json` — 100 questions, each with `id`, `category`, `prompt`, `expected_answer`, `accepted_variants`, `common_wrong_answer`, `rationale`, and `failure_mode`.
2. **Run files** (`runs/*.json`) contain model answers against the dataset. The canonical input shape has a top-level `results` list (also accepted: `runs`, `items`, `answers`, or a bare list).
3. **Scorer** (`scripts/score_run.py`) reads a run file + the dataset and writes a scored artifact.

### Two-layer scoring model

The scorer is **V1 conservative**: automatic scoring only handles final answer correctness (`score_answer`). Everything else is manual-review-only.

- **Automatic** (written by scorer): `score_answer` (0/1), `scoring_status` (match reason + heuristic flags), `score_answer_normalized` (debug fields).
- **Manual** (preserved, never auto-filled): `score_reasoning`, `score_constraint_extraction`, `penalties`, `notes`.

Scoring logic in `score_run.py`:
- `normalize_text` → NFKC + lowercase + punctuation-to-space + whitespace collapse
- `trim_prefillers` strips leading hedges ("the answer is", "i think", etc.)
- Binary (yes/no) questions use `extract_binary_token` — strict, first 6 tokens only
- Fallback heuristic: exact token sequence of `expected` must appear as a contiguous span inside a short answer (≤ 10 tokens); flagged with `is_heuristic: true`

Scored output shape: `{ schema_version, scoring_contract, scored_at, source_input, dataset_path, input_meta, summary, results }`. Summary separates `auto_scored` (accuracy metrics) from `manual_only` (counts of populated manual fields).

See `docs/scoring.md` for the full normalization and matching contract.

### Runs directory

`runs/` is gitignored except for `example-run.json` (sample unfilled run) and `example-run.scored.json` (scored output). New run files should follow the same shape as `example-run.json`.
