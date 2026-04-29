#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import unicodedata

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET_PATH = REPO_ROOT / "data" / "questions.json"
SUPPORTED_EVALUATION_MODES = {"exact", "rubric", "hybrid"}
ANSWER_CORRECTNESS_DIMENSION_IDS = {"answer_correctness", "score_answer", "final_answer_correctness"}
DEFAULT_ACCEPTED_VARIANT_POLICY = "normalized_exact_or_configured_heuristic"
NORMALIZED_EXACT_ACCEPTED_VARIANT_POLICY = "normalized_exact"
CATEGORY_TASK_FAMILY_IDS = {
    "GG": "goal-grounding",
    "CR": "classic-riddle-override",
    "TW": "temporal-state",
    "SP": "social-pragmatics",
    "IA": "instruction-ambiguity",
    "PR": "reference-resolution",
    "MC": "physical-commonsense",
    "LP": "literal-precision",
}
CATEGORY_AMBIGUITY_TYPES = {
    "GG": "none",
    "CR": "classic-template",
    "TW": "none",
    "SP": "pragmatic",
    "IA": "underspecified",
    "PR": "referential",
    "MC": "test-condition",
    "LP": "literal-trap",
}

BINARY_TOKEN_LOOKAHEAD = 6
BINARY_ANSWER_MAX_TOKENS = 4
BINARY_EXPLANATION_SHARED_SPAN_MIN_TOKENS = 4
BINARY_EXPLANATION_LONG_SHARED_SPAN_MIN_TOKENS = 6
HEURISTIC_SPAN_MAX_TOKENS = 10
CONCISE_PREFIX_MAX_TOKENS = 3


@dataclass(frozen=True)
class MatchResult:
    score: int
    matched: bool
    reason: str
    matched_by: str
    heuristic: bool
    expected: str
    expected_normalized: str
    answer: str
    answer_normalized: str


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)

    value = unicodedata.normalize("NFKC", value)
    value = value.strip().lower()

    if not value:
        return ""

    replacements = {
        "“": '"',
        "”": '"',
        "’": "'",
        "‘": "'",
        "`": "'",
        "–": "-",
        "—": "-",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)

    contraction_patterns = (
        (r"\b(can)not\b", r"\1 not"),
        (r"\b(won)'t\b", r"will not"),
        (r"\b(can)'t\b", r"can not"),
        (r"\b([a-z]+)n't\b", r"\1 not"),
        (r"\b([a-z]+)'re\b", r"\1 are"),
        (r"\b([a-z]+)'ve\b", r"\1 have"),
        (r"\b([a-z]+)'ll\b", r"\1 will"),
        (r"\b([a-z]+)'d\b", r"\1 would"),
        (r"\b(i)'m\b", r"\1 am"),
        (r"\b([a-z]+)'s\b", r"\1 s"),
    )
    for pattern, replacement in contraction_patterns:
        value = re.sub(pattern, replacement, value)

    spelling_variants = {
        "signalling": "signaling",
        "signalled": "signaled",
        "metres": "meters",
        "metre": "meter",
    }
    for old, new in spelling_variants.items():
        value = value.replace(old, new)

    # Keep words and spaces only; turn punctuation into spaces so suffixes do not block short matches.
    value = re.sub(r"[^a-z0-9\s]", " ", value.lower())
    value = re.sub(r"\s+", " ", value).strip()
    return value


def trim_prefillers(text: str) -> str:
    leading_phrases = (
        "the answer is",
        "the answer may be",
        "i think",
        "i believe",
        "i guess",
        "i would say",
        "it is",
        "it might be",
        "probably",
    )

    result = normalize_text(text)
    for _ in range(3):
        changed = False
        for prefix in leading_phrases:
            pref = f"{prefix} "
            if result.startswith(pref):
                result = result[len(pref) :].strip()
                changed = True
        if not changed:
            break
    return result


def extract_binary_token(text: str) -> Optional[str]:
    # Explicit yes/no handling should be deterministic for short answers.
    tokens = normalize_text(trim_prefillers(text)).split()
    for token in tokens[:BINARY_TOKEN_LOOKAHEAD]:
        if token == "yes":
            return "yes"
        if token == "no":
            return "no"
        if token == "true":
            return "yes"
        if token == "false":
            return "no"
    return None


def token_sequence(text: str) -> Sequence[str]:
    return normalize_text(text).split()


def contains_expected_as_contiguous_span(answer_tokens: Sequence[str], expected_tokens: Sequence[str]) -> bool:
    if not expected_tokens or not answer_tokens:
        return False
    if len(expected_tokens) > len(answer_tokens):
        return False
    if len(expected_tokens) == 1:
        return expected_tokens[0] in answer_tokens

    needle = tuple(expected_tokens)
    haystack = tuple(answer_tokens)
    for index in range(len(haystack) - len(needle) + 1):
        if haystack[index : index + len(needle)] == needle:
            return True
    return False


def starts_with_token_sequence(candidate_tokens: Sequence[str], prefix_tokens: Sequence[str]) -> bool:
    if not candidate_tokens or not prefix_tokens:
        return False
    if len(prefix_tokens) > len(candidate_tokens):
        return False
    return tuple(candidate_tokens[: len(prefix_tokens)]) == tuple(prefix_tokens)


