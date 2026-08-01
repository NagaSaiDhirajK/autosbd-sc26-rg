#!/usr/bin/env python3
"""Measure hot and cold AutoSBD deployment-selector inference overhead."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from autosbd.inference_overhead import (
    COLD_MEASURED_ITERATIONS,
    COLD_WARMUP_ITERATIONS,
    HOT_MEASURED_ITERATIONS,
    HOT_WARMUP_ITERATIONS,
    InferenceOverheadError,
    run_inference_overhead,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        type=Path,
        default=REPOSITORY_ROOT / "results/processed/stage5/models.json",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPOSITORY_ROOT / "results/processed/stage5/balanced_dataset.json",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=REPOSITORY_ROOT / "results/raw/inference_overhead",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY_ROOT / "results/processed/stage5",
    )
    parser.add_argument("--hot-warmup", type=int, default=HOT_WARMUP_ITERATIONS)
    parser.add_argument("--hot-iterations", type=int, default=HOT_MEASURED_ITERATIONS)
    parser.add_argument("--cold-warmup", type=int, default=COLD_WARMUP_ITERATIONS)
    parser.add_argument(
        "--cold-iterations", type=int, default=COLD_MEASURED_ITERATIONS
    )
    arguments = parser.parse_args()
    try:
        status = run_inference_overhead(
            models_path=arguments.models,
            dataset_path=arguments.dataset,
            raw_directory=arguments.raw_dir,
            output_directory=arguments.output_dir,
            repository_root=REPOSITORY_ROOT,
            hot_warmup_iterations=arguments.hot_warmup,
            hot_measured_iterations=arguments.hot_iterations,
            cold_warmup_iterations=arguments.cold_warmup,
            cold_measured_iterations=arguments.cold_iterations,
        )
    except InferenceOverheadError as error:
        parser.error(str(error))
    print(json.dumps(status, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
