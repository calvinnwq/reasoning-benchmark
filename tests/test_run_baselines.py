from __future__ import annotations

import argparse
import json
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
            def _score_input(input_path, scored_path, _dataset_path):
                scored_path.write_text("{}", encoding="utf-8")

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
        self.assertTrue(raw_path.is_file())
        self.assertTrue(scored_path.is_file())
        score_mock.assert_called_once()

        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["run_mode"], "smoke")
        self.assertEqual(payload["model"], "gpt-5.4")
        self.assertEqual(len(payload["results"]), 5)
        self.assertEqual([item["id"] for item in payload["results"]], ["GG-01", "GG-02", "GG-03", "GG-04", "GG-05"])

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


if __name__ == "__main__":
    unittest.main()
