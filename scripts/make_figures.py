#!/usr/bin/env python3
"""Generate internal, traceable AutoSBD figures from processed evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from autosbd.figures import (
    FigureError,
    generate_cpu_thread_scaling_figures,
    generate_inference_overhead_figures,
    generate_multifamily_figures,
    generate_multifamily_holdout_figures,
    generate_numerical_parity_figures,
    generate_run_eligibility_figures,
    generate_stage4_figures,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage4", type=Path)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--multifamily-summary", type=Path)
    parser.add_argument("--multifamily-predictions", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--table-dir", type=Path, required=True)
    arguments = parser.parse_args()
    if (arguments.stage4 is None) != (arguments.raw_dir is None):
        parser.error("--stage4 and --raw-dir must be supplied together")
    if (arguments.multifamily_summary is None) != (
        arguments.multifamily_predictions is None
    ):
        parser.error(
            "--multifamily-summary and --multifamily-predictions must be supplied together"
        )
    if arguments.stage4 is None and arguments.multifamily_summary is None:
        parser.error("select Stage 4 and/or multifamily figure inputs")
    try:
        statuses = {}
        if arguments.stage4 is not None:
            statuses["stage4"] = generate_stage4_figures(
                arguments.stage4,
                arguments.raw_dir,
                arguments.output_dir,
                arguments.table_dir,
            )
            statuses["cpu_thread_scaling"] = generate_cpu_thread_scaling_figures(
                arguments.raw_dir,
                arguments.output_dir,
                arguments.table_dir,
            )
            statuses["numerical_parity"] = generate_numerical_parity_figures(
                arguments.raw_dir,
                arguments.output_dir,
                arguments.table_dir,
            )
            statuses["run_eligibility"] = generate_run_eligibility_figures(
                arguments.stage4,
                arguments.raw_dir,
                arguments.output_dir,
                arguments.table_dir,
            )
        if arguments.multifamily_summary is not None:
            statuses["multifamily"] = generate_multifamily_figures(
                arguments.multifamily_summary,
                arguments.multifamily_predictions,
                arguments.output_dir,
                arguments.table_dir,
            )
            statuses["multifamily_holdout"] = generate_multifamily_holdout_figures(
                arguments.multifamily_summary,
                arguments.output_dir,
                arguments.table_dir,
            )
            inference_overhead_path = (
                arguments.multifamily_summary.parent / "inference_overhead.csv"
            )
            statuses["inference_overhead"] = generate_inference_overhead_figures(
                inference_overhead_path,
                arguments.output_dir,
                arguments.table_dir,
            )
        if arguments.stage4 is None and arguments.multifamily_summary is None:
            parser.error("select Stage 4 and/or multifamily figure inputs")
    except FigureError as error:
        parser.error(str(error))
    status = next(iter(statuses.values())) if len(statuses) == 1 else statuses
    print(json.dumps(status, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
