# Scoring Contract (V1)

This repo uses a two-layer scoring model:

- **Automatic layer**: only final answer correctness.
- **Manual layer**: reasoning quality, constraint extraction, penalties, and notes.

The goal is to keep automation safe and conservative while preserving the human signal for nuanced judgment.

## Run input shape

The scorer accepts JSON that is close to `scripts/run_benchmark.py --sample-run`, for example:

```json
{
  "schema_version": "2.0.0",
  "benchmark": "reasoning-benchmark",
  "created_at": "2026-04-21T00:00:00Z",
  "suite_id": "default",
  "case_count": 94,
  "question_count": 94,
  "results": [
    {
      "id": "GG-01",
      "case_id": "GG-01",
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

The scorer also accepts payloads where records are in `runs`, `items`, or `answers`, and also accepts a list of records directly. Records may use `case_id` instead of `id`; if both are present, `id` is used. Scored records emit `schema_version: "2.0.0"` and per-record `scored_at` timestamps, preserve both `id` and `case_id` when either identifier is available, and default missing or blank model identifiers to `unknown`.

## Automatic scoring (V1)

Each scored record includes `evaluation_mode` and `task_family_id`. Missing per-case evaluation config defaults to `exact`, and v1 `category` values are mapped to the v2 task-family ids from `docs/dataset-schema-v2.md`.
Each known scored record also carries the dataset `failure_mode` so reports can group behavior by the mistake pattern without reloading the dataset.
Known records also carry ambiguity metadata for v2 reporting: `ambiguity_type` is read from `ambiguity.ambiguity_type` when present, otherwise derived from the v1 category defaults documented in `docs/dataset-schema-v2.md`; `clarification_expected` is true only when explicitly set on the case. Detailed ambiguity review fields are preserved as `ambiguity_tags`, `literal_reading_defensible`, `preferred_resolution`, and `ambiguity_notes` when configured.
For ambiguity and pragmatic cases, known scored records also preserve configured `accepted_interpretations` and `cooperative_intent` values so manual reviewers can see the intended resolution context without reopening the dataset row.
Known records also carry calibration metadata for v2 suite/reporting slices: `calibration_difficulty`, `calibration_split`, `gold_confidence`, `human_disagreement_risk`, and `review_status`. Missing calibration defaults to `calibration_split: full` and `unknown` for the other calibration fields.
`exact` and `hybrid` modes run the conservative final-answer matcher; when a case configures `evaluation.answer_field`, that response field is used as the scored answer and recorded in `scoring_status.answer_field`. Known records also record the configured `evaluation.reasoning_field` in `scoring_status.reasoning_field`, defaulting to `reasoning`, so manual reviewers know which response field contains the model's rationale. Scoring traces also include `scoring_status.accepted_variant_policy`, defaulting to `normalized_exact_or_configured_heuristic`, so reviewers can see which accepted-answer policy the evaluator applied. Unknown-case records use the same default status fields (`answer`, `reasoning`, the default accepted-variant policy, and an empty dimensions list) while marking the record as `unknown_question_id`. `rubric` mode is left for manual review and emits `reason: rubric_manual_review_required` without an automatic answer score.

When a case defines `evaluation.dimensions`, the scorer preserves those dimensions under `scoring_status.dimensions` with normalized `id`, `label`, `type`, `weight`, and `auto_scored` fields. Dimensions mapped to final answer correctness (`answer_correctness`, `score_answer`, or `final_answer_correctness`) are populated from the exact matcher in `exact` and `hybrid` modes. Rubric or otherwise manual dimensions keep `score: null` and `status: manual_review_required`.

Automatic scoring writes/overwrites:

- `score_answer`: `0` or `1`.
- `score_answer_normalized`: debug fields for auditability.
- `scoring_status`: trace with match reason, heuristic flags, and optional dimension-level status.

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
- Also strip a leading `yes`/`no` wrapper from otherwise non-binary answers before retrying exact/heuristic matching (for answers like `No, bring the key with you.`), unless the case opts into `accepted_variant_policy: normalized_exact`.
- Cases that use `accepted_variant_policy: normalized_exact` compare only the raw normalized answer text against the normalized `expected_answer` and `accepted_variants`; they skip prefill stripping and other answer rewrites before matching.
- If exact match fails, allow conservative heuristics only when one of these holds:
  - normalized answer token length `<= 10`, and a full multi-token expected/accepted token sequence appears as a contiguous span inside the answer, or
  - after stripping a small set of soft determiners/pronouns (`the`, `your`, `you`, `now`, etc.), the answer and candidate still contain the same short multi-token contiguous phrase, or
  - the answer is a very short non-binary prefix (`<= 3` tokens) of an accepted answer such as `Drive` for `Drive there.`
- Heuristic matches are explicitly marked with `is_heuristic: true`.

Single-token candidates do not use the contiguous-span heuristic. Answers like `Three, ...` or `None, ...` must still match exactly or via another allowed path.

## Yes/No handling

If the expected answer begins with a binary form, the matcher uses binary mode unless the case opts into `accepted_variant_policy: normalized_exact`:

- `yes`/`no`
- `true`/`false` are mapped to `yes`/`no`
- a bare concise binary answer such as `No.` is accepted when it matches the expected polarity
- a longer binary answer such as `No, ...` is accepted only when its explanation substantially overlaps the expected answer or an accepted variant
- exact-output cases that use `accepted_variant_policy: normalized_exact` skip binary fallback and require a normalized exact match against `expected_answer` or `accepted_variants`
- `expected_binary_not_detected` (with `matched_by: binary_missing`) or `binary_mismatch` is scored as incorrect

This is deliberately strict; a matching `yes`/`no` token by itself is no longer enough for longer explanations, and if no binary token appears near the start of a short answer, it is marked incorrect.

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

- `summary.schema_version`: v2-compatible report summary schema marker.
- `summary.benchmark`: v2-compatible benchmark identifier, defaulting to `reasoning-benchmark`.
- `summary.suite_id`: v2-compatible suite identifier, derived from `suite_id`, `run_mode`, or `execution.mode` input metadata when available.
- `summary.source_bundles`: v2-compatible source bundle references. Baseline runs pass the planned adjacent manifest path into the scorer; standalone scoring leaves this empty unless `--source-bundle` is provided.
- `summary.generated_at`: v2-compatible report generation timestamp.
- `summary.overall.case_count`: v2-compatible alias for the legacy `summary.overall.question_count`.
- `summary.auto_scored`: total/correct/incorrect/accuracy from `score_answer`.
- `summary.manual_only`: legacy name for how many records already have manual fields (`score_reasoning`, `score_constraint_extraction`, `notes`) populated.
- `summary.manual_review`: v2-compatible name for the same manual-review aggregate, including total heuristic flags.
- `summary.by_model`: per-model `total` and v2 `case_count` totals, automatic correctness counts, accuracy over auto-scored records, and records requiring manual review.
- `summary.by_evaluation_mode`: per-mode `total` and v2 `case_count` totals, automatic correctness counts, accuracy over auto-scored records, and records requiring manual review.
- `summary.by_task_family`: per-task-family `total` and v2 `case_count` totals, automatic correctness counts, accuracy over auto-scored records, and records requiring manual review.
- `summary.by_failure_mode`: per-failure-mode `total` and v2 `case_count` totals, automatic correctness counts, accuracy over auto-scored records, and records requiring manual review.
- `summary.by_ambiguity_type`: per-ambiguity-type `total` and v2 `case_count` totals, automatic correctness counts, accuracy over auto-scored records, and records requiring manual review.
- `summary.by_calibration_split`: per-calibration-split `total` and v2 `case_count` totals, automatic correctness counts, accuracy over auto-scored records, and records requiring manual review.
- `summary.by_model_task_family`: model-by-task-family cross-tab with the same bucket fields.
- `summary.by_model_failure_mode`: model-by-failure-mode cross-tab with the same bucket fields.
- `summary.by_model_ambiguity_type`: model-by-ambiguity-type cross-tab with the same bucket fields.

`manual` and `automatic` are never conflated in the aggregate report.

## CLI

```bash
python3 scripts/score_run.py --input runs/example-run.json --output runs/example-run.scored.json
```

Use `--source-bundle path/to/manifest.json` when the scored output belongs to a known v2 `RunArtifactBundle` manifest. The option may be repeated, but `score_run.py` records those paths only as provenance in `summary.source_bundles`; use `scripts/report_summary.py` with repeated `--input` or `--bundle` arguments to build merged reports.
Baseline runs also copy the embedded scored-artifact `summary` object into a sibling `*.summary.json` sidecar and record that path in the bundle manifest as `artifacts.report_summary`.

Build or refresh a report summary from saved scored artifacts or v2 bundle manifests without reopening raw runner outputs with:

```bash
python3 scripts/report_summary.py --input runs/example-run.scored.json --output runs/report.summary.json
python3 scripts/report_summary.py --bundle runs/gpt-5-4.smoke.manifest.json --output runs/report.summary.json
```

When a bundle manifest is supplied, the report builder resolves `artifacts.scored_results` relative to the manifest file and records the manifest path in `summary.source_bundles`; this manifest path must be a non-empty, exact, unpadded string, manifest `schema_version` values must be exact, unpadded `2.0.0` strings, manifest `benchmark` must be the exact `reasoning-benchmark` identity, manifest `id` and `suite_id` values must be exact, unpadded, and non-empty, manifest `run_config` must be present and may be `null` for legacy CLI runs or an exact, unpadded, non-empty string for config-driven runs, manifest `models` must be a non-empty list of exact, unpadded strings, manifest `case_count` must be a non-negative integer, the raw artifact and scored artifact must each be JSON objects with `results` lists, every raw and scored `results` entry must be a JSON object with an exact, unpadded string `id` or `case_id`, records with both aliases must use the same value, and manifest `case_count` must match top-level `case_count`, `dataset.case_count`, legacy `dataset.question_count` when the raw artifact embeds those values, plus the raw `results` length, and `summary.overall.case_count`, `summary.overall.question_count`, and the actual `results` length from the scored artifact; paired raw and scored records must also use matching case identifiers in order, and raw or scored result `model` values must be listed in manifest `models`. Manifest `created_at` must be an exact, unpadded non-empty string, optional manifest `completed_at` must be `null` or an exact, unpadded non-empty string, manifest `fingerprints`, `fingerprints.dataset`, `fingerprints.scored_results`, and `fingerprints.raw_results` must be JSON objects, `fingerprints.dataset.algorithm` must be an exact, unpadded `sha256` string, `fingerprints.dataset.value` must be exact, unpadded, non-empty, and match `dataset.path_hash` when the raw artifact embeds it, `fingerprints.scored_results.algorithm` and `fingerprints.raw_results.algorithm` must be exact `sha256` strings, `fingerprints.scored_results.value` must be exact, unpadded, non-empty, and match the scored artifact bytes, `fingerprints.raw_results.value` must be exact, unpadded, non-empty, and match the raw artifact bytes, manifest `artifacts` must be a JSON object, and manifest `artifacts.raw_results` and `artifacts.scored_results` must be exact, unpadded, non-empty strings. When `artifacts.report_summary` is present, it must also be exact and unpadded, with a `fingerprints.report_summary` SHA-256 value matching the report-summary artifact bytes. When a scored input already embeds `summary.source_bundles`, the rebuilt report preserves those bundle references.

When multiple `--input` or `--bundle` sources are supplied, duplicate scored artifacts are
de-duplicated even if referenced both directly and through a bundle, `source_bundles` are
de-duplicated in first-seen order, and the output `suite_id` is `combined` when included sources use
different suite ids.

Output is written as JSON with:

- metadata (`schema_version: "2.0.0"`, `scoring_contract`, timestamps)
- preserved input metadata
- `results`
- `summary` with separated auto/manual sections
