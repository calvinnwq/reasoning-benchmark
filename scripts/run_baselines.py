#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import random
import shlex
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

BENCHMARK_ID = "reasoning-benchmark"
SUPPORTED_MODELS: tuple[str, ...] = ("gpt-5.4", "sonnet-4.6", "qwen3.5-9b")
SUPPORTED_MODES: tuple[str, ...] = ("smoke", "full")
SMOKE_COUNT = 5
RAW_ARTIFACT_SCHEMA_VERSION = "2.0.0"
RUNNER_VERSION = "1.0.0"
BUILTIN_ADAPTER_COMMANDS: dict[str, list[str]] = {
    "api": [sys.executable, str(SCRIPT_DIR / "api_adapter.py")],
    "cli": [sys.executable, str(SCRIPT_DIR / "cli_adapter.py")],
}

@dataclass(frozen=True)
class ProviderResult:
    answer: str
    reasoning: str
    notes: str | None = None
    raw_response_text: str = ""
    raw_response_format: str = "unknown"
    adapter_name: str | None = None
    adapter_command: list[str] | None = None
    adapter_exit_code: int | None = None
    adapter_stderr: str = ""
    started_at: str | None = None
    completed_at: str | None = None


@dataclass(frozen=True)
class RunRequest:
    mode: str
    dataset_path: Path
    run_dir: Path
    models: tuple[str, ...]
    provider_commands: dict[str, list[str]]
    prompt_timeout: float
    skip_scoring: bool
    max_cases: int | None = None
    seed: int | str | None = None
    suite_case_ids: tuple[str, ...] | None = None
    prompt_contract: dict[str, Any] | None = None
    config_payload: dict[str, Any] | None = None
    config_path: Path | None = None


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


def validate_artifact_label(value: str, field_name: str) -> None:
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"{field_name} cannot contain path separators or traversal segments")


def format_adapter_command(command: list[str]) -> str:
    if len(command) <= 1:
        return shlex.join(command)
    return shlex.join([command[0], "[arguments omitted]"])


def run_paths(run_dir: Path, model: str, mode: str) -> tuple[Path, Path]:
    model_slug = normalize_model_id(model)
    raw = run_dir / f"{model_slug}.{mode}.raw.json"
    scored = run_dir / f"{model_slug}.{mode}.scored.json"
    return raw, scored


def manifest_path(run_dir: Path, model: str, mode: str) -> Path:
    model_slug = normalize_model_id(model)
    return run_dir / f"{model_slug}.{mode}.manifest.json"


def summary_path(run_dir: Path, model: str, mode: str) -> Path:
    model_slug = normalize_model_id(model)
    return run_dir / f"{model_slug}.{mode}.summary.json"


def dataset_fingerprint(dataset_path: Path) -> str:
    digest = hashlib.sha256()
    with dataset_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4096), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4096), b""):
            digest.update(chunk)
    return digest.hexdigest()


