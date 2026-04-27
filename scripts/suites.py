"""Suite manifest loader for the reasoning benchmark.

A suite manifest names an ordered case selection from data/questions.json so
runs can be focused on a high-signal starter slice or a reserved holdout
without changing the dataset itself. Manifests are plain JSON living in
``data/suites/<name>.json`` with the shape::

    {
      "schema_version": "2.0.0",
      "suite_id": "starter",
      "name": "Calibrated Starter Slice",
      "description": "...",
      "selection_rationale": "...",
      "case_ids": ["GG-01", ...]
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SUITES_DIR = REPO_ROOT / "data" / "suites"

REQUIRED_FIELDS = (
    "schema_version",
    "suite_id",
    "name",
    "description",
    "selection_rationale",
    "case_ids",
)


def _suites_dir(suites_dir: Path | None) -> Path:
    return Path(suites_dir) if suites_dir is not None else SUITES_DIR


def _validate_name(name: str) -> None:
    if not isinstance(name, str) or not name:
        raise ValueError("suite name must be a non-empty string")
    if name != name.strip():
        raise ValueError("suite name must not have leading or trailing whitespace")
    if "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"invalid suite name: {name!r}")


def load_suite_manifest(name: str, suites_dir: Path | None = None) -> dict[str, Any]:
    """Load and validate a suite manifest by name."""

    _validate_name(name)
    base = _suites_dir(suites_dir)
    path = base / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"suite manifest not found: {path}")

    with path.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)

    if not isinstance(manifest, dict):
        raise ValueError(f"suite manifest must be a JSON object: {path}")

    missing = [field for field in REQUIRED_FIELDS if field not in manifest]
    if missing:
        raise ValueError(
            f"suite manifest {path} missing required fields: {', '.join(missing)}"
        )

    if manifest["suite_id"] != name:
        raise ValueError(
            f"suite manifest suite_id {manifest['suite_id']!r} does not match filename {name!r}"
        )

    case_ids = manifest["case_ids"]
    if not isinstance(case_ids, list) or not case_ids:
        raise ValueError(f"suite manifest {path} case_ids must be a non-empty list")

    seen: set[str] = set()
    for case_id in case_ids:
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(
                f"suite manifest {path} case_ids must be non-empty strings"
            )
        if case_id != case_id.strip():
            raise ValueError(
                f"suite manifest {path} case_ids must not have surrounding whitespace"
            )
        if case_id in seen:
            raise ValueError(
                f"suite manifest {path} case_ids must be unique (duplicate: {case_id})"
            )
        seen.add(case_id)

    return manifest


def resolve_suite_case_ids(
    name: str, suites_dir: Path | None = None
) -> tuple[str, ...]:
    """Return the ordered case_ids declared by the named suite."""

    manifest = load_suite_manifest(name, suites_dir=suites_dir)
    return tuple(manifest["case_ids"])


def list_available_suites(suites_dir: Path | None = None) -> list[str]:
    """List suite names with a manifest under ``suites_dir``, sorted alphabetically."""

    base = _suites_dir(suites_dir)
    if not base.exists():
        return []
    names = [path.stem for path in base.glob("*.json") if path.is_file()]
    return sorted(names)