def strip_soft_determiners(tokens: Sequence[str]) -> List[str]:
    soft_words = {"a", "an", "the", "my", "your", "our", "his", "her", "their", "you", "now"}
    return [token for token in tokens if token not in soft_words]


def build_candidate_norms(expected_text: str, accepted_variants: Iterable[Any]) -> List[str]:
    candidates: List[str] = []
    for raw in [expected_text, *accepted_variants]:
        if not isinstance(raw, str):
            continue
        normalized = normalize_text(raw)
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    return candidates


def build_answer_norms(answer_text: str) -> List[str]:
    primary = trim_prefillers(answer_text)
    candidates: List[str] = []
    if primary:
        candidates.append(primary)

    tokens = primary.split()
    if len(tokens) > 1 and tokens[0] in {"yes", "no"}:
        stripped = " ".join(tokens[1:]).strip()
        if stripped and stripped not in candidates:
            candidates.append(stripped)
    return candidates


def is_concise_binary_answer(answer_text: str) -> bool:
    tokens = normalize_text(trim_prefillers(answer_text)).split()
    if not tokens:
        return False
    if tokens[0] not in {"yes", "no", "true", "false"}:
        return False
    return len(tokens) == 1


def binary_explanation_tokens(text: str) -> List[str]:
    tokens = normalize_text(trim_prefillers(text)).split()
    if tokens and tokens[0] in {"yes", "no", "true", "false"}:
        return tokens[1:]
    return tokens


def longest_shared_contiguous_span(left: Sequence[str], right: Sequence[str]) -> int:
    if not left or not right:
        return 0

    longest = 0
    for left_index in range(len(left)):
        for right_index in range(len(right)):
            span = 0
            while (
                left_index + span < len(left)
                and right_index + span < len(right)
                and left[left_index + span] == right[right_index + span]
            ):
                span += 1
            if span > longest:
                longest = span
    return longest


def shared_contiguous_spans(left: Sequence[str], right: Sequence[str]) -> List[Tuple[int, int, int]]:
    spans: List[Tuple[int, int, int]] = []
    if not left or not right:
        return spans

    for left_index in range(len(left)):
        for right_index in range(len(right)):
            span = 0
            while (
                left_index + span < len(left)
                and right_index + span < len(right)
                and left[left_index + span] == right[right_index + span]
            ):
                span += 1
            if span >= BINARY_EXPLANATION_SHARED_SPAN_MIN_TOKENS:
                spans.append((left_index, right_index, span))
    return spans


def starts_with_contrastive_tail(tokens: Sequence[str]) -> bool:
    if not tokens:
        return False
    return tokens[0] in {
        "actually",
        "although",
        "but",
        "except",
        "however",
        "instead",
        "though",
        "yet",
    }


def allows_binary_tail_substitution(
    answer_index: int,
    candidate_index: int,
    span_length: int,
    answer_remaining: int,
    candidate_remaining: int,
) -> bool:
    if answer_index != candidate_index:
        return False
    if answer_index > 1:
        return False
    if span_length != BINARY_EXPLANATION_LONG_SHARED_SPAN_MIN_TOKENS:
        return False
    return 0 < answer_remaining <= 3 and 0 < candidate_remaining <= 3


def has_anchored_binary_explanation_overlap(answer_tokens: Sequence[str], candidate_tokens: Sequence[str]) -> bool:
    generic_tokens = {
        "a",
        "an",
        "are",
        "asking",
        "be",
        "being",
        "can",
        "do",
        "for",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "should",
        "still",
        "that",
        "the",
        "they",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "why",
        "you",
        "your",
    }

    for answer_index, candidate_index, span_length in shared_contiguous_spans(answer_tokens, candidate_tokens):
        span_tokens = answer_tokens[answer_index : answer_index + span_length]
        if not any(token not in generic_tokens for token in span_tokens):
            continue
        if answer_index != candidate_index and (answer_index == 0 or candidate_index == 0):
            continue
        answer_remaining = len(answer_tokens) - (answer_index + span_length)
        candidate_remaining = len(candidate_tokens) - (candidate_index + span_length)
        answer_tail = answer_tokens[answer_index + span_length :]
        candidate_tail = candidate_tokens[candidate_index + span_length :]
        if answer_index == candidate_index and (answer_remaining == 0) != (candidate_remaining == 0):
            continue
        if starts_with_contrastive_tail(answer_tail) or starts_with_contrastive_tail(candidate_tail):
            continue
        if span_length >= BINARY_EXPLANATION_LONG_SHARED_SPAN_MIN_TOKENS and (
            answer_remaining > 2 or candidate_remaining > 2
        ):
            if allows_binary_tail_substitution(
                answer_index,
                candidate_index,
                span_length,
                answer_remaining,
                candidate_remaining,
            ):
                return True
            continue
        if answer_remaining == 0 and candidate_remaining == 0:
            if max(answer_index, candidate_index) > 4:
                continue
            return True
    return False


