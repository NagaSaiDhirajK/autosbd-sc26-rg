"""Tests for sequential sweep orchestration and fail-fast behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from autosbd.runner import TrialRunResult
from autosbd.sweep import run_sweep


class _FakeConfig:
    def __init__(self, count: int = 4) -> None:
        self.templates = [
            SimpleNamespace(
                name=f"trial-{index}",
                workload=SimpleNamespace(reference_value=-float(index)),
            )
            for index in range(count)
        ]
        self.randomize_arguments: list[bool] = []

    def trial_templates(self, *, randomize: bool) -> list[SimpleNamespace]:
        self.randomize_arguments.append(randomize)
        return list(self.templates)


class _FakeRunner:
    def __init__(self, statuses: list[str]) -> None:
        self.statuses = list(statuses)
        self.calls: list[dict[str, object]] = []

    def run(
        self,
        template: SimpleNamespace,
        *,
        config: _FakeConfig,
        attempt_index: int,
        reference_value: float,
    ) -> TrialRunResult:
        call_index = len(self.calls)
        status = self.statuses[call_index]
        self.calls.append(
            {
                "template": template.name,
                "config": config,
                "attempt_index": attempt_index,
                "reference_value": reference_value,
            }
        )
        return TrialRunResult(
            record_path=Path(f"{template.name}.json"),
            record={"status": status},
            launched=True,
            reused=False,
        )


class SweepTests(unittest.TestCase):
    def test_default_continues_after_non_success(self) -> None:
        config = _FakeConfig(count=3)
        runner = _FakeRunner(["success", "failed", "success"])

        summary = run_sweep(config, runner, attempt_index=2, randomize=False)

        self.assertEqual(summary.total, 3)
        self.assertEqual(summary.launched, 3)
        self.assertEqual(summary.reused, 0)
        self.assertEqual(summary.statuses, {"success": 2, "failed": 1})
        self.assertEqual(len(runner.calls), 3)
        self.assertEqual(config.randomize_arguments, [False])
        self.assertEqual(runner.calls[0]["attempt_index"], 2)
        self.assertEqual(runner.calls[2]["reference_value"], -2.0)

    def test_fail_fast_includes_failure_and_skips_later_templates(self) -> None:
        config = _FakeConfig(count=4)
        runner = _FakeRunner(
            ["success", "skipped_memory", "success", "success"]
        )

        summary = run_sweep(config, runner, stop_on_non_success=True)

        self.assertEqual(summary.total, 2)
        self.assertEqual(summary.launched, 2)
        self.assertEqual(
            summary.statuses, {"success": 1, "skipped_memory": 1}
        )
        self.assertEqual(
            summary.records, ("trial-0.json", "trial-1.json")
        )
        self.assertEqual(len(runner.calls), 2)

    def test_fail_fast_processes_every_success_with_max_trials(self) -> None:
        config = _FakeConfig(count=4)
        runner = _FakeRunner(["success", "success", "failed", "failed"])

        summary = run_sweep(
            config,
            runner,
            max_trials=2,
            stop_on_non_success=True,
        )

        self.assertEqual(summary.total, 2)
        self.assertEqual(summary.statuses, {"success": 2})
        self.assertEqual(len(runner.calls), 2)


if __name__ == "__main__":
    unittest.main()
