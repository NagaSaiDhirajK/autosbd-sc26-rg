"""Bounded subprocess execution with process-tree and GPU resource monitoring."""

from __future__ import annotations

import csv
import math
import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExecutionResult:
    exit_code: int | None
    timed_out: bool
    termination_signal: int | None
    launch_error: str | None
    wall_time_s: float
    peak_host_rss_mb: float
    peak_gpu_memory_mb: float | None
    resource_samples: int
    host_monitor_complete: bool
    gpu_monitor_complete: bool | None
    gpu_process_observed: bool | None
    term_sent: bool
    kill_sent: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_monitored(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    resource_path: Path,
    timeout_s: float,
    termination_grace_s: float = 1.0,
    sample_interval_s: float = 0.1,
    monitor_gpu: bool = False,
) -> ExecutionResult:
    """Run one command and preserve logs for every terminal outcome."""

    if not command or not all(isinstance(argument, str) and argument for argument in command):
        raise ValueError("command must be a nonempty list of nonempty strings")
    if timeout_s <= 0 or termination_grace_s < 0 or sample_interval_s <= 0:
        raise ValueError("timeout/sample values are invalid")

    for artifact in (stdout_path, stderr_path, resource_path):
        artifact.parent.mkdir(parents=True, exist_ok=True)
        if artifact.exists():
            raise FileExistsError(f"Refusing to overwrite process artifact: {artifact}")

    started = time.monotonic()
    peak_host_rss_kib = 0
    peak_gpu_memory_mib: float | None = None
    samples = 0
    host_monitor_complete = True
    gpu_monitor_complete: bool | None = True if monitor_gpu else None
    gpu_process_observed: bool | None = False if monitor_gpu else None
    timed_out = False
    term_sent = False
    kill_sent = False
    launch_error: str | None = None
    process: subprocess.Popen[bytes] | None = None

    with (
        stdout_path.open("xb") as stdout_stream,
        stderr_path.open("xb") as stderr_stream,
        resource_path.open("x", encoding="utf-8", newline="") as resource_stream,
    ):
        resource_writer = csv.writer(resource_stream)
        resource_writer.writerow(
            [
                "elapsed_s",
                "host_rss_mib",
                "gpu_memory_mib",
                "gpu_utilization_pct",
                "gpu_temperature_c",
                "gpu_power_w",
            ]
        )
        resource_stream.flush()

        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=environment,
                stdout=stdout_stream,
                stderr=stderr_stream,
                start_new_session=True,
            )
        except OSError as error:
            launch_error = f"{type(error).__name__}: {error}"
            stderr_stream.write((launch_error + "\n").encode("utf-8", errors="replace"))
            stderr_stream.flush()

        if process is not None:
            while process.poll() is None:
                elapsed = time.monotonic() - started
                host_rss_kib, host_ok = _process_tree_rss_kib(process.pid)
                host_monitor_complete &= host_ok
                peak_host_rss_kib = max(peak_host_rss_kib, host_rss_kib)

                gpu_memory, gpu_utilization, gpu_temperature, gpu_power, gpu_ok = (
                    _gpu_sample_for_process_tree(process.pid) if monitor_gpu else (None,) * 4 + (True,)
                )
                if monitor_gpu:
                    assert gpu_monitor_complete is not None
                    assert gpu_process_observed is not None
                    gpu_monitor_complete &= gpu_ok
                    if gpu_memory is not None:
                        gpu_process_observed = True
                        peak_gpu_memory_mib = max(peak_gpu_memory_mib or 0.0, gpu_memory)

                resource_writer.writerow(
                    [
                        f"{elapsed:.9f}",
                        f"{host_rss_kib / 1024.0:.6f}",
                        "" if gpu_memory is None else f"{gpu_memory:.6f}",
                        "" if gpu_utilization is None else f"{gpu_utilization:.3f}",
                        "" if gpu_temperature is None else f"{gpu_temperature:.3f}",
                        "" if gpu_power is None else f"{gpu_power:.3f}",
                    ]
                )
                resource_stream.flush()
                samples += 1

                if elapsed >= timeout_s:
                    timed_out = True
                    term_sent = _signal_process_group(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=termination_grace_s)
                    except subprocess.TimeoutExpired:
                        pass
                    # The parent may exit on SIGTERM while a child in the same
                    # process group ignores it. Always attempt group SIGKILL.
                    kill_sent = _signal_process_group(process.pid, signal.SIGKILL)
                    if process.poll() is None:
                        process.wait()
                    break
                time.sleep(min(sample_interval_s, max(0.0, timeout_s - elapsed)))

            process.wait()
            final_rss_kib, final_host_ok = _process_tree_rss_kib(process.pid)
            host_monitor_complete &= final_host_ok
            peak_host_rss_kib = max(peak_host_rss_kib, final_rss_kib)

        stdout_stream.flush()
        stderr_stream.flush()
        resource_stream.flush()
        os.fsync(stdout_stream.fileno())
        os.fsync(stderr_stream.fileno())
        os.fsync(resource_stream.fileno())

    wall_time_s = time.monotonic() - started
    exit_code = process.returncode if process is not None else None
    termination_signal = -exit_code if exit_code is not None and exit_code < 0 else None
    if monitor_gpu:
        assert gpu_monitor_complete is not None
        assert gpu_process_observed is not None
        gpu_monitor_complete &= gpu_process_observed
    return ExecutionResult(
        exit_code=exit_code,
        timed_out=timed_out,
        termination_signal=termination_signal,
        launch_error=launch_error,
        wall_time_s=wall_time_s,
        peak_host_rss_mb=peak_host_rss_kib / 1024.0,
        peak_gpu_memory_mb=peak_gpu_memory_mib,
        resource_samples=samples,
        host_monitor_complete=host_monitor_complete,
        gpu_monitor_complete=gpu_monitor_complete,
        gpu_process_observed=gpu_process_observed,
        term_sent=term_sent,
        kill_sent=kill_sent,
    )


