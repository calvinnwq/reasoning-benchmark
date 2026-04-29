# Reasoning Benchmark v2 Dataset Schema

**Status:** M1 draft
**Scope owner:** NGX-133
**Depends on:** `docs/framework-v2.md`, `docs/contracts-v2.md`
**Purpose:** Extend the current question row contract so ambiguity and pragmatic reasoning cases can be evaluated without forcing every case into exact-answer scoring.

This document defines the richer `BenchmarkCase` fields now consumed by scoring and reporting. The current `data/questions.json` rows remain valid during the partial migration; migrated cases already carry v2 metadata, and new fields are additive until all cases are backfilled.

## Design Goals

- Preserve the short natural-language benchmark format.
- Keep exact final-answer scoring as the default path for current cases.
- Represent ambiguity explicitly instead of hiding it in free-text rationale.
- Support pragmatic and cooperative-intent cases where a literal answer may be defensible but not preferred.
- Make future reporting possible by task family, ambiguity class, evaluation mode, and calibration slice.
- Avoid adding non-stdlib dependencies or a separate schema compiler in M1.

## BenchmarkCase Shape

```json
{
  "schema_version": "2.0.0",
  "id": "SP-05",
  "task_family_id": "social-pragmatics",
  "category": "SP",
  "category_label": "Social / pragmatic reasoning",
  "provenance": "drafted",
  "prompt": "Someone asks, 'Do you mind opening the window?' If you don't mind, what should you do?",
  "expected_answer": "Open the window, or say 'not at all' and open it.",
  "accepted_variants": [
    "Open the window.",
    "Say you do not mind and open it."
  ],
  "accepted_interpretations": [
    {
      "id": "cooperative-request",
      "label": "Treat the utterance as a polite request",
      "preferred": true,
      "answer_requirements": [
        "indicates the window should be opened",
        "does not answer only the literal yes/no question"
      ]
    }
  ],
  "common_wrong_answer": "Say 'yes' and leave the window closed.",
  "rationale": "The phrase is normally a polite request to open the window, not only a question about whether the listener minds.",
  "failure_mode": "Literalist response to an indirect request.",
  "evaluation": {
    "mode": "hybrid",
    "answer_field": "answer",
    "reasoning_field": "reasoning",
    "accepted_variant_policy": "normalized_exact_or_configured_heuristic",
    "dimensions": [
      {
        "id": "answer_correctness",
        "label": "Final answer correctness",
        "type": "binary",
        "weight": 1.0,
        "auto_scored": true
      },
      {
        "id": "intent_alignment",
        "label": "Cooperative intent alignment",
        "type": "rubric",
        "weight": 1.0,
        "auto_scored": false
      }
    ]
  },
  "ambiguity": {
    "ambiguity_type": "pragmatic",
    "tags": ["indirect-request", "literal-vs-intended-meaning"],
    "clarification_expected": false,
    "literal_reading_defensible": true,
    "preferred_resolution": "cooperative-intent",
    "notes": "A model can acknowledge the literal wording, but the expected action follows the social request."
  },
  "cooperative_intent": {
    "expected_behavior": "answer the intended practical request",
    "literal_trap": "answering only whether the listener minds",
    "helpfulness_target": "open the window or agree and open it",
    "should_ask_clarifying_question": false
  },
  "calibration": {
    "difficulty": "starter",
    "split": "starter",
    "gold_confidence": "high",
    "human_disagreement_risk": "low",
    "review_status": "draft"
  },
  "metadata": {
    "tags": ["short-reasoning", "social-pragmatics"],
    "source_notes": ""
  }
}
```

## Required Fields

Current v1 rows must continue to provide:

- `id`
- `prompt`
- `expected_answer`
- `accepted_variants`
- `failure_mode`

V2 rows should additionally provide these fields after migration:

- `schema_version`
- `task_family_id`
- `evaluation`
- `calibration`

The fields below are optional by case type, but required when their concept applies:

- `accepted_interpretations` for cases with multiple defensible readings.
- `ambiguity` for ambiguity, pragmatic, or clarification-judgment cases.
- `cooperative_intent` for cases where the benchmark is testing helpful intended action instead of literal interpretation.

## Field Semantics

### `task_family_id`

Stable reporting group such as `goal-grounding`, `social-pragmatics`, `instruction-ambiguity`, `temporal-state`, `reference-resolution`, `physical-commonsense`, or `classic-riddle-override`.

The legacy `category` field remains for compatibility, but v2 reporting should group by `task_family_id`.

