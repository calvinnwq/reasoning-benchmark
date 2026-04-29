from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch
import unittest

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
sys.path.append(str(REPO_ROOT / "scripts"))

import run_benchmark


class RunBenchmarkHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(__file__).resolve().parent / "tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        for item in self.tmp_dir.glob("run-benchmark-*.json"):
            item.unlink()

    def _dataset(self) -> Path:
        dataset_path = self.tmp_dir / "run-benchmark-questions.json"
        dataset_path.write_text(
            json.dumps(
                [
                    {"id": "GG-01", "category": "GG", "prompt": "Prompt one"},
                    {"id": "GG-02", "category": "GG", "prompt": "Prompt two"},
                ]
            ),
            encoding="utf-8",
        )
        return dataset_path

    def test_sample_run_emits_v2_compatibility_aliases(self) -> None:
        output = io.StringIO()

        with patch.object(run_benchmark, "DATA_PATH", self._dataset()):
            with contextlib.redirect_stdout(output):
                run_benchmark.cmd_sample_run()

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["schema_version"], "2.0.0")
        self.assertEqual(payload["suite_id"], "default")
        self.assertEqual(payload["case_count"], 2)
        self.assertEqual(payload["question_count"], 2)
        self.assertEqual([item["case_id"] for item in payload["results"]], ["GG-01", "GG-02"])
        self.assertEqual([item["id"] for item in payload["results"]], ["GG-01", "GG-02"])

    def test_sample_run_without_suite_excludes_optional_instruction_ambiguity(self) -> None:
        dataset_path = self.tmp_dir / "run-benchmark-default-questions.json"
        dataset_path.write_text(
            json.dumps(
                [
                    {"id": "GG-01", "category": "GG", "prompt": "Prompt one"},
                    {"id": "IA-01", "category": "IA", "prompt": "Ambiguous prompt"},
                    {
                        "id": "IA-02",
                        "task_family_id": "instruction-ambiguity",
                        "category": "IA",
                        "prompt": "Another ambiguous prompt",
                    },
                ]
            ),
            encoding="utf-8",
        )
        output = io.StringIO()

        with patch.object(run_benchmark, "DATA_PATH", dataset_path):
            with contextlib.redirect_stdout(output):
                run_benchmark.cmd_sample_run()

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["suite_id"], "default")
        self.assertEqual(payload["case_count"], 1)
        self.assertEqual([item["id"] for item in payload["results"]], ["GG-01"])

    def _suited_dataset(self) -> Path:
        dataset_path = self.tmp_dir / "run-benchmark-suited-questions.json"
        dataset_path.write_text(
            json.dumps(
                [
                    {"id": "GG-01", "category": "GG", "prompt": "GG one"},
                    {"id": "GG-02", "category": "GG", "prompt": "GG two"},
                    {"id": "SP-01", "category": "SP", "prompt": "SP one"},
                    {"id": "SP-02", "category": "SP", "prompt": "SP two"},
                ]
            ),
            encoding="utf-8",
        )
        return dataset_path

    def _write_suite(self, suite_id: str, case_ids: list[str]) -> Path:
        suites_dir = self.tmp_dir / "suites"
        suites_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = suites_dir / f"{suite_id}.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "suite_id": suite_id,
                    "name": f"Suite {suite_id}",
                    "description": "test fixture",
                    "selection_rationale": "test fixture",
                    "case_ids": case_ids,
                }
            ),
            encoding="utf-8",
        )
        return suites_dir

    def tearDown(self) -> None:
        for item in self.tmp_dir.glob("run-benchmark-*.json"):
            item.unlink()
        suites_dir = self.tmp_dir / "suites"
        if suites_dir.exists():
            for item in suites_dir.glob("*.json"):
                item.unlink()
            suites_dir.rmdir()
        prompts = self.tmp_dir / "run-benchmark-prompts.jsonl"
        if prompts.exists():
            prompts.unlink()

    def test_cmd_list_filters_to_suite_case_ids(self) -> None:
        suites_dir = self._write_suite("starter", ["GG-01", "SP-02"])
        output = io.StringIO()

        with patch.object(run_benchmark, "DATA_PATH", self._suited_dataset()):
            with patch.object(run_benchmark, "SUITES_DIR", suites_dir):
                with contextlib.redirect_stdout(output):
                    run_benchmark.cmd_list(suite="starter")

        text = output.getvalue()
        self.assertIn("GG-01", text)
        self.assertIn("SP-02", text)
        self.assertNotIn("GG-02", text)
        self.assertNotIn("SP-01", text)
        self.assertIn("Total: 2 questions", text)

    def test_cmd_emit_prompts_filters_to_suite_case_ids(self) -> None:
        suites_dir = self._write_suite("starter", ["GG-02", "SP-01"])
        out_path = self.tmp_dir / "run-benchmark-prompts.jsonl"

        with patch.object(run_benchmark, "DATA_PATH", self._suited_dataset()):
            with patch.object(run_benchmark, "SUITES_DIR", suites_dir):
                run_benchmark.cmd_emit_prompts(str(out_path), suite="starter")

        rows = [
            json.loads(line)
            for line in out_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual([r["id"] for r in rows], ["GG-02", "SP-01"])

    def test_cmd_sample_run_uses_suite_id_when_suite_passed(self) -> None:
        suites_dir = self._write_suite("starter", ["GG-01", "SP-02"])
        output = io.StringIO()

        with patch.object(run_benchmark, "DATA_PATH", self._suited_dataset()):
            with patch.object(run_benchmark, "SUITES_DIR", suites_dir):
                with contextlib.redirect_stdout(output):
                    run_benchmark.cmd_sample_run(suite="starter")

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["suite_id"], "starter")
        self.assertEqual(payload["case_count"], 2)
        self.assertEqual(
            [item["case_id"] for item in payload["results"]], ["GG-01", "SP-02"]
        )

    def test_cmd_list_unknown_suite_raises(self) -> None:
        with patch.object(run_benchmark, "DATA_PATH", self._suited_dataset()):
            with patch.object(run_benchmark, "SUITES_DIR", self.tmp_dir / "suites"):
                with self.assertRaises(FileNotFoundError):
                    run_benchmark.cmd_list(suite="nonexistent")