def has_binary_explanation_overlap(answer_text: str, candidate_text: str) -> bool:
    answer_tokens = binary_explanation_tokens(answer_text)
    candidate_tokens = binary_explanation_tokens(candidate_text)
    if not answer_tokens or not candidate_tokens:
        return False

    if has_anchored_binary_explanation_overlap(answer_tokens, candidate_tokens):
        return True

    stripped_answer_tokens = strip_soft_determiners(answer_tokens)
    stripped_candidate_tokens = strip_soft_determiners(candidate_tokens)
    return has_anchored_binary_explanation_overlap(stripped_answer_tokens, stripped_candidate_tokens)


def score_single_answer(
    answer: Any,
    expected_text: str,
    accepted_variants: Iterable[Any],
    accepted_variant_policy: str = DEFAULT_ACCEPTED_VARIANT_POLICY,
) -> MatchResult:
    raw_answer = "" if answer is None else str(answer).strip()
    raw_answer_norm = normalize_text(raw_answer)
    answer_norms = build_answer_norms(raw_answer)
    answer_norm = answer_norms[0] if answer_norms else raw_answer_norm
    expected_norm = normalize_text(expected_text)
    candidate_norms = build_candidate_norms(expected_text, accepted_variants)

    expected_binary = extract_binary_token(expected_text)
    if not raw_answer_norm:
        return MatchResult(
            score=0,
            matched=False,
            reason="missing_answer",
            matched_by="missing",
            heuristic=False,
            expected=expected_text,
            expected_normalized=expected_norm,
            answer=raw_answer,
            answer_normalized=answer_norm,
        )

    if accepted_variant_policy == NORMALIZED_EXACT_ACCEPTED_VARIANT_POLICY:
        if raw_answer_norm in candidate_norms:
            return MatchResult(
                score=1,
                matched=True,
                reason="exact_normalized_match",
                matched_by="exact",
                heuristic=False,
                expected=expected_text,
                expected_normalized=expected_norm,
                answer=raw_answer,
                answer_normalized=raw_answer_norm,
            )
        return MatchResult(
            score=0,
            matched=False,
            reason="no_match_after_normalization",
            matched_by="none",
            heuristic=False,
            expected=expected_text,
            expected_normalized=expected_norm,
            answer=raw_answer,
            answer_normalized=raw_answer_norm,
        )

    for normalized_answer in answer_norms:
        if normalized_answer in candidate_norms:
            return MatchResult(
                score=1,
                matched=True,
                reason="exact_normalized_match",
                matched_by="exact",
                heuristic=False,
                expected=expected_text,
                expected_normalized=expected_norm,
                answer=raw_answer,
                answer_normalized=normalized_answer,
            )

    if expected_binary in {"yes", "no"} and accepted_variant_policy != NORMALIZED_EXACT_ACCEPTED_VARIANT_POLICY:
        answer_binary = extract_binary_token(raw_answer)
        if answer_binary is None:
            return MatchResult(
                score=0,
                matched=False,
                reason="expected_binary_not_detected",
                matched_by="binary_missing",
                heuristic=False,
                expected=expected_text,
                expected_normalized=expected_norm,
                answer=raw_answer,
                answer_normalized=answer_norm,
            )
        if answer_binary != expected_binary:
            return MatchResult(
                score=0,
                matched=False,
                reason="binary_mismatch",
                matched_by="binary_mismatch",
                heuristic=False,
                expected=expected_text,
                expected_normalized=expected_norm,
                answer=raw_answer,
                answer_normalized=answer_norm,
            )
        if is_concise_binary_answer(raw_answer):
            return MatchResult(
                score=1,
                matched=True,
                reason="expected_binary_answer_detected",
                matched_by="binary_match",
                heuristic=False,
                expected=expected_text,
                expected_normalized=expected_norm,
                answer=raw_answer,
                answer_normalized=answer_norm,
            )
        for candidate_text in [expected_text, *accepted_variants]:
            if isinstance(candidate_text, str) and has_binary_explanation_overlap(raw_answer, candidate_text):
                return MatchResult(
                    score=1,
                    matched=True,
                    reason="expected_binary_explanation_overlap",
                    matched_by="binary_overlap",
                    heuristic=True,
                    expected=expected_text,
                    expected_normalized=expected_norm,
                    answer=raw_answer,
                    answer_normalized=answer_norm,
                )

    for normalized_answer in answer_norms:
        answer_tokens = token_sequence(normalized_answer)
        if len(answer_tokens) <= HEURISTIC_SPAN_MAX_TOKENS:
            for candidate_norm in candidate_norms:
                candidate_tokens = token_sequence(candidate_norm)
                if len(candidate_tokens) > 1 and contains_expected_as_contiguous_span(answer_tokens, candidate_tokens):
                    return MatchResult(
                        score=1,
                        matched=True,
                        reason="candidate_phrase_as_contiguous_span",
                        matched_by="heuristic_subsequence",
                        heuristic=True,
                        expected=expected_text,
                        expected_normalized=expected_norm,
                        answer=raw_answer,
                        answer_normalized=normalized_answer,
                    )

                stripped_answer_tokens = strip_soft_determiners(answer_tokens)
                stripped_candidate_tokens = strip_soft_determiners(candidate_tokens)
                if len(stripped_candidate_tokens) > 1 and contains_expected_as_contiguous_span(stripped_answer_tokens, stripped_candidate_tokens):
                    return MatchResult(
                        score=1,
                        matched=True,
                        reason="candidate_match_after_soft_determiner_stripping",
                        matched_by="heuristic_subsequence",
                        heuristic=True,
                        expected=expected_text,
                        expected_normalized=expected_norm,
                        answer=raw_answer,
                        answer_normalized=normalized_answer,
                    )

    for normalized_answer in answer_norms:
        answer_tokens = token_sequence(normalized_answer)
        if 0 < len(answer_tokens) <= CONCISE_PREFIX_MAX_TOKENS and answer_tokens[0] not in {"yes", "no"}:
            for candidate_norm in candidate_norms:
                candidate_tokens = token_sequence(candidate_norm)
                if starts_with_token_sequence(candidate_tokens, answer_tokens):
                    return MatchResult(
                        score=1,
                        matched=True,
                        reason="concise_prefix_of_accepted_answer",
                        matched_by="heuristic_prefix",
                        heuristic=True,
                        expected=expected_text,
                        expected_normalized=expected_norm,
                        answer=raw_answer,
                        answer_normalized=normalized_answer,
                    )

    return MatchResult(
        score=0,
        matched=False,
        reason="no_match_after_normalization",
        matched_by="none",
        heuristic=False,
        expected=expected_text,
        expected_normalized=expected_norm,
        answer=raw_answer,
        answer_normalized=answer_norm,
    )


