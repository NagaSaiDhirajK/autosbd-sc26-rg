"""Command-line entry point for exactly one configured trial."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_sweep_config
from .runner import TrialRunner


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--logs-dir", type=Path)
    parser.add_argument("--workload")
    parser.add_argument("--candidate")
    parser.add_argument("--phase", choices=("warmup", "measured"))
    parser.add_argument("--repetition", type=int)
    parser.add_argument("--attempt-index", type=int, default=0)
    parser.add_argument("--reference-value", type=float)
    parser.add_argument("--require-success", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    config = load_sweep_config(arguments.config)
    templates = list(config.trial_templates(randomize=False))
    if arguments.workload is not None:
        templates = [
            item for item in templates if item.workload.name == arguments.workload
        ]
    if arguments.candidate is not None:
        templates = [
            item for item in templates if item.candidate.name == arguments.candidate
        ]
    if arguments.phase is not None:
        templates = [item for item in templates if item.phase == arguments.phase]
    if arguments.repetition is not None:
        templates = [
            item for item in templates if item.repetition == arguments.repetition
        ]
    if len(templates) != 1:
        raise SystemExit(
            f"selection must resolve to exactly one trial; matched {len(templates)}"
        )
    runner = TrialRunner(
        project_root=arguments.project_root,
        results_dir=arguments.results_dir,
        logs_dir=arguments.logs_dir,
    )
    result = runner.run(
        templates[0],
        config=config,
        attempt_index=arguments.attempt_index,
        reference_value=arguments.reference_value,
    )
    print(
        json.dumps(
            {
                "record": str(result.record_path),
                "trial_id": result.record["trial_id"],
                "status": result.record["status"],
                "launched": result.launched,
                "reused": result.reused,
            },
            sort_keys=True,
        )
    )
    return int(
        arguments.require_success and result.record["status"] != "success"
    )


if __name__ == "__main__":
    raise SystemExit(main())
