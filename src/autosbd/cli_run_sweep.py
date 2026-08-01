"""Command-line entry point for a sequential, resumable sweep."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_sweep_config
from .runner import TrialRunner
from .sweep import run_sweep


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--logs-dir", type=Path)
    parser.add_argument("--attempt-index", type=int, default=0)
    parser.add_argument("--max-trials", type=int)
    parser.add_argument("--no-randomize", action="store_true")
    parser.add_argument(
        "--stop-on-non-success",
        action="store_true",
        help=(
            "stop after preserving the first non-success record instead of "
            "continuing with later templates"
        ),
    )
    parser.add_argument("--require-all-success", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    config = load_sweep_config(arguments.config)
    runner = TrialRunner(
        project_root=arguments.project_root,
        results_dir=arguments.results_dir,
        logs_dir=arguments.logs_dir,
    )
    summary = run_sweep(
        config,
        runner,
        attempt_index=arguments.attempt_index,
        max_trials=arguments.max_trials,
        randomize=not arguments.no_randomize,
        stop_on_non_success=arguments.stop_on_non_success,
    )
    print(json.dumps(summary.to_dict(), sort_keys=True))
    successful = summary.statuses.get("success", 0)
    return int(
        arguments.require_all_success and successful != summary.total
    )


if __name__ == "__main__":
    raise SystemExit(main())
