#!/usr/bin/env python3
"""Build a deterministic CPU/GPU correctness calibration manifest.

The manifest produced here is correctness evidence only.  It deliberately
contains no runtime measurements and makes no speedup claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from autosbd.records import RecordError, load_record


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_UPSTREAM_URL = "https://github.com/AMD-HPC/amd-sbd"
OFFICIAL_UPSTREAM_COMMIT = "729cfa3a5011fb805eb9e686a7711f6919836dcb"
EXPECTED_BUILD_SHA256 = {
    "cpu": "190525bd05ff0b453e02e1762f7f221bac3e5da713e5d1d2999def3b0290ef07",
    "gpu": "8f1481b6bcb4ddf3326453fd3a7c03dc36e29034629f46c5e982a4c17e43bc07",
}
SOLVER_IDENTITY_KEYS = (
    "method",
    "iteration",
    "block",
    "tolerance",
    "max_time",
    "bit_length",
    "shuffle",
    "carryover_ratio",
    "rdm",
    "adet_comm_size",
    "bdet_comm_size",
    "task_comm_size",
)
RUN_ARTIFACT_NAMES = ("stdout", "stderr", "resources")
MAXIMUM_FINAL_RESIDUAL = 1.0e-8
ENERGY_RELATIVE_TOLERANCE = 1.0e-10
DENSITY_MAX_ABS_TOLERANCE = 1.0e-10
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class CalibrationError(RuntimeError):
    """Raised when records cannot establish the required correctness evidence."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CalibrationError(f"cannot hash evidence file {path}: {exc}") from exc
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _resolve_evidence_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise CalibrationError(f"{label} path must be a nonempty string")
    path = Path(value)
    if not path.is_absolute():
        path = REPOSITORY_ROOT / path
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CalibrationError(f"cannot resolve {label} path {path}: {exc}") from exc
    if not resolved.is_file():
        raise CalibrationError(f"{label} is not a regular file: {resolved}")
    return resolved