def select_questions(
    questions: list[dict[str, Any]],
    mode: str,
    max_cases: int | None = None,
    seed: int | str | None = None,
    case_ids: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    if case_ids is not None:
        by_id = {str(row["id"]): row for row in questions}
        missing = [case_id for case_id in case_ids if case_id not in by_id]
        if missing:
            raise ValueError(f"Suite case_ids not found in dataset: {', '.join(missing)}")
        selected = [by_id[case_id] for case_id in case_ids]
    elif mode == "smoke":
        selected = questions[:SMOKE_COUNT]
    elif mode == "full":
        selected = questions
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    selected = list(selected)
    if seed is not None:
        random.Random(seed).shuffle(selected)

    if max_cases is not None:
        selected = selected[:max_cases]
    return selected


def build_empty_record(row: dict[str, Any], model: str, notes: str | None = None) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "id": row["id"],
        "case_id": row["id"],
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


def parse_provider_output(raw_stdout: str) -> tuple[str, str, str | None, str]:
    text = raw_stdout.strip()
    if not text:
        return "", "", None, "empty"

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text, "", None, "text"

    if not isinstance(payload, dict):
        return "", "", "Provider output must be JSON object", "json"

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
    return answer, reasoning, notes, "json"


def build_result_record(
    row: dict[str, Any],
    model: str,
    answer: str,
    reasoning: str,
    notes: str | None = None,
    provider: ProviderResult | None = None,
) -> Dict[str, Any]:
    base = build_empty_record(row, model)
    base["answer"] = answer
    base["reasoning"] = reasoning
    if notes:
        base["notes"] = notes
    if provider is not None and provider.adapter_command is not None:
        base["raw_response"] = {
            "text": provider.raw_response_text,
            "format": provider.raw_response_format,
        }
        base["adapter"] = {
            "name": provider.adapter_name or "provider-command",
            "command": format_adapter_command(provider.adapter_command),
            "exit_code": provider.adapter_exit_code,
            "stderr": provider.adapter_stderr,
        }
        if provider.started_at:
            base["started_at"] = provider.started_at
        if provider.completed_at:
            base["completed_at"] = provider.completed_at
    return base


def run_provider(
    command: list[str],
    model: str,
    prompt: str,
    timeout: float,
) -> ProviderResult:
    started_at = datetime.now(timezone.utc).isoformat()
    process = subprocess.run(
        command + [model, prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    completed_at = datetime.now(timezone.utc).isoformat()
    stderr = process.stderr.strip()
    adapter_name = Path(command[0]).name if command else "provider-command"

    if process.returncode != 0:
        notes = f"provider_command_failed_exit_{process.returncode}: {stderr or process.stdout.strip()}"
        return ProviderResult(
            answer="",
            reasoning="",
            notes=notes,
            raw_response_text=process.stdout,
            raw_response_format="error",
            adapter_name=adapter_name,
            adapter_command=list(command),
            adapter_exit_code=process.returncode,
            adapter_stderr=stderr,
            started_at=started_at,
            completed_at=completed_at,
        )

    answer, reasoning, parsed_notes, response_format = parse_provider_output(process.stdout)
    notes = parsed_notes
    if parsed_notes is None and not answer and not reasoning and process.stdout.strip():
        notes = "provider_output_not_json" if process.stdout.strip() else None
    if stderr:
        extra = stderr
        notes = f"{notes + '; ' if notes else ''}{extra}" if extra else notes
    return ProviderResult(
        answer=answer,
        reasoning=reasoning,
        notes=notes,
        raw_response_text=process.stdout,
        raw_response_format=response_format,
        adapter_name=adapter_name,
        adapter_command=list(command),
        adapter_exit_code=process.returncode,
        adapter_stderr=stderr,
        started_at=started_at,
        completed_at=completed_at,
    )


def build_payload(
    model: str,
    mode: str,
    questions: list[dict[str, Any]],
    dataset_path: Path,
    max_cases: int | None = None,
    seed: int | str | None = None,
    prompt_contract: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    contract = copy.deepcopy(prompt_contract) if prompt_contract is not None else build_prompt_contract()
    payload = {
        "schema_version": RAW_ARTIFACT_SCHEMA_VERSION,
        "benchmark": BENCHMARK_ID,
        "runner": "scripts/run_baselines.py",
        "runner_version": RUNNER_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "suite_id": mode,
        "run_mode": mode,
        "case_count": len(questions),
        "question_count": len(questions),
        "model": model,
        "execution": {
            "mode": mode,
            "seed": seed,
            "max_cases": max_cases,
        },
        "dataset": {
            "path": str(dataset_path),
            "path_hash": dataset_fingerprint(dataset_path),
            "case_count": len(questions),
            "question_count": len(questions),
        },
        "prompt_contract": contract,
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


def build_run_artifact_bundle(
    *,
    model: str,
    mode: str,
    raw_path: Path,
    scored_path: Path | None,
    report_summary_path: Path | None = None,
    dataset_path: Path,
    case_count: int,
    created_at: str,
    config_path: Path | None = None,
) -> Dict[str, Any]:
    model_slug = normalize_model_id(model)
    scored_results = scored_path.name if scored_path else None
    scored_fingerprint = (
        {"algorithm": "sha256", "value": file_fingerprint(scored_path)}
        if scored_path
        else None
    )
    summary_fingerprint = (
        {"algorithm": "sha256", "value": file_fingerprint(report_summary_path)}
        if report_summary_path
        else None
    )
    return {
        "schema_version": "2.0.0",
        "id": f"baseline-{mode}-{model_slug}",
        "benchmark": BENCHMARK_ID,
        "suite_id": mode,
        "run_config": str(config_path) if config_path else None,
        "artifacts": {
            "raw_results": raw_path.name,
            "scored_results": scored_results,
            "report_summary": report_summary_path.name if report_summary_path else None,
            "prompt_pack": None,
        },
        "fingerprints": {
            "dataset": {"algorithm": "sha256", "value": dataset_fingerprint(dataset_path)},
            "raw_results": {"algorithm": "sha256", "value": file_fingerprint(raw_path)},
            "scored_results": scored_fingerprint,
            "report_summary": summary_fingerprint,
        },
        "models": [model],
        "case_count": case_count,
        "created_at": created_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def score_payload(
    input_path: Path,
    output_path: Path,
    dataset_path: Path,
    source_bundle: Path | None = None,
) -> None:
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
    if source_bundle is not None:
        cmd.extend(["--source-bundle", str(source_bundle)])
    process = subprocess.run(cmd, capture_output=True, text=True)
    if process.returncode != 0:
        stdout = process.stdout.strip()
        stderr = process.stderr.strip()
        raise RuntimeError(f"Scoring failed for {input_path}: {stdout or stderr}")


def write_report_summary(scored_path: Path, output_path: Path) -> None:
    with scored_path.open("r", encoding="utf-8") as stream:
        scored_payload = json.load(stream)

    if not isinstance(scored_payload, dict) or not isinstance(scored_payload.get("summary"), dict):
        raise ValueError(f"Scored artifact is missing summary: {scored_path}")

    write_json(output_path, scored_payload["summary"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the reasoning benchmark baseline models")
    parser.add_argument(
        "--config",
        help="Optional v2 RunConfig JSON file. When provided, it drives dataset, suite/mode, models, output, adapter command, and budgets.",
    )
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


def resolve_config_path(value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("RunConfig path value must be a non-empty string")
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def load_run_config(config_path: Path) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError("RunConfig must be a JSON object")
    return payload


def validate_config_benchmark(config_payload: dict[str, Any]) -> None:
    value = config_payload.get("benchmark")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"RunConfig benchmark must be {BENCHMARK_ID}")
    if value != value.strip():
        raise ValueError("RunConfig benchmark must be an exact string")
    if value != BENCHMARK_ID:
        raise ValueError(f"RunConfig benchmark must be {BENCHMARK_ID}")


def validate_config_schema_version(config_payload: dict[str, Any]) -> None:
    value = config_payload.get("schema_version")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("RunConfig schema_version must be 2.0.0")
    if value != value.strip():
        raise ValueError("RunConfig schema_version must be an exact string")
    if value != "2.0.0":
        raise ValueError("RunConfig schema_version must be 2.0.0")


def validate_config_id(config_payload: dict[str, Any]) -> None:
    value = config_payload.get("id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("RunConfig id must be a non-empty string")
    if value != value.strip():
        raise ValueError("RunConfig id must be an exact string")


def validate_config_suite_id(config_payload: dict[str, Any]) -> None:
    value = config_payload.get("suite_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("RunConfig suite_id must be a non-empty string")
    if value != value.strip():
        raise ValueError("RunConfig suite_id must be an exact string")
    validate_artifact_label(value, "RunConfig suite_id")


def config_execution(config_payload: dict[str, Any]) -> dict[str, Any]:
    if "execution" not in config_payload:
        raise ValueError("RunConfig execution is required")
    execution = config_payload.get("execution")
    if not isinstance(execution, dict):
        raise ValueError("RunConfig execution must be an object")
    return execution


def config_models(config_payload: dict[str, Any]) -> tuple[str, ...]:
    raw_models = config_payload.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise ValueError("RunConfig models must be a non-empty list")

    models: list[str] = []
    for item in raw_models:
        if isinstance(item, str):
            if not item.strip():
                raise ValueError("RunConfig model ids must be non-empty strings")
            if item != item.strip():
                raise ValueError("RunConfig model ids must be exact strings")
            models.append(item)
            continue
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            model_id = item["id"]
            if not model_id.strip():
                raise ValueError("RunConfig model ids must be non-empty strings")
            if model_id != model_id.strip():
                raise ValueError("RunConfig model ids must be exact strings")
            models.append(model_id)
            continue
        raise ValueError("Each RunConfig model must be a string or object with id")
    return resolve_models(models)


def parse_command_value(value: Any, field_name: str = "adapter_command") -> list[str]:
    if isinstance(value, str):
        if value != value.strip():
            raise ValueError(f"{field_name} string must be exact")
        command = shlex.split(value)
    elif isinstance(value, list):
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise ValueError(f"{field_name} list entries must be non-empty strings")
        if not all(item == item.strip() for item in value):
            raise ValueError(f"{field_name} list entries must be exact strings")
        command = list(value)
    else:
        raise ValueError(f"{field_name} must be a string or list")
    if not command:
        raise ValueError(f"{field_name} cannot be empty")
    return command


def config_provider_commands(
    config_payload: dict[str, Any],
    models: tuple[str, ...],
) -> dict[str, list[str]]:
    raw_models = config_payload.get("models", [])
    commands: dict[str, list[str]] = {}
    if isinstance(raw_models, list):
        for item in raw_models:
            if not isinstance(item, dict):
                continue

            model_id = item.get("id")
            if "adapter_command" in item:
                if not isinstance(model_id, str):
                    raise ValueError("RunConfig model adapter_command requires model id")
                command = parse_command_value(item.get("adapter_command"))
                if command:
                    commands[model_id] = command
                continue

            adapter = item.get("adapter")
            if adapter is None:
                continue
            if not isinstance(model_id, str):
                raise ValueError("RunConfig model adapter requires model id")
            if not isinstance(adapter, str):
                raise ValueError("RunConfig model adapter must be a string")
            if adapter != adapter.strip():
                raise ValueError("RunConfig model adapter must be an exact string")
            if adapter in BUILTIN_ADAPTER_COMMANDS:
                commands[model_id] = list(BUILTIN_ADAPTER_COMMANDS[adapter])
            elif adapter != "provider-command":
                raise ValueError(f"Unsupported RunConfig model adapter: {adapter}")

    execution = config_payload.get("execution", {})
    default_command = None
    if isinstance(execution, dict) and "provider_command" in execution:
        default_command = parse_command_value(
            execution.get("provider_command"),
            "RunConfig execution.provider_command",
        )

    if default_command:
        for model in models:
            commands.setdefault(model, list(default_command))
    return commands


def config_max_cases(execution: dict[str, Any]) -> int | None:
    value = execution.get("max_cases")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("RunConfig execution.max_cases must be a positive integer")
    if value < 1:
        raise ValueError("RunConfig execution.max_cases must be a positive integer")
    return value


def config_seed(execution: dict[str, Any]) -> int | str | None:
    value = execution.get("seed")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("RunConfig execution.seed must be an integer, string, or null")
    if isinstance(value, str) and not value.strip():
        raise ValueError("RunConfig execution.seed must be an integer, string, or null")
    if isinstance(value, str) and value != value.strip():
        raise ValueError("RunConfig execution.seed must be an exact string")
    return value


def config_timeout_seconds(execution: dict[str, Any]) -> float:
    value = execution.get("timeout_seconds", 45.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("RunConfig execution.timeout_seconds must be numeric")
    timeout = float(value)
    if not math.isfinite(timeout):
        raise ValueError("RunConfig execution.timeout_seconds must be finite")
    if timeout <= 0:
        raise ValueError("RunConfig execution.timeout_seconds must be positive")
    return timeout


def config_skip_scoring(execution: dict[str, Any]) -> bool:
    value = execution.get("skip_scoring", False)
    if not isinstance(value, bool):
        raise ValueError("RunConfig execution.skip_scoring must be a boolean")
    return value


def config_execution_mode(config_payload: dict[str, Any], execution: dict[str, Any]) -> str:
    if "mode" not in execution:
        return str(config_payload.get("suite_id"))
    mode = execution.get("mode")
    if not isinstance(mode, str) or not mode.strip():
        raise ValueError("RunConfig execution.mode must be a non-empty string")
    if mode != mode.strip():
        raise ValueError("RunConfig execution.mode must be an exact string")
    validate_artifact_label(mode, "RunConfig execution.mode")
    return mode


def config_suite_case_ids(config_payload: dict[str, Any]) -> tuple[str, ...] | None:
    suite = config_payload.get("suite")
    if suite is None:
        return None
    if not isinstance(suite, dict):
        raise ValueError("RunConfig suite must be an object")

    raw_case_ids = suite.get("case_ids")
    if not isinstance(raw_case_ids, list) or not raw_case_ids:
        raise ValueError("RunConfig suite.case_ids must be a non-empty list")

    case_ids: list[str] = []
    for case_id in raw_case_ids:
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("RunConfig suite.case_ids entries must be non-empty strings")
        if case_id != case_id.strip():
            raise ValueError("RunConfig suite.case_ids entries must be exact case ids")
        case_ids.append(case_id)
    return tuple(case_ids)


def config_prompt_contract(config_payload: dict[str, Any]) -> dict[str, Any]:
    if "prompt_contract" not in config_payload:
        raise ValueError("RunConfig prompt_contract is required")
    prompt_contract = config_payload.get("prompt_contract")
    if not isinstance(prompt_contract, dict):
        raise ValueError("RunConfig prompt_contract must be an object")
    version = prompt_contract.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("RunConfig prompt_contract.version must be a non-empty string")
    if version != version.strip():
        raise ValueError("RunConfig prompt_contract.version must be an exact string")
    response_format = prompt_contract.get("response_format")
    if not isinstance(response_format, str) or not response_format.strip():
        raise ValueError("RunConfig prompt_contract.response_format must be a non-empty string")
    if response_format != response_format.strip():
        raise ValueError("RunConfig prompt_contract.response_format must be an exact string")
    if response_format != "json_object":
        raise ValueError("RunConfig prompt_contract.response_format must be json_object")
    required_fields = prompt_contract.get("required_fields")
    if not isinstance(required_fields, list) or not required_fields:
        raise ValueError("RunConfig prompt_contract.required_fields must be a non-empty list")
    if not all(isinstance(field, str) and field.strip() for field in required_fields):
        raise ValueError("RunConfig prompt_contract.required_fields entries must be non-empty strings")
    if not all(field == field.strip() for field in required_fields):
        raise ValueError("RunConfig prompt_contract.required_fields entries must be exact field names")
    required_field_names = {field.strip() for field in required_fields}
    if "answer" not in required_field_names:
        raise ValueError("RunConfig prompt_contract.required_fields must include answer")
    if "reasoning" not in required_field_names:
        raise ValueError("RunConfig prompt_contract.required_fields must include reasoning")
    return copy.deepcopy(prompt_contract)


def config_output_dir(config_payload: dict[str, Any]) -> Path:
    output = config_payload.get("output")
    if not isinstance(output, dict) or "bundle_dir" not in output:
        raise ValueError("RunConfig output.bundle_dir is required")

    bundle_dir = output.get("bundle_dir")
    if not isinstance(bundle_dir, str) or not bundle_dir.strip():
        raise ValueError("RunConfig output.bundle_dir must be a non-empty string")
    if bundle_dir != bundle_dir.strip():
        raise ValueError("RunConfig output.bundle_dir must be an exact string")
    return resolve_config_path(bundle_dir)


def config_dataset_path(config_payload: dict[str, Any]) -> Path:
    dataset = config_payload.get("dataset")
    if not isinstance(dataset, dict) or "path" not in dataset:
        raise ValueError("RunConfig dataset.path is required")

    path = dataset.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("RunConfig dataset.path must be a non-empty string")
    if path != path.strip():
        raise ValueError("RunConfig dataset.path must be an exact string")
    return resolve_config_path(path)


def validate_dataset_fingerprint(dataset: dict[str, Any], dataset_path: Path) -> None:
    fingerprint = dataset.get("fingerprint")
    if fingerprint is None:
        return
    if not isinstance(fingerprint, dict):
        raise ValueError("RunConfig dataset.fingerprint must be an object")

    algorithm = fingerprint.get("algorithm")
    value = fingerprint.get("value")
    if (
        not isinstance(algorithm, str)
        or not algorithm.strip()
        or not isinstance(value, str)
        or not value.strip()
    ):
        raise ValueError("RunConfig dataset.fingerprint must include sha256 algorithm and value")
    if algorithm != algorithm.strip():
        raise ValueError("RunConfig dataset.fingerprint.algorithm must be an exact string")
    if algorithm != "sha256":
        raise ValueError("RunConfig dataset.fingerprint must include sha256 algorithm and value")
    if value != value.strip():
        raise ValueError("RunConfig dataset.fingerprint.value must be an exact string")

    actual = dataset_fingerprint(dataset_path)
    if value != actual:
        raise ValueError("RunConfig dataset.fingerprint does not match dataset")


def request_from_config(config_path: Path) -> RunRequest:
    config_payload = load_run_config(config_path)
    validate_config_schema_version(config_payload)
    validate_config_id(config_payload)
    validate_config_benchmark(config_payload)
    validate_config_suite_id(config_payload)

    dataset = config_payload.get("dataset")
    dataset_path = config_dataset_path(config_payload)
    validate_dataset_fingerprint(dataset, dataset_path)

    run_dir = config_output_dir(config_payload)

    execution = config_execution(config_payload)

    suite_case_ids = config_suite_case_ids(config_payload)
    mode = config_execution_mode(config_payload, execution)
    if mode not in SUPPORTED_MODES and suite_case_ids is None:
        raise ValueError(f"Unsupported suite or mode in RunConfig: {mode}")

    models = config_models(config_payload)
    prompt_contract = config_prompt_contract(config_payload)
    return RunRequest(
        mode=str(mode),
        dataset_path=dataset_path,
        run_dir=run_dir,
        models=models,
        provider_commands=config_provider_commands(config_payload, models),
        prompt_timeout=config_timeout_seconds(execution),
        skip_scoring=config_skip_scoring(execution),
        max_cases=config_max_cases(execution),
        seed=config_seed(execution),
        suite_case_ids=suite_case_ids,
        prompt_contract=prompt_contract,
        config_payload=config_payload,
        config_path=config_path,
    )


def request_from_args(args: argparse.Namespace) -> RunRequest:
    models = resolve_models(args.models)
    provider_commands = {
        model: list(args.provider_command)
        for model in models
        if args.provider_command
    }
    return RunRequest(
        mode=args.mode,
        dataset_path=Path(args.dataset),
        run_dir=Path(args.run_dir),
        models=models,
        provider_commands=provider_commands,
        prompt_timeout=args.prompt_timeout,
        skip_scoring=args.skip_scoring,
        max_cases=None,
        seed=None,
        suite_case_ids=None,
        prompt_contract=None,
    )


def build_run_request(args: argparse.Namespace) -> RunRequest:
    config = getattr(args, "config", None)
    if config:
        return request_from_config(resolve_config_path(config))
    return request_from_args(args)


def resolve_models(models: Iterable[str]) -> tuple[str, ...]:
    requested = tuple(models)
    unsupported = [model for model in requested if model not in SUPPORTED_MODELS]
    if unsupported:
        raise ValueError(f"Unsupported models requested: {', '.join(unsupported)}")
    return requested


def cmd_run(args: argparse.Namespace) -> int:
    request = build_run_request(args)
    questions = load_questions(request.dataset_path)
    selected = select_questions(
        questions,
        request.mode,
        request.max_cases,
        request.seed,
        request.suite_case_ids,
    )

    for model in request.models:
        provider_command = request.provider_commands.get(model)
        raw_path, scored_path = run_paths(request.run_dir, model, request.mode)
        report_summary_path = summary_path(request.run_dir, model, request.mode)
        payload = build_payload(
            model=model,
            mode=request.mode,
            questions=selected,
            dataset_path=request.dataset_path,
            max_cases=request.max_cases,
            seed=request.seed,
            prompt_contract=request.prompt_contract,
        )
        if request.config_payload:
            payload["run_config"] = request.config_payload

        if provider_command:
            for index, row in enumerate(selected):
                response = run_provider(provider_command, model, row["prompt"], request.prompt_timeout)
                payload["results"][index] = build_result_record(
                    row=row,
                    model=model,
                    answer=response.answer,
                    reasoning=response.reasoning,
                    notes=response.notes,
                    provider=response,
                )
        write_json(raw_path, payload)
        print(f"wrote raw artifact: {raw_path}")

        if request.skip_scoring:
            bundle_path = manifest_path(request.run_dir, model, request.mode)
            if bundle_path.exists():
                bundle_path.unlink()
            print("skipping scoring")
            continue

        bundle_path = manifest_path(request.run_dir, model, request.mode)
        score_payload(raw_path, scored_path, request.dataset_path, bundle_path)
        print(f"wrote scored artifact: {scored_path}")
        write_report_summary(scored_path, report_summary_path)
        print(f"wrote report summary: {report_summary_path}")

        manifest = build_run_artifact_bundle(
            model=model,
            mode=request.mode,
            raw_path=raw_path,
            scored_path=scored_path,
            report_summary_path=report_summary_path,
            dataset_path=request.dataset_path,
            case_count=len(selected),
            created_at=str(payload["created_at"]),
            config_path=request.config_path,
        )
        write_json(bundle_path, manifest)
        print(f"wrote manifest: {bundle_path}")

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
