#!/usr/bin/env python3
"""Analyze the complete, correctness-gated Phase C parameter screen."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from autosbd.parameter_screen import (
    ParameterScreenError,
    analyze_and_write_parameter_screen,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aggregate", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=REPOSITORY_ROOT,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        _, status = analyze_and_write_parameter_screen(
            arguments.aggregate,
            arguments.raw_dir,
            arguments.output_json,
            arguments.output_csv,
            repository_root=arguments.repository_root,
        )
    except ParameterScreenError as error:
        print(f"parameter-screen analysis failed: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "ok",
                "output_json": str(arguments.output_json),
                "output_csv": str(arguments.output_csv),
                **status,
            },
            allow_nan=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
