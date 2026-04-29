from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path
from unittest.mock import patch
import unittest

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
sys.path.append(str(REPO_ROOT / "scripts"))

import run_baselines


class BaselineSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.questions = [
            {"id": f"Q{i:02d}", "prompt": f"Prompt {i}"}
            for i in range(1, 8)
        ]

    def test_smoke_mode_selects_first_five_rows(self) -> None:
        selected = run_baselines.select_questions(self.questions, "smoke")
        self.assertEqual(len(selected), 5)
        self.assertEqual([item["id"] for item in selected], ["Q01", "Q02", "Q03", "Q04", "Q05"])

    def test_full_mode_returns_default_questions(self) -> None:
        selected = run_baselines.select_questions(self.questions, "full")
        self.assertEqual(len(selected), 7)

    def test_full_mode_excludes_optional_instruction_ambiguity_questions(self) -> None:
        questions = self.questions + [
            {"id": "IA-01", "category": "IA", "prompt": "Ambiguous prompt"},
            {
                "id": "IA-02",
                "task_family_id": "instruction-ambiguity",
                "prompt": "Another ambiguous prompt",
            },
        ]

        selected = run_baselines.select_questions(questions, "full")

        self.assertEqual([item["id"] for item in selected], [f"Q{i:02d}" for i in range(1, 8)])

    def test_explicit_case_ids_can_opt_into_instruction_ambiguity_questions(self) -> None:
        questions = self.questions + [
            {"id": "IA-01", "category": "IA", "prompt": "Ambiguous prompt"},
        ]

        selected = run_baselines.select_questions(
            questions,
            "full",
            case_ids=("Q02", "IA-01"),
        )

        self.assertEqual([item["id"] for item in selected], ["Q02", "IA-01"])

    def test_unsupported_mode_raises(self) -> None:
        with self.assertRaises(ValueError):
            run_baselines.select_questions(self.questions, "invalid")

    def test_model_slug_is_stable(self) -> None:
        self.assertEqual(run_baselines.normalize_model_id("gpt-5.4"), "gpt-5-4")
        self.assertEqual(run_baselines.normalize_model_id("qwen3.5-9b"), "qwen3-5-9b")

    def test_run_paths_are_stable(self) -> None:
        run_dir = Path("/tmp/baselines")
        raw, scored = run_baselines.run_paths(run_dir, "sonnet-4.6", "smoke")
        self.assertEqual(str(raw), "/tmp/baselines/sonnet-4-6.smoke.raw.json")
        self.assertEqual(str(scored), "/tmp/baselines/sonnet-4-6.smoke.scored.json")

    def test_summary_path_is_stable(self) -> None:
        run_dir = Path("/tmp/baselines")
        summary = run_baselines.summary_path(run_dir, "sonnet-4.6", "smoke")
        self.assertEqual(str(summary), "/tmp/baselines/sonnet-4-6.smoke.summary.json")

    def test_artifact_label_rejects_path_segments(self) -> None:
        with self.assertRaisesRegex(ValueError, "path separators or traversal"):
            run_baselines.validate_artifact_label("../outside", "RunConfig execution.mode")

    def test_adapter_command_omits_arguments(self) -> None:
        command = run_baselines.format_adapter_command(["provider", "--api-key", "secret"])
        self.assertEqual(command, "provider '[arguments omitted]'")
        self.assertNotIn("secret", command)

    def test_matrix_run_paths_are_scoped_under_suite_directory(self) -> None:
        run_dir = Path("/tmp/baselines")
        raw, scored = run_baselines.matrix_run_paths(
            run_dir, "starter-pragmatics", "sonnet-4.6", "full"
        )
        self.assertEqual(
            str(raw),
            "/tmp/baselines/starter-pragmatics/sonnet-4-6.full.raw.json",
        )
        self.assertEqual(
            str(scored),
            "/tmp/baselines/starter-pragmatics/sonnet-4-6.full.scored.json",
        )

    def test_matrix_summary_path_is_scoped_under_suite_directory(self) -> None:
        run_dir = Path("/tmp/baselines")
        summary = run_baselines.matrix_summary_path(
            run_dir, "starter-pragmatics", "sonnet-4.6", "full"
        )
        self.assertEqual(
            str(summary),
            "/tmp/baselines/starter-pragmatics/sonnet-4-6.full.summary.json",
        )

    def test_matrix_manifest_path_is_scoped_under_suite_directory(self) -> None:
        run_dir = Path("/tmp/baselines")
        manifest = run_baselines.matrix_manifest_path(
            run_dir, "starter-pragmatics", "sonnet-4.6", "full"
        )
        self.assertEqual(
            str(manifest),
            "/tmp/baselines/starter-pragmatics/sonnet-4-6.full.manifest.json",
        )

    def test_matrix_paths_reject_suite_id_with_traversal(self) -> None:
        run_dir = Path("/tmp/baselines")
        with self.assertRaisesRegex(ValueError, "path separators or traversal"):
            run_baselines.matrix_run_paths(run_dir, "../escape", "sonnet-4.6", "full")
        with self.assertRaisesRegex(ValueError, "path separators or traversal"):
            run_baselines.matrix_summary_path(run_dir, "..", "sonnet-4.6", "full")
        with self.assertRaisesRegex(ValueError, "path separators or traversal"):
            run_baselines.matrix_manifest_path(run_dir, "a/b", "sonnet-4.6", "full")

    def test_matrix_index_path_lives_at_run_dir_root(self) -> None:
        run_dir = Path("/tmp/baselines")
        index = run_baselines.matrix_index_path(run_dir)
        self.assertEqual(str(index), "/tmp/baselines/matrix.index.json")


class BaselineRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(__file__).resolve().parent / "tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        for item in self.tmp_dir.glob("*.json"):
            item.unlink()

    def _dataset(self) -> Path:
        dataset_path = self.tmp_dir / "questions.json"
        rows = [
            {"id": "GG-01", "prompt": "Prompt one"},
            {"id": "GG-02", "prompt": "Prompt two"},
            {"id": "GG-03", "prompt": "Prompt three"},
            {"id": "GG-04", "prompt": "Prompt four"},
            {"id": "GG-05", "prompt": "Prompt five"},
            {"id": "GG-06", "prompt": "Prompt six"},
        ]
        dataset_path.write_text(json.dumps(rows), encoding="utf-8")
        return dataset_path

    def test_smoke_run_writes_deterministic_raw_artifact(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "runs"

        with patch.object(run_baselines, "score_payload") as score_mock:
            def _score_input(input_path, scored_path, _dataset_path, _source_bundle):
                scored_path.write_text(
                    json.dumps(
                        {
                            "summary": {
                                "schema_version": "2.0.0",
                                "benchmark": "reasoning-benchmark",
                                "suite_id": "smoke",
                                "overall": {"case_count": 5},
                            },
                            "results": [],
                        }
                    ),
                    encoding="utf-8",
                )

            score_mock.side_effect = _score_input
            args = argparse.Namespace(
                mode="smoke",
                dataset=str(dataset_path),
                run_dir=str(run_dir),
                models=["gpt-5.4"],
                provider_command=None,
                prompt_timeout=1.0,
                skip_scoring=False,
            )
            run_baselines.cmd_run(args)

        raw_path = run_dir / "gpt-5-4.smoke.raw.json"
        scored_path = run_dir / "gpt-5-4.smoke.scored.json"
        summary_path = run_dir / "gpt-5-4.smoke.summary.json"
        self.assertTrue(raw_path.is_file())
        self.assertTrue(scored_path.is_file())
        self.assertTrue(summary_path.is_file())
        score_mock.assert_called_once()

        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["run_mode"], "smoke")
        self.assertEqual(payload["model"], "gpt-5.4")
        self.assertEqual(len(payload["results"]), 5)
        self.assertEqual([item["id"] for item in payload["results"]], ["GG-01", "GG-02", "GG-03", "GG-04", "GG-05"])
        self.assertEqual([item["case_id"] for item in payload["results"]], ["GG-01", "GG-02", "GG-03", "GG-04", "GG-05"])
        self.assertEqual(summary["schema_version"], "2.0.0")
        self.assertEqual(summary["overall"]["case_count"], 5)

    def test_raw_artifact_includes_v2_suite_and_case_count_aliases(self) -> None:
        dataset_path = self._dataset()
        selected = run_baselines.select_questions(run_baselines.load_questions(dataset_path), "smoke")

        payload = run_baselines.build_payload(
            model="gpt-5.4",
            mode="smoke",
            questions=selected,
            dataset_path=dataset_path,
        )

        self.assertEqual(payload["schema_version"], "2.0.0")
        self.assertEqual(payload["runner_version"], "1.0.0")
        self.assertEqual(payload["suite_id"], "smoke")
        self.assertIn("case_count", payload)
        self.assertIn("question_count", payload)
        self.assertEqual(payload["case_count"], 5)
        self.assertEqual(payload["question_count"], 5)
        self.assertEqual(payload["dataset"]["case_count"], 5)
        self.assertEqual(payload["dataset"]["question_count"], 5)

    def test_full_payload_defaults_suite_id_to_default(self) -> None:
        dataset_path = self._dataset()
        selected = run_baselines.select_questions(run_baselines.load_questions(dataset_path), "full")

        payload = run_baselines.build_payload(
            model="gpt-5.4",
            mode="full",
            questions=selected,
            dataset_path=dataset_path,
        )

        self.assertEqual(payload["suite_id"], "default")

    def test_full_manifest_defaults_suite_id_to_default(self) -> None:
        dataset_path = self._dataset()
        raw_path = self.tmp_dir / "bundle.raw.json"
        scored_path = self.tmp_dir / "bundle.scored.json"
        summary_path = self.tmp_dir / "bundle.summary.json"
        raw_path.write_text("{}", encoding="utf-8")
        scored_path.write_text("{}", encoding="utf-8")
        summary_path.write_text("{}", encoding="utf-8")

        manifest = run_baselines.build_run_artifact_bundle(
            model="gpt-5.4",
            mode="full",
            raw_path=raw_path,
            scored_path=scored_path,
            report_summary_path=summary_path,
            dataset_path=dataset_path,
            case_count=6,
            created_at="2026-01-01T00:00:00+00:00",
        )

        self.assertEqual(manifest["suite_id"], "default")
        self.assertEqual(manifest["id"], "baseline-default-gpt-5-4")

    def test_provider_command_answers_are_written_into_results(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "runs"

        provider = self.tmp_dir / "provider.py"
        provider.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json,sys",
                    "model, prompt = sys.argv[1], sys.argv[2]",
                    "print(json.dumps({'answer': 'ans_' + model, 'reasoning': 'r_' + prompt[:3]}))",
                ]
            ),
            encoding="utf-8",
        )
        provider.chmod(0o755)

        args = argparse.Namespace(
            mode="full",
            dataset=str(dataset_path),
            run_dir=str(run_dir),
            models=["sonnet-4.6"],
            provider_command=[str(provider)],
            prompt_timeout=2.0,
            skip_scoring=True,
        )
        run_baselines.cmd_run(args)

        raw_path = run_dir / "sonnet-4-6.default.raw.json"
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["suite_id"], "default")
        self.assertEqual(len(payload["results"]), 6)
        for row in payload["results"]:
            self.assertEqual(row["answer"], "ans_sonnet-4.6")
            self.assertEqual(row["raw_response"]["format"], "json")
            self.assertIn('"answer": "ans_sonnet-4.6"', row["raw_response"]["text"])
            self.assertEqual(row["adapter"]["name"], "provider.py")
            self.assertEqual(row["adapter"]["command"], str(provider))
            self.assertEqual(row["adapter"]["exit_code"], 0)
            self.assertEqual(row["adapter"]["stderr"], "")
            self.assertTrue(row["started_at"])
            self.assertTrue(row["completed_at"])

    def test_provider_command_arguments_are_not_written_into_results(self) -> None:
        row = {"id": "GG-01", "prompt": "Prompt one"}
        provider = run_baselines.ProviderResult(
            answer="answer",
            reasoning="reasoning",
            adapter_name="provider-command",
            adapter_command=["provider", "--api-key", "secret-token"],
            adapter_exit_code=0,
        )

        record = run_baselines.build_result_record(
            row=row,
            model="gpt-5.4",
            answer=provider.answer,
            reasoning=provider.reasoning,
            provider=provider,
        )

        self.assertEqual(record["adapter"]["command"], "provider '[arguments omitted]'")
        self.assertNotIn("secret-token", json.dumps(record))

    def test_config_file_drives_smoke_run_settings(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "config-runs"

        provider = self.tmp_dir / "provider.py"
        provider.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json,sys",
                    "model, prompt = sys.argv[1], sys.argv[2]",
                    "print(json.dumps({'answer': 'cfg_' + model, 'reasoning': prompt[:5]}))",
                ]
            ),
            encoding="utf-8",
        )
        provider.chmod(0o755)

        config_path = self.tmp_dir / "run-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-config-smoke",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": [
                        {
                            "id": "gpt-5.4",
                            "adapter": "provider-command",
                            "adapter_command": [str(provider)],
                        }
                    ],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "timeout_seconds": 2.0,
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )
        run_baselines.cmd_run(args)

        raw_path = run_dir / "gpt-5-4.smoke.raw.json"
        self.assertTrue(raw_path.is_file())
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["run_config"]["id"], "unit-config-smoke")
        self.assertEqual(payload["run_mode"], "smoke")
        self.assertEqual(payload["model"], "gpt-5.4")
        self.assertEqual(len(payload["results"]), 5)
        for row in payload["results"]:
            self.assertEqual(row["answer"], "cfg_gpt-5.4")

    def test_config_commands_are_sanitized_in_raw_artifact(self) -> None:
        config_payload = {
            "schema_version": "2.0.0",
            "id": "unit-config-secrets",
            "benchmark": "reasoning-benchmark",
            "suite_id": "smoke",
            "dataset": {"path": "data/questions.json"},
            "models": [
                {
                    "id": "gpt-5.4",
                    "adapter_command": ["provider", "--api-key", "model-secret"],
                }
            ],
            "prompt_contract": run_baselines.build_prompt_contract(),
            "execution": {
                "mode": "smoke",
                "provider_command": "provider --authorization execution-secret",
            },
            "output": {"bundle_dir": "runs/baseline"},
        }

        sanitized = run_baselines.sanitize_run_config_for_artifact(config_payload)
        serialized = json.dumps(sanitized)

        self.assertEqual(
            sanitized["models"][0]["adapter_command"],
            "provider '[arguments omitted]'",
        )
        self.assertEqual(
            sanitized["execution"]["provider_command"],
            "provider '[arguments omitted]'",
        )
        self.assertNotIn("model-secret", serialized)
        self.assertNotIn("execution-secret", serialized)
        self.assertEqual(config_payload["models"][0]["adapter_command"][2], "model-secret")

    def test_config_file_preserves_prompt_contract_metadata(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "prompt-contract-runs"
        prompt_contract = {
            "version": "2.0.0",
            "response_format": "json_object",
            "required_fields": ["answer", "reasoning", "confidence"],
            "instruction": "Return answer, reasoning, and confidence.",
        }

        config_path = self.tmp_dir / "prompt-contract-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-prompt-contract",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": prompt_contract,
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )
        run_baselines.cmd_run(args)

        payload = json.loads((run_dir / "gpt-5-4.smoke.raw.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["prompt_contract"], prompt_contract)

    def test_config_file_rejects_dataset_fingerprint_mismatch(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "fingerprint-runs"

        config_path = self.tmp_dir / "fingerprint-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-fingerprint-mismatch",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {
                        "path": str(dataset_path),
                        "fingerprint": {
                            "algorithm": "sha256",
                            "value": "not-the-current-dataset-hash",
                        },
                    },
                    "models": ["gpt-5.4"],
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig dataset.fingerprint does not match dataset"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_padded_dataset_fingerprint_value(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-fingerprint-runs"
        expected_fingerprint = run_baselines.dataset_fingerprint(dataset_path)

        config_path = self.tmp_dir / "padded-fingerprint-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-fingerprint",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {
                        "path": str(dataset_path),
                        "fingerprint": {
                            "algorithm": "sha256",
                            "value": f" {expected_fingerprint}",
                        },
                    },
                    "models": ["gpt-5.4"],
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig dataset.fingerprint.value must be an exact string"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_padded_dataset_fingerprint_algorithm(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-fingerprint-algorithm-runs"
        expected_fingerprint = run_baselines.dataset_fingerprint(dataset_path)

        config_path = self.tmp_dir / "padded-fingerprint-algorithm-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-fingerprint-algorithm",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {
                        "path": str(dataset_path),
                        "fingerprint": {
                            "algorithm": " sha256",
                            "value": expected_fingerprint,
                        },
                    },
                    "models": ["gpt-5.4"],
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(
            ValueError,
            "RunConfig dataset.fingerprint.algorithm must be an exact string",
        ):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_wrong_benchmark(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "wrong-benchmark-runs"

        config_path = self.tmp_dir / "wrong-benchmark-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-wrong-benchmark",
                    "benchmark": "other-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig benchmark must be reasoning-benchmark"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_padded_benchmark(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-benchmark-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "padded-benchmark-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-benchmark",
                    "benchmark": " reasoning-benchmark ",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig benchmark must be an exact string"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_missing_schema_version(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "missing-schema-version-runs"

        config_path = self.tmp_dir / "missing-schema-version-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "id": "unit-missing-schema-version",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig schema_version must be 2.0.0"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_padded_schema_version(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-schema-version-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "padded-schema-version-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": " 2.0.0 ",
                    "id": "unit-padded-schema-version",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig schema_version must be an exact string"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_missing_id(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "missing-id-runs"

        config_path = self.tmp_dir / "missing-id-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig id must be a non-empty string"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_padded_id(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-id-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "padded-id-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": " unit-padded-id ",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig id must be an exact string"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_missing_suite_id(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "missing-suite-id-runs"

        config_path = self.tmp_dir / "missing-suite-id-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-missing-suite-id",
                    "benchmark": "reasoning-benchmark",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig suite_id must be a non-empty string"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_padded_suite_id(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-suite-id-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "padded-suite-id-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-suite-id",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": " smoke ",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig suite_id must be an exact string"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_missing_execution(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "missing-execution-runs"

        config_path = self.tmp_dir / "missing-execution-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-missing-execution",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig execution is required"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_missing_prompt_contract(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "missing-prompt-contract-runs"

        config_path = self.tmp_dir / "missing-prompt-contract-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-missing-prompt-contract",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig prompt_contract is required"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_prompt_contract_without_required_fields(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "missing-prompt-required-fields-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "missing-prompt-required-fields-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-missing-prompt-required-fields",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": {
                        "version": "2.0.0",
                        "response_format": "json_object",
                    },
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig prompt_contract.required_fields must be a non-empty list"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_prompt_contract_without_response_format(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "missing-prompt-response-format-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "missing-prompt-response-format-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-missing-prompt-response-format",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": {
                        "version": "2.0.0",
                        "required_fields": ["answer", "reasoning"],
                    },
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(
            ValueError,
            "RunConfig prompt_contract.response_format must be a non-empty string",
        ):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_unsupported_prompt_contract_response_format(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "unsupported-prompt-response-format-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "unsupported-prompt-response-format-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-unsupported-prompt-response-format",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": {
                        "version": "2.0.0",
                        "response_format": "text",
                        "required_fields": ["answer", "reasoning"],
                    },
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(
            ValueError,
            "RunConfig prompt_contract.response_format must be json_object",
        ):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_padded_prompt_contract_response_format(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-prompt-response-format-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "padded-prompt-response-format-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-prompt-response-format",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": {
                        "version": "1.0.0",
                        "response_format": " json_object ",
                        "required_fields": ["answer", "reasoning"],
                    },
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(
            ValueError,
            "RunConfig prompt_contract.response_format must be an exact string",
        ):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_prompt_contract_without_version(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "missing-prompt-version-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "missing-prompt-version-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-missing-prompt-version",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": {
                        "response_format": "json_object",
                        "required_fields": ["answer", "reasoning"],
                    },
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(
            ValueError,
            "RunConfig prompt_contract.version must be a non-empty string",
        ):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_padded_prompt_contract_version(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-prompt-version-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "padded-prompt-version-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-prompt-version",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": {
                        "version": " 1.0.0 ",
                        "response_format": "json_object",
                        "required_fields": ["answer", "reasoning"],
                    },
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(
            ValueError,
            "RunConfig prompt_contract.version must be an exact string",
        ):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_blank_prompt_contract_required_field(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "blank-prompt-required-field-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "blank-prompt-required-field-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-blank-prompt-required-field",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": {
                        "version": "2.0.0",
                        "response_format": "json_object",
                        "required_fields": ["answer", "   "],
                    },
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(
            ValueError,
            "RunConfig prompt_contract.required_fields entries must be non-empty strings",
        ):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_padded_prompt_contract_required_field(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-prompt-required-field-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "padded-prompt-required-field-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-prompt-required-field",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": {
                        "version": "2.0.0",
                        "response_format": "json_object",
                        "required_fields": [" answer ", "reasoning"],
                    },
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(
            ValueError,
            "RunConfig prompt_contract.required_fields entries must be exact field names",
        ):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_prompt_contract_without_answer_field(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "missing-answer-field-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "missing-answer-field-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-missing-answer-field",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": {
                        "version": "2.0.0",
                        "response_format": "json_object",
                        "required_fields": ["reasoning"],
                    },
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(
            ValueError,
            "RunConfig prompt_contract.required_fields must include answer",
        ):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_prompt_contract_without_reasoning_field(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "missing-reasoning-field-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "missing-reasoning-field-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-missing-reasoning-field",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": {
                        "version": "2.0.0",
                        "response_format": "json_object",
                        "required_fields": ["answer"],
                    },
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(
            ValueError,
            "RunConfig prompt_contract.required_fields must include reasoning",
        ):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_blank_output_bundle_dir(self) -> None:
        dataset_path = self._dataset()

        config_path = self.tmp_dir / "blank-output-bundle-dir-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-blank-output-bundle-dir",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": ""},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig output.bundle_dir must be a non-empty string"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_padded_output_bundle_dir(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-output-bundle-dir-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "padded-output-bundle-dir-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-output-bundle-dir",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": f" {run_dir} "},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig output.bundle_dir must be an exact string"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_blank_dataset_path(self) -> None:
        run_dir = self.tmp_dir / "blank-dataset-path-runs"

        config_path = self.tmp_dir / "blank-dataset-path-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-blank-dataset-path",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": ""},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig dataset.path must be a non-empty string"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_padded_dataset_path(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-dataset-path-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "padded-dataset-path-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-dataset-path",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": f" {dataset_path} "},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig dataset.path must be an exact string"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_blank_model_id(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "blank-model-id-runs"

        config_path = self.tmp_dir / "blank-model-id-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-blank-model-id",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": [" "],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig model ids must be non-empty strings"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_blank_object_model_id(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "blank-object-model-id-runs"

        config_path = self.tmp_dir / "blank-object-model-id-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-blank-object-model-id",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": [{"id": "\t"}],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig model ids must be non-empty strings"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_padded_model_id(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-model-id-runs"

        config_path = self.tmp_dir / "padded-model-id-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-model-id",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": [" gpt-5.4 "],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig model ids must be exact strings"):
            run_baselines.cmd_run(args)
        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_non_positive_timeout(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "non-positive-timeout-runs"

        config_path = self.tmp_dir / "non-positive-timeout-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-non-positive-timeout",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "timeout_seconds": 0,
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig execution.timeout_seconds must be positive"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_boolean_timeout(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "boolean-timeout-runs"

        config_path = self.tmp_dir / "boolean-timeout-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-boolean-timeout",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "timeout_seconds": True,
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig execution.timeout_seconds must be numeric"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_string_timeout(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "string-timeout-runs"

        config_path = self.tmp_dir / "string-timeout-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-string-timeout",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "timeout_seconds": "5",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig execution.timeout_seconds must be numeric"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_non_finite_timeout(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "non-finite-timeout-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "non-finite-timeout-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-non-finite-timeout",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "timeout_seconds": math.nan,
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig execution.timeout_seconds must be finite"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_non_boolean_skip_scoring(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "non-boolean-skip-scoring-runs"

        config_path = self.tmp_dir / "non-boolean-skip-scoring-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-non-boolean-skip-scoring",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": "false",
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig execution.skip_scoring must be a boolean"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_fractional_max_cases(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "fractional-max-cases-runs"

        config_path = self.tmp_dir / "fractional-max-cases-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-fractional-max-cases",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "max_cases": 2.5,
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig execution.max_cases must be a positive integer"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_string_max_cases(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "string-max-cases-runs"

        config_path = self.tmp_dir / "string-max-cases-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-string-max-cases",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "max_cases": "2",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig execution.max_cases must be a positive integer"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_blank_seed(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "blank-seed-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "blank-seed-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-blank-seed",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "seed": "   ",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig execution.seed must be an integer, string, or null"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_padded_seed(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-seed-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "padded-seed-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-seed",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "seed": " seed-123 ",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig execution.seed must be an exact string"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_blank_execution_mode(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "blank-execution-mode-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "blank-execution-mode-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-blank-execution-mode",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig execution.mode must be a non-empty string"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_padded_execution_mode(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-execution-mode-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "padded-execution-mode-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-execution-mode",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": " smoke ",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig execution.mode must be an exact string"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_path_execution_mode(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "path-execution-mode-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "path-execution-mode-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-path-execution-mode",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "../outside",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig execution.mode cannot contain path separators"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_blank_adapter_command_entry(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "blank-adapter-command-entry-runs"

        config_path = self.tmp_dir / "blank-adapter-command-entry-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-blank-adapter-command-entry",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": [
                        {
                            "id": "gpt-5.4",
                            "adapter": "provider-command",
                            "adapter_command": [""],
                        }
                    ],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "adapter_command list entries must be non-empty strings"):
            run_baselines.cmd_run(args)

    def test_config_file_rejects_padded_adapter_command_entry(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-adapter-command-entry-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "padded-adapter-command-entry-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-adapter-command-entry",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": [
                        {
                            "id": "gpt-5.4",
                            "adapter": "provider-command",
                            "adapter_command": [" python3"],
                        }
                    ],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "adapter_command list entries must be exact strings"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_padded_adapter_command_string(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-adapter-command-string-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "padded-adapter-command-string-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-adapter-command-string",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": [
                        {
                            "id": "gpt-5.4",
                            "adapter": "provider-command",
                            "adapter_command": " python3",
                        }
                    ],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "adapter_command string must be exact"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_padded_execution_provider_command_string(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-provider-command-string-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "padded-provider-command-string-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-provider-command-string",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "provider_command": " python3",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig execution.provider_command string must be exact"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_null_model_adapter_command(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "null-adapter-command-runs"

        config_path = self.tmp_dir / "null-adapter-command-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-null-adapter-command",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": [
                        {
                            "id": "gpt-5.4",
                            "adapter": "provider-command",
                            "adapter_command": None,
                        }
                    ],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "adapter_command must be a string or list"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_padded_model_adapter(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-model-adapter-runs"
        shutil.rmtree(run_dir, ignore_errors=True)

        config_path = self.tmp_dir / "padded-model-adapter-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-model-adapter",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": [
                        {
                            "id": "gpt-5.4",
                            "adapter": " cli",
                        }
                    ],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig model adapter must be an exact string"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_supports_per_model_adapter_commands(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "per-model-runs"

        gpt_provider = self.tmp_dir / "provider-gpt.py"
        gpt_provider.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json,sys",
                    "model, prompt = sys.argv[1], sys.argv[2]",
                    "print(json.dumps({'answer': 'gpt_' + model, 'reasoning': prompt[:4]}))",
                ]
            ),
            encoding="utf-8",
        )
        gpt_provider.chmod(0o755)

        sonnet_provider = self.tmp_dir / "provider-sonnet.py"
        sonnet_provider.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json,sys",
                    "model, prompt = sys.argv[1], sys.argv[2]",
                    "print(json.dumps({'answer': 'sonnet_' + model, 'reasoning': prompt[:4]}))",
                ]
            ),
            encoding="utf-8",
        )
        sonnet_provider.chmod(0o755)

        config_path = self.tmp_dir / "per-model-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-per-model-adapters",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": [
                        {
                            "id": "gpt-5.4",
                            "adapter": "provider-command",
                            "adapter_command": [str(gpt_provider)],
                        },
                        {
                            "id": "sonnet-4.6",
                            "adapter": "provider-command",
                            "adapter_command": [str(sonnet_provider)],
                        },
                    ],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "timeout_seconds": 2.0,
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["qwen3.5-9b"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )
        run_baselines.cmd_run(args)

        gpt_payload = json.loads((run_dir / "gpt-5-4.smoke.raw.json").read_text(encoding="utf-8"))
        sonnet_payload = json.loads((run_dir / "sonnet-4-6.smoke.raw.json").read_text(encoding="utf-8"))
        self.assertEqual(gpt_payload["results"][0]["answer"], "gpt_gpt-5.4")
        self.assertEqual(sonnet_payload["results"][0]["answer"], "sonnet_sonnet-4.6")

    def test_config_file_uses_builtin_adapter_command_from_model_adapter(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "builtin-adapter-runs"

        config_path = self.tmp_dir / "builtin-adapter-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-builtin-adapter",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": [
                        {
                            "id": "gpt-5.4",
                            "adapter": "cli",
                        }
                    ],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        with patch.object(run_baselines, "run_provider", return_value=run_baselines.ProviderResult("via-cli", "adapter")) as provider_mock:
            args = argparse.Namespace(
                config=str(config_path),
                mode="full",
                dataset=str(self.tmp_dir / "ignored.json"),
                run_dir=str(self.tmp_dir / "ignored-runs"),
                models=["sonnet-4.6"],
                provider_command=None,
                prompt_timeout=1.0,
                skip_scoring=False,
            )
            run_baselines.cmd_run(args)

        expected_command = [sys.executable, str(REPO_ROOT / "scripts" / "cli_adapter.py")]
        self.assertEqual(provider_mock.call_args.args[0], expected_command)

        payload = json.loads((run_dir / "gpt-5-4.smoke.raw.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["results"][0]["answer"], "via-cli")

    def test_config_file_uses_builtin_api_adapter_command_from_model_adapter(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "builtin-api-adapter-runs"

        config_path = self.tmp_dir / "builtin-api-adapter-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-builtin-api-adapter",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "smoke",
                    "dataset": {"path": str(dataset_path)},
                    "models": [
                        {
                            "id": "qwen3.5-9b",
                            "adapter": "api",
                        }
                    ],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "smoke",
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        with patch.object(run_baselines, "run_provider", return_value=run_baselines.ProviderResult("via-api", "adapter")) as provider_mock:
            args = argparse.Namespace(
                config=str(config_path),
                mode="full",
                dataset=str(self.tmp_dir / "ignored.json"),
                run_dir=str(self.tmp_dir / "ignored-runs"),
                models=["sonnet-4.6"],
                provider_command=None,
                prompt_timeout=1.0,
                skip_scoring=False,
            )
            run_baselines.cmd_run(args)

        expected_command = [sys.executable, str(REPO_ROOT / "scripts" / "api_adapter.py")]
        self.assertEqual(provider_mock.call_args.args[0], expected_command)

        payload = json.loads((run_dir / "qwen3-5-9b.smoke.raw.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["results"][0]["answer"], "via-api")

    def test_config_file_max_cases_limits_selected_questions(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "budgeted-runs"

        config_path = self.tmp_dir / "budgeted-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-budgeted-run",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "full",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "full",
                        "max_cases": 3,
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="smoke",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )
        run_baselines.cmd_run(args)

        payload = json.loads((run_dir / "gpt-5-4.default.raw.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["suite_id"], "default")
        self.assertEqual([item["id"] for item in payload["results"]], ["GG-01", "GG-02", "GG-03"])
        self.assertEqual(payload["execution"]["max_cases"], 3)
        self.assertFalse((run_dir / "gpt-5-4.default.manifest.json").exists())

    def test_config_file_default_suite_id_round_trips_without_execution_mode(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "default-suite-runs"

        config_path = self.tmp_dir / "default-suite-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-default-suite",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "default",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="smoke",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )
        run_baselines.cmd_run(args)

        payload = json.loads((run_dir / "gpt-5-4.default.raw.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["suite_id"], "default")
        self.assertEqual(payload["run_mode"], "full")

    def test_config_file_seed_makes_budgeted_selection_reproducible(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "seeded-runs"

        config_path = self.tmp_dir / "seeded-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-seeded-run",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "full",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "full",
                        "seed": 7,
                        "max_cases": 3,
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="smoke",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )
        run_baselines.cmd_run(args)

        payload = json.loads((run_dir / "gpt-5-4.default.raw.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["suite_id"], "default")
        self.assertEqual([item["id"] for item in payload["results"]], ["GG-05", "GG-01", "GG-06"])
        self.assertEqual(payload["execution"]["seed"], 7)

    def test_config_file_embedded_suite_case_ids_selects_ordered_cases(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "suite-runs"

        config_path = self.tmp_dir / "suite-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-explicit-suite",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "custom",
                    "suite": {
                        "id": "custom",
                        "name": "Custom",
                        "case_ids": ["GG-04", "GG-02", "GG-06"],
                    },
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="smoke",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )
        run_baselines.cmd_run(args)

        payload = json.loads((run_dir / "gpt-5-4.custom.raw.json").read_text(encoding="utf-8"))
        self.assertEqual([item["id"] for item in payload["results"]], ["GG-04", "GG-02", "GG-06"])
        self.assertEqual(payload["execution"]["mode"], "custom")
        self.assertFalse((run_dir / "gpt-5-4.custom.manifest.json").exists())

    def test_config_file_seed_does_not_shuffle_explicit_suite_case_ids(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "seeded-suite-runs"

        config_path = self.tmp_dir / "seeded-suite-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-seeded-explicit-suite",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "custom",
                    "suite": {
                        "id": "custom",
                        "name": "Custom",
                        "case_ids": ["GG-04", "GG-02", "GG-06"],
                    },
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "seed": 7,
                        "max_cases": 2,
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="smoke",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )
        run_baselines.cmd_run(args)

        payload = json.loads((run_dir / "gpt-5-4.custom.raw.json").read_text(encoding="utf-8"))
        self.assertEqual([item["id"] for item in payload["results"]], ["GG-04", "GG-02"])
        self.assertEqual(payload["execution"]["seed"], 7)

    def test_skip_scoring_does_not_write_bundle_manifest(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "skip-scoring-manifest-runs"

        args = argparse.Namespace(
            config=None,
            mode="smoke",
            dataset=str(dataset_path),
            run_dir=str(run_dir),
            models=["gpt-5.4"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=True,
        )
        run_baselines.cmd_run(args)

        self.assertTrue((run_dir / "gpt-5-4.smoke.raw.json").is_file())
        self.assertFalse((run_dir / "gpt-5-4.smoke.manifest.json").exists())

    def test_config_file_rejects_padded_suite_case_ids(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "padded-suite-case-runs"

        config_path = self.tmp_dir / "padded-suite-case-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-padded-suite-case",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "custom",
                    "suite": {
                        "id": "custom",
                        "name": "Custom",
                        "case_ids": [" GG-01 ", "GG-02"],
                    },
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="smoke",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig suite.case_ids entries must be exact case ids"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_config_file_rejects_duplicate_suite_case_ids(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "duplicate-suite-case-runs"

        config_path = self.tmp_dir / "duplicate-suite-case-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-duplicate-suite-case",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "custom",
                    "suite": {
                        "id": "custom",
                        "name": "Custom",
                        "case_ids": ["GG-01", "GG-02", "GG-01"],
                    },
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "skip_scoring": True,
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="smoke",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )

        with self.assertRaisesRegex(ValueError, "RunConfig suite.case_ids entries must be unique"):
            run_baselines.cmd_run(args)

        self.assertFalse(run_dir.exists())

    def test_run_writes_v2_manifest_next_to_artifacts(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "manifest-runs"

        with patch.object(run_baselines, "score_payload") as score_mock:
            def _score_input(input_path, scored_path, _dataset_path, source_bundle):
                scored_path.write_text(
                    json.dumps(
                        {
                            "summary": {
                                "schema_version": "2.0.0",
                                "benchmark": "reasoning-benchmark",
                                "suite_id": "smoke",
                                "overall": {"case_count": 5},
                            },
                            "results": [],
                        }
                    ),
                    encoding="utf-8",
                )
                self.assertEqual(source_bundle, run_dir / "gpt-5-4.smoke.manifest.json")

            score_mock.side_effect = _score_input
            args = argparse.Namespace(
                config=None,
                mode="smoke",
                dataset=str(dataset_path),
                run_dir=str(run_dir),
                models=["gpt-5.4"],
                provider_command=None,
                prompt_timeout=1.0,
                skip_scoring=False,
            )
            run_baselines.cmd_run(args)

        manifest_path = run_dir / "gpt-5-4.smoke.manifest.json"
        self.assertTrue(manifest_path.is_file())

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], "2.0.0")
        self.assertEqual(manifest["benchmark"], "reasoning-benchmark")
        self.assertEqual(manifest["suite_id"], "smoke")
        self.assertEqual(manifest["models"], ["gpt-5.4"])
        self.assertEqual(manifest["case_count"], 5)
        self.assertEqual(manifest["artifacts"]["raw_results"], "gpt-5-4.smoke.raw.json")
        self.assertEqual(manifest["artifacts"]["scored_results"], "gpt-5-4.smoke.scored.json")
        self.assertEqual(manifest["artifacts"]["report_summary"], "gpt-5-4.smoke.summary.json")
        self.assertEqual(manifest["fingerprints"]["dataset"]["algorithm"], "sha256")
        self.assertEqual(manifest["fingerprints"]["raw_results"]["algorithm"], "sha256")
        self.assertEqual(manifest["fingerprints"]["scored_results"]["algorithm"], "sha256")
        self.assertEqual(manifest["fingerprints"]["report_summary"]["algorithm"], "sha256")
        self.assertIn("created_at", manifest)
        self.assertIn("completed_at", manifest)
        score_mock.assert_called_once()


class MatrixSuiteParsingTests(unittest.TestCase):
    def _payload_with_matrix(self, suites: list) -> dict:
        return {
            "schema_version": "2.0.0",
            "id": "unit-matrix",
            "benchmark": "reasoning-benchmark",
            "matrix": {"suites": suites},
        }

    def test_returns_none_when_matrix_absent(self) -> None:
        self.assertIsNone(run_baselines.config_matrix_suites({"id": "no-matrix"}))

    def test_parses_mode_only_suite(self) -> None:
        payload = self._payload_with_matrix(
            [{"suite_id": "smoke-only", "mode": "smoke"}]
        )
        suites = run_baselines.config_matrix_suites(payload)
        self.assertIsNotNone(suites)
        self.assertEqual(len(suites), 1)
        self.assertEqual(suites[0].suite_id, "smoke-only")
        self.assertEqual(suites[0].mode, "smoke")
        self.assertIsNone(suites[0].case_ids)

    def test_parses_multiple_suites_preserving_order(self) -> None:
        payload = self._payload_with_matrix(
            [
                {"suite_id": "starter-pragmatics", "mode": "full"},
                {"suite_id": "instruction-ambiguity", "mode": "smoke"},
            ]
        )
        suites = run_baselines.config_matrix_suites(payload)
        self.assertEqual(
            [s.suite_id for s in suites],
            ["starter-pragmatics", "instruction-ambiguity"],
        )
        self.assertEqual([s.mode for s in suites], ["full", "smoke"])

    def test_parses_case_ids_suite(self) -> None:
        payload = self._payload_with_matrix(
            [{"suite_id": "custom", "case_ids": ["GG-01", "GG-02"]}]
        )
        suites = run_baselines.config_matrix_suites(payload)
        self.assertEqual(suites[0].suite_id, "custom")
        self.assertEqual(suites[0].case_ids, ("GG-01", "GG-02"))
        self.assertEqual(suites[0].mode, "custom")

    def test_parses_default_suite_id_without_explicit_mode(self) -> None:
        payload = self._payload_with_matrix([{"suite_id": "default"}])
        suites = run_baselines.config_matrix_suites(payload)
        self.assertIsNotNone(suites)
        self.assertEqual(len(suites), 1)
        self.assertEqual(suites[0].suite_id, "default")
        self.assertEqual(suites[0].mode, "full")
        self.assertIsNone(suites[0].case_ids)

    def test_rejects_empty_suites_list(self) -> None:
        payload = self._payload_with_matrix([])
        with self.assertRaisesRegex(ValueError, "non-empty"):
            run_baselines.config_matrix_suites(payload)

    def test_rejects_non_list_suites(self) -> None:
        payload = {"matrix": {"suites": "not-a-list"}}
        with self.assertRaisesRegex(ValueError, "must be a list"):
            run_baselines.config_matrix_suites(payload)

    def test_rejects_non_object_matrix(self) -> None:
        payload = {"matrix": "oops"}
        with self.assertRaisesRegex(ValueError, "must be an object"):
            run_baselines.config_matrix_suites(payload)

    def test_rejects_missing_suite_id(self) -> None:
        payload = self._payload_with_matrix([{"mode": "smoke"}])
        with self.assertRaisesRegex(ValueError, "suite_id"):
            run_baselines.config_matrix_suites(payload)

    def test_rejects_blank_suite_id(self) -> None:
        payload = self._payload_with_matrix([{"suite_id": "   ", "mode": "smoke"}])
        with self.assertRaisesRegex(ValueError, "suite_id"):
            run_baselines.config_matrix_suites(payload)

    def test_rejects_padded_suite_id(self) -> None:
        payload = self._payload_with_matrix([{"suite_id": " smoke ", "mode": "smoke"}])
        with self.assertRaisesRegex(ValueError, "exact"):
            run_baselines.config_matrix_suites(payload)

    def test_rejects_traversal_in_suite_id(self) -> None:
        payload = self._payload_with_matrix([{"suite_id": "../escape", "mode": "smoke"}])
        with self.assertRaisesRegex(ValueError, "path separators or traversal"):
            run_baselines.config_matrix_suites(payload)

    def test_rejects_duplicate_suite_ids(self) -> None:
        payload = self._payload_with_matrix(
            [
                {"suite_id": "smoke", "mode": "smoke"},
                {"suite_id": "smoke", "mode": "full"},
            ]
        )
        with self.assertRaisesRegex(ValueError, "unique"):
            run_baselines.config_matrix_suites(payload)

    def test_rejects_padded_mode(self) -> None:
        payload = self._payload_with_matrix([{"suite_id": "smoke", "mode": " smoke "}])
        with self.assertRaisesRegex(ValueError, "exact"):
            run_baselines.config_matrix_suites(payload)

    def test_rejects_unsupported_mode_without_case_ids(self) -> None:
        payload = self._payload_with_matrix([{"suite_id": "smoke", "mode": "wat"}])
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            run_baselines.config_matrix_suites(payload)

    def test_rejects_blank_case_ids(self) -> None:
        payload = self._payload_with_matrix([{"suite_id": "custom", "case_ids": []}])
        with self.assertRaisesRegex(ValueError, "non-empty"):
            run_baselines.config_matrix_suites(payload)

    def test_rejects_duplicate_case_ids(self) -> None:
        payload = self._payload_with_matrix(
            [{"suite_id": "custom", "case_ids": ["GG-01", "GG-01"]}]
        )
        with self.assertRaisesRegex(ValueError, "unique"):
            run_baselines.config_matrix_suites(payload)

    def test_rejects_non_string_case_id(self) -> None:
        payload = self._payload_with_matrix(
            [{"suite_id": "custom", "case_ids": ["GG-01", 7]}]
        )
        with self.assertRaisesRegex(ValueError, "case_ids"):
            run_baselines.config_matrix_suites(payload)


class MatrixRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(__file__).resolve().parent / "tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        for item in self.tmp_dir.glob("*.json"):
            item.unlink()

    def _dataset(self) -> Path:
        dataset_path = self.tmp_dir / "matrix-questions.json"
        rows = [
            {"id": "GG-01", "prompt": "Prompt one"},
            {"id": "GG-02", "prompt": "Prompt two"},
            {"id": "GG-03", "prompt": "Prompt three"},
            {"id": "GG-04", "prompt": "Prompt four"},
            {"id": "GG-05", "prompt": "Prompt five"},
            {"id": "GG-06", "prompt": "Prompt six"},
        ]
        dataset_path.write_text(json.dumps(rows), encoding="utf-8")
        return dataset_path

    def test_request_from_config_carries_matrix_suites(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-req-runs"
        config_path = self.tmp_dir / "matrix-req-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-matrix-req",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "matrix-baseline",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "matrix-baseline",
                        "skip_scoring": True,
                    },
                    "matrix": {
                        "suites": [
                            {"suite_id": "smoke", "mode": "smoke"},
                            {"suite_id": "starter", "case_ids": ["GG-01", "GG-03"]},
                        ],
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        request = run_baselines.request_from_config(config_path)
        self.assertIsNotNone(request.matrix_suites)
        self.assertEqual(len(request.matrix_suites), 2)
        self.assertEqual(request.matrix_suites[0].suite_id, "smoke")
        self.assertEqual(request.matrix_suites[0].mode, "smoke")
        self.assertIsNone(request.matrix_suites[0].case_ids)
        self.assertEqual(request.matrix_suites[1].suite_id, "starter")
        self.assertEqual(request.matrix_suites[1].case_ids, ("GG-01", "GG-03"))
        shutil.rmtree(run_dir, ignore_errors=True)

    def test_request_from_config_rejects_top_level_suite_case_ids_with_matrix(
        self,
    ) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-conflict-runs"
        config_path = self.tmp_dir / "matrix-conflict-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-matrix-conflict",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "matrix-baseline",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "matrix-baseline",
                        "skip_scoring": True,
                    },
                    "suite": {"case_ids": ["GG-01"]},
                    "matrix": {
                        "suites": [
                            {"suite_id": "smoke", "mode": "smoke"},
                        ],
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ValueError,
            "RunConfig suite.case_ids cannot be combined with matrix.suites",
        ):
            run_baselines.request_from_config(config_path)
        shutil.rmtree(run_dir, ignore_errors=True)

    def test_matrix_config_writes_per_suite_raw_artifacts(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-runs"

        config_path = self.tmp_dir / "matrix-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-matrix-runner",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "matrix-baseline",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "matrix-baseline",
                        "skip_scoring": True,
                    },
                    "matrix": {
                        "suites": [
                            {"suite_id": "smoke", "mode": "smoke"},
                            {"suite_id": "starter", "case_ids": ["GG-01", "GG-03"]},
                        ],
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )
        run_baselines.cmd_run(args)

        smoke_raw = run_dir / "smoke" / "gpt-5-4.smoke.raw.json"
        starter_raw = run_dir / "starter" / "gpt-5-4.starter.raw.json"
        self.assertTrue(smoke_raw.is_file(), f"Expected {smoke_raw}")
        self.assertTrue(starter_raw.is_file(), f"Expected {starter_raw}")

        smoke_payload = json.loads(smoke_raw.read_text(encoding="utf-8"))
        self.assertEqual(smoke_payload["run_mode"], "smoke")
        self.assertEqual(len(smoke_payload["results"]), 5)
        self.assertEqual(
            [r["id"] for r in smoke_payload["results"]],
            ["GG-01", "GG-02", "GG-03", "GG-04", "GG-05"],
        )

        starter_payload = json.loads(starter_raw.read_text(encoding="utf-8"))
        self.assertEqual(starter_payload["run_mode"], "starter")
        self.assertEqual(
            [r["id"] for r in starter_payload["results"]],
            ["GG-01", "GG-03"],
        )
        shutil.rmtree(run_dir, ignore_errors=True)

    def test_matrix_config_writes_scored_and_manifest_per_suite(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-scored-runs"

        config_path = self.tmp_dir / "matrix-scored-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-matrix-scored",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "matrix-baseline",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "matrix-baseline",
                    },
                    "matrix": {
                        "suites": [
                            {"suite_id": "starter-pragmatics", "mode": "full"},
                        ],
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        with patch.object(run_baselines, "score_payload") as score_mock:
            def _score_input(input_path, scored_path, _dataset_path, source_bundle):
                scored_path.write_text(
                    json.dumps(
                        {
                            "summary": {
                                "schema_version": "2.0.0",
                                "benchmark": "reasoning-benchmark",
                                "suite_id": "starter-pragmatics",
                                "overall": {"case_count": 6},
                            },
                            "results": [],
                        }
                    ),
                    encoding="utf-8",
                )

            score_mock.side_effect = _score_input
            args = argparse.Namespace(
                config=str(config_path),
                mode="full",
                dataset=str(self.tmp_dir / "ignored.json"),
                run_dir=str(self.tmp_dir / "ignored-runs"),
                models=["sonnet-4.6"],
                provider_command=None,
                prompt_timeout=1.0,
                skip_scoring=False,
            )
            run_baselines.cmd_run(args)

        raw_path = run_dir / "starter-pragmatics" / "gpt-5-4.full.raw.json"
        scored_path = run_dir / "starter-pragmatics" / "gpt-5-4.full.scored.json"
        summary_path = run_dir / "starter-pragmatics" / "gpt-5-4.full.summary.json"
        manifest_path = run_dir / "starter-pragmatics" / "gpt-5-4.full.manifest.json"
        self.assertTrue(raw_path.is_file())
        self.assertTrue(scored_path.is_file())
        self.assertTrue(summary_path.is_file())
        self.assertTrue(manifest_path.is_file())

        raw_payload = json.loads(raw_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(raw_payload["suite_id"], "starter-pragmatics")
        self.assertEqual(raw_payload["run_mode"], "full")
        self.assertEqual(manifest["id"], "baseline-starter-pragmatics-gpt-5-4")
        self.assertEqual(manifest["suite_id"], "starter-pragmatics")
        self.assertEqual(manifest["artifacts"]["raw_results"], "gpt-5-4.full.raw.json")
        self.assertEqual(manifest["artifacts"]["scored_results"], "gpt-5-4.full.scored.json")
        shutil.rmtree(run_dir, ignore_errors=True)

    def test_matrix_index_inlines_per_cell_summary_metrics_from_report_summaries(
        self,
    ) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-summaries-cmd-runs"

        config_path = self.tmp_dir / "matrix-index-summaries-cmd-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-matrix-index-summaries-cmd",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "matrix-baseline",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4", "sonnet-4.6"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "matrix-baseline",
                    },
                    "matrix": {
                        "suites": [
                            {"suite_id": "smoke", "mode": "smoke"},
                            {"suite_id": "starter", "case_ids": ["GG-01", "GG-03"]},
                        ],
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        with patch.object(run_baselines, "score_payload") as score_mock:
            def _score_input(input_path, scored_path, _dataset_path, source_bundle):
                stem = scored_path.stem
                if stem.endswith(".scored"):
                    stem = stem[: -len(".scored")]
                suite_dir = scored_path.parent.name
                accuracy_table = {
                    ("smoke", "gpt-5-4.smoke"): 0.8,
                    ("smoke", "sonnet-4-6.smoke"): 0.6,
                    ("starter", "gpt-5-4.starter"): 0.5,
                    ("starter", "sonnet-4-6.starter"): 0.3,
                }
                accuracy = accuracy_table[(suite_dir, stem)]
                scored_path.write_text(
                    json.dumps(
                        {
                            "summary": {
                                "schema_version": "2.0.0",
                                "benchmark": "reasoning-benchmark",
                                "suite_id": suite_dir,
                                "auto_scored": {"accuracy": accuracy},
                                "overall": {"case_count": 2},
                            },
                            "results": [],
                        }
                    ),
                    encoding="utf-8",
                )

            score_mock.side_effect = _score_input
            args = argparse.Namespace(
                config=str(config_path),
                mode="full",
                dataset=str(self.tmp_dir / "ignored.json"),
                run_dir=str(self.tmp_dir / "ignored-runs"),
                models=["ignored"],
                provider_command=None,
                prompt_timeout=1.0,
                skip_scoring=False,
            )
            run_baselines.cmd_run(args)

        index_path = run_dir / "matrix.index.json"
        self.assertTrue(index_path.is_file(), f"Expected {index_path}")
        index = json.loads(index_path.read_text(encoding="utf-8"))
        cells = {(c["suite_id"], c["model"]): c for c in index["cells"]}
        self.assertEqual(
            cells[("smoke", "gpt-5.4")]["summary_metrics"],
            {
                "schema_version": "2.0.0",
                "benchmark": "reasoning-benchmark",
                "suite_id": "smoke",
                "auto_scored": {"accuracy": 0.8},
                "overall": {"case_count": 2},
            },
        )
        self.assertEqual(
            cells[("smoke", "sonnet-4.6")]["summary_metrics"]["auto_scored"],
            {"accuracy": 0.6},
        )
        self.assertEqual(
            cells[("starter", "gpt-5.4")]["summary_metrics"]["auto_scored"],
            {"accuracy": 0.5},
        )
        self.assertEqual(
            cells[("starter", "sonnet-4.6")]["summary_metrics"]["auto_scored"],
            {"accuracy": 0.3},
        )
        shutil.rmtree(run_dir, ignore_errors=True)

    def test_matrix_config_writes_top_level_matrix_index(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-cmd-runs"

        config_path = self.tmp_dir / "matrix-index-cmd-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-matrix-index-cmd",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "matrix-baseline",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "matrix-baseline",
                        "skip_scoring": True,
                    },
                    "matrix": {
                        "suites": [
                            {"suite_id": "smoke", "mode": "smoke"},
                            {"suite_id": "starter", "case_ids": ["GG-01", "GG-03"]},
                        ],
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            mode="full",
            dataset=str(self.tmp_dir / "ignored.json"),
            run_dir=str(self.tmp_dir / "ignored-runs"),
            models=["sonnet-4.6"],
            provider_command=None,
            prompt_timeout=1.0,
            skip_scoring=False,
        )
        run_baselines.cmd_run(args)

        index_path = run_dir / "matrix.index.json"
        self.assertTrue(index_path.is_file(), f"Expected {index_path}")
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(index["schema_version"], "1.0.0")
        self.assertEqual(index["benchmark"], run_baselines.BENCHMARK_ID)
        self.assertEqual(index["models"], ["gpt-5.4"])
        self.assertEqual(
            index["suites"],
            [
                {"suite_id": "smoke", "mode": "smoke", "case_ids": None},
                {
                    "suite_id": "starter",
                    "mode": "starter",
                    "case_ids": ["GG-01", "GG-03"],
                },
            ],
        )
        self.assertEqual(index["run_config"], str(config_path))
        self.assertEqual(index["dataset"]["path"], str(dataset_path))
        self.assertEqual(
            index["dataset"]["fingerprint"]["value"],
            run_baselines.dataset_fingerprint(dataset_path),
        )
        cells = index["cells"]
        self.assertEqual(len(cells), 2)
        self.assertEqual(
            [(c["suite_id"], c["model"], c["mode"]) for c in cells],
            [("smoke", "gpt-5.4", "smoke"), ("starter", "gpt-5.4", "starter")],
        )
        self.assertEqual(cells[0]["raw_results"], "smoke/gpt-5-4.smoke.raw.json")
        self.assertIsNone(cells[0]["scored_results"])
        self.assertIsNone(cells[1]["scored_results"])
        shutil.rmtree(run_dir, ignore_errors=True)

    def test_matrix_continues_after_cell_failure_and_records_error(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-cell-error-runs"

        config_path = self.tmp_dir / "matrix-cell-error-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "id": "unit-matrix-cell-error",
                    "benchmark": "reasoning-benchmark",
                    "suite_id": "matrix-baseline",
                    "dataset": {"path": str(dataset_path)},
                    "models": ["gpt-5.4", "sonnet-4.6"],
                    "prompt_contract": run_baselines.build_prompt_contract(),
                    "execution": {
                        "mode": "matrix-baseline",
                        "skip_scoring": True,
                    },
                    "matrix": {
                        "suites": [
                            {"suite_id": "smoke", "mode": "smoke"},
                            {"suite_id": "starter", "case_ids": ["GG-01", "GG-03"]},
                        ],
                    },
                    "output": {"bundle_dir": str(run_dir)},
                }
            ),
            encoding="utf-8",
        )

        real_execute = run_baselines._execute_run_pass

        def _maybe_fail(**kwargs):
            if kwargs["mode"] == "smoke" and kwargs["model"] == "sonnet-4.6":
                raise RuntimeError("provider unavailable")
            return real_execute(**kwargs)

        with patch.object(
            run_baselines, "_execute_run_pass", side_effect=_maybe_fail
        ):
            args = argparse.Namespace(
                config=str(config_path),
                mode="full",
                dataset=str(self.tmp_dir / "ignored.json"),
                run_dir=str(self.tmp_dir / "ignored-runs"),
                models=["ignored"],
                provider_command=None,
                prompt_timeout=1.0,
                skip_scoring=False,
            )
            rc = run_baselines.cmd_run(args)

        self.assertEqual(rc, 1)
        index_path = run_dir / "matrix.index.json"
        self.assertTrue(index_path.is_file(), f"Expected {index_path}")
        index = json.loads(index_path.read_text(encoding="utf-8"))
        cells_by_key = {(c["suite_id"], c["model"]): c for c in index["cells"]}
        self.assertEqual(
            cells_by_key[("smoke", "sonnet-4.6")]["error"],
            {"type": "RuntimeError", "message": "provider unavailable"},
        )
        self.assertIsNone(cells_by_key[("smoke", "gpt-5.4")]["error"])
        self.assertIsNone(cells_by_key[("starter", "gpt-5.4")]["error"])
        self.assertIsNone(cells_by_key[("starter", "sonnet-4.6")]["error"])

        smoke_failed_raw = run_dir / "smoke" / "sonnet-4-6.smoke.raw.json"
        smoke_ok_raw = run_dir / "smoke" / "gpt-5-4.smoke.raw.json"
        self.assertFalse(smoke_failed_raw.exists())
        self.assertTrue(smoke_ok_raw.is_file())
        shutil.rmtree(run_dir, ignore_errors=True)


class MatrixIndexBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(__file__).resolve().parent / "tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        for item in self.tmp_dir.glob("*.json"):
            item.unlink()

    def _dataset(self) -> Path:
        dataset_path = self.tmp_dir / "matrix-index-questions.json"
        rows = [
            {"id": "GG-01", "prompt": "Prompt one"},
            {"id": "GG-02", "prompt": "Prompt two"},
            {"id": "GG-03", "prompt": "Prompt three"},
            {"id": "GG-04", "prompt": "Prompt four"},
            {"id": "GG-05", "prompt": "Prompt five"},
        ]
        dataset_path.write_text(json.dumps(rows), encoding="utf-8")
        return dataset_path

    def _request(
        self,
        *,
        run_dir: Path,
        dataset_path: Path,
        models: tuple[str, ...],
        suites: tuple[run_baselines.MatrixSuite, ...],
        skip_scoring: bool = False,
        config_path: Path | None = None,
    ) -> run_baselines.RunRequest:
        return run_baselines.RunRequest(
            mode="matrix-baseline",
            dataset_path=dataset_path,
            run_dir=run_dir,
            models=models,
            provider_commands={model: ["true"] for model in models},
            prompt_timeout=1.0,
            skip_scoring=skip_scoring,
            matrix_suites=suites,
            config_path=config_path,
        )

    def test_build_matrix_index_records_models_suites_and_dataset(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-runs"
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4",),
            suites=(
                run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),
            ),
        )

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
        )

        self.assertEqual(index["schema_version"], "1.0.0")
        self.assertEqual(index["benchmark"], run_baselines.BENCHMARK_ID)
        self.assertEqual(index["models"], ["gpt-5.4"])
        self.assertEqual(
            index["suites"],
            [{"suite_id": "smoke", "mode": "smoke", "case_ids": None}],
        )
        self.assertEqual(index["dataset"]["path"], str(dataset_path))
        self.assertEqual(index["dataset"]["fingerprint"]["algorithm"], "sha256")
        self.assertEqual(
            index["dataset"]["fingerprint"]["value"],
            run_baselines.dataset_fingerprint(dataset_path),
        )
        self.assertEqual(index["created_at"], "2026-04-27T00:00:00+00:00")
        self.assertIn("completed_at", index)
        self.assertIsNone(index["run_config"])

    def test_build_matrix_index_enumerates_all_model_suite_cells(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-cells-runs"
        suites = (
            run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),
            run_baselines.MatrixSuite(
                suite_id="starter", mode="starter", case_ids=("GG-01", "GG-03")
            ),
        )
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4", "sonnet-4.6"),
            suites=suites,
        )

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
        )

        cells = index["cells"]
        self.assertEqual(len(cells), 4)
        self.assertEqual(
            [(c["suite_id"], c["model"], c["mode"]) for c in cells],
            [
                ("smoke", "gpt-5.4", "smoke"),
                ("smoke", "sonnet-4.6", "smoke"),
                ("starter", "gpt-5.4", "starter"),
                ("starter", "sonnet-4.6", "starter"),
            ],
        )
        self.assertEqual(cells[0]["raw_results"], "smoke/gpt-5-4.smoke.raw.json")
        self.assertEqual(cells[0]["scored_results"], "smoke/gpt-5-4.smoke.scored.json")
        self.assertEqual(cells[0]["report_summary"], "smoke/gpt-5-4.smoke.summary.json")
        self.assertEqual(cells[0]["manifest"], "smoke/gpt-5-4.smoke.manifest.json")
        self.assertEqual(
            index["suites"][1],
            {"suite_id": "starter", "mode": "starter", "case_ids": ["GG-01", "GG-03"]},
        )

    def test_build_matrix_index_omits_scored_paths_when_skip_scoring(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-skip-runs"
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4",),
            suites=(run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),),
            skip_scoring=True,
        )

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
        )

        cell = index["cells"][0]
        self.assertEqual(cell["raw_results"], "smoke/gpt-5-4.smoke.raw.json")
        self.assertIsNone(cell["scored_results"])
        self.assertIsNone(cell["report_summary"])
        self.assertIsNone(cell["manifest"])

    def test_build_matrix_index_records_run_config_path(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-config-runs"
        config_path = self.tmp_dir / "matrix-index-config.json"
        config_path.write_text("{}", encoding="utf-8")
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4",),
            suites=(run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),),
            config_path=config_path,
        )

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
        )

        self.assertEqual(index["run_config"], str(config_path))

    def test_build_matrix_index_inlines_cell_summary_metrics(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-cell-summaries-runs"
        suites = (
            run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),
            run_baselines.MatrixSuite(suite_id="starter", mode="starter"),
        )
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4", "sonnet-4.6"),
            suites=suites,
        )
        cell_summaries = {
            ("smoke", "gpt-5.4"): {"auto_scored": {"accuracy": 0.8}},
            ("starter", "sonnet-4.6"): {"auto_scored": {"accuracy": 0.4}},
        }

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
            cell_summaries=cell_summaries,
        )

        cells = {(c["suite_id"], c["model"]): c for c in index["cells"]}
        self.assertEqual(
            cells[("smoke", "gpt-5.4")]["summary_metrics"],
            {"auto_scored": {"accuracy": 0.8}},
        )
        self.assertEqual(
            cells[("starter", "sonnet-4.6")]["summary_metrics"],
            {"auto_scored": {"accuracy": 0.4}},
        )
        self.assertIsNone(cells[("smoke", "sonnet-4.6")]["summary_metrics"])
        self.assertIsNone(cells[("starter", "gpt-5.4")]["summary_metrics"])

    def test_build_matrix_index_summary_metrics_default_none(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-no-summaries-runs"
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4",),
            suites=(run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),),
        )

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
        )

        self.assertIsNone(index["cells"][0]["summary_metrics"])

    def test_build_matrix_index_summary_metrics_none_when_skip_scoring(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-skip-summaries-runs"
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4",),
            suites=(run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),),
            skip_scoring=True,
        )

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
            cell_summaries={("smoke", "gpt-5.4"): {"auto_scored": {"accuracy": 1.0}}},
        )

        self.assertIsNone(index["cells"][0]["summary_metrics"])

    def test_build_matrix_index_aggregates_per_model_summaries_across_suites(
        self,
    ) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-model-summaries-runs"
        suites = (
            run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),
            run_baselines.MatrixSuite(suite_id="starter", mode="starter"),
        )
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4", "sonnet-4.6"),
            suites=suites,
        )
        cell_summaries = {
            ("smoke", "gpt-5.4"): {
                "auto_scored": {"total": 5, "correct": 4, "incorrect": 1, "accuracy": 0.8}
            },
            ("starter", "gpt-5.4"): {
                "auto_scored": {"total": 5, "correct": 3, "incorrect": 2, "accuracy": 0.6}
            },
            ("smoke", "sonnet-4.6"): {
                "auto_scored": {"total": 5, "correct": 2, "incorrect": 3, "accuracy": 0.4}
            },
            ("starter", "sonnet-4.6"): {
                "auto_scored": {"total": 5, "correct": 1, "incorrect": 4, "accuracy": 0.2}
            },
        }

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
            cell_summaries=cell_summaries,
        )

        self.assertEqual(
            index["model_summaries"],
            {
                "gpt-5.4": {
                    "suite_count": 2,
                    "auto_scored": {
                        "total": 10,
                        "correct": 7,
                        "incorrect": 3,
                        "accuracy": 0.7,
                    },
                },
                "sonnet-4.6": {
                    "suite_count": 2,
                    "auto_scored": {
                        "total": 10,
                        "correct": 3,
                        "incorrect": 7,
                        "accuracy": 0.3,
                    },
                },
            },
        )

    def test_build_matrix_index_model_summaries_skip_cells_without_summaries(
        self,
    ) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-partial-summaries-runs"
        suites = (
            run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),
            run_baselines.MatrixSuite(suite_id="starter", mode="starter"),
        )
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4",),
            suites=suites,
        )
        cell_summaries = {
            ("smoke", "gpt-5.4"): {
                "auto_scored": {"total": 5, "correct": 4, "incorrect": 1, "accuracy": 0.8}
            },
        }

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
            cell_summaries=cell_summaries,
        )

        self.assertEqual(
            index["model_summaries"],
            {
                "gpt-5.4": {
                    "suite_count": 1,
                    "auto_scored": {
                        "total": 5,
                        "correct": 4,
                        "incorrect": 1,
                        "accuracy": 0.8,
                    },
                },
            },
        )

    def test_build_matrix_index_model_summaries_default_none(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-empty-model-summaries-runs"
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4",),
            suites=(run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),),
        )

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
        )

        self.assertIsNone(index["model_summaries"])

    def test_build_matrix_index_model_summaries_none_when_skip_scoring(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-skip-model-summaries-runs"
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4",),
            suites=(run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),),
            skip_scoring=True,
        )

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
            cell_summaries={
                ("smoke", "gpt-5.4"): {
                    "auto_scored": {"total": 5, "correct": 5, "incorrect": 0, "accuracy": 1.0}
                }
            },
        )

        self.assertIsNone(index["model_summaries"])

    def test_build_matrix_index_aggregates_per_suite_summaries_across_models(
        self,
    ) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-suite-summaries-runs"
        suites = (
            run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),
            run_baselines.MatrixSuite(suite_id="starter", mode="starter"),
        )
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4", "sonnet-4.6"),
            suites=suites,
        )
        cell_summaries = {
            ("smoke", "gpt-5.4"): {
                "auto_scored": {"total": 5, "correct": 4, "incorrect": 1, "accuracy": 0.8}
            },
            ("smoke", "sonnet-4.6"): {
                "auto_scored": {"total": 5, "correct": 2, "incorrect": 3, "accuracy": 0.4}
            },
            ("starter", "gpt-5.4"): {
                "auto_scored": {"total": 5, "correct": 3, "incorrect": 2, "accuracy": 0.6}
            },
            ("starter", "sonnet-4.6"): {
                "auto_scored": {"total": 5, "correct": 1, "incorrect": 4, "accuracy": 0.2}
            },
        }

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
            cell_summaries=cell_summaries,
        )

        self.assertEqual(
            index["suite_summaries"],
            {
                "smoke": {
                    "model_count": 2,
                    "auto_scored": {
                        "total": 10,
                        "correct": 6,
                        "incorrect": 4,
                        "accuracy": 0.6,
                    },
                },
                "starter": {
                    "model_count": 2,
                    "auto_scored": {
                        "total": 10,
                        "correct": 4,
                        "incorrect": 6,
                        "accuracy": 0.4,
                    },
                },
            },
        )

    def test_build_matrix_index_suite_summaries_skip_cells_without_summaries(
        self,
    ) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-partial-suite-summaries-runs"
        suites = (
            run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),
            run_baselines.MatrixSuite(suite_id="starter", mode="starter"),
        )
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4", "sonnet-4.6"),
            suites=suites,
        )
        cell_summaries = {
            ("smoke", "gpt-5.4"): {
                "auto_scored": {"total": 5, "correct": 4, "incorrect": 1, "accuracy": 0.8}
            },
        }

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
            cell_summaries=cell_summaries,
        )

        self.assertEqual(
            index["suite_summaries"],
            {
                "smoke": {
                    "model_count": 1,
                    "auto_scored": {
                        "total": 5,
                        "correct": 4,
                        "incorrect": 1,
                        "accuracy": 0.8,
                    },
                },
            },
        )

    def test_build_matrix_index_suite_summaries_default_none(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-empty-suite-summaries-runs"
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4",),
            suites=(run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),),
        )

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
        )

        self.assertIsNone(index["suite_summaries"])

    def test_build_matrix_index_suite_summaries_none_when_skip_scoring(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-skip-suite-summaries-runs"
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4",),
            suites=(run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),),
            skip_scoring=True,
        )

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
            cell_summaries={
                ("smoke", "gpt-5.4"): {
                    "auto_scored": {"total": 5, "correct": 5, "incorrect": 0, "accuracy": 1.0}
                }
            },
        )

        self.assertIsNone(index["suite_summaries"])

    def test_build_matrix_index_aggregates_overall_summary_across_all_cells(
        self,
    ) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-overall-summary-runs"
        suites = (
            run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),
            run_baselines.MatrixSuite(suite_id="starter", mode="starter"),
        )
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4", "sonnet-4.6"),
            suites=suites,
        )
        cell_summaries = {
            ("smoke", "gpt-5.4"): {
                "auto_scored": {"total": 5, "correct": 4, "incorrect": 1, "accuracy": 0.8}
            },
            ("smoke", "sonnet-4.6"): {
                "auto_scored": {"total": 5, "correct": 2, "incorrect": 3, "accuracy": 0.4}
            },
            ("starter", "gpt-5.4"): {
                "auto_scored": {"total": 5, "correct": 3, "incorrect": 2, "accuracy": 0.6}
            },
            ("starter", "sonnet-4.6"): {
                "auto_scored": {"total": 5, "correct": 1, "incorrect": 4, "accuracy": 0.2}
            },
        }

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
            cell_summaries=cell_summaries,
        )

        self.assertEqual(
            index["overall_summary"],
            {
                "cell_count": 4,
                "auto_scored": {
                    "total": 20,
                    "correct": 10,
                    "incorrect": 10,
                    "accuracy": 0.5,
                },
            },
        )

    def test_build_matrix_index_overall_summary_skips_cells_without_summaries(
        self,
    ) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-partial-overall-summary-runs"
        suites = (
            run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),
            run_baselines.MatrixSuite(suite_id="starter", mode="starter"),
        )
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4", "sonnet-4.6"),
            suites=suites,
        )
        cell_summaries = {
            ("smoke", "gpt-5.4"): {
                "auto_scored": {"total": 5, "correct": 4, "incorrect": 1, "accuracy": 0.8}
            },
            ("starter", "sonnet-4.6"): {
                "auto_scored": {"total": 5, "correct": 1, "incorrect": 4, "accuracy": 0.2}
            },
        }

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
            cell_summaries=cell_summaries,
        )

        self.assertEqual(
            index["overall_summary"],
            {
                "cell_count": 2,
                "auto_scored": {
                    "total": 10,
                    "correct": 5,
                    "incorrect": 5,
                    "accuracy": 0.5,
                },
            },
        )

    def test_build_matrix_index_overall_summary_default_none(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-empty-overall-summary-runs"
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4",),
            suites=(run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),),
        )

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
        )

        self.assertIsNone(index["overall_summary"])

    def test_build_matrix_index_overall_summary_none_when_skip_scoring(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-skip-overall-summary-runs"
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4",),
            suites=(run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),),
            skip_scoring=True,
        )

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
            cell_summaries={
                ("smoke", "gpt-5.4"): {
                    "auto_scored": {"total": 5, "correct": 5, "incorrect": 0, "accuracy": 1.0}
                }
            },
        )

        self.assertIsNone(index["overall_summary"])

    def test_build_matrix_index_cell_error_default_none(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-cell-error-default-runs"
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4",),
            suites=(run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),),
        )

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
        )

        self.assertIsNone(index["cells"][0]["error"])

    def test_build_matrix_index_records_cell_errors(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-cell-errors-runs"
        suites = (
            run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),
            run_baselines.MatrixSuite(suite_id="starter", mode="starter"),
        )
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4", "sonnet-4.6"),
            suites=suites,
        )

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
            cell_errors={
                ("smoke", "sonnet-4.6"): {
                    "message": "provider timed out",
                    "type": "TimeoutError",
                },
            },
        )

        cells_by_key = {(c["suite_id"], c["model"]): c for c in index["cells"]}
        self.assertIsNone(cells_by_key[("smoke", "gpt-5.4")]["error"])
        self.assertEqual(
            cells_by_key[("smoke", "sonnet-4.6")]["error"],
            {"message": "provider timed out", "type": "TimeoutError"},
        )
        self.assertIsNone(cells_by_key[("starter", "gpt-5.4")]["error"])
        self.assertIsNone(cells_by_key[("starter", "sonnet-4.6")]["error"])

    def test_build_matrix_index_cell_errors_alongside_summaries(self) -> None:
        dataset_path = self._dataset()
        run_dir = self.tmp_dir / "matrix-index-cell-errors-with-summaries-runs"
        suites = (run_baselines.MatrixSuite(suite_id="smoke", mode="smoke"),)
        request = self._request(
            run_dir=run_dir,
            dataset_path=dataset_path,
            models=("gpt-5.4", "sonnet-4.6"),
            suites=suites,
        )

        index = run_baselines.build_matrix_index(
            request=request,
            created_at="2026-04-27T00:00:00+00:00",
            cell_summaries={
                ("smoke", "gpt-5.4"): {
                    "auto_scored": {
                        "total": 5,
                        "correct": 4,
                        "incorrect": 1,
                        "accuracy": 0.8,
                    }
                }
            },
            cell_errors={
                ("smoke", "sonnet-4.6"): {
                    "message": "boom",
                    "type": "RuntimeError",
                },
            },
        )

        cells_by_key = {(c["suite_id"], c["model"]): c for c in index["cells"]}
        successful = cells_by_key[("smoke", "gpt-5.4")]
        failed = cells_by_key[("smoke", "sonnet-4.6")]
        self.assertIsNone(successful["error"])
        self.assertEqual(
            successful["summary_metrics"]["auto_scored"]["correct"], 4
        )
        self.assertEqual(
            failed["error"],
            {"message": "boom", "type": "RuntimeError"},
        )
        self.assertIsNone(failed["summary_metrics"])


