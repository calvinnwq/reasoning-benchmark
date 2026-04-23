#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from benchmark_adapters import AdapterError, run_api_adapter


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: api_adapter.py MODEL PROMPT", file=sys.stderr)
        return 2

    model, prompt = argv[1], argv[2]
    try:
        result = run_api_adapter(model, prompt)
    except AdapterError as exc:
        print(json.dumps({"answer": "", "reasoning": "", "notes": str(exc)}))
        return 0

    print(json.dumps(result.to_payload(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
