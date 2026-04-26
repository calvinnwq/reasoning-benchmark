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
    "answered_count": 5,
    "missing_count": 0
  },
  "by_model": {
    "gpt-5.4": {
      "correct": 4,
      "incorrect": 1,
      "accuracy": 0.8
    }
  },
  "by_task_family": {
    "goal-grounding": {
      "case_count": 5,
      "accuracy": 0.8
    }
  },
  "by_failure_mode": {
    "optimizes for distance while ignoring the task object": {
      "case_count": 1,
      "accuracy": 1.0
    }
  },
  "manual_review": {
    "reasoning_scores_present": 0,
    "constraint_scores_present": 0,
    "notes_present": 0,
    "heuristic_flags_total": 0
  }
}
```

Required fields:

- `schema_version`
- `benchmark`
- `suite_id`
- `source_bundles`
- `generated_at`
- `overall`
- `by_model`

Optional but expected for M3 reporting:

- `by_task_family`
- `by_evaluation_mode`
- `by_failure_mode`
- `manual_review`

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
