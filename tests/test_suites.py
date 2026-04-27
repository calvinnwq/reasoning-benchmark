from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
sys.path.append(str(REPO_ROOT / "scripts"))


class SuiteManifestLayoutTests(unittest.TestCase):
    """Manifests for calibrated suites must live under data/suites/."""

    def setUp(self) -> None:
        self.suites_dir = REPO_ROOT / "data" / "suites"
        self.dataset = json.loads(
            (REPO_ROOT / "data" / "questions.json").read_text(encoding="utf-8")
        )
        self.dataset_ids = {row["id"] for row in self.dataset}

    def _load(self, name: str) -> dict:
        path = self.suites_dir / f"{name}.json"
        self.assertTrue(path.exists(), f"missing suite manifest: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _category(self, case_id: str) -> str:
        return case_id.split("-", 1)[0]

    def test_starter_manifest_has_required_fields(self) -> None:
        manifest = self._load("starter")

        self.assertEqual(manifest["schema_version"], "2.0.0")
        self.assertEqual(manifest["suite_id"], "starter")
        self.assertIn("name", manifest)
        self.assertIn("description", manifest)
        self.assertIn("selection_rationale", manifest)
        self.assertIsInstance(manifest["case_ids"], list)
        self.assertGreaterEqual(len(manifest["case_ids"]), 7)

    def test_holdout_manifest_has_required_fields(self) -> None:
        manifest = self._load("holdout")

        self.assertEqual(manifest["schema_version"], "2.0.0")
        self.assertEqual(manifest["suite_id"], "holdout")
        self.assertIn("name", manifest)
        self.assertIn("description", manifest)
        self.assertIn("selection_rationale", manifest)
        self.assertIsInstance(manifest["case_ids"], list)
        self.assertGreaterEqual(len(manifest["case_ids"]), 7)

    def test_starter_case_ids_exist_and_are_unique(self) -> None:
        manifest = self._load("starter")
        case_ids = manifest["case_ids"]

        self.assertEqual(len(case_ids), len(set(case_ids)))
        missing = [cid for cid in case_ids if cid not in self.dataset_ids]
        self.assertEqual([], missing)

    def test_holdout_case_ids_exist_and_are_unique(self) -> None:
        manifest = self._load("holdout")
        case_ids = manifest["case_ids"]

        self.assertEqual(len(case_ids), len(set(case_ids)))
        missing = [cid for cid in case_ids if cid not in self.dataset_ids]
        self.assertEqual([], missing)

    def test_starter_covers_every_task_family(self) -> None:
        manifest = self._load("starter")
        categories = {self._category(cid) for cid in manifest["case_ids"]}

        self.assertEqual(
            categories,
            {"GG", "CR", "TW", "SP", "IA", "PR", "MC"},
        )

    def test_holdout_covers_every_task_family(self) -> None:
        manifest = self._load("holdout")
        categories = {self._category(cid) for cid in manifest["case_ids"]}

        self.assertEqual(
            categories,
            {"GG", "CR", "TW", "SP", "IA", "PR", "MC"},
        )

    def test_starter_and_holdout_do_not_overlap(self) -> None:
        starter = set(self._load("starter")["case_ids"])
        holdout = set(self._load("holdout")["case_ids"])

        self.assertEqual(set(), starter & holdout)


class SuiteLoaderTests(unittest.TestCase):
    """The suites module exposes a typed loader used by the runner and CLI."""

    def setUp(self) -> None:
        import suites  # type: ignore

        self.suites = suites

    def test_load_suite_manifest_returns_dict_for_starter(self) -> None:
        manifest = self.suites.load_suite_manifest("starter")

        self.assertEqual(manifest["suite_id"], "starter")
        self.assertIsInstance(manifest["case_ids"], list)

    def test_load_suite_manifest_returns_dict_for_holdout(self) -> None:
        manifest = self.suites.load_suite_manifest("holdout")

        self.assertEqual(manifest["suite_id"], "holdout")
        self.assertIsInstance(manifest["case_ids"], list)

    def test_load_suite_manifest_raises_for_unknown_name(self) -> None:
        with self.assertRaises(FileNotFoundError):
            self.suites.load_suite_manifest("does-not-exist")

    def test_load_suite_manifest_rejects_path_traversal(self) -> None:
        with self.assertRaises(ValueError):
            self.suites.load_suite_manifest("../questions")

    def test_load_suite_manifest_validates_schema(self) -> None:
        tmp_dir = REPO_ROOT / "tests" / "tmp" / "suites-bad"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        bad_path = tmp_dir / "broken.json"
        bad_path.write_text(json.dumps({"suite_id": "broken"}), encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                self.suites.load_suite_manifest("broken", suites_dir=tmp_dir)
        finally:
            bad_path.unlink()

    def test_resolve_suite_case_ids_returns_tuple_for_starter(self) -> None:
        case_ids = self.suites.resolve_suite_case_ids("starter")

        self.assertIsInstance(case_ids, tuple)
        self.assertGreater(len(case_ids), 0)

    def test_list_available_suites_includes_starter_and_holdout(self) -> None:
        names = self.suites.list_available_suites()

        self.assertIn("starter", names)
        self.assertIn("holdout", names)
        self.assertEqual(sorted(names), list(names))


if __name__ == "__main__":
    unittest.main()
