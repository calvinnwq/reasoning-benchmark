#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from benchmark_contract import build_prompt_contract

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET_PATH = REPO_ROOT / "data" / "questions.json"
DEFAULT_RUN_DIR = REPO_ROOT / "runs" / "baseline"

SUPPORTED_MODELS: tuple[str, ...] = ("gpt-5.4", "sonnet-4.6", "qwen3.5-9b")
SUPPORTED_MODES: tuple[str, ...] = ("smoke", "full")
SMOKE_COUNT = 5
RUNNER_VERSION = "1.0.0"

@dataclass(frozen=True)
class ProviderResult:
    answer: str
    reasoning: str
    notes: str | None = None


def load_questions(dataset_path: Path) -> list[dict[str, Any]]:
    with dataset_path.open("r", encoding="utf-8") as stream:
        rows = json.load(stream)

    if not isinstance(rows, list):
        raise ValueError("Dataset must be a JSON list")
    for row in rows:
        if not isinstance(row, dict) or "id" not in row or "prompt" not in row:
            raise ValueError("Each dataset row must include at least id and prompt")
    return rows


def normalize_model_id(model: str) -> str:
    safe = [
        char if char.isalnum() else "-"
        for char in model.strip().lower()
    ]
    normalized = "".join(safe).strip("-")
    return normalized


def run_paths(run_dir: Path, model: str, mode: str) -> tuple[Path, Path]:
    model_slug = normalize_model_id(model)
    raw = run_dir / f"{model_slug}.{mode}.raw.json"
    scored = run_dir / f"{model_slug}.{mode}.scored.json"
    return raw, scored


def dataset_fingerprint(dataset_path: Path) -> str:
    digest = hashlib.sha256()
    with dataset_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4096), b""):
            digest.update(chunk)
    return digest.hexdigest()


def select_questions(questions: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    if mode == "smoke":
        return questions[:SMOKE_COUNT]
    if mode == "full":
        return questions
    raise ValueError(f"Unsupported mode: {mode}")


def build_empty_record(row: dict[str, Any], model: str, notes: str | None = None) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "id": row["id"],
        "prompt": row["prompt"],
        "category": row.get("category", ""),
        "model": model,
        "answer": "",
        "reasoning": "",
        "score_answer": None,
        "score_reasoning": None,
        "score_constraint_extraction": None,
        "penalties": [],
        "notes": notes or "",
    }
    return record


def parse_provider_output(raw_stdout: str) -> tuple[str, str, str | None]:
    text = raw_stdout.strip()
    if not text:
        return "", "", None

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text, "", None

    if not isinstance(payload, dict):
        return "", "", "Provider output must be JSON object"

    answer = payload.get("answer")
    reasoning = payload.get("reasoning")
    notes = payload.get("notes")
    if answer is None:
        answer = ""
    if reasoning is None:
        reasoning = ""
    if notes is None:
        notes = None
    if not isinstance(answer, str):
        answer = str(answer)
    if not isinstance(reasoning, str):
        reasoning = str(reasoning) if reasoning is not None else ""
    if notes is not None and not isinstance(notes, str):
        notes = str(notes)
    return answer, reasoning, notes


def build_result_record(
    row: dict[str, Any],
    model: str,
    answer: str,
    reasoning: str,
    notes: str | None = None,
) -> Dict[str, Any]:
    base = build_empty_record(row, model)
    base["answer"] = answer
    base["reasoning"] = reasoning
    if notes:
        base["notes"] = notes
    return base