class ExampleMatrixConfigTests(unittest.TestCase):
    """Validate the shipped example matrix RunConfig parses end-to-end.

    The example doubles as a copy-paste starting point for users running the
    baseline matrix runner. If this fails, the example has drifted from the
    runner's RunConfig schema and should be updated alongside the schema change.
    """

    EXAMPLE_PATH = REPO_ROOT / "examples" / "configs" / "matrix-baseline.config.json"

    def test_example_matrix_config_file_is_present(self) -> None:
        self.assertTrue(
            self.EXAMPLE_PATH.is_file(),
            f"example matrix config missing at {self.EXAMPLE_PATH}",
        )

    def test_example_matrix_config_parses_via_request_from_config(self) -> None:
        request = run_baselines.request_from_config(self.EXAMPLE_PATH)
        self.assertIsNotNone(request.matrix_suites)
        suite_ids = [s.suite_id for s in request.matrix_suites]
        self.assertIn("smoke", suite_ids)
        self.assertIn("starter", suite_ids)
        starter = next(
            s for s in request.matrix_suites if s.suite_id == "starter"
        )
        self.assertIsNotNone(starter.case_ids)
        self.assertGreaterEqual(len(starter.case_ids), 2)
        self.assertTrue(request.skip_scoring)
        self.assertEqual(request.dataset_path, REPO_ROOT / "data" / "questions.json")
        self.assertGreaterEqual(len(request.models), 1)
        for model in request.models:
            self.assertIn(model, run_baselines.SUPPORTED_MODELS)


