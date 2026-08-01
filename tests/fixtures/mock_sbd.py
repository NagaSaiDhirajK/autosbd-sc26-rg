#!/usr/bin/env python3
"""Deterministic subprocess fixture that emits AMD SBD-shaped output.

This executable exists only to test AutoSBD's process-management and parsing
code.  It is not an SBD implementation and its output is not scientific data.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


MODES = ("success", "nonconverged", "malformed", "fail", "timeout", "oom")
ENERGY_HARTREE = -326.6982536731583
CONVERGED_RESIDUAL = 8.931146441578446e-09
NONCONVERGED_RESIDUAL = 1.7589424916975e-07
DENSITY = tuple(1.99 - (index * 0.01) for index in range(36))


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    raw_arguments = sys.argv[1:]
    positional_mode: str | None = None
    if raw_arguments and raw_arguments[0] in MODES:
        positional_mode = raw_arguments.pop(0)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", dest="option_mode", choices=MODES)
    parser.add_argument(
        "--invocation-counter",
        "--counter",
        dest="invocation_counter",
        type=Path,
        help="Append one mode name per invocation to this caller-provided path.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=60.0,
        help="Sleep duration for timeout mode (default: 60 seconds).",
    )
    parser.add_argument(
        "--spawn-child",
        action="store_true",
        help="In timeout mode, spawn a child that ignores SIGTERM.",
    )
    parser.add_argument(
        "--child-pid-file",
        type=Path,
        help="Write the optional timeout child's PID to this path.",
    )
    parser.add_argument(
        "--exit-code",
        type=int,
        help="Override the default exit code for fail or oom mode.",
    )
    arguments, unknown = parser.parse_known_args(raw_arguments)
    arguments.positional_mode = positional_mode
    if arguments.sleep_seconds < 0:
        parser.error("--sleep-seconds must be nonnegative")
    if arguments.child_pid_file is not None and not arguments.spawn_child:
        parser.error("--child-pid-file requires --spawn-child")
    return arguments, unknown


def append_invocation(path: Path | None, mode: str) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"{mode}\n")
        stream.flush()
        os.fsync(stream.fileno())


def emit_iteration(residual: float) -> None:
    print(
        " Davidson iteration 0.0 (tol=0.302058428013592): "
        "-326.5243347700003",
        flush=True,
    )
    print(
        f" Davidson iteration 0.1 (tol={residual}): "
        f"{ENERGY_HARTREE} -326.0526795299164",
        flush=True,
    )


def emit_complete_result(residual: float) -> None:
    print(" Elapsed time for helper construction 0.001 (sec) ", flush=True)
    print(" Elapsed time for init 0.0001 (sec) ", flush=True)
    emit_iteration(residual)
    print(" Elapsed time for davidson 0.02 (sec) ", flush=True)
    print(" Elapsed time for diagonalization 0.021 (sec) ", flush=True)
    print(" Elapsed time for mult 0.005 (sec) ", flush=True)
    print(f" Energy = {ENERGY_HARTREE}", flush=True)
    print(" Elapsed time for measurement 0.001 (sec) ", flush=True)
    print(
        f" Sample-based diagonalization: Energy = {ENERGY_HARTREE}",
        flush=True,
    )
    density_text = ",".join(f"{value:.12f}" for value in DENSITY)
    # The pinned upstream formatter omits the closing bracket; preserve that
    # exact quirk so parser tests exercise the compatibility path.
    print(
        f" Sample-based diagonalization: density = [{density_text}",
        flush=True,
    )


def write_child_pid(path: Path | None, pid: int) -> None:
    if path is None:
        return
    with path.open("w", encoding="utf-8") as stream:
        stream.write(f"{pid}\n")
        stream.flush()
        os.fsync(stream.fileno())


def spawn_sigterm_ignoring_child(sleep_seconds: float) -> subprocess.Popen[bytes]:
    child_program = (
        "import signal,time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"time.sleep({sleep_seconds!r})"
    )
    return subprocess.Popen(
        [sys.executable, "-c", child_program],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def run_timeout(arguments: argparse.Namespace) -> int:
    print("rank 0 has device 0", flush=True)
    emit_iteration(0.03715544425092371)
    print("mock_sbd: entering intentional timeout sleep", file=sys.stderr, flush=True)

    child: subprocess.Popen[bytes] | None = None
    try:
        if arguments.spawn_child:
            child = spawn_sigterm_ignoring_child(arguments.sleep_seconds + 60.0)
            write_child_pid(arguments.child_pid_file, child.pid)
        time.sleep(arguments.sleep_seconds)
    finally:
        # A normally completing fixture must not leak its optional child.  A
        # timeout test should kill the entire process group before this path.
        if child is not None and child.poll() is None:
            child.kill()
            child.wait()
    return 0


def main() -> int:
    arguments, _unknown = parse_args()
    mode = arguments.option_mode or arguments.positional_mode or "success"
    append_invocation(arguments.invocation_counter, mode)

    if mode == "success":
        emit_complete_result(CONVERGED_RESIDUAL)
        return 0
    if mode == "nonconverged":
        emit_complete_result(NONCONVERGED_RESIDUAL)
        return 0
    if mode == "malformed":
        emit_iteration(CONVERGED_RESIDUAL)
        print(" Sample-based diagonalization: density = [1.0,not-a-number", flush=True)
        return 0
    if mode == "fail":
        emit_iteration(0.03715544425092371)
        print("mock_sbd: intentional nonzero failure", file=sys.stderr, flush=True)
        return arguments.exit_code if arguments.exit_code is not None else 17
    if mode == "timeout":
        return run_timeout(arguments)
    if mode == "oom":
        emit_iteration(0.03715544425092371)
        print(
            "mock_sbd: CUDA error: out of memory (simulated; no allocation attempted)",
            file=sys.stderr,
            flush=True,
        )
        return arguments.exit_code if arguments.exit_code is not None else 42
    raise AssertionError(f"unhandled mock mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