def _verified_description(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise CalibrationError(f"{label} description must be an object")
    expected_sha256 = value.get("sha256")
    expected_size = value.get("size_bytes")
    if not isinstance(expected_sha256, str) or not SHA256_RE.fullmatch(
        expected_sha256
    ):
        raise CalibrationError(f"{label} has an invalid SHA-256")
    if (
        isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or expected_size < 0
    ):
        raise CalibrationError(f"{label} has an invalid size_bytes")
    path = _resolve_evidence_path(value.get("path"), label)
    observed_size = path.stat().st_size
    if observed_size != expected_size:
        raise CalibrationError(
            f"{label} size mismatch: recorded {expected_size}, observed {observed_size}"
        )
    observed_sha256 = _sha256_file(path)
    if observed_sha256 != expected_sha256:
        raise CalibrationError(
            f"{label} SHA-256 mismatch: recorded {expected_sha256}, "
            f"observed {observed_sha256}"
        )
    return {
        "path": _display_path(path),
        "sha256": observed_sha256,
        "size_bytes": observed_size,
    }


def _record_description(path: Path) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise CalibrationError(f"record is not a regular file: {resolved}")
    return {
        "path": _display_path(resolved),
        "sha256": _sha256_file(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalibrationError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise CalibrationError(f"{label} must be a finite number") from exc
    if not math.isfinite(result):
        raise CalibrationError(f"{label} must be a finite number")
    return result


def _exact_solver(record: Mapping[str, Any], label: str) -> dict[str, object]:
    identity = record.get("logical_identity")
    solver = identity.get("solver") if isinstance(identity, Mapping) else None
    if not isinstance(solver, Mapping):
        raise CalibrationError(f"{label} has no logical solver identity")
    if set(solver) != set(SOLVER_IDENTITY_KEYS):
        missing = sorted(set(SOLVER_IDENTITY_KEYS).difference(solver))
        extra = sorted(set(solver).difference(SOLVER_IDENTITY_KEYS))
        raise CalibrationError(
            f"{label} solver identity keys differ; missing={missing}, extra={extra}"
        )
    return {key: solver[key] for key in SOLVER_IDENTITY_KEYS}


def _solver_group_key(solver: Mapping[str, object]) -> str:
    """Return a stable key that distinguishes exact solver configurations."""

    return json.dumps(
        {key: solver[key] for key in SOLVER_IDENTITY_KEYS},
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _validate_input_integrity(
    record: Mapping[str, Any], label: str
) -> list[dict[str, object]]:
    integrity = record.get("input_integrity")
    if not isinstance(integrity, Mapping):
        raise CalibrationError(f"{label} has no input_integrity object")
    if integrity.get("unchanged_before_launch") is not True:
        raise CalibrationError(f"{label} input changed before launch")
    if integrity.get("unchanged_after_run") is not True:
        raise CalibrationError(f"{label} input changed during execution")
    if integrity.get("rehash_error") is not None:
        raise CalibrationError(f"{label} input rehash reported an error")

    initial = integrity.get("initial")
    before = integrity.get("before_launch")
    after = integrity.get("after_run")
    if not isinstance(initial, list) or not initial:
        raise CalibrationError(f"{label} initial input description is missing")
    if initial != before or initial != after or initial != record.get("input_files"):
        raise CalibrationError(f"{label} input descriptions are not byte-identical")

    verified: list[dict[str, object]] = []
    for index, description in enumerate(initial):
        item_label = f"{label} input[{index}]"
        verified_item = _verified_description(description, item_label)
        role = description.get("role") if isinstance(description, Mapping) else None
        if not isinstance(role, str) or not role:
            raise CalibrationError(f"{item_label} role must be a nonempty string")
        verified_item["role"] = role
        verified.append(verified_item)
    return verified


def _validate_run_artifacts(
    record: Mapping[str, Any], label: str
) -> dict[str, dict[str, object]]:
    artifacts = record.get("run_artifacts")
    if not isinstance(artifacts, Mapping):
        raise CalibrationError(f"{label} has no run_artifacts object")
    verified = {
        name: _verified_description(artifacts.get(name), f"{label} {name}")
        for name in RUN_ARTIFACT_NAMES
    }
    if record.get("stdout_log") != artifacts["stdout"].get("path"):
        raise CalibrationError(f"{label} stdout path disagrees with run_artifacts")
    if record.get("stderr_log") != artifacts["stderr"].get("path"):
        raise CalibrationError(f"{label} stderr path disagrees with run_artifacts")
    monitoring = record.get("resource_monitoring")
    if not isinstance(monitoring, Mapping) or monitoring.get(
        "resource_log"
    ) != artifacts["resources"].get("path"):
        raise CalibrationError(f"{label} resource path disagrees with run_artifacts")
    return verified


def _validate_build_artifact(
    record: Mapping[str, Any], backend: str, label: str
) -> dict[str, object]:
    expected_sha256 = EXPECTED_BUILD_SHA256[backend]
    artifact = _verified_description(record.get("build_artifact"), f"{label} build")
    if artifact["sha256"] != expected_sha256:
        raise CalibrationError(
            f"{label} build SHA-256 is not the exact expected {backend} artifact"
        )
    identity = record.get("logical_identity")
    candidate = identity.get("candidate") if isinstance(identity, Mapping) else None
    if not isinstance(candidate, Mapping):
        raise CalibrationError(f"{label} has no logical candidate identity")
    if candidate.get("backend") != backend:
        raise CalibrationError(f"{label} logical candidate backend mismatch")
    if candidate.get("artifact_sha256") != expected_sha256:
        raise CalibrationError(f"{label} logical candidate artifact hash mismatch")
    if candidate.get("build_id") != record.get("build_id"):
        raise CalibrationError(f"{label} logical candidate build_id mismatch")
    return artifact


def _validate_gpu_evidence(record: Mapping[str, Any], label: str) -> None:
    environment = record.get("environment_overrides")
    if not isinstance(environment, Mapping):
        raise CalibrationError(f"{label} has no environment overrides")
    if environment.get("OMP_TARGET_OFFLOAD") != "MANDATORY":
        raise CalibrationError(f"{label} did not require mandatory GPU offload")
    visible_device = environment.get("CUDA_VISIBLE_DEVICES")
    if not isinstance(visible_device, str) or not visible_device.strip():
        raise CalibrationError(f"{label} has no explicit CUDA device assignment")

    preflight = record.get("preflight")
    gpu = preflight.get("gpu") if isinstance(preflight, Mapping) else None
    if not isinstance(gpu, Mapping):
        raise CalibrationError(f"{label} has no GPU preflight description")
    gpu_index = gpu.get("index")
    if isinstance(gpu_index, bool) or not isinstance(gpu_index, int):
        raise CalibrationError(f"{label} has no numeric GPU index")
    if visible_device.strip() != str(gpu_index):
        raise CalibrationError(
            f"{label} CUDA device disagrees with preflight GPU index"
        )
    if preflight.get("gpu_process_query_ok") is not True:
        raise CalibrationError(f"{label} GPU process preflight was incomplete")
    if preflight.get("gpu_idle") is not True:
        raise CalibrationError(f"{label} GPU was not idle at preflight")

    monitoring = record.get("resource_monitoring")
    if not isinstance(monitoring, Mapping):
        raise CalibrationError(f"{label} has no GPU monitoring evidence")
    if monitoring.get("host_complete") is not True:
        raise CalibrationError(f"{label} host monitoring was incomplete")
    if monitoring.get("gpu_complete") is not True:
        raise CalibrationError(f"{label} GPU monitoring was incomplete")
    if monitoring.get("gpu_process_observed") is not True:
        raise CalibrationError(f"{label} solver process was not observed on the GPU")
    samples = monitoring.get("samples")
    if isinstance(samples, bool) or not isinstance(samples, int) or samples <= 0:
        raise CalibrationError(f"{label} has no resource-monitor samples")
    peak_gpu_memory = _finite_number(
        record.get("peak_gpu_memory_mb"), f"{label} peak GPU memory"
    )
    if peak_gpu_memory <= 0:
        raise CalibrationError(f"{label} has no positive GPU allocation evidence")

    output = record.get("upstream_output")
    if not isinstance(output, Mapping) or output.get(
        "device_assignment_seen"
    ) is not True:
        raise CalibrationError(
            f"{label} solver output has no device assignment evidence"
        )


def _validate_node_preflight(record: Mapping[str, Any], label: str) -> None:
    preflight = record.get("preflight")
    gpu = preflight.get("gpu") if isinstance(preflight, Mapping) else None
    if not isinstance(gpu, Mapping):
        raise CalibrationError(f"{label} has no GPU preflight description")
    if preflight.get("gpu_process_query_ok") is not True:
        raise CalibrationError(f"{label} GPU process preflight was incomplete")
    if preflight.get("gpu_idle") is not True:
        raise CalibrationError(f"{label} GPU was not idle at preflight")


def _validate_record_evidence(
    record: Mapping[str, Any], path: Path
) -> dict[str, Any]:
    label = f"record {path.name}"
    if record.get("schema_version") not in {2, 3}:
        raise CalibrationError(f"{label} must use schema_version 2 or 3")
    backend = record.get("backend")
    if backend not in EXPECTED_BUILD_SHA256:
        raise CalibrationError(f"{label} backend must be exactly cpu or gpu")
    if record.get("upstream_url") != OFFICIAL_UPSTREAM_URL:
        raise CalibrationError(f"{label} upstream URL is not official AMD-HPC/amd-sbd")
    if record.get("upstream_git_commit") != OFFICIAL_UPSTREAM_COMMIT:
        raise CalibrationError(f"{label} upstream commit mismatch")
    if record.get("official_upstream_primary") is not True:
        raise CalibrationError(
            f"{label} does not identify official upstream as primary"
        )
    if record.get("project_git_dirty") is not False:
        raise CalibrationError(f"{label} was produced from a dirty project worktree")
    if (
        record.get("status") != "success"
        or record.get("process_success") is not True
        or record.get("scientific_success") is not True
        or record.get("exit_code") != 0
        or record.get("timeout") is not False
        or record.get("oom") is not False
    ):
        raise CalibrationError(f"{label} is not a successful scientific run")
    if record.get("correct") is False:
        raise CalibrationError(f"{label} explicitly failed its reference check")
    protocol = record.get("protocol")
    if not isinstance(protocol, Mapping) or protocol.get("purpose") != "correctness":
        raise CalibrationError(f"{label} is not a correctness-purpose record")
    if record.get("timing_eligible") is not False:
        raise CalibrationError(f"{label} is timing evidence, not calibration evidence")

    input_sha256 = record.get("input_sha256")
    if not isinstance(input_sha256, str) or not SHA256_RE.fullmatch(input_sha256):
        raise CalibrationError(f"{label} has an invalid input SHA-256")
    identity = record.get("logical_identity")
    if not isinstance(identity, Mapping):
        raise CalibrationError(f"{label} has no logical identity")
    if identity.get("input_sha256") != input_sha256:
        raise CalibrationError(f"{label} logical input hash mismatch")
    if identity.get("upstream_commit") != OFFICIAL_UPSTREAM_COMMIT:
        raise CalibrationError(f"{label} logical upstream commit mismatch")
    problem_instance = record.get("problem_instance")
    if not isinstance(problem_instance, str) or not problem_instance:
        raise CalibrationError(f"{label} has no problem_instance")

    output = record.get("upstream_output")
    if not isinstance(output, Mapping) or output.get("converged") is not True:
        raise CalibrationError(f"{label} did not converge")
    residual = _finite_number(output.get("final_residual"), f"{label} residual")
    if residual < 0 or residual > MAXIMUM_FINAL_RESIDUAL:
        raise CalibrationError(
            f"{label} residual {residual:.17g} exceeds {MAXIMUM_FINAL_RESIDUAL:.1e}"
        )
    energy = _finite_number(record.get("energy_or_eigenvalue"), f"{label} energy")
    parsed_energy = _finite_number(output.get("energy"), f"{label} parsed energy")
    if energy != parsed_energy:
        raise CalibrationError(f"{label} top-level and parsed energies disagree")
    iterations = record.get("iterations")
    if (
        isinstance(iterations, bool)
        or not isinstance(iterations, int)
        or iterations < 0
    ):
        raise CalibrationError(f"{label} iteration count is invalid")
    if output.get("iteration_records") != iterations:
        raise CalibrationError(
            f"{label} top-level and parsed iteration counts disagree"
        )
    density = output.get("density")
    if not isinstance(density, list) or not density:
        raise CalibrationError(f"{label} has no density vector")
    verified_density = [
        _finite_number(value, f"{label} density[{index}]")
        for index, value in enumerate(density)
    ]
    n_orbitals = record.get("n_orbitals")
    if (
        isinstance(n_orbitals, bool)
        or not isinstance(n_orbitals, int)
        or n_orbitals <= 0
    ):
        raise CalibrationError(f"{label} n_orbitals must be a positive integer")
    if len(verified_density) != n_orbitals:
        raise CalibrationError(
            f"{label} density length {len(verified_density)} does not match "
            f"n_orbitals {n_orbitals}"
        )

    _validate_node_preflight(record, label)
    if backend == "cpu":
        environment = record.get("environment_overrides")
        if not isinstance(environment, Mapping) or environment.get(
            "OMP_TARGET_OFFLOAD"
        ) != "DISABLED":
            raise CalibrationError(f"{label} is not an explicitly CPU-only run")
        monitoring = record.get("resource_monitoring")
        if not isinstance(monitoring, Mapping) or monitoring.get(
            "host_complete"
        ) is not True:
            raise CalibrationError(f"{label} host monitoring was incomplete")
    else:
        _validate_gpu_evidence(record, label)

    input_files = _validate_input_integrity(record, label)
    run_artifacts = _validate_run_artifacts(record, label)
    build_artifact = _validate_build_artifact(record, backend, label)
    record_before = _record_description(path)
    record_after = _record_description(path)
    if record_before != record_after:
        raise CalibrationError(f"{label} changed while it was being validated")

    return {
        "record": record,
        "record_artifact": record_after,
        "build_artifact": build_artifact,
        "run_artifacts": run_artifacts,
        "input_files": input_files,
        "solver": _exact_solver(record, label),
        "residual": residual,
        "energy": energy,
        "density": verified_density,
    }


def _load_and_validate(path: Path) -> dict[str, Any]:
    try:
        resolved = path.resolve(strict=True)
        before = _record_description(resolved)
        record = load_record(resolved)
        after = _record_description(resolved)
    except (OSError, json.JSONDecodeError, RecordError) as exc:
        raise CalibrationError(f"invalid record {path}: {exc}") from exc
    if before != after:
        raise CalibrationError(f"record changed while loading: {resolved}")
    return _validate_record_evidence(record, resolved)


def _same_workload_field(
    cpu: Mapping[str, Any], gpu: Mapping[str, Any], field: str, label: str
) -> object:
    cpu_value = cpu.get(field)
    gpu_value = gpu.get(field)
    if cpu_value != gpu_value:
        raise CalibrationError(f"{label} CPU/GPU {field} mismatch")
    return cpu_value


def _relative_difference(first: float, second: float) -> float:
    scale = max(abs(first), abs(second))
    return 0.0 if scale == 0.0 else abs(first - second) / scale


def _pair_manifest_entry(
    key: tuple[str, ...], pair: Mapping[str, Mapping[str, Any]]
) -> dict[str, object]:
    cpu_evidence = pair["cpu"]
    gpu_evidence = pair["gpu"]
    cpu = cpu_evidence["record"]
    gpu = gpu_evidence["record"]
    record_schema_version = cpu["schema_version"]
    if gpu["schema_version"] != record_schema_version:
        raise CalibrationError("CPU/GPU record schema_version mismatch")
    if record_schema_version == 2:
        problem_instance, input_sha256, solver_group_key = key
    else:
        family_id, problem_instance, input_sha256, solver_group_key = key
    label = f"{problem_instance}/{input_sha256}"

    if cpu_evidence["solver"] != gpu_evidence["solver"]:
        raise CalibrationError(f"{label} CPU/GPU solver identity mismatch")
    if _solver_group_key(cpu_evidence["solver"]) != solver_group_key:
        raise CalibrationError(f"{label} internal solver grouping mismatch")
    n_configurations = _same_workload_field(
        cpu, gpu, "n_configurations", label
    )
    iterations = _same_workload_field(cpu, gpu, "iterations", label)
    if cpu_evidence["input_files"] != gpu_evidence["input_files"]:
        raise CalibrationError(f"{label} CPU/GPU input-file descriptions mismatch")

    workload_fields = (
        "problem_family",
        "n_orbitals",
        "n_spin_orbitals",
        "n_alpha_strings",
        "n_beta_strings",
        "estimated_work",
        "estimated_cache_bytes",
    )
    if record_schema_version == 3:
        workload_fields += ("family_id", "molecule", "basis")
    workload = {
        field: _same_workload_field(cpu, gpu, field, label)
        for field in workload_fields
    }
    workload.update(
        {
            "name": _same_workload_field(
                cpu["logical_identity"], gpu["logical_identity"], "workload", label
            ),
            "problem_instance": problem_instance,
            "n_configurations": n_configurations,
        }
    )
    if not isinstance(workload["name"], str) or not workload["name"]:
        raise CalibrationError(f"{label} has no workload name")
    if (
        not isinstance(workload["problem_family"], str)
        or not workload["problem_family"]
    ):
        raise CalibrationError(f"{label} has no problem family")

    energy_relative_error = _relative_difference(
        cpu_evidence["energy"], gpu_evidence["energy"]
    )
    if energy_relative_error > ENERGY_RELATIVE_TOLERANCE:
        raise CalibrationError(
            f"{label} CPU/GPU energy relative error {energy_relative_error:.17g} "
            f"exceeds {ENERGY_RELATIVE_TOLERANCE:.1e}"
        )
    cpu_density = cpu_evidence["density"]
    gpu_density = gpu_evidence["density"]
    if len(cpu_density) != len(gpu_density):
        raise CalibrationError(f"{label} CPU/GPU density-vector length mismatch")
    density_max_abs_difference = max(
        abs(cpu_value - gpu_value)
        for cpu_value, gpu_value in zip(cpu_density, gpu_density, strict=True)
    )
    if density_max_abs_difference > DENSITY_MAX_ABS_TOLERANCE:
        raise CalibrationError(
            f"{label} CPU/GPU density max absolute difference "
            f"{density_max_abs_difference:.17g} exceeds "
            f"{DENSITY_MAX_ABS_TOLERANCE:.1e}"
        )

    records: dict[str, object] = {}
    for backend, evidence in (("cpu", cpu_evidence), ("gpu", gpu_evidence)):
        records[backend] = {
            "trial_id": evidence["record"]["trial_id"],
            **evidence["record_artifact"],
            "run_artifacts": evidence["run_artifacts"],
        }

    entry = {
        "problem_instance": problem_instance,
        "input_sha256": input_sha256,
        "solver": cpu_evidence["solver"],
        "reference_value": cpu_evidence["energy"],
        "workload": workload,
        "records": records,
        "comparison": {
            "converged": True,
            "iteration_count": iterations,
            "cpu_final_residual": cpu_evidence["residual"],
            "gpu_final_residual": gpu_evidence["residual"],
            "cpu_energy": cpu_evidence["energy"],
            "gpu_energy": gpu_evidence["energy"],
            "energy_relative_error": energy_relative_error,
            "density_length": len(cpu_density),
            "density_max_abs_difference": density_max_abs_difference,
        },
    }
    if record_schema_version == 3:
        entry.update(
            {
                "family_id": family_id,
                "molecule": workload["molecule"],
                "basis": workload["basis"],
            }
        )
    return entry


def make_calibration_manifest(record_paths: Sequence[Path]) -> dict[str, object]:
    """Validate explicit record paths and return deterministic manifest data."""

    if not record_paths:
        raise CalibrationError("at least one explicit record path is required")
    pairs: dict[tuple[str, ...], dict[str, Mapping[str, Any]]] = {}
    build_artifacts: dict[str, dict[str, object]] = {}
    seen_paths: set[Path] = set()
    manifest_schema_version: int | None = None

    for supplied_path in record_paths:
        path = Path(supplied_path).resolve(strict=True)
        if path in seen_paths:
            raise CalibrationError(f"duplicate record path: {path}")
        seen_paths.add(path)
        evidence = _load_and_validate(path)
        record = evidence["record"]
        record_schema_version = record["schema_version"]
        if manifest_schema_version is None:
            manifest_schema_version = record_schema_version
        elif record_schema_version != manifest_schema_version:
            raise CalibrationError(
                "cannot mix schema_version 2 and 3 records in one manifest"
            )
        solver_group_key = _solver_group_key(evidence["solver"])
        if record_schema_version == 3:
            key = (
                record["family_id"],
                record["problem_instance"],
                record["input_sha256"],
                solver_group_key,
            )
        else:
            key = (
                record["problem_instance"],
                record["input_sha256"],
                solver_group_key,
            )
        backend = record["backend"]
        pair = pairs.setdefault(key, {})
        if backend in pair:
            raise CalibrationError(
                f"duplicate {backend} record for {'/'.join(key)}"
            )
        pair[backend] = evidence
        previous_build = build_artifacts.get(backend)
        if previous_build is not None and previous_build != evidence["build_artifact"]:
            raise CalibrationError(
                f"{backend} records do not use one identical build artifact"
            )
        build_artifacts[backend] = evidence["build_artifact"]

    for key, pair in sorted(pairs.items()):
        missing = sorted({"cpu", "gpu"}.difference(pair))
        if missing:
            raise CalibrationError(
                f"missing {', '.join(missing)} record for {'/'.join(key)}"
            )
    if set(build_artifacts) != {"cpu", "gpu"}:
        raise CalibrationError("manifest requires both exact CPU and GPU artifacts")

    candidate_artifacts = [
        {"backend": backend, **build_artifacts[backend]}
        for backend in ("cpu", "gpu")
    ]
    validated_inputs = [
        _pair_manifest_entry(key, pairs[key]) for key in sorted(pairs)
    ]
    assert manifest_schema_version is not None
    return {
        "schema_version": manifest_schema_version,
        "passed": True,
        "upstream_url": OFFICIAL_UPSTREAM_URL,
        "upstream_git_commit": OFFICIAL_UPSTREAM_COMMIT,
        "upstream": {
            "url": OFFICIAL_UPSTREAM_URL,
            "commit": OFFICIAL_UPSTREAM_COMMIT,
        },
        "candidate_artifacts": candidate_artifacts,
        "criteria": {
            "maximum_final_residual": MAXIMUM_FINAL_RESIDUAL,
            "energy_relative_tolerance": ENERGY_RELATIVE_TOLERANCE,
            "density_max_abs_tolerance": DENSITY_MAX_ABS_TOLERANCE,
            "exact_iteration_count_required": True,
            "input_integrity_required": True,
            "project_git_clean_required": True,
            "run_artifact_hashes_verified": list(RUN_ARTIFACT_NAMES),
            "gpu_monitoring_and_device_assignment_required": True,
        },
        "scope": {
            "correctness_only": True,
            "timing_evidence_used": False,
        },
        "validated_inputs": validated_inputs,
    }


def _atomic_write_changed(path: Path, payload: bytes) -> bool:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.exists() and path.read_bytes() == payload:
            return False
    except OSError as exc:
        raise CalibrationError(f"cannot inspect output {path}: {exc}") from exc

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        directory_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            directory_flags |= os.O_DIRECTORY
        directory_descriptor = os.open(path.parent, directory_flags)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        raise CalibrationError(f"cannot atomically write output {path}: {exc}") from exc
    finally:
        temporary_path.unlink(missing_ok=True)
    return True


def build_calibration_manifest(
    record_paths: Sequence[Path], output: Path
) -> tuple[dict[str, object], bool]:
    """Validate records and atomically write a changed-only manifest."""

    manifest = make_calibration_manifest(record_paths)
    payload = (
        json.dumps(manifest, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    changed = _atomic_write_changed(Path(output), payload)
    return manifest, changed


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "records",
        nargs="+",
        type=Path,
        help="explicit schema-v2 CPU/GPU record JSON paths",
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(argv)
    try:
        manifest, changed = build_calibration_manifest(
            arguments.records, arguments.output
        )
    except (CalibrationError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    outcome = {
        "output": _display_path(arguments.output),
        "status": "written" if changed else "unchanged",
        "validated_inputs": len(manifest["validated_inputs"]),
    }
    print(json.dumps(outcome, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