def coerce_penalties(value: Any) -> List[dict]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [{"value": value, "is_heuristic": True, "note": "Converted non-list penalties value"}]


def coerce_scoring_fields(record: Dict[str, Any]) -> Dict[str, Any]:
    coerced = dict(record)
    model = coerced.get("model")
    if not isinstance(model, str) or not model.strip():
        coerced["model"] = "unknown"
    coerced.setdefault("score_reasoning", None)
    coerced.setdefault("score_constraint_extraction", None)
    coerced["penalties"] = coerce_penalties(coerced.get("penalties"))
    coerced.setdefault("notes", "")
    return coerced


def evaluation_mode_for(question: Dict[str, Any]) -> str:
    evaluation = question.get("evaluation")
    if not isinstance(evaluation, dict):
        return "exact"

    mode = evaluation.get("mode")
    if not isinstance(mode, str) or not mode.strip():
        return "exact"
    return mode.strip().lower()


def answer_field_for(question: Dict[str, Any]) -> str:
    evaluation = question.get("evaluation")
    if not isinstance(evaluation, dict):
        return "answer"

    answer_field = evaluation.get("answer_field")
    if not isinstance(answer_field, str) or not answer_field.strip():
        return "answer"
    return answer_field.strip()


def reasoning_field_for(question: Dict[str, Any]) -> str:
    evaluation = question.get("evaluation")
    if not isinstance(evaluation, dict):
        return "reasoning"

    reasoning_field = evaluation.get("reasoning_field")
    if not isinstance(reasoning_field, str) or not reasoning_field.strip():
        return "reasoning"
    return reasoning_field.strip()


def accepted_variant_policy_for(question: Dict[str, Any]) -> str:
    evaluation = question.get("evaluation")
    if not isinstance(evaluation, dict):
        return DEFAULT_ACCEPTED_VARIANT_POLICY

    policy = evaluation.get("accepted_variant_policy")
    if not isinstance(policy, str) or not policy.strip():
        return DEFAULT_ACCEPTED_VARIANT_POLICY
    return policy.strip()


def task_family_id_for(question: Dict[str, Any]) -> str:
    task_family_id = question.get("task_family_id")
    if isinstance(task_family_id, str) and task_family_id.strip():
        return task_family_id.strip()

    category = question.get("category")
    if isinstance(category, str):
        return CATEGORY_TASK_FAMILY_IDS.get(category.strip().upper(), "unknown")
    return "unknown"


def ambiguity_type_for(question: Dict[str, Any]) -> str:
    ambiguity = question.get("ambiguity")
    if isinstance(ambiguity, dict):
        ambiguity_type = ambiguity.get("ambiguity_type")
        if isinstance(ambiguity_type, str) and ambiguity_type.strip():
            return ambiguity_type.strip()

    category = question.get("category")
    if isinstance(category, str):
        return CATEGORY_AMBIGUITY_TYPES.get(category.strip().upper(), "unknown")
    return "unknown"


def clarification_expected_for(question: Dict[str, Any]) -> bool:
    ambiguity = question.get("ambiguity")
    if not isinstance(ambiguity, dict):
        return False
    return ambiguity.get("clarification_expected") is True


def ambiguity_review_context_for(question: Dict[str, Any]) -> Dict[str, Any]:
    context: Dict[str, Any] = {}
    ambiguity = question.get("ambiguity")
    if isinstance(ambiguity, dict):
        tags = ambiguity.get("tags")
        if isinstance(tags, list):
            context["ambiguity_tags"] = copy.deepcopy(tags)

        literal_reading_defensible = ambiguity.get("literal_reading_defensible")
        if isinstance(literal_reading_defensible, bool):
            context["literal_reading_defensible"] = literal_reading_defensible

        preferred_resolution = ambiguity.get("preferred_resolution")
        if isinstance(preferred_resolution, str) and preferred_resolution.strip():
            context["preferred_resolution"] = preferred_resolution.strip()

        notes = ambiguity.get("notes")
        if isinstance(notes, str) and notes.strip():
            context["ambiguity_notes"] = notes.strip()

    accepted_interpretations = question.get("accepted_interpretations")
    if isinstance(accepted_interpretations, list):
        context["accepted_interpretations"] = copy.deepcopy(accepted_interpretations)

    cooperative_intent = question.get("cooperative_intent")
    if isinstance(cooperative_intent, dict):
        context["cooperative_intent"] = copy.deepcopy(cooperative_intent)
    return context


