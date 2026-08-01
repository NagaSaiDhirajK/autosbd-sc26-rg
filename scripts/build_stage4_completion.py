#!/usr/bin/env python3
"""Build the deterministic, fail-closed Stage 4 completion attestation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from autosbd.completion import CompletionError, build_and_write_stage4_completion


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the explicit frozen protocol, deterministic aggregate, "
            "and aggregate-listed raw records, then write a completion attestation."
        )
    )
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--aggregate", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        status = build_and_write_stage4_completion(
            arguments.protocol,
            arguments.aggregate,
            arguments.raw_dir,
            arguments.output,
            repository_root=REPOSITORY_ROOT,
        )
    except CompletionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(status, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
