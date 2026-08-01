"""Tests for bounded, monitored subprocess execution."""

from __future__ import annotations

import csv
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest import mock

from autosbd.process import ExecutionResult, run_monitored


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MOCK_SBD = REPOSITORY_ROOT / "tests" / "fixtures" / "mock_sbd.py"


def pid_is_running(pid: int) -> bool:
    """Return false for absent processes and zombies, which cannot execute."""

    stat_path = Path(f"/proc/{pid}/stat")
    try:
        stat = stat_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    try:
        state = stat.rsplit(")", 1)[1].strip().split()[0]
    except (IndexError, ValueError):
        return True
    return state != "Z"


class MonitoredProcessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.output_directory = Path(self.temporary_directory.name)
        self.environment = os.environ.copy()
        self.environment["PYTHONDONTWRITEBYTECODE"] = "1"

    def artifact_paths(self, label: str) -> tuple[Path, Path, Path]:
        return (
            self.output_directory / f"{label}.stdout.log",
            self.output_directory / f"{label}.stderr.log",
            self.output_directory / f"{label}.resources.csv",
        )

    def run_mode(
        self,
        label: str,
        mode: str,
        *,
        extra_arguments: list[str] | None = None,
        timeout_s: float = 2.0,
        termination_grace_s: float = 0.05,
        sample_interval_s: float = 0.01,
        monitor_gpu: bool = False,
    ) -> tuple[ExecutionResult, Path, Path, Path]:
        stdout_path, stderr_path, resource_path = self.artifact_paths(label)
        command = [sys.executable, str(MOCK_SBD), mode]
        if extra_arguments:
            command.extend(extra_arguments)
        result = run_monitored(
            command,
            cwd=REPOSITORY_ROOT,
            environment=self.environment,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            resource_path=resource_path,
            timeout_s=timeout_s,
            termination_grace_s=termination_grace_s,
            sample_interval_s=sample_interval_s,
            monitor_gpu=monitor_gpu,
        )
        return result, stdout_path, stderr_path, resource_path

    def assert_resource_log(self, resource_path: Path) -> None:
        with resource_path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.reader(stream))
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(
            rows[0],
            [
                "elapsed_s",
                "host_rss_mib",
                "gpu_memory_mib",
                "gpu_utilization_pct",
                "gpu_temperature_c",
                "gpu_power_w",
            ],
        )

    def test_monitored_success_preserves_logs_and_metrics(self) -> None:
        result, stdout_path, stderr_path, resource_path = self.run_mode(
            "success", "success"
        )

        self.assertEqual(result.exit_code, 0)
        self.assertFalse(result.timed_out)
        self.assertIsNone(result.termination_signal)
        self.assertIsNone(result.launch_error)
        self.assertGreater(result.wall_time_s, 0.0)
        self.assertGreaterEqual(result.peak_host_rss_mb, 0.0)
        self.assertGreaterEqual(result.resource_samples, 0)
        self.assertTrue(result.host_monitor_complete)
        self.assertIsNone(result.gpu_monitor_complete)
        self.assertIsNone(result.gpu_process_observed)
        self.assertFalse(result.term_sent)
        self.assertFalse(result.kill_sent)
        self.assertIn(
            "Sample-based diagonalization: Energy",
            stdout_path.read_text(encoding="utf-8"),
        )
        self.assertEqual(stderr_path.read_text(encoding="utf-8"), "")
        self.assert_resource_log(resource_path)

    def test_nonzero_exit_preserves_stdout_stderr_and_resources(self) -> None:
        result, stdout_path, stderr_path, resource_path = self.run_mode(
            "failure", "fail"
        )

        self.assertEqual(result.exit_code, 17)
        self.assertFalse(result.timed_out)
        self.assertIsNone(result.termination_signal)
        self.assertIsNone(result.launch_error)
        self.assertIn("Davidson iteration", stdout_path.read_text(encoding="utf-8"))
        self.assertIn(
            "intentional nonzero failure", stderr_path.read_text(encoding="utf-8")
        )
        self.assert_resource_log(resource_path)

    def test_timeout_kills_sigterm_resistant_child_without_orphan(self) -> None:
        child_pid_path = self.output_directory / "timeout-child.pid"
        child_pid: int | None = None
        try:
            result, stdout_path, stderr_path, resource_path = self.run_mode(
                "timeout",
                "timeout",
                extra_arguments=[
                    "--sleep-seconds",
                    "30",
                    "--spawn-child",
                    "--child-pid-file",
                    str(child_pid_path),
                ],
                timeout_s=0.3,
                termination_grace_s=0.05,
                sample_interval_s=0.01,
            )
            self.assertTrue(child_pid_path.is_file())
            child_pid = int(child_pid_path.read_text(encoding="utf-8").strip())

            deadline = time.monotonic() + 1.0
            while pid_is_running(child_pid) and time.monotonic() < deadline:
                time.sleep(0.02)

            self.assertTrue(result.timed_out)
            self.assertTrue(result.term_sent)
            self.assertTrue(result.kill_sent)
            self.assertIsNotNone(result.exit_code)
            self.assertLess(result.wall_time_s, 2.0)
            self.assertFalse(pid_is_running(child_pid), "timeout left a runnable child")
            self.assertIn("Davidson iteration", stdout_path.read_text(encoding="utf-8"))
            self.assertIn(
                "intentional timeout sleep", stderr_path.read_text(encoding="utf-8")
            )
            self.assert_resource_log(resource_path)
        finally:
            if child_pid is not None and pid_is_running(child_pid):
                os.kill(child_pid, signal.SIGKILL)

    def test_existing_artifact_paths_are_never_overwritten(self) -> None:
        for occupied_index, occupied_name in enumerate(("stdout", "stderr", "resource")):
            with self.subTest(artifact=occupied_name):
                stdout_path, stderr_path, resource_path = self.artifact_paths(
                    f"occupied-{occupied_name}"
                )
                paths = (stdout_path, stderr_path, resource_path)
                occupied_path = paths[occupied_index]
                occupied_path.write_bytes(b"immutable-sentinel\n")

                with self.assertRaises(FileExistsError):
                    run_monitored(
                        [sys.executable, str(MOCK_SBD), "success"],
                        cwd=REPOSITORY_ROOT,
                        environment=self.environment,
                        stdout_path=stdout_path,
                        stderr_path=stderr_path,
                        resource_path=resource_path,
                        timeout_s=2.0,
                        monitor_gpu=False,
                    )

                self.assertEqual(occupied_path.read_bytes(), b"immutable-sentinel\n")
                for index, candidate in enumerate(paths):
                    if index != occupied_index:
                        self.assertFalse(candidate.exists())

    def test_gpu_monitor_is_incomplete_without_associated_process_sample(self) -> None:
        with mock.patch(
            "autosbd.process._gpu_sample_for_process_tree",
            return_value=(None, 0.0, 34.0, 16.0, True),
        ):
            result, _, _, resource_path = self.run_mode(
                "gpu-unobserved",
                "timeout",
                extra_arguments=["--sleep-seconds", "0.1"],
                monitor_gpu=True,
            )

        self.assertGreater(result.resource_samples, 0)
        self.assertFalse(result.gpu_process_observed)
        self.assertFalse(result.gpu_monitor_complete)
        self.assertIsNone(result.peak_gpu_memory_mb)
        self.assert_resource_log(resource_path)

    def test_gpu_monitor_is_complete_after_associated_process_sample(self) -> None:
        with mock.patch(
            "autosbd.process._gpu_sample_for_process_tree",
            return_value=(12.5, 7.0, 35.0, 17.0, True),
        ):
            result, _, _, resource_path = self.run_mode(
                "gpu-observed",
                "timeout",
                extra_arguments=["--sleep-seconds", "0.1"],
                monitor_gpu=True,
            )

        self.assertGreater(result.resource_samples, 0)
        self.assertTrue(result.gpu_process_observed)
        self.assertTrue(result.gpu_monitor_complete)
        self.assertEqual(result.peak_gpu_memory_mb, 12.5)
        self.assert_resource_log(resource_path)

    def test_gpu_monitor_is_incomplete_when_a_query_fails(self) -> None:
        with mock.patch(
            "autosbd.process._gpu_sample_for_process_tree",
            return_value=(12.5, None, None, None, False),
        ):
            result, _, _, _ = self.run_mode(
                "gpu-query-failed",
                "timeout",
                extra_arguments=["--sleep-seconds", "0.1"],
                monitor_gpu=True,
            )

        self.assertTrue(result.gpu_process_observed)
        self.assertFalse(result.gpu_monitor_complete)


if __name__ == "__main__":
    unittest.main()
