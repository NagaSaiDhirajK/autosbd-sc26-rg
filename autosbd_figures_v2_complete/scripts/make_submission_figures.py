#!/usr/bin/env python3
"""Generate the publication-grade AutoSBD SC26 figure suite.

All defaults point to tracked, sealed repository artifacts. The generator does
not run SBD, refit a model, or modify raw benchmark records.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from autosbd.submission_figures import (
    SubmissionFigureError,
    generate_submission_figure_suite,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage4", type=_repo_path, default=_repo_path("results/processed/stage4_final.json"))
    parser.add_argument("--phaseb", type=_repo_path, default=_repo_path("results/processed/phaseb_n2_h2o_grid_final.json"))
    parser.add_argument("--policy-summary", type=_repo_path, default=_repo_path("results/processed/stage5_multifamily/policy_summary.csv"))
    parser.add_argument("--policy-predictions", type=_repo_path, default=_repo_path("results/processed/stage5_multifamily/policy_predictions.csv"))
    parser.add_argument("--models", type=_repo_path, default=_repo_path("results/processed/stage5_multifamily/models.json"))
    parser.add_argument("--inference-overhead", type=_repo_path, default=_repo_path("results/processed/stage5_multifamily/inference_overhead.csv"))
    parser.add_argument("--raw-dir", type=_repo_path, default=_repo_path("results/raw"))
    parser.add_argument("--numerical-parity", type=_repo_path, default=_repo_path("results/processed/figure_data/numerical_parity.csv"))
    parser.add_argument("--output-dir", type=_repo_path, default=_repo_path("figures/submission"))
    parser.add_argument("--table-dir", type=_repo_path, default=_repo_path("results/processed/submission_figure_data"))
    arguments = parser.parse_args()

    try:
        status = generate_submission_figure_suite(
            stage4_aggregate=arguments.stage4,
            phaseb_aggregate=arguments.phaseb,
            policy_summary=arguments.policy_summary,
            policy_predictions=arguments.policy_predictions,
            models=arguments.models,
            inference_overhead=arguments.inference_overhead,
            raw_dir=arguments.raw_dir,
            numerical_parity_csv=arguments.numerical_parity,
            output_dir=arguments.output_dir,
            table_dir=arguments.table_dir,
        )
    except SubmissionFigureError as error:
        parser.error(str(error))
    print(json.dumps(status, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
