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

V2 has eight core entities:

1. `Suite`: an ordered selection of cases.
2. `TaskFamily`: a reporting and curation grouping.
3. `BenchmarkCase`: one prompt plus answer and evaluation metadata.
4. `RunConfig`: one reproducible execution request.
5. `RunArtifactBundle`: the manifest tying a run's durable files together.
6. `ScoreRecord`: one evaluated model result for one case.
7. `ReportSummary`: aggregate metrics derived from scored records.
8. `MatrixIndex`: the top-level index for matrix baseline run artifacts.

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

### Persisted suite manifests

Calibrated suites are stored as plain JSON files under `data/suites/<suite_id>.json` and loaded by `scripts/suites.py`. The persisted shape uses `suite_id` instead of `id` to match how the runner reads suite identifiers from RunConfig matrices, and adds a `selection_rationale` field that explains why each case was included.

```json
{
  "schema_version": "2.0.0",
  "suite_id": "starter",
  "name": "Calibrated Starter Slice",
  "description": "...",
  "selection_rationale": "...",
  "case_ids": ["GG-01", "GG-02", "..."]
}
```

The current calibrated manifests are:

- `data/suites/starter.json` — high-signal default subset for frequent runs (2 cases per default family, 12 total).
- `data/suites/holdout.json` — disjoint default reserved set for cross-model comparison and future public reporting (2 cases per default family, 12 total).
- `data/suites/instruction-ambiguity.json` — optional hybrid/manual-review ambiguity pack, kept outside default suites until manual review scoring is mature enough for headline comparisons.

