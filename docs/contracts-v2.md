# Reasoning Benchmark v2 Contracts

**Status:** M1 draft
**Scope owner:** NGX-132
**Depends on:** `docs/framework-v2.md`
**Purpose:** Define the canonical entities and JSON artifact shapes that runner, scorer, and reporting work should preserve as the framework evolves.

These contracts are data-first. They describe stable JSON objects the current stdlib scripts can read and write without introducing a package dependency, database, or class hierarchy.

## Contract Rules

- Every persisted top-level artifact should include `schema_version`.
- New v2 fields are additive until the dataset migration is complete.
- Existing dataset rows and run files must remain readable.
- Optional fields may be omitted or set to `null`; consumers should not require empty placeholder strings except where current v1 files already do.
- IDs are stable strings. They should not encode file paths or display names that may change.
- Timestamps use ISO 8601 UTC strings.
- Paths inside artifacts should be repository-relative when practical, with absolute paths reserved for local diagnostic metadata.

## Canonical Entities

V2 has seven core entities:

1. `Suite`: an ordered selection of cases.
2. `TaskFamily`: a reporting and curation grouping.
3. `BenchmarkCase`: one prompt plus answer and evaluation metadata.
4. `RunConfig`: one reproducible execution request.
5. `RunArtifactBundle`: the manifest tying a run's durable files together.
6. `ScoreRecord`: one evaluated model result for one case.
7. `ReportSummary`: aggregate metrics derived from scored records.

`PromptContract` and `ModelResult` remain support objects. They are embedded in `RunConfig`, raw result files, and artifact bundles rather than owned as standalone persisted entities.

## Suite

A suite is an ordered case selection. The current `smoke` and `full` baseline modes can be represented as suites without changing runner behavior.

```json
{
  "schema_version": "2.0.0",
  "id": "smoke",
  "name": "Smoke",
  "description": "Fast sanity-check slice over the first five cases.",
  "case_ids": ["GG-01", "GG-02", "GG-03", "GG-04", "GG-05"],
  "selection": {
    "mode": "explicit",
    "source": "data/questions.json",
    "reason": "Fast local verification"
  },
  "created_at": "2026-04-26T00:00:00Z"
}
```

Required fields:

- `schema_version`
- `id`
- `name`
- `case_ids`

`case_ids` entries are exact, unique case identifiers. Config-driven runner validation rejects blank,
duplicate, non-string, or whitespace-padded entries before dataset selection.

Optional fields:

- `description`
- `selection`
- `created_at`
- `tags`

## TaskFamily

A task family is a stable grouping used for curation and reporting. It should be broader than an individual case and more stable than a one-off tag.

```json
{
  "schema_version": "2.0.0",
  "id": "goal-grounding",
  "label": "Goal grounding",
  "legacy_category": "GG",
  "description": "Prompts where the model must preserve the real-world objective rather than optimize a local shortcut.",
  "default_evaluation_mode": "exact",
  "reporting_order": 10
}
```

Required fields:

- `schema_version`
- `id`
- `label`

Optional fields:

- `legacy_category`
- `description`
- `default_evaluation_mode`
- `reporting_order`
- `tags`

## BenchmarkCase

`BenchmarkCase` is the v2 name for one row in `data/questions.json`. Current rows can be read as v2-compatible cases by mapping `category` to `legacy_category` and deriving `task_family_id` later. The extended ambiguity, cooperative-intent, accepted-interpretation, and calibration fields are defined in [`docs/dataset-schema-v2.md`](dataset-schema-v2.md).

```json
{
  "schema_version": "2.0.0",
  "id": "GG-01",
  "task_family_id": "goal-grounding",
  "legacy_category": "GG",
  "category_label": "Goal grounding",
  "provenance": "sourced/inspired",
  "prompt": "I want to wash my car. The car wash is only 100 metres away. Should I drive there or walk?",
  "expected_answer": "Drive there. The car is the thing that needs to reach the car wash.",
  "accepted_variants": ["Drive the car there."],
  "common_wrong_answer": "Walk there because it is only 100 metres.",
  "rationale": "The goal is to wash the car, so the car must reach the car wash.",
  "failure_mode": "optimizes for distance while ignoring the task object",
  "evaluation": {
    "mode": "exact",
    "answer_field": "answer",
    "reasoning_field": "reasoning",
    "accepted_variant_policy": "normalized_exact_or_configured_heuristic"
  },
  "metadata": {
    "difficulty": "starter",
    "tags": ["short-reasoning"]
  }
}
```

Required fields:

- `id`
- `prompt`
- `expected_answer`
- `accepted_variants`
- `failure_mode`

