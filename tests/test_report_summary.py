from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
import unittest

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
sys.path.append(str(REPO_ROOT / "scripts"))

import report_summary


_DELETE = object()
_UNSET = object()

_DEFAULT_RAW_PAYLOAD = {"results": [{"id": "q001"}]}
_DEFAULT_SCORED_PAYLOAD = {
    "results": [
        {
            "case_id": "q001",
            "model": "gpt-5.4",
            "evaluation_mode": "exact",
            "scoring_status": {"score": 1, "dimensions": []},
        }
    ],
}


def _deep_merge(base: dict, overrides: dict) -> dict:
    result = dict(base)
    for key, value in overrides.items():
        if value is _DELETE:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ReportSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(__file__).resolve().parent / "tmp" / "report-summary"
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir)
        self.tmp_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir)

    def _make_bundle(
        self,
        *,
        manifest_overrides: dict | None = None,
        raw_content=_UNSET,
        scored_content=_UNSET,
        auto_fingerprints: bool = True,
        raw_artifact_in_manifest: str | None = None,
        scored_artifact_in_manifest: str | None = None,
        prefix: str = "gpt-5-4.smoke",
    ) -> Path:
        raw_path = self.tmp_dir / f"{prefix}.raw.json"
        scored_path = self.tmp_dir / f"{prefix}.scored.json"
        bundle_path = self.tmp_dir / f"{prefix}.manifest.json"

        raw_payload = _DEFAULT_RAW_PAYLOAD if raw_content is _UNSET else raw_content
        scored_payload = _DEFAULT_SCORED_PAYLOAD if scored_content is _UNSET else scored_content

        write_raw = raw_payload is not None
        if write_raw:
            raw_path.write_text(json.dumps(raw_payload), encoding="utf-8")

        write_scored = scored_payload is not None
        if write_scored:
            scored_path.write_text(json.dumps(scored_payload), encoding="utf-8")

        artifacts: dict = {}
        if write_scored:
            artifacts["scored_results"] = (
                scored_artifact_in_manifest
                if scored_artifact_in_manifest is not None
                else scored_path.name
            )
        if write_raw:
            artifacts["raw_results"] = (
                raw_artifact_in_manifest
                if raw_artifact_in_manifest is not None
                else raw_path.name
            )

        fingerprints: dict = {}
        if auto_fingerprints:
            if write_scored:
                fingerprints["scored_results"] = {
                    "algorithm": "sha256",
                    "value": hashlib.sha256(scored_path.read_bytes()).hexdigest(),
                }
            if write_raw:
                fingerprints["raw_results"] = {
                    "algorithm": "sha256",
                    "value": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                }
                fingerprints["dataset"] = {
                    "algorithm": "sha256",
                    "value": "dataset-fingerprint",
                }

        case_count = 0
        if write_scored and isinstance(scored_payload, dict):
            results = scored_payload.get("results")
            if isinstance(results, list):
                case_count = len(results)

        manifest = {
            "schema_version": "2.0.0",
            "id": "baseline-smoke-gpt-5-4",
            "benchmark": "reasoning-benchmark",
            "suite_id": "smoke",
            "run_config": None,
            "models": ["gpt-5.4"],
            "case_count": case_count,
            "created_at": "2026-04-26T00:00:00Z",
            "fingerprints": fingerprints,
            "artifacts": artifacts,
        }

        if manifest_overrides:
            manifest = _deep_merge(manifest, manifest_overrides)

        bundle_path.write_text(json.dumps(manifest), encoding="utf-8")
        return bundle_path

    def test_report_can_be_built_from_bundle_manifest(self) -> None:
        bundle_path = self._make_bundle()

        summary = report_summary.build_report_summary(bundle_paths=[bundle_path])

        self.assertEqual(summary["schema_version"], "2.0.0")
        self.assertEqual(summary["benchmark"], "reasoning-benchmark")
        self.assertEqual(summary["suite_id"], "smoke")
        self.assertEqual(summary["source_bundles"], [str(bundle_path)])
        self.assertEqual(summary["overall"]["case_count"], 1)
        self.assertEqual(summary["by_model"]["gpt-5.4"]["accuracy"], 1.0)

    def test_bundle_manifest_rejects_traversing_scored_results_path(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content=None,
            auto_fingerprints=False,
            manifest_overrides={
                "fingerprints": {
                    "scored_results": {"algorithm": "sha256", "value": "0" * 64},
                },
                "artifacts": {"scored_results": "../outside.scored.json"},
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest artifacts.scored_results must stay within bundle directory",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_report_deduplicates_scored_input_also_referenced_by_bundle(self) -> None:
        bundle_path = self._make_bundle()
        scored_path = self.tmp_dir / "gpt-5-4.smoke.scored.json"

        summary = report_summary.build_report_summary(
            input_paths=[scored_path],
            bundle_paths=[bundle_path],
        )

        self.assertEqual(summary["overall"]["case_count"], 1)

    def test_bundle_manifest_rejects_mismatched_scored_results_fingerprint(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content={"results": []},
            manifest_overrides={
                "fingerprints": {
                    "scored_results": {"algorithm": "sha256", "value": "0" * 64},
                },
                "case_count": 1,
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.scored_results.value does not match scored artifact",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_mismatched_raw_results_fingerprint(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": []},
            scored_content={"results": []},
            manifest_overrides={
                "fingerprints": {
                    "raw_results": {"algorithm": "sha256", "value": "0" * 64},
                },
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.raw_results.value does not match raw artifact",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_mismatched_report_summary_fingerprint(self) -> None:
        summary_path = self.tmp_dir / "gpt-5-4.smoke.summary.json"
        summary_path.write_text(json.dumps({"schema_version": "2.0.0"}), encoding="utf-8")
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content={"results": []},
            manifest_overrides={
                "fingerprints": {
                    "raw_results": {"algorithm": "sha256", "value": "raw-results-fingerprint"},
                    "report_summary": {"algorithm": "sha256", "value": "0" * 64},
                },
                "artifacts": {
                    "raw_results": "gpt-5-4.smoke.raw.json",
                    "report_summary": summary_path.name,
                },
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.report_summary.value does not match report summary artifact",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_report_preserves_source_bundles_from_scored_input_summary(self) -> None:
        scored_path = self.tmp_dir / "gpt-5-4.smoke.scored.json"
        scored_path.write_text(
            json.dumps(
                {
                    "summary": {
                        "benchmark": "reasoning-benchmark",
                        "suite_id": "smoke",
                        "source_bundles": ["runs/gpt-5-4.smoke.manifest.json"],
                    },
                    "results": [
                        {
                            "model": "gpt-5.4",
                            "answer": "42",
                            "evaluation_mode": "exact",
                            "scoring_status": {"score": 1, "dimensions": []},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        summary = report_summary.build_report_summary(input_paths=[scored_path])

        self.assertEqual(summary["source_bundles"], ["runs/gpt-5-4.smoke.manifest.json"])

    def test_bundle_manifest_rejects_padded_scored_results_path(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content=None,
            auto_fingerprints=False,
            manifest_overrides={
                "case_count": 1,
                "fingerprints": {
                    "scored_results": {"algorithm": "sha256", "value": "0" * 64},
                },
                "artifacts": {"scored_results": " gpt-5-4.smoke.scored.json "},
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest artifacts.scored_results must be an exact path",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_missing_case_count(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content=None,
            auto_fingerprints=False,
            manifest_overrides={
                "case_count": _DELETE,
                "artifacts": {"scored_results": "gpt-5-4.smoke.scored.json"},
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest case_count must be a non-negative integer",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_missing_created_at(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content={"results": []},
            auto_fingerprints=False,
            manifest_overrides={"created_at": _DELETE},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest created_at must be a non-empty string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_missing_run_config_field(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content={"results": []},
            manifest_overrides={"run_config": _DELETE},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest run_config field is required",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_blank_run_config_path(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content={"results": []},
            manifest_overrides={"run_config": "   "},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest run_config must be null or a non-empty string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_padded_run_config_path(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content={"results": []},
            manifest_overrides={"run_config": " config.json "},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest run_config must be an exact string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_padded_created_at(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content={"results": []},
            auto_fingerprints=False,
            manifest_overrides={"created_at": " 2026-04-26T00:00:00Z "},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest created_at must be an exact string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_padded_completed_at(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content={"results": []},
            manifest_overrides={"completed_at": " 2026-04-26T00:00:01Z "},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest completed_at must be an exact string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_missing_fingerprints(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content={"results": []},
            auto_fingerprints=False,
            manifest_overrides={"fingerprints": _DELETE},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints must be a JSON object",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_missing_scored_results_fingerprint(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content=None,
            auto_fingerprints=False,
            manifest_overrides={
                "case_count": 1,
                "artifacts": {"scored_results": "gpt-5-4.smoke.scored.json"},
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.scored_results must be a JSON object",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_missing_artifacts_object(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content=None,
            auto_fingerprints=False,
            manifest_overrides={
                "case_count": 1,
                "fingerprints": {
                    "scored_results": {"algorithm": "sha256", "value": "0" * 64},
                },
                "artifacts": _DELETE,
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest artifacts must be a JSON object",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_blank_scored_results_artifact_path(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content=None,
            auto_fingerprints=False,
            manifest_overrides={
                "case_count": 1,
                "fingerprints": {
                    "scored_results": {"algorithm": "sha256", "value": "0" * 64},
                },
                "artifacts": {"scored_results": "   "},
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest artifacts.scored_results must be a non-empty string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_missing_raw_results_artifact_path(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content={"results": []},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest artifacts.raw_results must be a non-empty string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_padded_raw_results_artifact_path(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content={"results": []},
            manifest_overrides={
                "artifacts": {"raw_results": " gpt-5-4.smoke.raw.json "},
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest artifacts.raw_results must be an exact path",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_missing_raw_results_fingerprint(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content={"results": []},
            manifest_overrides={
                "artifacts": {"raw_results": "gpt-5-4.smoke.raw.json"},
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.raw_results must be a JSON object",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_missing_dataset_fingerprint(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": []},
            scored_content={"results": []},
            manifest_overrides={"fingerprints": {"dataset": _DELETE}},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.dataset must be a JSON object",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_unsupported_dataset_fingerprint_algorithm(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": []},
            scored_content={"results": []},
            manifest_overrides={
                "fingerprints": {
                    "dataset": {"algorithm": "md5", "value": "not-a-sha256-fingerprint"},
                },
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.dataset.algorithm must be sha256",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_padded_dataset_fingerprint_algorithm(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": []},
            scored_content={"results": []},
            manifest_overrides={
                "fingerprints": {"dataset": {"algorithm": " sha256 "}},
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.dataset.algorithm must be an exact string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_missing_dataset_fingerprint_value(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": []},
            scored_content={"results": []},
            manifest_overrides={
                "fingerprints": {"dataset": {"value": _DELETE}},
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.dataset.value must be a non-empty string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_padded_dataset_fingerprint_value(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": []},
            scored_content={"results": []},
            manifest_overrides={
                "fingerprints": {"dataset": {"value": " dataset-fingerprint "}},
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.dataset.value must be an exact string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_dataset_fingerprint_mismatching_raw_artifact(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={
                "dataset": {"path_hash": "raw-dataset-fingerprint"},
                "results": [],
            },
            scored_content={"results": []},
            manifest_overrides={
                "fingerprints": {"dataset": {"value": "manifest-dataset-fingerprint"}},
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.dataset.value does not match raw artifact dataset.path_hash",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_case_count_mismatching_raw_artifact(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"case_count": 2, "results": []},
            scored_content={"results": []},
            manifest_overrides={"case_count": 1},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest case_count does not match raw artifact case_count",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_case_count_mismatching_raw_dataset_metadata(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"dataset": {"case_count": 2}, "results": []},
            scored_content={"results": []},
            manifest_overrides={"case_count": 1},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest case_count does not match raw artifact dataset.case_count",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_case_count_mismatching_raw_dataset_question_count(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"dataset": {"question_count": 2}, "results": []},
            scored_content={"results": []},
            manifest_overrides={"case_count": 1},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest case_count does not match raw artifact dataset.question_count",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_case_count_mismatching_scored_summary(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": []},
            scored_content={"summary": {"overall": {"case_count": 2}}, "results": []},
            manifest_overrides={"case_count": 1},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest case_count does not match scored artifact summary.overall.case_count",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_case_count_mismatching_scored_summary_question_count(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": []},
            scored_content={"summary": {"overall": {"question_count": 2}}, "results": []},
            manifest_overrides={"case_count": 1},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest case_count does not match scored artifact summary.overall.question_count",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_case_count_mismatching_scored_results_length(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": [{"id": "q001"}]},
            scored_content={"results": []},
            manifest_overrides={"case_count": 1},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest case_count does not match scored artifact results length",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_scored_artifact_that_is_not_json_object(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": []},
            scored_content=[],
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest scored artifact must be a JSON object",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_scored_artifact_missing_results_list(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": []},
            scored_content={"summary": {"overall": {"case_count": 0}}},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest scored artifact is missing results list",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_scored_artifact_with_non_object_result(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": [{"id": "q001"}]},
            scored_content={"results": [None]},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest scored artifact results must contain JSON objects",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_case_count_mismatching_raw_results_length(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": []},
            scored_content={"results": [{"id": "q001"}]},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest case_count does not match raw artifact results length",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_raw_artifact_with_non_object_result(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": [None]},
            scored_content={"results": [{"id": "q001"}]},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest raw artifact results must contain JSON objects",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_mismatched_raw_and_scored_case_ids(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": [{"id": "q001"}]},
            scored_content={"results": [{"case_id": "q002"}]},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest raw and scored artifact case ids do not match",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_record_with_mismatched_id_aliases(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": [{"id": "q001", "case_id": "q002"}]},
            scored_content={"results": [{"case_id": "q001"}]},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest result id and case_id values must match",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_scored_model_outside_manifest_models(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": [{"id": "q001"}]},
            scored_content={"results": [{"case_id": "q001", "model": "claude"}]},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest scored artifact models must be listed in manifest models",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_raw_model_outside_manifest_models(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": [{"id": "q001", "model": "claude"}]},
            scored_content={"results": [{"case_id": "q001", "model": "gpt-5.4"}]},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest raw artifact models must be listed in manifest models",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_padded_result_case_ids(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": [{"id": " q001 "}]},
            scored_content={"results": [{"case_id": "q001"}]},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest result case ids must be exact strings",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_non_string_result_case_ids(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": [{"id": 1001}]},
            scored_content={"results": [{"case_id": "1001"}]},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest result case ids must be exact strings",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_raw_result_without_case_id(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": [{"answer": "raw"}]},
            scored_content={"results": [{"case_id": "q001"}]},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest raw artifact results must include case ids",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_scored_result_without_case_id(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"results": [{"id": "q001"}]},
            scored_content={"results": [{"answer": "scored"}]},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest scored artifact results must include case ids",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_raw_artifact_that_is_not_json_object(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=[],
            scored_content={"results": []},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest raw artifact must be a JSON object",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_raw_artifact_missing_results_list(self) -> None:
        bundle_path = self._make_bundle(
            raw_content={"case_count": 0},
            scored_content={"results": []},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest raw artifact is missing results list",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_unsupported_raw_results_fingerprint_algorithm(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content={"results": []},
            manifest_overrides={
                "case_count": 1,
                "artifacts": {"raw_results": "gpt-5-4.smoke.raw.json"},
                "fingerprints": {
                    "raw_results": {
                        "algorithm": "md5",
                        "value": "not-a-sha256-fingerprint",
                    },
                },
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.raw_results.algorithm must be sha256",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_padded_raw_results_fingerprint_algorithm(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content={"results": []},
            manifest_overrides={
                "case_count": 1,
                "artifacts": {"raw_results": "gpt-5-4.smoke.raw.json"},
                "fingerprints": {
                    "raw_results": {
                        "algorithm": " sha256 ",
                        "value": "not-a-sha256-fingerprint",
                    },
                },
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.raw_results.algorithm must be an exact string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_missing_raw_results_fingerprint_value(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content={"results": []},
            manifest_overrides={
                "case_count": 1,
                "artifacts": {"raw_results": "gpt-5-4.smoke.raw.json"},
                "fingerprints": {"raw_results": {"algorithm": "sha256"}},
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.raw_results.value must be a non-empty string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_padded_raw_results_fingerprint_value(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content={"results": []},
            manifest_overrides={
                "case_count": 1,
                "artifacts": {"raw_results": "gpt-5-4.smoke.raw.json"},
                "fingerprints": {
                    "raw_results": {
                        "algorithm": "sha256",
                        "value": " raw-results-fingerprint ",
                    },
                },
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.raw_results.value must be an exact string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_unsupported_scored_results_fingerprint_algorithm(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content=None,
            auto_fingerprints=False,
            manifest_overrides={
                "case_count": 1,
                "fingerprints": {
                    "scored_results": {
                        "algorithm": "md5",
                        "value": "not-a-sha256-fingerprint",
                    },
                },
                "artifacts": {"scored_results": "gpt-5-4.smoke.scored.json"},
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.scored_results.algorithm must be sha256",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_missing_scored_results_fingerprint_value(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content=None,
            auto_fingerprints=False,
            manifest_overrides={
                "case_count": 1,
                "fingerprints": {"scored_results": {"algorithm": "sha256"}},
                "artifacts": {"scored_results": "gpt-5-4.smoke.scored.json"},
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.scored_results.value must be a non-empty string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_padded_scored_results_fingerprint_value(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content=None,
            auto_fingerprints=False,
            manifest_overrides={
                "case_count": 1,
                "fingerprints": {
                    "scored_results": {
                        "algorithm": "sha256",
                        "value": f" {'0' * 64} ",
                    },
                },
                "artifacts": {"scored_results": "gpt-5-4.smoke.scored.json"},
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest fingerprints.scored_results.value must be an exact string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_padded_schema_version(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content=None,
            auto_fingerprints=False,
            manifest_overrides={"schema_version": " 2.0.0 "},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest schema_version must be an exact string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_unsupported_schema_version(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content=None,
            auto_fingerprints=False,
            manifest_overrides={"schema_version": "1.0.0"},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest schema_version must be 2.0.0",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_padded_benchmark(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content=None,
            auto_fingerprints=False,
            manifest_overrides={"benchmark": " reasoning-benchmark "},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest benchmark must be an exact string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_padded_suite_id(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content=None,
            auto_fingerprints=False,
            manifest_overrides={"suite_id": " smoke "},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest suite_id must be an exact string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_padded_id(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content=None,
            auto_fingerprints=False,
            manifest_overrides={"id": " baseline-smoke-gpt-5-4 "},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest id must be an exact string",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])

    def test_bundle_manifest_rejects_padded_model_ids(self) -> None:
        bundle_path = self._make_bundle(
            raw_content=None,
            scored_content=None,
            auto_fingerprints=False,
            manifest_overrides={"models": [" gpt-5.4 "]},
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bundle manifest models must contain exact strings",
        ):
            report_summary.build_report_summary(bundle_paths=[bundle_path])
