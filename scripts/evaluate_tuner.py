#!/usr/bin/env python3
"""Run the frozen, completion-bound AutoSBD Stage 5 evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from autosbd.evaluation_artifacts import (
    EvaluationArtifactError,
    build_and_write_evaluation,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        status = build_and_write_evaluation(
            arguments.config,
            arguments.output_dir,
            repository_root=REPOSITORY_ROOT,
        )
    except EvaluationArtifactError as error:
        parser.error(str(error))
    print(json.dumps(status, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