class RunConfigExtensionsHookTests(unittest.TestCase):
    """RunConfig must validate the optional extensions hook block."""

    def setUp(self) -> None:
        self.tmp_dir = Path(__file__).resolve().parent / "tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        for item in self.tmp_dir.glob("ext-config-*"):
            if item.is_file():
                item.unlink()

    def _dataset(self) -> Path:
        dataset_path = self.tmp_dir / "ext-config-questions.json"
        rows = [
            {"id": "GG-01", "prompt": "Prompt one"},
            {"id": "GG-02", "prompt": "Prompt two"},
            {"id": "GG-03", "prompt": "Prompt three"},
            {"id": "GG-04", "prompt": "Prompt four"},
            {"id": "GG-05", "prompt": "Prompt five"},
        ]
        dataset_path.write_text(json.dumps(rows), encoding="utf-8")
        return dataset_path

    def _config(self, extensions_block: object) -> Path:
        dataset_path = self._dataset()
        config_path = self.tmp_dir / "ext-config-payload.json"
        payload = {
            "schema_version": "2.0.0",
            "id": "ext-hook-config",
            "benchmark": "reasoning-benchmark",
            "suite_id": "smoke",
            "dataset": {"path": str(dataset_path)},
            "models": ["gpt-5.4"],
            "prompt_contract": run_baselines.build_prompt_contract(),
            "execution": {"mode": "smoke", "skip_scoring": True},
            "output": {"bundle_dir": str(self.tmp_dir / "ext-config-runs")},
            "extensions": extensions_block,
        }
        config_path.write_text(json.dumps(payload), encoding="utf-8")
        return config_path

    def test_extensions_block_with_disabled_reserved_namespace_passes(self) -> None:
        config_path = self._config(
            {"tool_use": {"enabled": False, "notes": "reserved for future"}}
        )
        request = run_baselines.request_from_config(config_path)
        self.assertEqual(request.mode, "smoke")

    def test_extensions_block_with_unknown_namespace_is_rejected(self) -> None:
        config_path = self._config({"browser_use": {"enabled": False}})
        with self.assertRaisesRegex(ValueError, "unknown extension namespace"):
            run_baselines.request_from_config(config_path)

    def test_extensions_block_with_enabled_reserved_namespace_is_rejected(
        self,
    ) -> None:
        config_path = self._config({"tool_use": {"enabled": True}})
        with self.assertRaisesRegex(ValueError, "no implementation"):
            run_baselines.request_from_config(config_path)