### `accepted_interpretations`

Lists the defensible readings for a prompt when exact answer strings are not enough.

Each entry should include:

- `id`: stable slug for the interpretation.
- `label`: human-readable interpretation.
- `preferred`: whether this is the benchmark's target interpretation.
- `answer_requirements`: observable requirements for credit.

Accepted interpretations should not turn every vague prompt into a valid case. If humans would split heavily and no preferred resolution is defensible, the case should be revised or excluded.

### `evaluation`

Defines how a result should be scored.

Supported `mode` values:

- `exact`: current normalized final-answer scoring.
- `rubric`: manual or future judge-based scoring over named dimensions.
- `hybrid`: exact final-answer scoring plus rubric dimensions.

`dimensions[]` names the scored properties for manual review and reporting. M2 can preserve current manual fields by mapping:

- `score_answer` to `answer_correctness`
- `score_reasoning` to `reasoning_quality`
- `score_constraint_extraction` to `constraint_extraction`

### `ambiguity`

Captures whether the prompt has an intended ambiguity and how the benchmark expects it to be resolved.

Recommended `ambiguity_type` values are descriptive slugs. Broad legacy values remain valid, and migrated instruction-ambiguity cases use concrete `*-ambiguous` values such as `reference-ambiguous`, `temporal-ambiguous`, `payment-ambiguous`, and `ticket-closure-ambiguous`.

Common broad values:

- `none`
- `lexical`
- `referential`
- `pragmatic`
- `underspecified`
- `classic-template`
- `test-condition`

`clarification_expected` should be `true` only when asking a clarifying question is the target behavior. Most current short-reasoning cases should set it to `false` because they contain enough information for a direct answer.

### `cooperative_intent`

Captures practical, helpful interpretation requirements for social and instruction-following cases.

Use it when the failure mode is not merely factual wrongness, but a model choosing an unhelpful literal reading despite a clear cooperative intent.

### `calibration`

Describes how the case should be used in suites and reports.

Recommended fields:

- `difficulty`: `starter`, `standard`, or `hard`.
- `split`: `smoke`, `starter`, `full`, `holdout`, or `calibration`.
- `gold_confidence`: `high`, `medium`, or `low`.
- `human_disagreement_risk`: `low`, `medium`, or `high`.
- `review_status`: `draft`, `reviewed`, or `retired`.

Named suite manifests in `data/suites/` are the source of truth for calibrated slices such as `starter` and `holdout`; per-case calibration metadata explains intended use in reports and future suite curation.

## Current-To-V2 Category Mapping

| Current category | V2 `task_family_id` | Default evaluation mode | Default ambiguity type |
|---|---|---|---|
| `GG` | `goal-grounding` | `exact` | `none` |
| `CR` | `classic-riddle-override` | `exact` | `classic-template` |
| `TW` | `temporal-state` | `exact` | `none` |
| `SP` | `social-pragmatics` | `hybrid` | `pragmatic` |
| `IA` | `instruction-ambiguity` | `hybrid` | `underspecified` |
| `PR` | `reference-resolution` | `exact` | `referential` |
| `MC` | `physical-commonsense` | `exact` | `test-condition` |
| `LP` | `literal-precision` | `exact` | `literal-trap` |

These defaults are migration helpers, not hard rules. Individual cases may override them when the prompt structure demands it.

## Migration Rules

1. Readers must continue accepting v1 rows without `schema_version`, `task_family_id`, `evaluation`, `ambiguity`, `cooperative_intent`, or `calibration`.
2. Writers that emit v2 rows should include `schema_version: "2.0.0"`.
3. The scorer should default missing `evaluation.mode` to `exact`.
4. Missing `task_family_id` may be derived from `category` during migration.
5. Missing `accepted_interpretations` means only `expected_answer` and `accepted_variants` are accepted.
6. Missing `ambiguity` means `ambiguity_type: "none"` unless category-derived defaults say otherwise.
7. Missing `calibration` means the case belongs only to the current full dataset until a suite explicitly selects it.

## Validation Checklist

Before a migrated case is marked `reviewed`:

- The prompt has a short, natural-language surface form.
- The preferred answer is supported by the prompt without hidden assumptions.
- Accepted variants cover wording differences but do not admit the common wrong answer.
- Ambiguity metadata explains any non-literal or multiple-reading behavior.
- Evaluation dimensions match what the scorer or manual reviewer can actually assess.
- Calibration metadata says whether the case belongs in smoke, starter, full, holdout, or calibration usage.
