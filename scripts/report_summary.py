#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import score_run


BENCHMARK_ID = "reasoning-benchmark"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def result_case_id(record: Dict[str, Any]) -> str:
    for field in ("id", "case_id"):
        raw_id = record.get(field)
        if raw_id is None:
            continue
        if not isinstance(raw_id, str):
            continue
        case_id = raw_id
        if case_id.strip():
            return case_id
    return ""


def has_non_string_case_id(record: Dict[str, Any]) -> bool:
    for field in ("id", "case_id"):
        raw_id = record.get(field)
        if raw_id is not None and not isinstance(raw_id, str):
            return True
    return False


def has_padded_case_id(record: Dict[str, Any]) -> bool:
    for field in ("id", "case_id"):
        raw_id = record.get(field)
        if raw_id is None:
            continue
        if not isinstance(raw_id, str):
            continue
        case_id = raw_id
        if case_id.strip() and case_id != case_id.strip():
            return True
    return False


def has_mismatched_case_id_aliases(record: Dict[str, Any]) -> bool:
    raw_id = record.get("id")
    raw_case_id = record.get("case_id")
    return isinstance(raw_id, str) and isinstance(raw_case_id, str) and raw_id != raw_case_id


def has_model_outside_manifest(record: Dict[str, Any], manifest_models: Sequence[str]) -> bool:
    raw_model = record.get("model")
    return isinstance(raw_model, str) and raw_model.strip() and raw_model not in manifest_models


