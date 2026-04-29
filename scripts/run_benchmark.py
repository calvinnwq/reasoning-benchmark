#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from suites import (
    SUITES_DIR as _DEFAULT_SUITES_DIR,
    list_available_suites,
    resolve_suite_case_ids,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "data" / "questions.json"
SUITES_DIR = _DEFAULT_SUITES_DIR
DEFAULT_SUITE_ID = "default"
OPTIONAL_TASK_FAMILY_IDS: frozenset[str] = frozenset({"instruction-ambiguity"})
OPTIONAL_CATEGORIES: frozenset[str] = frozenset({"IA"})


def is_optional_question(row: dict) -> bool:
    task_family_id = row.get("task_family_id")
    if isinstance(task_family_id, str) and task_family_id in OPTIONAL_TASK_FAMILY_IDS:
        return True
    category = row.get("category")
    return isinstance(category, str) and category in OPTIONAL_CATEGORIES


def default_questions(questions: list[dict]) -> list[dict]:
    return [row for row in questions if not is_optional_question(row)]


def load_questions() -> list[dict]:
    with DATA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _select_questions(suite: str | None) -> tuple[list[dict], str]:
    questions = load_questions()
    if suite is None:
        return default_questions(questions), DEFAULT_SUITE_ID

    case_ids = resolve_suite_case_ids(suite, suites_dir=SUITES_DIR)
    by_id = {q["id"]: q for q in questions}
    missing = [cid for cid in case_ids if cid not in by_id]
    if missing:
        raise ValueError(
            f"suite {suite!r} references unknown case ids: {', '.join(missing)}"
        )
    selected = [by_id[cid] for cid in case_ids]
    return selected, suite


def cmd_list(suite: str | None = None) -> int:
    questions, _ = _select_questions(suite)
    for q in questions:
        print(f"{q['id']} [{q['category']}] {q['prompt']}")
    print(f"\nTotal: {len(questions)} questions")
    return 0


def cmd_sample_run(suite: str | None = None) -> int:
    questions, suite_id = _select_questions(suite)
    payload = {
        "schema_version": "2.0.0",
        "benchmark": "reasoning-benchmark",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "suite_id": suite_id,
        "case_count": len(questions),
        "question_count": len(questions),
        "results": [
            {
                "id": q["id"],
                "case_id": q["id"],
                "prompt": q["prompt"],
                "model": "",
                "answer": "",
                "reasoning": "",
                "score_answer": None,
                "score_reasoning": None,
                "score_constraint_extraction": None,
                "penalties": [],
                "notes": "",
            }
            for q in questions
        ],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_emit_prompts(output: str, suite: str | None = None) -> int:
    questions, _ = _select_questions(suite)
    out_path = Path(output)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        for q in questions:
            row = {
                "id": q["id"],
                "category": q["category"],
                "prompt": q["prompt"],
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Wrote {len(questions)} prompts to {out_path}")
    return 0


def cmd_list_suites() -> int:
    names = list_available_suites(suites_dir=SUITES_DIR)
    if not names:
        print("No suite manifests found.")
        return 0
    for name in names:
        print(name)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reasoning benchmark helper")
    parser.add_argument(
        "--suite",
        metavar="NAME",
        help="Restrict the command to a named suite manifest (e.g. starter, holdout)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List benchmark questions")
    group.add_argument("--sample-run", action="store_true", help="Print a blank run template JSON")
    group.add_argument("--emit-prompts", metavar="OUTPUT", help="Write a JSONL prompt pack")
    group.add_argument(
        "--list-suites",
        action="store_true",
        help="List the available named suite manifests",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.list_suites:
        if args.suite is not None:
            parser.error("--suite cannot be combined with --list-suites")
        return cmd_list_suites()
    if args.list:
        return cmd_list(suite=args.suite)
    if args.sample_run:
        return cmd_sample_run(suite=args.suite)
    if args.emit_prompts:
        return cmd_emit_prompts(args.emit_prompts, suite=args.suite)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