def calibration_metadata_for(question: Dict[str, Any]) -> Dict[str, str]:
    calibration = question.get("calibration")
    if not isinstance(calibration, dict):
        calibration = {}

    def field(name: str, default: str) -> str:
        value = calibration.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return default

    return {
        "calibration_difficulty": field("difficulty", "unknown"),
        "calibration_split": field("split", "full"),
        "gold_confidence": field("gold_confidence", "unknown"),
        "human_disagreement_risk": field("human_disagreement_risk", "unknown"),
        "review_status": field("review_status", "unknown"),
    }


def coerce_dimension_weight(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0
    if isinstance(value, (int, float)):
        return float(value)
    return 1.0


def normalize_dimension(raw_dimension: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw_dimension, str):
        dimension_id = raw_dimension.strip()
        if not dimension_id:
            return None
        dimension_type = "binary" if dimension_id in ANSWER_CORRECTNESS_DIMENSION_IDS else "rubric"
        return {
            "id": dimension_id,
            "label": dimension_id.replace("_", " "),
            "type": dimension_type,
            "weight": 1.0,
            "auto_scored": dimension_id in ANSWER_CORRECTNESS_DIMENSION_IDS,
        }

    if not isinstance(raw_dimension, dict):
        return None

    dimension_id = raw_dimension.get("id")
    if not isinstance(dimension_id, str) or not dimension_id.strip():
        return None

    dimension_id = dimension_id.strip()
    raw_type = raw_dimension.get("type")
    dimension_type = raw_type.strip().lower() if isinstance(raw_type, str) and raw_type.strip() else "rubric"
    raw_label = raw_dimension.get("label")
    label = raw_label if isinstance(raw_label, str) and raw_label.strip() else dimension_id.replace("_", " ")
    auto_scored = raw_dimension.get("auto_scored")
    if not isinstance(auto_scored, bool):
        auto_scored = dimension_id in ANSWER_CORRECTNESS_DIMENSION_IDS

    return {
        "id": dimension_id,
        "label": label,
        "type": dimension_type,
        "weight": coerce_dimension_weight(raw_dimension.get("weight")),
        "auto_scored": auto_scored,
    }


def evaluation_dimensions_for(question: Dict[str, Any]) -> List[Dict[str, Any]]:
    evaluation = question.get("evaluation")
    if not isinstance(evaluation, dict):
        return []

    raw_dimensions = evaluation.get("dimensions")
    if not isinstance(raw_dimensions, list):
        return []

    dimensions = []
    for raw_dimension in raw_dimensions:
        dimension = normalize_dimension(raw_dimension)
        if dimension is not None:
            dimensions.append(dimension)
    return dimensions


def score_dimensions(
    dimensions: Sequence[Dict[str, Any]],
    evaluation_mode: str,
    answer_score: Optional[int],
) -> List[Dict[str, Any]]:
    scored_dimensions = []
    for dimension in dimensions:
        scored = dict(dimension)
        can_auto_score_answer = (
            evaluation_mode in {"exact", "hybrid"}
            and dimension["id"] in ANSWER_CORRECTNESS_DIMENSION_IDS
            and dimension["auto_scored"] is True
            and answer_score in {0, 1}
        )
        if can_auto_score_answer:
            scored["score"] = answer_score
            scored["status"] = "auto_scored"
        else:
            scored["score"] = None
            scored["status"] = "manual_review_required"
        scored_dimensions.append(scored)
    return scored_dimensions


def normalize_run_payload(payload: Any) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if isinstance(payload, list):
        return {}, [dict(item) for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        raise ValueError("Unsupported run file structure; expected an object or a list of records")

    for list_key in ("results", "runs", "items", "answers"):
        records = payload.get(list_key)
        if isinstance(records, list):
            meta = {k: v for k, v in payload.items() if k != list_key}
            return meta, [dict(item) for item in records if isinstance(item, dict)]

    raise ValueError("Unsupported run file shape: missing top-level list of results")


def load_dataset(dataset_path: Path) -> Dict[str, Dict[str, Any]]:
    with dataset_path.open("r", encoding="utf-8") as stream:
        rows = json.load(stream)
    if not isinstance(rows, list):
        raise ValueError("Dataset must be a JSON list.")
    return {str(row["id"]): row for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)}


def score_record(result: Dict[str, Any], dataset: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    coerced = coerce_scoring_fields(result)
    record_id = str(coerced.get("id") or coerced.get("case_id", "")).strip()
    coerced.setdefault("schema_version", "2.0.0")
    coerced["scored_at"] = datetime.now(timezone.utc).isoformat()
    if record_id:
        coerced.setdefault("id", record_id)
        coerced.setdefault("case_id", record_id)

    if not record_id or record_id not in dataset:
        coerced.setdefault("evaluation_mode", "exact")
        coerced.setdefault("task_family_id", "unknown")
        coerced.setdefault("failure_mode", "unknown")
        coerced.setdefault("ambiguity_type", "unknown")
        coerced.setdefault("calibration_difficulty", "unknown")
        coerced.setdefault("calibration_split", "unknown")
        coerced.setdefault("gold_confidence", "unknown")
        coerced.setdefault("human_disagreement_risk", "unknown")
        coerced.setdefault("review_status", "unknown")
        status = {
            "matched": False,
            "score": None,
            "reason": "unknown_question_id",
            "matched_by": "metadata_missing",
            "answer_field": "answer",
            "reasoning_field": "reasoning",
            "accepted_variant_policy": DEFAULT_ACCEPTED_VARIANT_POLICY,
            "heuristic_flags": [
                {"name": "missing_or_unknown_id", "value": True, "is_heuristic": True},
            ],
            "dimensions": [],
        }
        coerced.update(
            {
                "score_answer": None,
                "scoring_status": status,
                "score_answer_normalized": {
                    "expected": "",
                    "expected_normalized": "",
                    "answer": coerced.get("answer", ""),
                    "answer_normalized": normalize_text(coerced.get("answer", "")),
                },
            }
        )
        return coerced

    question = dataset[record_id]
    evaluation_mode = evaluation_mode_for(question)
    answer_field = answer_field_for(question)
    reasoning_field = reasoning_field_for(question)
    accepted_variant_policy = accepted_variant_policy_for(question)
    answer = coerced.get(answer_field, "")
    dimensions = evaluation_dimensions_for(question)
    coerced["evaluation_mode"] = evaluation_mode
    coerced["task_family_id"] = task_family_id_for(question)
    coerced["failure_mode"] = str(question.get("failure_mode") or "unknown").strip() or "unknown"
    coerced["ambiguity_type"] = ambiguity_type_for(question)
    coerced["clarification_expected"] = clarification_expected_for(question)
    coerced.update(ambiguity_review_context_for(question))
    coerced.update(calibration_metadata_for(question))

    if evaluation_mode == "rubric":
        expected_text = str(question.get("expected_answer", ""))
        status = {
            "matched": False,
            "score": None,
            "reason": "rubric_manual_review_required",
            "matched_by": "manual_rubric",
            "answer_field": answer_field,
            "reasoning_field": reasoning_field,
            "accepted_variant_policy": accepted_variant_policy,
            "heuristic_flags": [],
            "dimensions": score_dimensions(dimensions, evaluation_mode, None),
        }
        coerced.update(
            {
                "score_answer": None,
                "scoring_status": status,
                "score_answer_normalized": {
                    "expected": expected_text,
                    "expected_normalized": normalize_text(expected_text),
                    "answer": answer,
                    "answer_normalized": normalize_text(answer),
                },
                "score_reason": status["reason"],
            }
        )
        return coerced

    if evaluation_mode not in SUPPORTED_EVALUATION_MODES:
        expected_text = str(question.get("expected_answer", ""))
        status = {
            "matched": False,
            "score": None,
            "reason": "unsupported_evaluation_mode",
            "matched_by": "unsupported_evaluator",
            "answer_field": answer_field,
            "reasoning_field": reasoning_field,
            "accepted_variant_policy": accepted_variant_policy,
            "heuristic_flags": [],
            "dimensions": score_dimensions(dimensions, evaluation_mode, None),
        }
        coerced.update(
            {
                "score_answer": None,
                "scoring_status": status,
                "score_answer_normalized": {
                    "expected": expected_text,
                    "expected_normalized": normalize_text(expected_text),
                    "answer": answer,
                    "answer_normalized": normalize_text(answer),
                },
                "score_reason": status["reason"],
            }
        )
        return coerced

    match = score_single_answer(
        answer=answer,
        expected_text=str(question.get("expected_answer", "")),
        accepted_variants=question.get("accepted_variants", []),
        accepted_variant_policy=accepted_variant_policy,
    )
    status = {
        "matched": bool(match.matched),
        "score": match.score,
        "reason": match.reason,
        "matched_by": match.matched_by,
        "answer_field": answer_field,
        "reasoning_field": reasoning_field,
        "accepted_variant_policy": accepted_variant_policy,
        "heuristic_flags": [{"name": "answer_match", "value": match.heuristic, "is_heuristic": match.heuristic}],
        "dimensions": score_dimensions(dimensions, evaluation_mode, match.score),
    }
    if match.heuristic is False:
        # Keep a consistent flag schema: even non-heuristic matching records are explicit.
        status["heuristic_flags"].append(
            {"name": "exact_match", "value": match.matched_by == "exact", "is_heuristic": False}
        )

    coerced.update(
        {
            "score_answer": match.score,
            "scoring_status": status,
            "score_answer_normalized": {
                "expected": match.expected,
                "expected_normalized": match.expected_normalized,
                "answer": match.answer,
                "answer_normalized": match.answer_normalized,
            },
            "score_reason": status["reason"],
        }
    )
    return coerced


def suite_id_from_meta(input_meta: Dict[str, Any]) -> str:
    suite_id = input_meta.get("suite_id")
    if isinstance(suite_id, str) and suite_id.strip():
        return suite_id.strip()

    run_mode = input_meta.get("run_mode")
    if isinstance(run_mode, str) and run_mode.strip():
        return run_mode.strip()

    execution = input_meta.get("execution")
    if isinstance(execution, dict):
        mode = execution.get("mode")
        if isinstance(mode, str) and mode.strip():
            return mode.strip()

    return "unknown"


def answered_text_for_summary(item: Dict[str, Any]) -> Any:
    normalized = item.get("score_answer_normalized")
    if isinstance(normalized, dict) and "answer" in normalized:
        return normalized.get("answer")
    return item.get("answer", "")


def build_summary(
    scored: List[Dict[str, Any]],
    *,
    benchmark: str = "reasoning-benchmark",
    suite_id: str = "unknown",
    source_bundles: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    auto_scored = [item for item in scored if item.get("scoring_status", {}).get("score") in {0, 1}]
    auto_total = len(auto_scored)
    auto_correct = sum(1 for item in auto_scored if item["scoring_status"]["score"] == 1)
    auto_accuracy = round(auto_correct / auto_total, 4) if auto_total else 0.0

    manual_reasoning_scores = sum(1 for item in scored if isinstance(item.get("score_reasoning"), int))
    manual_constraint_scores = sum(1 for item in scored if isinstance(item.get("score_constraint_extraction"), int))
    manual_notes = sum(1 for item in scored if str(item.get("notes", "")).strip())
    heuristic_flags_total = sum(
        1
        for item in auto_scored
        for flag in item.get("scoring_status", {}).get("heuristic_flags", [])
        if isinstance(flag, dict) and flag.get("is_heuristic")
    )

    heuristics = Counter()
    for item in auto_scored:
        for flag in item.get("scoring_status", {}).get("heuristic_flags", []):
            if isinstance(flag, dict) and flag.get("is_heuristic"):
                heuristics.update([flag.get("name", "unknown")])

    answered = sum(1 for item in scored if normalize_text(answered_text_for_summary(item)) != "")
    by_model: Dict[str, Dict[str, Any]] = {}
    by_evaluation_mode: Dict[str, Dict[str, Any]] = {}
    by_task_family: Dict[str, Dict[str, Any]] = {}
    by_failure_mode: Dict[str, Dict[str, Any]] = {}
    by_ambiguity_type: Dict[str, Dict[str, Any]] = {}
    by_calibration_split: Dict[str, Dict[str, Any]] = {}
    by_model_task_family: Dict[str, Dict[str, Dict[str, Any]]] = {}
    by_model_failure_mode: Dict[str, Dict[str, Dict[str, Any]]] = {}
    by_model_ambiguity_type: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def empty_bucket() -> Dict[str, Any]:
        return {
            "total": 0,
            "auto_scored": 0,
            "correct": 0,
            "incorrect": 0,
            "accuracy": 0.0,
            "manual_review_required": 0,
        }

    for item in scored:
        model = str(item.get("model") or "unknown").strip() or "unknown"
        model_bucket = by_model.setdefault(model, empty_bucket())
        model_bucket["total"] += 1

        mode = str(item.get("evaluation_mode") or "exact").strip() or "exact"
        bucket = by_evaluation_mode.setdefault(mode, empty_bucket())
        bucket["total"] += 1

        task_family_id = str(item.get("task_family_id") or "unknown").strip() or "unknown"
        task_family_bucket = by_task_family.setdefault(task_family_id, empty_bucket())
        task_family_bucket["total"] += 1

        failure_mode = str(item.get("failure_mode") or "unknown").strip() or "unknown"
        failure_mode_bucket = by_failure_mode.setdefault(failure_mode, empty_bucket())
        failure_mode_bucket["total"] += 1

        ambiguity_type = str(item.get("ambiguity_type") or "unknown").strip() or "unknown"
        ambiguity_type_bucket = by_ambiguity_type.setdefault(ambiguity_type, empty_bucket())
        ambiguity_type_bucket["total"] += 1

        calibration_split = str(item.get("calibration_split") or "full").strip() or "full"
        calibration_split_bucket = by_calibration_split.setdefault(calibration_split, empty_bucket())
        calibration_split_bucket["total"] += 1

        model_task_family_bucket = by_model_task_family.setdefault(model, {}).setdefault(
            task_family_id, empty_bucket()
        )
        model_task_family_bucket["total"] += 1

        model_failure_mode_bucket = by_model_failure_mode.setdefault(model, {}).setdefault(
            failure_mode, empty_bucket()
        )
        model_failure_mode_bucket["total"] += 1

        model_ambiguity_type_bucket = by_model_ambiguity_type.setdefault(model, {}).setdefault(
            ambiguity_type, empty_bucket()
        )
        model_ambiguity_type_bucket["total"] += 1

        status = item.get("scoring_status", {})
        score = status.get("score") if isinstance(status, dict) else None
        all_buckets = [
            model_bucket,
            bucket,
            task_family_bucket,
            failure_mode_bucket,
            ambiguity_type_bucket,
            calibration_split_bucket,
            model_task_family_bucket,
            model_failure_mode_bucket,
            model_ambiguity_type_bucket,
        ]
        if score in {0, 1}:
            for entry in all_buckets:
                entry["auto_scored"] += 1
                entry["correct" if score == 1 else "incorrect"] += 1

        dimensions = status.get("dimensions", []) if isinstance(status, dict) else []
        has_manual_dimension = any(
            isinstance(dimension, dict) and dimension.get("status") == "manual_review_required"
            for dimension in dimensions
        )
        if score is None or has_manual_dimension:
            for entry in all_buckets:
                entry["manual_review_required"] += 1

    cross_tab_buckets = [
        bucket
        for cross_tab in (
            by_model_task_family,
            by_model_failure_mode,
            by_model_ambiguity_type,
        )
        for nested in cross_tab.values()
        for bucket in nested.values()
    ]
    for bucket in [
        *by_model.values(),
        *by_evaluation_mode.values(),
        *by_task_family.values(),
        *by_failure_mode.values(),
        *by_ambiguity_type.values(),
        *by_calibration_split.values(),
        *cross_tab_buckets,
    ]:
        bucket["case_count"] = bucket["total"]
        bucket["accuracy"] = (
            round(bucket["correct"] / bucket["auto_scored"], 4)
            if bucket["auto_scored"]
            else 0.0
        )

    manual_review = {
        "reasoning_scores_present": manual_reasoning_scores,
        "constraint_scores_present": manual_constraint_scores,
        "notes_present": manual_notes,
        "heuristic_flags_total": heuristic_flags_total,
    }

    return {
        "schema_version": "2.0.0",
        "benchmark": benchmark,
        "suite_id": suite_id,
        "source_bundles": list(source_bundles or []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": {
            "case_count": len(scored),
            "question_count": len(scored),
            "answered_count": answered,
            "missing_count": len(scored) - answered,
        },
        "auto_scored": {
            "total": auto_total,
            "correct": auto_correct,
            "incorrect": auto_total - auto_correct,
            "accuracy": auto_accuracy,
        },
        "manual_only": dict(manual_review),
        "manual_review": dict(manual_review),
        "by_model": by_model,
        "by_evaluation_mode": by_evaluation_mode,
        "by_task_family": by_task_family,
        "by_failure_mode": by_failure_mode,
        "by_ambiguity_type": by_ambiguity_type,
        "by_calibration_split": by_calibration_split,
        "by_model_task_family": by_model_task_family,
        "by_model_failure_mode": by_model_failure_mode,
        "by_model_ambiguity_type": by_model_ambiguity_type,
        "heuristic_flags": dict(heuristics),
    }


def build_output_payload(
    input_meta: Dict[str, Any],
    scored: List[Dict[str, Any]],
    dataset_path: str,
    source_input: Optional[str],
    source_bundles: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "scoring_contract": "conservative_answer_correctness_only",
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "source_input": source_input,
        "dataset_path": dataset_path,
        "input_meta": input_meta,
        "summary": build_summary(
            scored,
            benchmark=str(input_meta.get("benchmark") or "reasoning-benchmark"),
            suite_id=suite_id_from_meta(input_meta),
            source_bundles=source_bundles,
        ),
        "results": scored,
    }


def score_to_file(
    input_path: Path,
    output_path: Path,
    dataset_path: Path,
    source_bundles: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    if not input_path.is_file():
        raise FileNotFoundError(f"Run input not found: {input_path}")

    with input_path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)

    input_meta, records = normalize_run_payload(payload)
    dataset = load_dataset(dataset_path)
    scored = [score_record(record, dataset) for record in records]

    output_payload = build_output_payload(
        input_meta=input_meta,
        scored=scored,
        dataset_path=str(dataset_path),
        source_input=str(input_path),
        source_bundles=source_bundles,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as stream:
        json.dump(output_payload, stream, ensure_ascii=False, indent=2)

    return output_payload


def cmd_score(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    output_path = Path(args.output)
    dataset_path = Path(args.dataset)

    output_payload = score_to_file(
        input_path=input_path,
        output_path=output_path,
        dataset_path=dataset_path,
        source_bundles=getattr(args, "source_bundle", None),
    )

    scored = output_payload["results"]
    summary = output_payload["summary"]
    auto = summary["auto_scored"]
    manual = summary["manual_only"]

    print(f"Scored {len(scored)} items from {input_path}")
    print(
        f"Auto correctness: {auto['correct']}/{auto['total']} "
        f"({auto['accuracy']:.2%})"
    )
    print(
        "Manual fields: "
        f"reasoning={manual['reasoning_scores_present']}, "
        f"constraint={manual['constraint_scores_present']}, "
        f"notes={manual['notes_present']}"
    )
    print(f"Wrote scored run to {output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score a reasoning benchmark run")
    parser.add_argument("--input", required=True, help="Input run JSON path")
    parser.add_argument("--output", required=True, help="Output scored run JSON path")
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET_PATH),
        help="Path to dataset questions JSON",
    )
    parser.add_argument(
        "--source-bundle",
        action="append",
        help="Optional source RunArtifactBundle manifest path to record in summary.source_bundles",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return cmd_score(args)
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
