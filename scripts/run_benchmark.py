#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "data" / "questions.json"


def load_questions() -> list[dict]:
    with DATA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def cmd_list() -> int:
    questions = load_questions()
    for q in questions:
        print(f"{q['id']} [{q['category']}] {q['prompt']}")
    print(f"\nTotal: {len(questions)} questions")
    return 0


def cmd_sample_run() -> int:
    questions = load_questions()
    payload = {
        "schema_version": "2.0.0",
        "benchmark": "reasoning-benchmark",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "suite_id": "full",
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


def cmd_emit_prompts(output: str) -> int:
    questions = load_questions()
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reasoning benchmark helper")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List benchmark questions")
    group.add_argument("--sample-run", action="store_true", help="Print a blank run template JSON")
    group.add_argument("--emit-prompts", metavar="OUTPUT", help="Write a JSONL prompt pack")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.list:
        return cmd_list()
    if args.sample_run:
        return cmd_sample_run()
    if args.emit_prompts:
        return cmd_emit_prompts(args.emit_prompts)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