Required fields for persisted manifests: `schema_version`, `suite_id`, `name`, `description`, `selection_rationale`, `case_ids`. The suite loader rejects manifests whose `suite_id` does not match the filename, whose `case_ids` list is empty, or which contain duplicate or whitespace-padded ids.

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
    "max_cases": 5,
    "skip_scoring": false
  },
  "output": {
    "bundle_dir": "runs/baseline/gpt-5-4.smoke"
  },
  "matrix": {
    "suites": [
      {
        "suite_id": "smoke",
        "mode": "smoke"
      },
      {
        "suite_id": "starter",
        "case_ids": [
          "GG-01",
          "GG-02",
          "CR-01",
          "CR-02",
          "TW-01",
          "TW-02",
          "SP-01",
          "SP-02",
          "IA-01",
          "IA-02",
          "PR-01",
          "PR-02",
          "MC-01",
          "MC-02"
        ]
      }
    ]
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
It requires `suite_id` to be an exact, unpadded, non-empty string without path separators or `.`/`..`
traversal segments so run configs reference a stable suite identifier and artifact label.
It also requires `id` to be an exact, unpadded, non-empty string so artifacts preserve a stable
execution request identifier.
It requires `dataset.path` to be an exact, unpadded, non-empty string so configs do not preserve
ambiguous dataset references.
Relative RunConfig paths, including the config file path itself, `dataset.path`, and
`output.bundle_dir`, resolve from the repository root rather than the current working directory or
the config file's directory.
When supplied, `dataset.fingerprint.algorithm` and `dataset.fingerprint.value` must also be exact,
unpadded strings before the value is compared with the dataset's SHA-256 hash.
It requires `output.bundle_dir` to be an exact, unpadded, non-empty string so configs do not write
artifacts into ambiguous output locations.
It requires model ids, whether listed directly or inside model objects, to be exact, unpadded,
non-empty strings from the current baseline runner set: `gpt-5.4`, `sonnet-4.6`, or `qwen3.5-9b`.
It requires `execution.mode` to be an exact, unpadded, non-empty string without path separators or
`.`/`..` traversal segments when present so configs do not preserve ambiguous suite mode selections
or artifact labels.
Without an embedded `suite.case_ids` list or `matrix.suites`, `execution.mode` must be `smoke` or
`full`; with `suite.case_ids` or `matrix.suites`, custom top-level mode names are allowed. Explicit
`suite.case_ids` run in the supplied order; matrix suite entries control each cell's selection.
When `matrix` is supplied, it must be an object with a non-empty `suites` list, and the runner
executes every suite/model cell. Each matrix suite must declare a unique exact `suite_id` without
path separators or `.`/`..` traversal segments, may declare an exact `mode` without path separators
or `.`/`..` traversal segments, and may declare
non-empty unique exact `case_ids`. Matrix suites without `case_ids` must use `smoke` or `full` as
their mode; if `mode` is omitted, the suite id is used as the mode.
Top-level `suite.case_ids` cannot be combined with `matrix.suites`; set `case_ids` per matrix suite
instead.
`execution.seed` shuffles only `smoke` or `full` selections, and `execution.max_cases` truncates the
selected cases after mode or explicit-suite selection.
It requires `execution.timeout_seconds` to be a finite positive number and `execution.skip_scoring`
to be a boolean when supplied.
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

### Forward-compatible extension hooks

`RunConfig` may carry an optional top-level `extensions` block that reserves namespaces for future
expansion packs without activating them in the current short-reasoning core. The reserved namespaces
are `tool_use` and `multi_agent`; unknown namespaces are rejected so a typo cannot silently disable
the forward-compatibility check. Each declared namespace must be a JSON object with an explicit
`enabled` boolean. Until the corresponding milestone wires runner support, `enabled` must be `false`
so configs can persist planned extension metadata without referring to code that does not exist yet.
Anything else inside a namespace payload is opaque to the validator; individual expansion packs own
their own schema in their own milestone.

```json
{
  "extensions": {
    "tool_use": {"enabled": false, "notes": "reserved for M5 tool-use pack"},
    "multi_agent": {"enabled": false}
  }
}
```

The validator lives in `scripts/extensions.py` (`RESERVED_EXTENSION_NAMESPACES`,
`validate_extensions_block`) and is wired into RunConfig parsing in `scripts/run_baselines.py`.

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
    "name": "python3",
    "command": "python3 '[arguments omitted]'",
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

For live provider-backed runs, `adapter.name` records the executed program basename and
`adapter.command` redacts arguments as `program '[arguments omitted]'` so artifact audit metadata
does not persist adapter arguments or secrets.

## ScoreRecord

`ScoreRecord` is one evaluated result. It must preserve current manual review fields while adding enough trace data for auditability.

```json
{
  "schema_version": "2.0.0",
  "case_id": "GG-01",
  "model": "gpt-5.4",
  "evaluation_mode": "exact",
  "task_family_id": "goal-grounding",
  "failure_mode": "optimizes for distance while ignoring the task object",
  "ambiguity_type": "none",
  "clarification_expected": false,
  "calibration_difficulty": "starter",
  "calibration_split": "smoke",
  "gold_confidence": "high",
  "human_disagreement_risk": "low",
  "review_status": "reviewed",
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
    ],
    "dimensions": []
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
- `task_family_id`
- `failure_mode`
- `ambiguity_type`
- `score_answer`
- `score_reasoning`
- `score_constraint_extraction`
- `penalties`
- `notes`
- `scoring_status`
- `score_answer_normalized`
- `scored_at`

Dataset-backed records also preserve `clarification_expected`, calibration fields
(`calibration_difficulty`, `calibration_split`, `gold_confidence`, `human_disagreement_risk`, and
`review_status`), and any available ambiguity or cooperative-intent review context such as
`ambiguity_tags`, `literal_reading_defensible`, `preferred_resolution`, `ambiguity_notes`,
`accepted_interpretations`, and `cooperative_intent`.

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
Baseline runs write the `ReportSummary` as a sibling `*.summary.json` artifact copied from the scored output's embedded `summary` object. When `execution.skip_scoring` is true, baseline runs write only the raw artifact, skip the scored artifact, summary sidecar, and bundle manifest, and remove any stale manifest for that model/mode.
Matrix baseline runs write per-suite raw, scored, summary, and manifest artifacts under suite
subdirectories, plus a top-level `matrix.index.json` artifact. The index records the configured
models and suites, one `cells[]` entry per suite/model pair, relative paths for each cell artifact,
optional per-cell `summary_metrics`, optional per-cell `error` objects, and scored rollups in
`model_summaries`, `suite_summaries`, and `overall_summary` when scoring is enabled. Failed matrix
cells are captured in the index and do not prevent later cells from running.
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

## MatrixIndex

`matrix.index.json` is the top-level artifact for matrix baseline runs. It records every configured suite/model cell, the cell artifact paths, any cell failure, and scored rollups when scoring is enabled.

```json
{
  "schema_version": "1.0.0",
  "benchmark": "reasoning-benchmark",
  "run_config": "examples/configs/matrix-baseline.config.json",
  "models": ["gpt-5.4", "sonnet-4.6"],
  "suites": [
    {
      "suite_id": "smoke",
      "mode": "smoke",
      "case_ids": null
    }
  ],
  "cells": [
    {
      "suite_id": "smoke",
      "model": "gpt-5.4",
      "mode": "smoke",
      "raw_results": "smoke/gpt-5-4.smoke.raw.json",
      "scored_results": "smoke/gpt-5-4.smoke.scored.json",
      "report_summary": "smoke/gpt-5-4.smoke.summary.json",
      "manifest": "smoke/gpt-5-4.smoke.manifest.json",
      "summary_metrics": null,
      "error": null
    }
  ],
  "model_summaries": null,
  "suite_summaries": null,
  "overall_summary": null,
  "dataset": {
    "path": "data/questions.json",
    "fingerprint": {
      "algorithm": "sha256",
      "value": "..."
    }
  },
  "created_at": "2026-04-26T00:00:00Z",
  "completed_at": "2026-04-26T00:00:02Z"
}
```

Required fields:

- `schema_version`
- `benchmark`
- `run_config`
- `models`
- `suites`
- `cells`
- `model_summaries`
- `suite_summaries`
- `overall_summary`
- `dataset`
- `created_at`
- `completed_at`

Each `cells[]` entry includes `suite_id`, `model`, `mode`, `raw_results`, `scored_results`,
`report_summary`, `manifest`, `summary_metrics`, and `error`. When scoring is skipped, scored
artifact paths and summaries are `null`; when a cell fails, `error` records the exception type and
message. Failed cells may still list deterministic artifact paths that were planned for that cell;
consumers must treat non-null `error` as authoritative and not assume those paths exist.

When scoring is enabled, `summary_metrics` is the cell's report-summary object. `model_summaries`
is keyed by model and each value contains `suite_count` plus `auto_scored.total`, `correct`,
`incorrect`, and `accuracy`. `suite_summaries` is keyed by suite id and each value contains
`model_count` plus the same `auto_scored` fields. `overall_summary` contains `cell_count` plus the
same `auto_scored` fields. Rollups include only cells that produced a report-summary object with
`auto_scored`; cells with errors, missing summaries, or summaries without `auto_scored` are omitted,
so `suite_count`, `model_count`, and `cell_count` can be lower than the configured matrix dimensions.

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
  "by_evaluation_mode": {
    "exact": {
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
  "by_model_task_family": {
    "gpt-5.4": {
      "goal-grounding": {
        "total": 5,
        "auto_scored": 5,
        "correct": 4,
        "incorrect": 1,
        "accuracy": 0.8,
        "manual_review_required": 0,
        "case_count": 5
      }
    }
  },
  "by_model_failure_mode": {
    "gpt-5.4": {
      "optimizes for distance while ignoring the task object": {
        "total": 1,
        "auto_scored": 1,
        "correct": 1,
        "incorrect": 0,
        "accuracy": 1.0,
        "manual_review_required": 0,
        "case_count": 1
      }
    }
  },
  "by_model_ambiguity_type": {
    "gpt-5.4": {
      "none": {
        "total": 5,
        "auto_scored": 5,
        "correct": 4,
        "incorrect": 1,
        "accuracy": 0.8,
        "manual_review_required": 0,
        "case_count": 5
      }
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
- `by_evaluation_mode`
- `by_task_family`
- `by_failure_mode`
- `by_ambiguity_type`
- `by_calibration_split`
- `by_model_task_family`
- `by_model_failure_mode`
- `by_model_ambiguity_type`
- `manual_review`
- `heuristic_flags`

Per-bucket summaries in `by_model`, `by_evaluation_mode`, `by_task_family`, `by_failure_mode`, `by_ambiguity_type`, and `by_calibration_split` use the same shape: `total`, `auto_scored`, `correct`, `incorrect`, `accuracy`, `manual_review_required`, and `case_count`.

Cross-tab summaries in `by_model_task_family`, `by_model_failure_mode`, and `by_model_ambiguity_type` are nested two-level objects keyed by model id then by the secondary dimension. Each leaf bucket uses the same shape as the single-dimension breakdowns. Cases with missing metadata fall under the `unknown` key at either level. These cross-tabs let reports compare models within the same task family, ambiguity class, or failure mode without rebuilding from scored records.

## Current-To-V2 Mapping

| Current field or artifact | V2 destination |
|---|---|
| `data/questions.json[]` | `BenchmarkCase` |
| `category` | `legacy_category`, then `task_family_id` after migration |
| `scripts/benchmark_contract.py::PROMPT_CONTRACT` | embedded `prompt_contract` |
| `scripts/run_baselines.py` payload metadata | `RunConfig` plus `RunArtifactBundle` |
| `runs/baseline/matrix.index.json` | `MatrixIndex` |
| raw run `results[]` | `ModelResult[]` |
| scored run `results[]` | `ScoreRecord[]` |
| scored run `summary` | `ReportSummary.overall`, `auto_scored`, `manual_only`, `by_model`, `by_evaluation_mode`, `by_task_family`, `by_failure_mode`, `by_ambiguity_type`, `by_calibration_split`, `by_model_task_family`, `by_model_failure_mode`, `by_model_ambiguity_type`, `manual_review`, and `heuristic_flags` |
| `runs/example-run.json` | v1-compatible raw result artifact |
| `runs/example-run.scored.json` | v1-compatible scored result artifact |

## Migration Guidance

M3 implements these contracts incrementally:

1. Keep reading current v1 dataset rows and run shapes.
2. Add v2-compatible aliases such as `case_id` while preserving `id`.
3. Emit `schema_version` consistently for new artifacts.
4. Write baseline `RunArtifactBundle` manifests next to existing raw, scored, and report-summary outputs.
5. Emit `MatrixIndex` for matrix baseline runs.
6. Let reports consume scored artifacts and bundle manifests instead of raw runner internals.

NGX-133 owns the richer dataset fields for ambiguity and pragmatic reasoning in [`docs/dataset-schema-v2.md`](dataset-schema-v2.md). This document reserves the top-level object boundary; the dataset schema document defines the detailed `evaluation`, `accepted_interpretations`, `ambiguity`, `cooperative_intent`, and `calibration` contents.