V2 fields that should become required after migration:

- `schema_version`
- `task_family_id`
- `evaluation`

Compatibility fields preserved from v1:

- `category`
- `category_label`
- `provenance`
- `common_wrong_answer`
- `rationale`

## RunConfig

`RunConfig` declares what should be executed. It should be enough to reproduce a dry-run prompt pack, a CLI-backed run, or a direct/provider run.

```json
{
  "schema_version": "2.0.0",
  "id": "baseline-smoke-2026-04-26",
  "benchmark": "reasoning-benchmark",
  "suite_id": "smoke",
  "dataset": {
    "path": "data/questions.json",
    "fingerprint": {
      "algorithm": "sha256",
      "value": "..."
    }
  },
  "models": [
    {
      "id": "gpt-5.4",
      "adapter": "cli",
      "adapter_command": "python3 scripts/cli_adapter.py"
    }
  ],
  "prompt_contract": {
    "version": "1.0.0",
    "response_format": "json_object",
    "required_fields": ["answer", "reasoning"]
  },
  "execution": {
    "runner": "scripts/run_baselines.py",
    "runner_version": "1.0.0",
    "mode": "smoke",
    "timeout_seconds": 45.0,
    "seed": null,
    "max_cases": 5
  },
  "output": {
    "bundle_dir": "runs/baseline/gpt-5-4.smoke"
  },
  "created_at": "2026-04-26T00:00:00Z"
}
```

Required fields:

- `schema_version`
- `id`
- `benchmark`
- `suite_id`
- `dataset`
- `models`
- `prompt_contract`
- `execution`
- `output`

Current runner validation supports the exact, unpadded `prompt_contract.response_format: "json_object"` value,
matching the shared adapter contract used by CLI and direct/provider runners.
It requires `schema_version` to be the exact, unpadded `2.0.0` string so configs do not preserve
ambiguous contract-version identifiers.
It requires `benchmark` to be the exact, unpadded `reasoning-benchmark` value so configs do not
preserve ambiguous benchmark identifiers.
It requires `suite_id` to be an exact, unpadded, non-empty string so run configs reference a stable
suite identifier without preserving ambiguous whitespace.
It also requires `id` to be an exact, unpadded, non-empty string so artifacts preserve a stable
execution request identifier.
It requires `dataset.path` to be an exact, unpadded, non-empty string so configs do not preserve
ambiguous dataset references.
When supplied, `dataset.fingerprint.algorithm` and `dataset.fingerprint.value` must also be exact,
unpadded strings before the value is compared with the dataset's SHA-256 hash.
It requires `output.bundle_dir` to be an exact, unpadded, non-empty string so configs do not write
artifacts into ambiguous output locations.
It requires model ids, whether listed directly or inside model objects, to be exact, unpadded,
non-empty strings so configs do not preserve ambiguous model selections.
It requires `execution.mode` to be an exact, unpadded, non-empty string when present so configs do
not preserve ambiguous suite mode selections.
It requires model adapter names to be exact, unpadded strings so configs do not preserve ambiguous
adapter selections. Supported adapter values are `api`, `cli`, and `provider-command`; `api` and
`cli` select the built-in adapter entrypoints, while `provider-command` relies on an explicit
command. A model-level `adapter_command` overrides both the model adapter value and any default
`execution.provider_command`; `execution.provider_command` is used as the default command for
models that do not specify their own command.
It requires string `execution.seed` values to be exact, unpadded, and non-empty so reproducible case
selection does not depend on ambiguous invisible whitespace.
It requires `prompt_contract.version` to be an exact, unpadded, non-empty string so artifacts do not
preserve ambiguous contract identifiers.
It also requires `prompt_contract.required_fields` to include both `answer` and `reasoning`, matching
the built-in prompt contract and adapter result shape. Field names must be exact, unpadded strings so
artifacts do not preserve ambiguous response keys.
String-form `adapter_command` and `execution.provider_command` values and list-form entries must
also be exact, unpadded, non-empty strings so configured commands fail validation before subprocess
execution when they preserve ambiguous whitespace.

## ModelResult

`ModelResult` is the raw model answer for one case before scoring. Current `results[]` records in run files already cover the minimum shape.

```json
{
  "case_id": "GG-01",
  "model": "gpt-5.4",
  "prompt": "I want to wash my car...",
  "answer": "Drive there.",
  "reasoning": "The car needs to reach the car wash.",
  "raw_response": {
    "text": "{\"answer\":\"Drive there.\",\"reasoning\":\"The car needs to reach the car wash.\"}",
    "format": "json"
  },
  "adapter": {
    "name": "cli",
    "command": "python3 scripts/cli_adapter.py",
    "exit_code": 0,
    "stderr": ""
  },
  "started_at": "2026-04-26T00:00:00Z",
  "completed_at": "2026-04-26T00:00:01Z"
}
```

