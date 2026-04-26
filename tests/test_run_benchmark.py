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
        self.assertEqual(payload["suite_id"], "full")
        self.assertEqual(payload["case_count"], 2)
        self.assertEqual(payload["question_count"], 2)
        self.assertEqual([item["case_id"] for item in payload["results"]], ["GG-01", "GG-02"])
        self.assertEqual([item["id"] for item in payload["results"]], ["GG-01", "GG-02"])
