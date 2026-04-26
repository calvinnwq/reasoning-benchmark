# Scoring Contract (V1)

This repo uses a two-layer scoring model:

- **Automatic layer**: only final answer correctness.
- **Manual layer**: reasoning quality, constraint extraction, penalties, and notes.

The goal is to keep automation safe and conservative while preserving the human signal for nuanced judgment.

## Run input shape

The scorer accepts JSON that is close to `scripts/run_benchmark.py --sample-run`, for example:

```json
{
  "benchmark": "reasoning-benchmark",
  "created_at": "2026-04-21T00:00:00Z",
  "question_count": 50,
  "results": [
    {
      "id": "GG-01",
      "prompt": "...",
      "model": "",
      "answer": "...",
      "reasoning": "...",
      "score_answer": null,
      "score_reasoning": null,
      "score_constraint_extraction": null,
      "penalties": [],
      "notes": ""
    }
  ]
}
```

The scorer also accepts payloads where records are in `runs`, `items`, or `answers`, and also accepts a list of records directly. Records may use `case_id` instead of `id`; if both are present, `id` is used.

## Automatic scoring (V1)

Automatic scoring writes/overwrites:

- `score_answer`: `0` or `1`.
- `score_answer_normalized`: debug fields for auditability.
- `scoring_status`: trace with match reason and heuristic flags.

All other manual scoring fields are preserved and **not auto-filled**:

- `score_reasoning`
- `score_constraint_extraction`
- `penalties`
- `notes`

If an input is missing an answer, only non-auto fields are preserved and `score_answer` is set to `0` with `reason: missing_answer`.

## Normalization rules

The automatic answer matcher applies deterministic normalisation before comparison.

- Unicode cleanup:
  - normalise `NFKC`
  - lowercase
  - map common quote/dash variants to ASCII
- Normalize a small conservative set of common contractions/spelling variants before matching:
  - e.g. `they're` → `they are`, `won't` → `will not`, `don't` → `do not`
  - e.g. `signalling` → `signaling`, `metres` → `meters`
- Remove non alphanumeric characters (except whitespace), then normalize whitespace.
- Apply short prefill stripping (at most once per phrase block):
  - `the answer is`, `i think`, `i believe`, `i guess`, `it is`, `probably`, ...
- Compare against expected and `accepted_variants` as normalized exact matches.
- Also strip a leading `yes`/`no` wrapper from otherwise non-binary answers before retrying exact/heuristic matching (for answers like `No, bring the key with you.`).
- If exact match fails, allow conservative heuristics only when one of these holds:
  - normalized answer token length `<= 10`, and a full expected/accepted token sequence appears as a contiguous span inside the answer, or
  - after stripping a small set of soft determiners/pronouns (`the`, `your`, `you`, `now`, etc.), the answer and candidate still contain the same short contiguous phrase, or
  - the answer is a very short non-binary prefix (`<= 3` tokens) of an accepted answer such as `Drive` for `Drive there.`
- Heuristic matches are explicitly marked with `is_heuristic: true`.

## Yes/No handling

If the expected answer begins with a binary form, the matcher uses binary mode:

- `yes`/`no`
- `true`/`false` are mapped to `yes`/`no`
- expected `No...` and answer forms like `No, ...` are accepted
- `expected_binary_missing` / `binary_mismatch` is scored as incorrect

This is deliberately strict; if no binary token appears near the start of a short answer, it is marked incorrect.

## Missing/blank answer handling

- Empty string, whitespace-only, or `null` answers are scored `0`.
- `scoring_status.reason` is set to `missing_answer`.

## Heuristic flags and output format

Every match result includes `scoring_status.heuristic_flags`.

Each flag has:

- `name`
- `value`
- `is_heuristic`

Any heuristic match is explicitly marked with `"is_heuristic": true`.  
This is required so downstream consumers never treat heuristic matches as ground truth.

## Summary output

V1 summary separates automatic and manual-only metrics:

- `summary.auto_scored`: total/correct/incorrect/accuracy from `score_answer`.
- `summary.manual_only`: how many records already have manual fields (`score_reasoning`, `score_constraint_extraction`, `notes`) populated.

`manual` and `automatic` are never conflated in the aggregate report.

## CLI

```bash
python3 scripts/score_run.py --input runs/example-run.json --output runs/example-run.scored.json
```

Output is written as JSON with:

- metadata (`schema_version`, `scoring_contract`, timestamps)
- preserved input metadata
- `results`
- `summary` with separated auto/manual sections