def _process_tree_rss_kib(root_pid: int) -> tuple[int, bool]:
    pending = [root_pid]
    seen: set[int] = set()
    total_kib = 0
    complete = True
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        status_path = Path(f"/proc/{pid}/status")
        children_path = Path(f"/proc/{pid}/task/{pid}/children")
        try:
            for line in status_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("VmRSS:"):
                    total_kib += int(line.split()[1])
                    break
        except FileNotFoundError:
            pass
        except (PermissionError, ProcessLookupError, ValueError):
            complete = False
        try:
            children = children_path.read_text(encoding="utf-8").split()
            pending.extend(int(child) for child in children)
        except FileNotFoundError:
            pass
        except (PermissionError, ProcessLookupError, ValueError):
            if status_path.exists():
                complete = False
    return total_kib, complete


def _process_tree_pids(root_pid: int) -> tuple[set[int], bool]:
    pending = [root_pid]
    seen: set[int] = set()
    complete = True
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        children_path = Path(f"/proc/{pid}/task/{pid}/children")
        try:
            pending.extend(int(child) for child in children_path.read_text().split())
        except FileNotFoundError:
            pass
        except (PermissionError, ProcessLookupError, ValueError):
            if Path(f"/proc/{pid}").exists():
                complete = False
    return seen, complete


def _gpu_sample_for_process_tree(
    root_pid: int,
) -> tuple[float | None, float | None, float | None, float | None, bool]:
    pids, tree_ok = _process_tree_pids(root_pid)
    try:
        application_query = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,used_gpu_memory",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        gpu_query = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None, None, None, False
    if application_query.returncode != 0 or gpu_query.returncode != 0:
        return None, None, None, None, False

    gpu_memory_mib = 0.0
    found_process = False
    for row in csv.reader(application_query.stdout.splitlines()):
        if len(row) != 2:
            return None, None, None, None, False
        try:
            pid = int(row[0].strip())
            memory = float(row[1].strip())
        except ValueError:
            return None, None, None, None, False
        if pid <= 0 or not math.isfinite(memory) or memory < 0:
            return None, None, None, None, False
        if pid in pids:
            found_process = True
            gpu_memory_mib += memory

    gpu_rows = list(csv.reader(gpu_query.stdout.splitlines()))
    if not gpu_rows or len(gpu_rows[0]) < 3:
        return (gpu_memory_mib if found_process else None), None, None, None, False
    try:
        utilization, temperature, power = (float(value.strip()) for value in gpu_rows[0][:3])
    except ValueError:
        return (gpu_memory_mib if found_process else None), None, None, None, False
    if not all(math.isfinite(value) for value in (utilization, temperature, power)):
        return (gpu_memory_mib if found_process else None), None, None, None, False
    return (
        gpu_memory_mib if found_process else None,
        utilization,
        temperature,
        power,
        tree_ok,
    )


def _signal_process_group(pid: int, requested_signal: signal.Signals) -> bool:
    try:
        os.killpg(pid, requested_signal)
        return True
    except ProcessLookupError:
        return False