Required fields:

- `case_id` or the v1-compatible alias `id`
- `model`
- `prompt`
- `answer`
- `reasoning`

Optional fields:

- `raw_response`
- `adapter`
- `started_at`
- `completed_at`
- `notes`

## ScoreRecord

`ScoreRecord` is one evaluated result. It must preserve current manual review fields while adding enough trace data for auditability.

```json
{
  "schema_version": "2.0.0",
  "case_id": "GG-01",
  "model": "gpt-5.4",
  "evaluation_mode": "exact",
  "answer": "Drive there.",
  "reasoning": "The car needs to reach the car wash.",
  "score_answer": 1,
  "score_reasoning": null,
  "score_constraint_extraction": null,
  "penalties": [],
  "notes": "",
  "scoring_status": {
    "matched": true,
    "score": 1,
    "reason": "exact_normalized_match",
    "matched_by": "exact",
    "answer_field": "answer",
    "reasoning_field": "reasoning",
    "accepted_variant_policy": "normalized_exact_or_configured_heuristic",
    "heuristic_flags": [
      {
        "name": "exact_match",
        "value": true,
        "is_heuristic": false
      }
    ]
  },
  "score_answer_normalized": {
    "expected": "Drive there. The car is the thing that needs to reach the car wash.",
    "expected_normalized": "drive there the car is the thing that needs to reach the car wash",
    "answer": "Drive there.",
    "answer_normalized": "drive there"
  },
  "score_reason": "exact_normalized_match",
  "scored_at": "2026-04-26T00:00:02Z"
}
```

Required fields:

- `schema_version`
- `case_id` or the v1-compatible alias `id`
- `model`
- `evaluation_mode`
- `score_answer`
- `score_reasoning`
- `score_constraint_extraction`
- `penalties`
- `notes`
- `scoring_status`

## RunArtifactBundle

`RunArtifactBundle` is the durable manifest for one run. It ties together config, raw output, scored output, and summary data so a future reporter can compare runs without guessing file relationships.

```json
{
  "schema_version": "2.0.0",
  "id": "baseline-smoke-gpt-5-4-2026-04-26",
  "benchmark": "reasoning-benchmark",
  "suite_id": "smoke",
  "run_config": "config.json",
  "artifacts": {
    "raw_results": "raw.json",
    "scored_results": "scored.json",
    "report_summary": "summary.json",
    "prompt_pack": "prompts.jsonl"
  },
  "fingerprints": {
    "dataset": {
      "algorithm": "sha256",
      "value": "..."
    },
    "raw_results": {
      "algorithm": "sha256",
      "value": "..."
    },
    "scored_results": {
      "algorithm": "sha256",
      "value": "..."
    },
    "report_summary": {
      "algorithm": "sha256",
      "value": "..."
    }
  },
  "models": ["gpt-5.4"],
  "case_count": 5,
  "created_at": "2026-04-26T00:00:00Z",
  "completed_at": "2026-04-26T00:00:02Z"
}
```

Required fields:

- `schema_version`
- `id`
- `benchmark`
- `suite_id`
- `run_config`
- `artifacts`
- `fingerprints`
- `models`
- `case_count`
- `created_at`