class ScorePayloadIntegrationTests(unittest.TestCase):
    """score_payload must score in-process and surface real exceptions."""

    def setUp(self) -> None:
        self.tmp_dir = Path(__file__).resolve().parent / "tmp" / "score-payload"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        for item in self.tmp_dir.glob("*.json"):
            item.unlink()

    def _dataset(self) -> Path:
        dataset_path = self.tmp_dir / "questions.json"
        dataset_path.write_text(
            json.dumps(
                [
                    {
                        "id": "GG-01",
                        "prompt": "Is the sky blue?",
                        "expected_answer": "yes",
                        "accepted_variants": [],
                    }
                ]
            ),
            encoding="utf-8",
        )
        return dataset_path

    def test_score_payload_writes_scored_artifact_in_process(self) -> None:
        dataset_path = self._dataset()
        raw_path = self.tmp_dir / "raw.json"
        raw_path.write_text(
            json.dumps(
                {
                    "input_meta": {"benchmark": "reasoning-benchmark", "suite_id": "smoke"},
                    "results": [{"id": "GG-01", "answer": "yes"}],
                }
            ),
            encoding="utf-8",
        )
        scored_path = self.tmp_dir / "scored.json"

        run_baselines.score_payload(raw_path, scored_path, dataset_path)

        scored = json.loads(scored_path.read_text(encoding="utf-8"))
        self.assertEqual(scored["summary"]["auto_scored"]["correct"], 1)

    def test_score_payload_surfaces_file_not_found_directly(self) -> None:
        dataset_path = self._dataset()
        missing = self.tmp_dir / "missing.json"
        scored_path = self.tmp_dir / "scored.json"

        with self.assertRaises(FileNotFoundError):
            run_baselines.score_payload(missing, scored_path, dataset_path)


if __name__ == "__main__":
    unittest.main()
