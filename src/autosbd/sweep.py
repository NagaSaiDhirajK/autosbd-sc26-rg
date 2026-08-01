"""Sequential, resumable sweep orchestration."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .config import SweepConfig
from .runner import TrialRunResult, TrialRunner


@dataclass(frozen=True)
class SweepRunSummary:
    total: int
    launched: int
    reused: int
    statuses: dict[str, int]
    records: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "launched": self.launched,
            "reused": self.reused,
            "statuses": dict(sorted(self.statuses.items())),
            "records": list(self.records),
        }


def run_sweep(
    config: SweepConfig,
    runner: TrialRunner,
    *,
    attempt_index: int = 0,
    max_trials: int | None = None,
    randomize: bool = True,
    stop_on_non_success: bool = False,
) -> SweepRunSummary:
    """Run trials one at a time; final timing is never concurrent.

    When ``stop_on_non_success`` is true, return immediately after recording
    the first result whose status is not ``success``.  The failing result is
    included in the summary, so callers can distinguish a clean completion
    from a fail-fast stop without losing its immutable evidence path.
    """

    if max_trials is not None and max_trials < 1:
        raise ValueError("max_trials must be positive")
    templates = config.trial_templates(randomize=randomize)
    if max_trials is not None:
        templates = templates[:max_trials]
    results: list[TrialRunResult] = []
    for template in templates:
        result = runner.run(
            template,
            config=config,
            attempt_index=attempt_index,
            reference_value=template.workload.reference_value,
        )
        results.append(result)
        if stop_on_non_success and result.record["status"] != "success":
            break
    statuses = Counter(result.record["status"] for result in results)
    return SweepRunSummary(
        total=len(results),
        launched=sum(result.launched for result in results),
        reused=sum(result.reused for result in results),
        statuses=dict(statuses),
        records=tuple(str(result.record_path) for result in results),
    )