def scored_results_from_payload(payload: Any, source_path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not isinstance(payload, dict):
        raise ValueError(f"Scored artifact must be a JSON object: {source_path}")

    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError(f"Scored artifact is missing results list: {source_path}")
    if any(not isinstance(item, dict) for item in results):
        raise ValueError(f"Scored artifact results must contain JSON objects: {source_path}")

    summary = payload.get("summary")
    summary_meta = summary if isinstance(summary, dict) else {}
    return summary_meta, [dict(item) for item in results]


def scored_path_from_bundle(bundle_path: Path) -> Tuple[Path, Dict[str, Any]]:
    manifest = load_json(bundle_path)
    if not isinstance(manifest, dict):
        raise ValueError(f"Bundle manifest must be a JSON object: {bundle_path}")

    schema_version = manifest.get("schema_version")
    if isinstance(schema_version, str) and schema_version != schema_version.strip():
        raise ValueError(f"Bundle manifest schema_version must be an exact string: {bundle_path}")
    if schema_version != "2.0.0":
        raise ValueError(f"Bundle manifest schema_version must be 2.0.0: {bundle_path}")

    bundle_id = manifest.get("id")
    if not isinstance(bundle_id, str) or not bundle_id.strip():
        raise ValueError(f"Bundle manifest id must be a non-empty string: {bundle_path}")
    if bundle_id != bundle_id.strip():
        raise ValueError(f"Bundle manifest id must be an exact string: {bundle_path}")

    benchmark = manifest.get("benchmark")
    if not isinstance(benchmark, str) or not benchmark.strip():
        raise ValueError(f"Bundle manifest benchmark must be {BENCHMARK_ID}: {bundle_path}")
    if benchmark != benchmark.strip():
        raise ValueError(f"Bundle manifest benchmark must be an exact string: {bundle_path}")
    if benchmark != BENCHMARK_ID:
        raise ValueError(f"Bundle manifest benchmark must be {BENCHMARK_ID}: {bundle_path}")

    suite_id = manifest.get("suite_id")
    if not isinstance(suite_id, str) or not suite_id.strip():
        raise ValueError(f"Bundle manifest suite_id must be a non-empty string: {bundle_path}")
    if suite_id != suite_id.strip():
        raise ValueError(f"Bundle manifest suite_id must be an exact string: {bundle_path}")

    models = manifest.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError(f"Bundle manifest models must be a non-empty list: {bundle_path}")
    for model in models:
        if not isinstance(model, str) or not model.strip():
            raise ValueError(f"Bundle manifest models must contain non-empty strings: {bundle_path}")
        if model != model.strip():
            raise ValueError(f"Bundle manifest models must contain exact strings: {bundle_path}")

    case_count = manifest.get("case_count")
    if isinstance(case_count, bool) or not isinstance(case_count, int) or case_count < 0:
        raise ValueError(f"Bundle manifest case_count must be a non-negative integer: {bundle_path}")

    created_at = manifest.get("created_at")
    if not isinstance(created_at, str) or not created_at.strip():
        raise ValueError(f"Bundle manifest created_at must be a non-empty string: {bundle_path}")
    if created_at != created_at.strip():
        raise ValueError(f"Bundle manifest created_at must be an exact string: {bundle_path}")

    completed_at = manifest.get("completed_at")
    if completed_at is not None and (not isinstance(completed_at, str) or not completed_at.strip()):
        raise ValueError(
            f"Bundle manifest completed_at must be null or a non-empty string: {bundle_path}"
        )
    if isinstance(completed_at, str) and completed_at != completed_at.strip():
        raise ValueError(f"Bundle manifest completed_at must be an exact string: {bundle_path}")

    fingerprints = manifest.get("fingerprints")
    if not isinstance(fingerprints, dict):
        raise ValueError(f"Bundle manifest fingerprints must be a JSON object: {bundle_path}")
    scored_results_fingerprint = fingerprints.get("scored_results")
    if not isinstance(scored_results_fingerprint, dict):
        raise ValueError(
            f"Bundle manifest fingerprints.scored_results must be a JSON object: {bundle_path}"
        )
    scored_results_algorithm = scored_results_fingerprint.get("algorithm")
    if (
        isinstance(scored_results_algorithm, str)
        and scored_results_algorithm != scored_results_algorithm.strip()
    ):
        raise ValueError(
            f"Bundle manifest fingerprints.scored_results.algorithm must be an exact string: {bundle_path}"
        )
    if scored_results_algorithm != "sha256":
        raise ValueError(
            f"Bundle manifest fingerprints.scored_results.algorithm must be sha256: {bundle_path}"
        )
    scored_results_value = scored_results_fingerprint.get("value")
    if not isinstance(scored_results_value, str) or not scored_results_value.strip():
        raise ValueError(
            f"Bundle manifest fingerprints.scored_results.value must be a non-empty string: {bundle_path}"
        )
    if scored_results_value != scored_results_value.strip():
        raise ValueError(
            f"Bundle manifest fingerprints.scored_results.value must be an exact string: {bundle_path}"
        )

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError(f"Bundle manifest artifacts must be a JSON object: {bundle_path}")
    scored_results = artifacts.get("scored_results")
    if not isinstance(scored_results, str) or not scored_results.strip():
        raise ValueError(
            f"Bundle manifest artifacts.scored_results must be a non-empty string: {bundle_path}"
        )
    if scored_results != scored_results.strip():
        raise ValueError(f"Bundle manifest artifacts.scored_results must be an exact path: {bundle_path}")

    scored_path = Path(scored_results)
    if not scored_path.is_absolute():
        scored_path = bundle_path.parent / scored_path
    actual_scored_results_value = file_sha256(scored_path)
    if actual_scored_results_value != scored_results_value:
        raise ValueError(
            f"Bundle manifest fingerprints.scored_results.value does not match scored artifact: {bundle_path}"
        )

    report_summary = artifacts.get("report_summary")
    if report_summary is not None:
        if not isinstance(report_summary, str) or not report_summary.strip():
            raise ValueError(
                f"Bundle manifest artifacts.report_summary must be null or a non-empty string: {bundle_path}"
            )
        if report_summary != report_summary.strip():
            raise ValueError(
                f"Bundle manifest artifacts.report_summary must be an exact path: {bundle_path}"
            )
        report_summary_fingerprint = fingerprints.get("report_summary")
        if not isinstance(report_summary_fingerprint, dict):
            raise ValueError(
                f"Bundle manifest fingerprints.report_summary must be a JSON object: {bundle_path}"
            )
        report_summary_algorithm = report_summary_fingerprint.get("algorithm")
        if (
            isinstance(report_summary_algorithm, str)
            and report_summary_algorithm != report_summary_algorithm.strip()
        ):
            raise ValueError(
                f"Bundle manifest fingerprints.report_summary.algorithm must be an exact string: {bundle_path}"
            )
        if report_summary_algorithm != "sha256":
            raise ValueError(
                f"Bundle manifest fingerprints.report_summary.algorithm must be sha256: {bundle_path}"
            )
        report_summary_value = report_summary_fingerprint.get("value")
        if not isinstance(report_summary_value, str) or not report_summary_value.strip():
            raise ValueError(
                f"Bundle manifest fingerprints.report_summary.value must be a non-empty string: {bundle_path}"
            )
        if report_summary_value != report_summary_value.strip():
            raise ValueError(
                f"Bundle manifest fingerprints.report_summary.value must be an exact string: {bundle_path}"
            )

        report_summary_path = Path(report_summary)
        if not report_summary_path.is_absolute():
            report_summary_path = bundle_path.parent / report_summary_path
        actual_report_summary_value = file_sha256(report_summary_path)
        if actual_report_summary_value != report_summary_value:
            raise ValueError(
                "Bundle manifest fingerprints.report_summary.value does not match "
                f"report summary artifact: {bundle_path}"
            )
    if "run_config" not in manifest:
        raise ValueError(f"Bundle manifest run_config field is required: {bundle_path}")
    run_config = manifest.get("run_config")
    if run_config is not None and (not isinstance(run_config, str) or not run_config.strip()):
        raise ValueError(
            f"Bundle manifest run_config must be null or a non-empty string: {bundle_path}"
        )
    if isinstance(run_config, str) and run_config != run_config.strip():
        raise ValueError(f"Bundle manifest run_config must be an exact string: {bundle_path}")

    raw_results = artifacts.get("raw_results")
    if not isinstance(raw_results, str) or not raw_results.strip():
        raise ValueError(
            f"Bundle manifest artifacts.raw_results must be a non-empty string: {bundle_path}"
        )
    if raw_results != raw_results.strip():
        raise ValueError(f"Bundle manifest artifacts.raw_results must be an exact path: {bundle_path}")
    raw_results_fingerprint = fingerprints.get("raw_results")
    if not isinstance(raw_results_fingerprint, dict):
        raise ValueError(
            f"Bundle manifest fingerprints.raw_results must be a JSON object: {bundle_path}"
        )
    raw_results_algorithm = raw_results_fingerprint.get("algorithm")
    if (
        isinstance(raw_results_algorithm, str)
        and raw_results_algorithm != raw_results_algorithm.strip()
    ):
        raise ValueError(
            f"Bundle manifest fingerprints.raw_results.algorithm must be an exact string: {bundle_path}"
        )
    if raw_results_algorithm != "sha256":
        raise ValueError(
            f"Bundle manifest fingerprints.raw_results.algorithm must be sha256: {bundle_path}"
        )
    raw_results_value = raw_results_fingerprint.get("value")
    if not isinstance(raw_results_value, str) or not raw_results_value.strip():
        raise ValueError(
            f"Bundle manifest fingerprints.raw_results.value must be a non-empty string: {bundle_path}"
        )
    if raw_results_value != raw_results_value.strip():
        raise ValueError(
            f"Bundle manifest fingerprints.raw_results.value must be an exact string: {bundle_path}"
        )
    raw_path = Path(raw_results)
    if not raw_path.is_absolute():
        raw_path = bundle_path.parent / raw_path
    actual_raw_results_value = file_sha256(raw_path)
    if actual_raw_results_value != raw_results_value:
        raise ValueError(
            f"Bundle manifest fingerprints.raw_results.value does not match raw artifact: {bundle_path}"
        )
    dataset_fingerprint = fingerprints.get("dataset")
    if not isinstance(dataset_fingerprint, dict):
        raise ValueError(
            f"Bundle manifest fingerprints.dataset must be a JSON object: {bundle_path}"
        )
    dataset_algorithm = dataset_fingerprint.get("algorithm")
    if isinstance(dataset_algorithm, str) and dataset_algorithm != dataset_algorithm.strip():
        raise ValueError(
            f"Bundle manifest fingerprints.dataset.algorithm must be an exact string: {bundle_path}"
        )
    if dataset_algorithm != "sha256":
        raise ValueError(
            f"Bundle manifest fingerprints.dataset.algorithm must be sha256: {bundle_path}"
        )
    dataset_value = dataset_fingerprint.get("value")
    if not isinstance(dataset_value, str) or not dataset_value.strip():
        raise ValueError(
            f"Bundle manifest fingerprints.dataset.value must be a non-empty string: {bundle_path}"
        )
    if dataset_value != dataset_value.strip():
        raise ValueError(
            f"Bundle manifest fingerprints.dataset.value must be an exact string: {bundle_path}"
        )
    raw_payload = load_json(raw_path)
    if not isinstance(raw_payload, dict):
        raise ValueError(f"Bundle manifest raw artifact must be a JSON object: {bundle_path}")
    raw_results_list = raw_payload.get("results")
    if not isinstance(raw_results_list, list):
        raise ValueError(f"Bundle manifest raw artifact is missing results list: {bundle_path}")
    if any(not isinstance(item, dict) for item in raw_results_list):
        raise ValueError(
            f"Bundle manifest raw artifact results must contain JSON objects: {bundle_path}"
        )
    raw_case_count = raw_payload.get("case_count")
    if (
        isinstance(raw_case_count, int)
        and not isinstance(raw_case_count, bool)
        and raw_case_count != case_count
    ):
        raise ValueError(
            "Bundle manifest case_count does not match "
            f"raw artifact case_count: {bundle_path}"
        )
    raw_dataset = raw_payload.get("dataset")
    if isinstance(raw_dataset, dict):
        raw_dataset_case_count = raw_dataset.get("case_count")
        if (
            isinstance(raw_dataset_case_count, int)
            and not isinstance(raw_dataset_case_count, bool)
            and raw_dataset_case_count != case_count
        ):
            raise ValueError(
                "Bundle manifest case_count does not match "
                f"raw artifact dataset.case_count: {bundle_path}"
            )
        raw_dataset_question_count = raw_dataset.get("question_count")
        if (
            isinstance(raw_dataset_question_count, int)
            and not isinstance(raw_dataset_question_count, bool)
            and raw_dataset_question_count != case_count
        ):
            raise ValueError(
                "Bundle manifest case_count does not match "
                f"raw artifact dataset.question_count: {bundle_path}"
            )
        raw_dataset_hash = raw_dataset.get("path_hash")
        if isinstance(raw_dataset_hash, str) and raw_dataset_hash != dataset_value:
            raise ValueError(
                "Bundle manifest fingerprints.dataset.value does not match "
                f"raw artifact dataset.path_hash: {bundle_path}"
            )
    scored_payload = load_json(scored_path)
    if not isinstance(scored_payload, dict):
        raise ValueError(f"Bundle manifest scored artifact must be a JSON object: {bundle_path}")
    scored_results = scored_payload.get("results")
    if not isinstance(scored_results, list):
        raise ValueError(f"Bundle manifest scored artifact is missing results list: {bundle_path}")
    if any(not isinstance(item, dict) for item in scored_results):
        raise ValueError(
            f"Bundle manifest scored artifact results must contain JSON objects: {bundle_path}"
        )
    scored_summary = scored_payload.get("summary")
    if isinstance(scored_summary, dict):
        scored_overall = scored_summary.get("overall")
        if isinstance(scored_overall, dict):
            scored_summary_case_count = scored_overall.get("case_count")
            if (
                isinstance(scored_summary_case_count, int)
                and not isinstance(scored_summary_case_count, bool)
                and scored_summary_case_count != case_count
            ):
                raise ValueError(
                    "Bundle manifest case_count does not match "
                    f"scored artifact summary.overall.case_count: {bundle_path}"
                )
            scored_summary_question_count = scored_overall.get("question_count")
            if (
                isinstance(scored_summary_question_count, int)
                and not isinstance(scored_summary_question_count, bool)
                and scored_summary_question_count != case_count
            ):
                raise ValueError(
                    "Bundle manifest case_count does not match "
                    f"scored artifact summary.overall.question_count: {bundle_path}"
                )
    if len(scored_results) != case_count:
        raise ValueError(
            "Bundle manifest case_count does not match "
            f"scored artifact results length: {bundle_path}"
        )
    if len(raw_results_list) != case_count:
        raise ValueError(
            "Bundle manifest case_count does not match "
            f"raw artifact results length: {bundle_path}"
        )
    if any(has_non_string_case_id(raw_result) for raw_result in raw_results_list) or any(
        has_non_string_case_id(scored_result) for scored_result in scored_results
    ):
        raise ValueError(
            f"Bundle manifest result case ids must be exact strings: {bundle_path}"
        )
    if any(has_padded_case_id(raw_result) for raw_result in raw_results_list) or any(
        has_padded_case_id(scored_result) for scored_result in scored_results
    ):
        raise ValueError(
            f"Bundle manifest result case ids must be exact strings: {bundle_path}"
        )
    if any(has_mismatched_case_id_aliases(raw_result) for raw_result in raw_results_list) or any(
        has_mismatched_case_id_aliases(scored_result) for scored_result in scored_results
    ):
        raise ValueError(
            f"Bundle manifest result id and case_id values must match: {bundle_path}"
        )
    if any(has_model_outside_manifest(raw_result, models) for raw_result in raw_results_list):
        raise ValueError(
            "Bundle manifest raw artifact models must be listed in manifest models: "
            f"{bundle_path}"
        )
    if any(has_model_outside_manifest(scored_result, models) for scored_result in scored_results):
        raise ValueError(
            "Bundle manifest scored artifact models must be listed in manifest models: "
            f"{bundle_path}"
        )
    if any(not result_case_id(raw_result) for raw_result in raw_results_list):
        raise ValueError(
            f"Bundle manifest raw artifact results must include case ids: {bundle_path}"
        )
    if any(not result_case_id(scored_result) for scored_result in scored_results):
        raise ValueError(
            f"Bundle manifest scored artifact results must include case ids: {bundle_path}"
        )
    for raw_result, scored_result in zip(raw_results_list, scored_results):
        raw_case_id = result_case_id(raw_result)
        scored_case_id = result_case_id(scored_result)
        if raw_case_id and scored_case_id and raw_case_id != scored_case_id:
            raise ValueError(
                "Bundle manifest raw and scored artifact case ids do not match: "
                f"{bundle_path}"
            )
    return scored_path, manifest


def select_summary_identity(summary_metas: Sequence[Dict[str, Any]]) -> Tuple[str, str]:
    benchmarks = {
        str(meta.get("benchmark")).strip()
        for meta in summary_metas
        if isinstance(meta.get("benchmark"), str) and str(meta.get("benchmark")).strip()
    }
    suite_ids = {
        str(meta.get("suite_id")).strip()
        for meta in summary_metas
        if isinstance(meta.get("suite_id"), str) and str(meta.get("suite_id")).strip()
    }

    benchmark = next(iter(benchmarks)) if len(benchmarks) == 1 else "reasoning-benchmark"
    suite_id = next(iter(suite_ids)) if len(suite_ids) == 1 else "combined"
    return benchmark, suite_id


def collect_source_bundles(summary_metas: Sequence[Dict[str, Any]], explicit_bundles: Sequence[str]) -> List[str]:
    source_bundles: List[str] = []
    seen = set()

    summary_source_bundles: List[Any] = []
    for meta in summary_metas:
        meta_source_bundles = meta.get("source_bundles")
        if isinstance(meta_source_bundles, list):
            summary_source_bundles.extend(meta_source_bundles)

    for source in [*explicit_bundles, *summary_source_bundles]:
        if not isinstance(source, str) or not source.strip() or source in seen:
            continue
        seen.add(source)
        source_bundles.append(source)

    return source_bundles


def build_report_summary(
    *,
    input_paths: Optional[Sequence[Path]] = None,
    bundle_paths: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    scored_paths = list(input_paths or [])
    explicit_source_bundles = [str(path) for path in bundle_paths or []]
    manifest_metas: List[Dict[str, Any]] = []
    for bundle_path in bundle_paths or []:
        scored_path, manifest_meta = scored_path_from_bundle(bundle_path)
        scored_paths.append(scored_path)
        manifest_metas.append(manifest_meta)

    if not scored_paths:
        raise ValueError("At least one scored artifact or bundle manifest is required")

    summary_metas: List[Dict[str, Any]] = list(manifest_metas)
    scored_records: List[Dict[str, Any]] = []
    for scored_path in scored_paths:
        summary_meta, records = scored_results_from_payload(load_json(scored_path), scored_path)
        summary_metas.append(summary_meta)
        scored_records.extend(records)

    benchmark, suite_id = select_summary_identity(summary_metas)
    source_bundles = collect_source_bundles(summary_metas, explicit_source_bundles)
    return score_run.build_summary(
        scored_records,
        benchmark=benchmark,
        suite_id=suite_id,
        source_bundles=source_bundles,
    )


def cmd_report(args: argparse.Namespace) -> int:
    summary = build_report_summary(
        input_paths=[Path(path) for path in args.input or []],
        bundle_paths=[Path(path) for path in args.bundle or []],
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)

    print(f"Wrote report summary to {output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a v2 report summary from scored artifacts")
    parser.add_argument(
        "--input",
        action="append",
        help="Scored artifact JSON path to include in the report",
    )
    parser.add_argument(
        "--bundle",
        action="append",
        help="RunArtifactBundle manifest whose scored artifact should be included",
    )
    parser.add_argument("--output", required=True, help="Output report summary JSON path")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return cmd_report(args)
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
