#!/usr/bin/env python3
"""Aggregate explicitly listed AutoSBD records into deterministic artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from autosbd.analysis import AnalysisError, aggregate_and_write


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate explicit immutable trial-record paths; no files are "
            "discovered automatically."
        )
    )
    parser.add_argument(
        "records",
        nargs="+",
        type=Path,
        help="explicit immutable record JSON path",
    )
    parser.add_argument(
        "--output-json",
        required=True,
        type=Path,
        help="deterministic aggregate JSON path",
    )
    parser.add_argument(
        "--output-csv",
        required=True,
        type=Path,
        help="deterministic companion row CSV path",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        _, status = aggregate_and_write(
            arguments.records,
            arguments.output_json,
            arguments.output_csv,
        )
    except AnalysisError as error:
        print(f"analysis failed: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "ok",
                "input_records": status["input_records"],
                "included_records": status["included_records"],
                "excluded_records": status["excluded_records"],
                "json_changed": status["json_changed"],
                "csv_changed": status["csv_changed"],
                "output_json": str(arguments.output_json),
                "output_csv": str(arguments.output_csv),
            },
            allow_nan=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