The initial implementation may store the bundle as a single JSON file beside existing raw and scored files. Later work can move to a directory layout without changing the manifest contract.
Baseline runs write the `ReportSummary` as a sibling `*.summary.json` artifact copied from the scored output's embedded `summary` object.
Report-summary regeneration requires bundle manifests to use exact, unpadded, non-empty `id`
values so bundle identity is not silently normalized from malformed manifest metadata.
Report-summary regeneration requires bundle manifests to use exact, unpadded, non-empty `suite_id`
values so summary identity is not silently normalized from malformed bundle metadata.
Report-summary regeneration requires bundle manifests to include the `run_config` field; legacy
CLI-produced bundles may set it to `null`, while config-driven bundles must set it to a
exact, unpadded, non-empty string.
Report-summary regeneration requires bundle manifests to include a non-empty `models` list whose
entries are exact, unpadded, non-empty strings.
Report-summary regeneration requires bundle manifests to include `case_count` as a non-negative
integer.
Report-summary regeneration requires the referenced raw artifact to be a JSON object before
checking any embedded raw metadata.
Report-summary regeneration requires the referenced raw artifact to include a `results` list so
bundle manifests cannot point at metadata-only raw files.
Report-summary regeneration requires every raw artifact `results` entry to be a JSON object so
malformed raw records are not accepted as valid bundle contents.
Report-summary regeneration requires the referenced scored artifact to be a JSON object with a
`results` list before checking scored summary metadata or rebuilding the report summary.
Report-summary regeneration requires every scored artifact `results` entry to be a JSON object so
malformed scored records are not silently dropped while rebuilding summaries.
When the raw artifact embeds top-level `case_count`, report-summary regeneration requires
manifest `case_count` to match it so bundle case metadata stays consistent with the raw output
artifact it references.
Report-summary regeneration also requires manifest `case_count` to match the actual raw record
count from the raw artifact `results` list.
When the raw artifact embeds `dataset.case_count`, report-summary regeneration also requires
manifest `case_count` to match that dataset-level count alias.
When the scored artifact embeds `summary.overall.case_count`, report-summary regeneration requires
manifest `case_count` to match it so bundle case metadata stays consistent with the scored output
artifact it references.
When the scored artifact embeds legacy `summary.overall.question_count`, report-summary
regeneration also requires manifest `case_count` to match it.
When the scored artifact embeds a `results` list, report-summary regeneration also requires
manifest `case_count` to match the actual scored record count.
Report-summary regeneration requires every raw and scored result record in a consumed bundle to
expose an exact, unpadded string `id` or `case_id`, requires records with both aliases to use the
same value, and requires paired raw/scored case identifiers to match in order so a bundle cannot
combine raw and scored artifacts from different case selections.
When raw or scored result records include a `model` value, report-summary regeneration requires it
to be listed in manifest `models` so bundle metadata cannot claim a different model set than the
artifacts being summarized.
Report-summary regeneration requires bundle manifests to include `created_at` as an exact,
unpadded, non-empty string.
When present, `completed_at` must be `null` or an exact, unpadded, non-empty string so regenerated
summaries do not preserve ambiguous completion timestamp metadata.
Report-summary regeneration requires bundle manifests to include `fingerprints` as a JSON object
so bundle integrity metadata is not silently omitted.
Report-summary regeneration requires bundle manifests to include `fingerprints.dataset` as a JSON object
so consumed bundle manifests preserve dataset identity metadata.
Report-summary regeneration requires bundle manifests to include `fingerprints.scored_results` as a JSON object
so the scored artifact being consumed has explicit integrity metadata.
Report-summary regeneration requires bundle manifests to include `fingerprints.raw_results` as a JSON object
so consumed bundle manifests preserve raw-output integrity metadata.
Report-summary regeneration requires `fingerprints.dataset.algorithm` to be the exact, unpadded
`sha256` string so dataset identity metadata uses the supported digest algorithm.
Report-summary regeneration requires `fingerprints.dataset.value` to be an exact, unpadded,
non-empty string so
dataset identity metadata is not silently omitted from consumed manifests.
When the raw artifact embeds `dataset.path_hash`, report-summary regeneration requires
`fingerprints.dataset.value` to match it so the bundle's dataset identity stays consistent with
the raw output artifact it references.
Report-summary regeneration requires `fingerprints.scored_results.algorithm` to be the exact,
unpadded `sha256` string.
Report-summary regeneration requires `fingerprints.raw_results.algorithm` to be the exact,
unpadded `sha256` string so raw-output integrity metadata uses the supported digest algorithm.
Report-summary regeneration requires `fingerprints.scored_results.value` to be an exact,
unpadded, non-empty string that matches the scored artifact bytes.
Report-summary regeneration requires `fingerprints.raw_results.value` to be an exact,
unpadded, non-empty string that matches the raw artifact bytes.
When `artifacts.report_summary` is present, report-summary regeneration validates it as an exact,
unpadded, non-empty path and requires `fingerprints.report_summary.algorithm` to be the exact
`sha256` string with a non-empty, exact value matching the report-summary artifact bytes.
Report-summary regeneration requires bundle manifests to include `artifacts` as a JSON object
before reading `artifacts.scored_results`.
Report-summary regeneration requires `artifacts.scored_results` to be a non-empty string
before resolving the scored artifact path.
Report-summary regeneration requires `artifacts.raw_results` to be a non-empty string
so consumed bundle manifests preserve the required raw-output artifact reference.
Report-summary generation validates `artifacts.raw_results` and `artifacts.scored_results` as exact, unpadded paths before resolving them relative to the manifest, rejects absolute paths and `..` traversal for `artifacts.raw_results`, `artifacts.scored_results`, and `artifacts.report_summary`, rejects missing, unsupported, or whitespace-padded manifest `schema_version` values, and requires manifest `benchmark` to be the exact `reasoning-benchmark` identity.

