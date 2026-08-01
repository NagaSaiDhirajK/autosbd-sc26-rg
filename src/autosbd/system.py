"""System, source, build, and input provenance capture."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import socket
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .records import canonical_json


GIB = 1024**3
MIB = 1024**2
DEFAULT_GPU_CEILING_BYTES = 20 * GIB


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def describe_input_files(files: Mapping[str, Path], project_root: Path) -> list[dict[str, Any]]:
    described: list[dict[str, Any]] = []
    for role, path in sorted(files.items()):
        resolved = path.resolve(strict=True)
        try:
            display_path = str(resolved.relative_to(project_root.resolve()))
        except ValueError:
            display_path = str(resolved)
        described.append(
            {
                "role": role,
                "path": display_path,
                "sha256": sha256_file(resolved),
                "size_bytes": resolved.stat().st_size,
            }
        )
    return described


def combined_input_sha256(input_files: list[dict[str, Any]]) -> str:
    semantic = [
        {"role": item["role"], "sha256": item["sha256"], "size_bytes": item["size_bytes"]}
        for item in input_files
    ]
    return hashlib.sha256(canonical_json(semantic).encode("utf-8")).hexdigest()


def git_state(path: Path) -> dict[str, Any]:
    return {
        "commit": _command_output(["git", "-C", str(path), "rev-parse", "HEAD"]),
        "dirty": bool(
            _command_output(["git", "-C", str(path), "status", "--porcelain"], allow_empty=True)
        ),
        "url": _command_output(
            ["git", "-C", str(path), "remote", "get-url", "origin"], allow_empty=True
        ),
    }


def static_system_snapshot(cuda_toolkit_version: str | None) -> dict[str, Any]:
    gpu = query_gpu()
    snapshot = {
        "hostname": socket.gethostname(),
        "cpu_model": _cpu_model(),
        "physical_cores": _physical_core_count(),
        "logical_cpus": os.cpu_count(),
        "gpu": gpu,
        "cuda_toolkit_version": cuda_toolkit_version,
    }
    fingerprint_fields = {
        "cpu_model": snapshot["cpu_model"],
        "physical_cores": snapshot["physical_cores"],
        "gpu_name": gpu.get("name") if gpu else None,
        "gpu_uuid": gpu.get("uuid") if gpu else None,
        "driver_version": gpu.get("driver_version") if gpu else None,
        "compute_capability": gpu.get("compute_capability") if gpu else None,
        "cuda_toolkit_version": cuda_toolkit_version,
    }
    snapshot["machine_fingerprint"] = hashlib.sha256(
        canonical_json(fingerprint_fields).encode("utf-8")
    ).hexdigest()
    return snapshot


def dynamic_preflight() -> dict[str, Any]:
    gpu = query_gpu()
    compute_processes = query_gpu_processes() if gpu is not None else None
    gpu_process_query_ok = compute_processes is not None if gpu is not None else None
    free_host_bytes = _mem_available_bytes()
    gpu_free_mib = gpu.get("memory_free_mib") if gpu is not None else None
    gpu_free_bytes = (
        int(gpu_free_mib * MIB)
        if isinstance(gpu_free_mib, (int, float))
        else None
    )
    gpu_cap_bytes = (
        min(DEFAULT_GPU_CEILING_BYTES, int(0.8 * gpu_free_bytes))
        if gpu_free_bytes is not None
        else None
    )
    return {
        "load_average_1m": os.getloadavg()[0],
        "host_memory_available_bytes": free_host_bytes,
        "host_memory_cap_bytes": int(0.8 * free_host_bytes),
        "gpu": gpu,
        "gpu_compute_processes": compute_processes,
        "gpu_process_query_ok": gpu_process_query_ok,
        "gpu_idle": (
            len(compute_processes) == 0
            if gpu is not None and compute_processes is not None
            else None
        ),
        "gpu_memory_cap_bytes": gpu_cap_bytes,
        "gpu_memory_policy": (
            "min(20 GiB, 80% of preflight free VRAM)"
            if gpu is not None
            else None
        ),
    }


def query_gpu() -> dict[str, Any] | None:
    command = [
        "nvidia-smi",
        "--query-gpu=index,uuid,name,driver_version,compute_cap,memory.total,memory.used,"
        "memory.free,utilization.gpu,temperature.gpu,power.draw,power.limit",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    rows = list(csv.reader(result.stdout.splitlines()))
    if not rows or len(rows[0]) < 12:
        return None
    row = [value.strip() for value in rows[0]]
    return {
        "index": _optional_int(row[0]),
        "uuid": row[1],
        "name": row[2],
        "driver_version": row[3],
        "compute_capability": row[4],
        "memory_total_mib": _optional_float(row[5]),
        "memory_used_mib": _optional_float(row[6]),
        "memory_free_mib": _optional_float(row[7]),
        "utilization_gpu_pct": _optional_float(row[8]),
        "temperature_c": _optional_float(row[9]),
        "power_draw_w": _optional_float(row[10]),
        "power_limit_w": _optional_float(row[11]),
    }


def query_gpu_processes() -> list[dict[str, Any]] | None:
    command = [
        "nvidia-smi",
        "--query-compute-apps=pid,process_name,used_gpu_memory",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    if not isinstance(result.stdout, str):
        return None
    processes = []
    try:
        for row in csv.reader(
            result.stdout.splitlines(), skipinitialspace=True, strict=True
        ):
            if len(row) != 3:
                return None
            pid = _optional_int(row[0].strip())
            process_name = row[1].strip()
            used_gpu_memory_mib = _optional_float(row[2].strip())
            if (
                pid is None
                or pid <= 0
                or not process_name
                or used_gpu_memory_mib is None
                or not math.isfinite(used_gpu_memory_mib)
                or used_gpu_memory_mib < 0
            ):
                return None
            processes.append(
                {
                    "pid": pid,
                    "process_name": process_name,
                    "used_gpu_memory_mib": used_gpu_memory_mib,
                }
            )
    except csv.Error:
        return None
    return processes


def artifact_description(path: Path, project_root: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    try:
        display_path = str(resolved.relative_to(project_root.resolve()))
    except ValueError:
        display_path = str(resolved)
    return {
        "path": display_path,
        "sha256": sha256_file(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _command_output(command: list[str], allow_empty: bool = False) -> str:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {command!r}: {result.stderr}")
    output = result.stdout.strip()
    if not output and not allow_empty:
        raise RuntimeError(f"Command returned empty output: {command!r}")
    return output


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "unknown"


def _physical_core_count() -> int:
    physical_cores: set[tuple[str, str]] = set()
    physical_id = "0"
    core_id: str | None = None
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines() + [""]:
            if line.startswith("physical id"):
                physical_id = line.split(":", 1)[1].strip()
            elif line.startswith("core id"):
                core_id = line.split(":", 1)[1].strip()
            elif not line and core_id is not None:
                physical_cores.add((physical_id, core_id))
                physical_id = "0"
                core_id = None
    except OSError:
        pass
    return len(physical_cores) or (os.cpu_count() or 1)


def _mem_available_bytes() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable not found in /proc/meminfo")


def _optional_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _optional_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None
