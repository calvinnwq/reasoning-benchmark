#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
    for token in tokens[:6]:
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


def score_single_answer(answer: Any, expected_text: str, accepted_variants: Iterable[Any]) -> MatchResult:
    raw_answer = "" if answer is None else str(answer).strip()
    answer_norms = build_answer_norms(raw_answer)
    answer_norm = answer_norms[0] if answer_norms else ""
    expected_norm = normalize_text(expected_text)
    candidate_norms = build_candidate_norms(expected_text, accepted_variants)

    expected_binary = extract_binary_token(expected_text)
    if not answer_norm:
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

    if expected_binary in {"yes", "no"}:
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
        if answer_binary == expected_binary:
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

    for normalized_answer in answer_norms:
        answer_tokens = token_sequence(normalized_answer)
        if len(answer_tokens) <= 10:
            for candidate_norm in candidate_norms:
                candidate_tokens = token_sequence(candidate_norm)
                if contains_expected_as_contiguous_span(answer_tokens, candidate_tokens):
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
                if contains_expected_as_contiguous_span(stripped_answer_tokens, stripped_candidate_tokens):
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
        if 0 < len(answer_tokens) <= 3 and answer_tokens[0] not in {"yes", "no"}:
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
    coerced.setdefault("score_reasoning", None)
    coerced.setdefault("score_constraint_extraction", None)
    coerced["penalties"] = coerce_penalties(coerced.get("penalties"))
    coerced.setdefault("notes", "")
    return coerced


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
    record_id = str(coerced.get("id", "")).strip()

    if not record_id or record_id not in dataset:
        status = {
            "matched": False,
            "score": None,
            "reason": "unknown_question_id",
            "matched_by": "metadata_missing",
            "heuristic_flags": [
                {"name": "missing_or_unknown_id", "value": True, "is_heuristic": True},
            ],
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
    match = score_single_answer(
        answer=coerced.get("answer", ""),
        expected_text=str(question.get("expected_answer", "")),
        accepted_variants=question.get("accepted_variants", []),
    )
    status = {
        "matched": bool(match.matched),
        "score": match.score,
        "reason": match.reason,
        "matched_by": match.matched_by,
        "heuristic_flags": [{"name": "answer_match", "value": match.heuristic, "is_heuristic": match.heuristic}],
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


def build_summary(scored: List[Dict[str, Any]]) -> Dict[str, Any]:
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

    answered = sum(1 for item in scored if normalize_text(item.get("answer", "")) != "")
    return {
        "overall": {
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
        "manual_only": {
            "reasoning_scores_present": manual_reasoning_scores,
            "constraint_scores_present": manual_constraint_scores,
            "notes_present": manual_notes,
            "heuristic_flags_total": heuristic_flags_total,
        },
        "heuristic_flags": dict(heuristics),
    }


def build_output_payload(
    input_meta: Dict[str, Any],
    scored: List[Dict[str, Any]],
    dataset_path: str,
    source_input: Optional[str],
) -> Dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "scoring_contract": "conservative_answer_correctness_only",
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "source_input": source_input,
        "dataset_path": dataset_path,
        "input_meta": input_meta,
        "summary": build_summary(scored),
        "results": scored,
    }


def cmd_score(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    output_path = Path(args.output)
    dataset_path = Path(args.dataset)

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
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as stream:
        json.dump(output_payload, stream, ensure_ascii=False, indent=2)

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