def run_provider(
    command: list[str],
    model: str,
    prompt: str,
    timeout: float,
) -> ProviderResult:
    process = subprocess.run(
        command + [model, prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if process.returncode != 0:
        notes = f"provider_command_failed_exit_{process.returncode}: {process.stderr.strip() or process.stdout.strip()}"
        return ProviderResult(answer="", reasoning="", notes=notes)

    answer, reasoning, parsed_notes = parse_provider_output(process.stdout)
    notes = parsed_notes
    if parsed_notes is None and not answer and not reasoning and process.stdout.strip():
        notes = "provider_output_not_json" if process.stdout.strip() else None
    if process.stderr.strip():
        extra = process.stderr.strip()
        notes = f"{notes + '; ' if notes else ''}{extra}" if extra else notes
    return ProviderResult(answer=answer, reasoning=reasoning, notes=notes)


def build_payload(
    model: str,
    mode: str,
    questions: list[dict[str, Any]],
    dataset_path: Path,
) -> Dict[str, Any]:
    payload = {
        "schema_version": RUNNER_VERSION,
        "benchmark": "reasoning-benchmark",
        "runner": "scripts/run_baselines.py",
        "runner_version": RUNNER_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_mode": mode,
        "model": model,
        "dataset": {
            "path": str(dataset_path),
            "path_hash": dataset_fingerprint(dataset_path),
            "question_count": len(questions),
        },
        "prompt_contract": build_prompt_contract(),
        "results": [
            build_empty_record(row=row, model=model)
            for row in questions
        ],
    }
    return payload


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)


def score_payload(input_path: Path, output_path: Path, dataset_path: Path) -> None:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "score_run.py"),
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--dataset",
        str(dataset_path),
    ]
    process = subprocess.run(cmd, capture_output=True, text=True)
    if process.returncode != 0:
        stdout = process.stdout.strip()
        stderr = process.stderr.strip()
        raise RuntimeError(f"Scoring failed for {input_path}: {stdout or stderr}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the reasoning benchmark baseline models")
    parser.add_argument(
        "--mode",
        choices=SUPPORTED_MODES,
        default="smoke",
        help="Smoke runs first 5 questions; full runs all 50",
    )
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET_PATH),
        help=f"Path to benchmark dataset JSON (default: {DEFAULT_DATASET_PATH})",
    )
    parser.add_argument(
        "--run-dir",
        default=str(DEFAULT_RUN_DIR),
        help=f"Directory for raw and scored artifacts (default: {DEFAULT_RUN_DIR})",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=list(SUPPORTED_MODELS),
        help="Subset of supported models to run",
    )
    parser.add_argument(
        "--provider-command",
        nargs="+",
        help=(
            "Optional command for live execution: MODEL and prompt are appended as positional args.\n"
            "If omitted, runner writes dry-run payloads with empty answers and still calls scoring."
        ),
    )
    parser.add_argument(
        "--prompt-timeout",
        type=float,
        default=45.0,
        help="Timeout (seconds) for each provider call when --provider-command is used",
    )
    parser.add_argument(
        "--skip-scoring",
        action="store_true",
        help="Skip automatic scoring step",
    )
    return parser


def resolve_models(models: Iterable[str]) -> tuple[str, ...]:
    requested = tuple(models)
    unsupported = [model for model in requested if model not in SUPPORTED_MODELS]
    if unsupported:
        raise ValueError(f"Unsupported models requested: {', '.join(unsupported)}")
    return requested


def cmd_run(args: argparse.Namespace) -> int:
    dataset_path = Path(args.dataset)
    run_dir = Path(args.run_dir)
    models = resolve_models(args.models)
    questions = load_questions(dataset_path)
    selected = select_questions(questions, args.mode)

    did_execute_live = bool(args.provider_command)

    for model in models:
        raw_path, scored_path = run_paths(run_dir, model, args.mode)
        payload = build_payload(model=model, mode=args.mode, questions=selected, dataset_path=dataset_path)

        if did_execute_live:
            for index, row in enumerate(selected):
                response = run_provider(args.provider_command, model, row["prompt"], args.prompt_timeout)
                payload["results"][index] = build_result_record(
                    row=row,
                    model=model,
                    answer=response.answer,
                    reasoning=response.reasoning,
                    notes=response.notes,
                )
        write_json(raw_path, payload)
        print(f"wrote raw artifact: {raw_path}")

        if args.skip_scoring:
            print("skipping scoring")
            continue

        score_payload(raw_path, scored_path, dataset_path)
        print(f"wrote scored artifact: {scored_path}")

    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        return cmd_run(args)
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
