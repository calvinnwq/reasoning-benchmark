from __future__ import annotations

import argparse
import json
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

    def test_full_mode_returns_all_questions(self) -> None:
        selected = run_baselines.select_questions(self.questions, "full")
        self.assertEqual(len(selected), 7)

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

        raw_path = run_dir / "sonnet-4-6.full.raw.json"
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
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
                        "timeout_seconds": "nan",
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

        payload = json.loads((run_dir / "gpt-5-4.full.raw.json").read_text(encoding="utf-8"))
        manifest = json.loads((run_dir / "gpt-5-4.full.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([item["id"] for item in payload["results"]], ["GG-01", "GG-02", "GG-03"])
        self.assertEqual(payload["execution"]["max_cases"], 3)
        self.assertEqual(manifest["case_count"], 3)

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

        payload = json.loads((run_dir / "gpt-5-4.full.raw.json").read_text(encoding="utf-8"))
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
        manifest = json.loads((run_dir / "gpt-5-4.custom.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([item["id"] for item in payload["results"]], ["GG-04", "GG-02", "GG-06"])
        self.assertEqual(payload["execution"]["mode"], "custom")
        self.assertEqual(manifest["suite_id"], "custom")
        self.assertEqual(manifest["case_count"], 3)

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


if __name__ == "__main__":
    unittest.main()
