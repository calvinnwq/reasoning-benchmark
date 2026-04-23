#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from benchmark_adapters import AdapterError, run_cli_adapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CLI adapter for reasoning benchmark baseline runs")
    parser.add_argument("model", help="Benchmark model id (gpt-5.4 | sonnet-4.6 | qwen3.5-9b)")
    parser.add_argument("prompt", help="Benchmark question prompt")
    parser.add_argument(
        "--prefer",
        choices=("subscription", "opencode"),
        default="subscription",
        help="Preferred CLI harness for subscription-backed models",
    )
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv[1:])

    try:
        result = run_cli_adapter(args.model, args.prompt, prefer=args.prefer)
    except AdapterError as exc:
        print(json.dumps({"answer": "", "reasoning": "", "notes": str(exc)}))
        return 0

    print(json.dumps(result.to_payload(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
