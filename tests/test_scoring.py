from __future__ import annotations

import json
import sys
from pathlib import Path
import unittest

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
sys.path.append(str(REPO_ROOT / "scripts"))

import score_run


class ScoringNormalizationTests(unittest.TestCase):
    def test_normalize_text(self) -> None:
        self.assertEqual(
            score_run.normalize_text("  No, The cat’s   at the door. "),
            "no the cat s at the door",
        )

    def test_missing_answer_scores_zero(self) -> None:
        result = score_run.score_single_answer("", "Yes. Carry the object.", [])
        self.assertEqual(result.score, 0)
        self.assertEqual(result.matched_by, "missing")
        self.assertEqual(result.reason, "missing_answer")

    def test_yes_no_binary_match(self) -> None:
        result = score_run.score_single_answer(
            "No, that's not what they asked.",
            "No. They are asking you to hand it over.",
            [],
        )
        self.assertEqual(result.score, 1)
        self.assertEqual(result.matched_by, "binary_match")

    def test_yes_no_mismatch(self) -> None:
        result = score_run.score_single_answer(
            "Yes, you should.",
            "No. It is not requested.",
            [],
        )
        self.assertEqual(result.score, 0)
        self.assertEqual(result.matched_by, "binary_mismatch")


class ScoringFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = score_run.load_dataset(score_run.DEFAULT_DATASET_PATH)
        self.input_payload = {
            "results": [
                {
                    "id": "GG-01",
                    "answer": "Drive there.",
                    "score_answer": None,
                    "score_reasoning": None,
                    "score_constraint_extraction": None,
                    "penalties": None,
                    "notes": "",
                },
                {
                    "id": "ZZ-99",
                    "answer": "No.",
                },
            ]
        }

    def test_unknown_question_id_is_marked(self) -> None:
        meta, records = score_run.normalize_run_payload(self.input_payload)
        scored = [score_run.score_record(record, self.dataset) for record in records]
        self.assertEqual(scored[1]["score_answer"], None)
        status = scored[1]["scoring_status"]
        self.assertEqual(status["reason"], "unknown_question_id")
        self.assertTrue(status["heuristic_flags"][0]["is_heuristic"])

    def test_scored_payload_building(self) -> None:
        _, records = score_run.normalize_run_payload(self.input_payload)
        scored = [score_run.score_record(item, self.dataset) for item in records]
        output = score_run.build_output_payload(
            {},
            scored,
            str(score_run.DEFAULT_DATASET_PATH),
            "runs/example-run.json",
        )
        parsed_json = json.dumps(output)
        parsed = json.loads(parsed_json)
        self.assertEqual(parsed["schema_version"], "1.0.0")
        self.assertIn("summary", parsed)
        self.assertIn("auto_scored", parsed["summary"])
        self.assertIn("manual_only", parsed["summary"])
        self.assertEqual(parsed["summary"]["overall"]["question_count"], 2)


if __name__ == "__main__":
    unittest.main()
