#!/usr/bin/env python3
"""Build the deterministic Phase B final completion attestation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from autosbd.phaseb_completion import (
    PhaseBCompletionError,
    build_and_write_phaseb_final_completion,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--aggregate", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        status = build_and_write_phaseb_final_completion(
            arguments.protocol,
            arguments.aggregate,
            arguments.raw_dir,
            arguments.output,
            repository_root=REPOSITORY_ROOT,
        )
    except PhaseBCompletionError as error:
        _parser().error(str(error))
    print(json.dumps(status, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