## ReportSummary

`ReportSummary` aggregates scored results for comparison. It should be generated from scored artifacts, not from raw model outputs.

```json
{
  "schema_version": "2.0.0",
  "benchmark": "reasoning-benchmark",
  "suite_id": "smoke",
  "source_bundles": ["runs/baseline/gpt-5-4.smoke/manifest.json"],
  "generated_at": "2026-04-26T00:00:03Z",
  "overall": {
    "case_count": 5,
    "question_count": 5,
    "answered_count": 5,
    "missing_count": 0
  },
  "auto_scored": {
    "total": 5,
    "correct": 4,
    "incorrect": 1,
    "accuracy": 0.8
  },
  "manual_only": {
    "reasoning_scores_present": 0,
    "constraint_scores_present": 0,
    "notes_present": 0,
    "heuristic_flags_total": 0
  },
  "by_model": {
    "gpt-5.4": {
      "total": 5,
      "auto_scored": 5,
      "correct": 4,
      "incorrect": 1,
      "accuracy": 0.8,
      "manual_review_required": 0,
      "case_count": 5
    }
  },
  "by_task_family": {
    "goal-grounding": {
      "total": 5,
      "auto_scored": 5,
      "correct": 4,
      "incorrect": 1,
      "accuracy": 0.8,
      "manual_review_required": 0,
      "case_count": 5
    }
  },
  "by_failure_mode": {
    "optimizes for distance while ignoring the task object": {
      "total": 1,
      "auto_scored": 1,
      "correct": 1,
      "incorrect": 0,
      "accuracy": 1.0,
      "manual_review_required": 0,
      "case_count": 1
    }
  },
  "by_ambiguity_type": {
    "none": {
      "total": 5,
      "auto_scored": 5,
      "correct": 4,
      "incorrect": 1,
      "accuracy": 0.8,
      "manual_review_required": 0,
      "case_count": 5
    }
  },
  "by_calibration_split": {
    "smoke": {
      "total": 5,
      "auto_scored": 5,
      "correct": 4,
      "incorrect": 1,
      "accuracy": 0.8,
      "manual_review_required": 0,
      "case_count": 5
    }
  },
  "manual_review": {
    "reasoning_scores_present": 0,
    "constraint_scores_present": 0,
    "notes_present": 0,
    "heuristic_flags_total": 0
  },
  "heuristic_flags": {}
}
```

Required fields:

- `schema_version`
- `benchmark`
- `suite_id`
- `source_bundles`
- `generated_at`
- `overall`
- `auto_scored`
- `manual_only`
- `by_model`
- `heuristic_flags`

Optional but expected for M3 reporting:

- `by_task_family`
- `by_evaluation_mode`
- `by_failure_mode`
- `by_ambiguity_type`
- `by_calibration_split`
- `manual_review`

Per-bucket summaries in `by_model`, `by_evaluation_mode`, `by_task_family`, `by_failure_mode`, `by_ambiguity_type`, and `by_calibration_split` use the same shape: `total`, `auto_scored`, `correct`, `incorrect`, `accuracy`, `manual_review_required`, and `case_count`.

## Current-To-V2 Mapping

| Current field or artifact | V2 destination |
|---|---|
| `data/questions.json[]` | `BenchmarkCase` |
| `category` | `legacy_category`, then `task_family_id` after migration |
| `scripts/benchmark_contract.py::PROMPT_CONTRACT` | embedded `prompt_contract` |
| `scripts/run_baselines.py` payload metadata | `RunConfig` plus `RunArtifactBundle` |
| raw run `results[]` | `ModelResult[]` |
| scored run `results[]` | `ScoreRecord[]` |
| scored run `summary` | `ReportSummary.overall`, `by_model`, and `manual_review` |
| `runs/example-run.json` | v1-compatible raw result artifact |
| `runs/example-run.scored.json` | v1-compatible scored result artifact |

## Migration Guidance

M2 should implement these contracts incrementally:

1. Keep reading current v1 dataset rows and run shapes.
2. Add v2-compatible aliases such as `case_id` while preserving `id`.
3. Emit `schema_version` consistently for new artifacts.
4. Introduce manifest writing next to existing raw and scored outputs before changing directory layout.
5. Let reports consume scored artifacts and bundle manifests instead of raw runner internals.

NGX-133 owns the richer dataset fields for ambiguity and pragmatic reasoning in [`docs/dataset-schema-v2.md`](dataset-schema-v2.md). This document reserves the top-level object boundary; the dataset schema document defines the detailed `evaluation`, `accepted_interpretations`, `ambiguity`, `cooperative_intent`, and `calibration` contents.
