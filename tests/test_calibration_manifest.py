"""Tests for the deterministic CPU/GPU calibration-manifest builder."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from autosbd.records import make_trial_id, write_immutable_json


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "build_calibration_manifest.py"
SPEC = importlib.util.spec_from_file_location(
    "build_calibration_manifest_script", SCRIPT_PATH
)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import machinery guard
    raise RuntimeError(f"cannot load {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SOLVER = {
    "method": 0,
    "iteration": 6,
    "block": 10,
    "tolerance": 1.0e-8,
    "max_time": 240,
    "bit_length": 20,
    "shuffle": 0,
    "carryover_ratio": 0.5,
    "rdm": 0,
    "adet_comm_size": 1,
    "bdet_comm_size": 1,
    "task_comm_size": 1,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _description(path: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


class CalibrationManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name)
        self.records = self.root / "records"
        self.logs = self.root / "logs"
        self.inputs = self.root / "inputs"
        self.build = self.root / "build"
        for directory in (self.records, self.logs, self.inputs, self.build):
            directory.mkdir()

        self.executables = {
            "cpu": self.build / "diag_cpu",
            "gpu": self.build / "diag_gpu",
        }
        self.executables["cpu"].write_bytes(b"synthetic exact CPU executable\n")
        self.executables["gpu"].write_bytes(b"synthetic exact GPU executable\n")
        expected_builds = {
            backend: _sha256(path) for backend, path in self.executables.items()
        }
        patcher = mock.patch.object(MODULE, "EXPECTED_BUILD_SHA256", expected_builds)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _input_description(self, instance: str) -> tuple[str, list[dict[str, object]]]:
        path = self.inputs / f"{instance}.dat"
        if not path.exists():
            path.write_bytes(f"authentic-input-fixture:{instance}\n".encode())
        description = {"role": "fcidump", **_description(path)}
        return _sha256(path), [description]

    def _write_record(
        self,
        backend: str,
        instance: str,
        *,
        input_sha256: str | None = None,
        input_files: list[dict[str, object]] | None = None,
        attempt_index: int = 0,
        solver: dict[str, object] | None = None,
        n_configurations: int = 16,
        n_orbitals: object = 2,
        iterations: int = 7,
        energy: float = -10.0,
        density: list[float] | None = None,
        residual: float = 1.0e-9,
        converged: bool = True,
        dirty: bool = False,
        gpu_complete: bool = True,
        gpu_process_observed: bool = True,
        device_assignment_seen: bool = True,
        visible_device: str | None = "0",
        gpu_idle: bool = True,
        protocol_purpose: str = "correctness",
        timing_eligible: bool = False,
        upstream_url: str | None = None,
        schema_version: int = 2,
        family_id: str = "fixture-family",
        molecule: str = "Fixture",
        basis: str = "fixture-basis",
    ) -> Path:
        if input_sha256 is None or input_files is None:
            input_sha256, input_files = self._input_description(instance)
        solver = dict(SOLVER if solver is None else solver)
        density = list([0.25, 1.75] if density is None else density)

        artifacts: dict[str, dict[str, object]] = {}
        for name in MODULE.RUN_ARTIFACT_NAMES:
            artifact_path = (
                self.logs / f"{instance}.{backend}.{attempt_index}.{name}.evidence"
            )
            artifact_path.write_bytes(
                f"{instance}:{backend}:{attempt_index}:{name}\n".encode()
            )
            artifacts[name] = _description(artifact_path)

        build_artifact = _description(self.executables[backend])
        build_id = f"exact-{backend}-{build_artifact['sha256'][:12]}"
        candidate = {
            "name": f"fixture-{backend}",
            "backend": backend,
            "threads": 1,
            "mpi_ranks": 1,
            "build_id": build_id,
            "artifact_sha256": build_artifact["sha256"],
            "compiler_identity": "synthetic NVHPC fixture",
            "compiler_flags": ["-mp=gpu" if backend == "gpu" else "-mp"],
        }
        logical_identity = {
            "schema_version": schema_version,
            "sweep_name": (
                "synthetic-amd-calibration"
                if schema_version == 3
                else "synthetic-calibration"
            ),
            "workload": instance,
            "input_sha256": input_sha256,
            "candidate": candidate,
            "solver": solver,
            "protocol": {
                "purpose": protocol_purpose,
                "warmups": 0,
                "repetitions": 1,
                "seed": 1729,
                "timeout_s": 300,
                "correctness_validated": False,
                "validation_manifest_sha256": None,
            },
            "phase": "measured",
            "repetition": 0,
            "reference_value": None,
            "reference_source": None,
            "command": [str(self.executables[backend]), "--fixture", instance],
            "environment_overrides": {},
            "project_commit": "a" * 40,
            "project_dirty": dirty,
            "harness_sha256": "b" * 64,
            "upstream_commit": MODULE.OFFICIAL_UPSTREAM_COMMIT,
            "machine_fingerprint": "c" * 64,
        }
        if schema_version == 3:
            logical_identity.update(
                {
                    "family_id": family_id,
                    "molecule": molecule,
                    "basis": basis,
                }
            )
        logical_trial_id = make_trial_id(logical_identity)
        trial_id = make_trial_id(
            {
                "logical_trial_id": logical_trial_id,
                "attempt_index": attempt_index,
            }
        )

        environment = {
            "OMP_TARGET_OFFLOAD": "DISABLED" if backend == "cpu" else "MANDATORY",
            "OMP_NUM_THREADS": "1",
        }
        if backend == "gpu" and visible_device is not None:
            environment["CUDA_VISIBLE_DEVICES"] = visible_device
        preflight = {
            "gpu": {"index": 0, "name": "NVIDIA L4"},
            "gpu_process_query_ok": True,
            "gpu_idle": gpu_idle,
            "input_unchanged_before_launch": True,
        }
        monitoring = {
            "resource_log": artifacts["resources"]["path"],
            "host_complete": True,
            "gpu_complete": gpu_complete if backend == "gpu" else None,
            "gpu_process_observed": (
                gpu_process_observed if backend == "gpu" else None
            ),
            "samples": 3,
            "term_sent": False,
            "kill_sent": False,
        }
        input_integrity = {
            "initial": input_files,
            "before_launch": input_files,
            "after_run": input_files,
            "unchanged_before_launch": True,
            "unchanged_after_run": True,
            "rehash_error": None,
        }
        record: dict[str, object] = {
            "schema_version": schema_version,
            "trial_id": trial_id,
            "logical_trial_id": logical_trial_id,
            "logical_identity": logical_identity,
            "attempt_index": attempt_index,
            "timestamp_utc": "2026-08-01T00:00:00.000000Z",
            "finished_timestamp_utc": "2026-08-01T00:00:01.000000Z",
            "hostname": "synthetic-host",
            "project_git_commit": "a" * 40,
            "upstream_url": upstream_url or MODULE.OFFICIAL_UPSTREAM_URL,
            "upstream_git_commit": MODULE.OFFICIAL_UPSTREAM_COMMIT,
            "build_id": build_id,
            "compiler_and_flags": "synthetic NVHPC fixture",
            "gpu_name": "NVIDIA L4" if backend == "gpu" else None,
            "driver_version": "fixture" if backend == "gpu" else None,
            "cuda_toolkit_version": "fixture" if backend == "gpu" else None,
            "cpu_model": "fixture CPU",
            "physical_cores": 16,
            "problem_family": "synthetic-amd-calibration",
            "problem_instance": instance,
            "input_sha256": input_sha256,
            "seed": 1729,
            "n_orbitals": n_orbitals,
            "n_spin_orbitals": 4,
            "n_alpha_strings": 4,
            "n_beta_strings": 4,
            "n_configurations": n_configurations,
            "estimated_work": 256,
            "estimated_cache_bytes": 1024,
            "backend": backend,
            "cpu_threads": 1,
            "mpi_ranks": 1,
            "bit_length": solver["bit_length"],
            "shuffle": bool(solver["shuffle"]),
            "cache_mode": "persistent-determinant-cache",
            "decomposition": {
                "adet_comm_size": 1,
                "bdet_comm_size": 1,
                "task_comm_size": 1,
                "h_comm_size": 1,
            },
            "warmup_or_measured": "correctness",
            "repetition": 0,
            "command": logical_identity["command"],
            # Deliberately non-evidentiary diagnostic timings.  The manifest
            # tests assert these do not leak into correctness evidence.
            "wall_time_s": 99.0,
            "initialization_time_s": 11.0,
            "solver_time_s": 88.0,
            "matvec_time_s": None,
            "transfer_time_s": None,
            "iterations": iterations,
            "energy_or_eigenvalue": energy,
            "reference_value": None,
            "relative_error": None,
            "correct": None,
            "peak_host_rss_mb": 64.0,
            "peak_gpu_memory_mb": 32.0 if backend == "gpu" else None,
            "timeout": False,
            "oom": False,
            "exit_code": 0,
            "stdout_log": artifacts["stdout"]["path"],
            "stderr_log": artifacts["stderr"]["path"],
            "notes": [],
            "status": "success",
            "failure_kind": None,
            "parse_error": None,
            "skip_reason": None,
            "process_success": True,
            "scientific_success": True,
            "timing_eligible": timing_eligible,
            "input_files": input_files,
            "environment_overrides": environment,
            "preflight": preflight,
            "resource_monitoring": monitoring,
            "official_upstream_primary": True,
            "project_git_dirty": dirty,
            "harness_sha256": "b" * 64,
            "machine_fingerprint": "c" * 64,
            "compiler_identity": "synthetic NVHPC fixture",
            "build_artifact": build_artifact,
            "run_artifacts": artifacts,
            "protocol": {
                "purpose": protocol_purpose,
                "warmups": 0,
                "repetitions": 1,
                "timeout_s": 300,
                "correctness_validated": False,
            },
            "reference_source": None,
            "validation_evidence": {
                "required": False,
                "valid": False,
                "path": None,
                "sha256": None,
                "errors": ["no validation manifest configured"],
            },
            "input_integrity": input_integrity,
            "input_features": {"fixture": True},
            "source_memory_estimate": {"fixture": True},
            "upstream_output": {
                "converged": converged,
                "energy": energy,
                "final_residual": residual,
                "iteration_records": iterations,
                "density": density,
                "device_assignment_seen": (
                    device_assignment_seen if backend == "gpu" else False
                ),
            },
            "launch_error": None,
            "termination_signal": None,
        }
        if schema_version == 3:
            record.update(
                {
                    "family_id": family_id,
                    "molecule": molecule,
                    "basis": basis,
                }
            )
        record_path = self.records / f"{trial_id}.json"
        write_immutable_json(record_path, record)
        return record_path

    def _write_pair(
        self,
        instance: str,
        *,
        cpu: dict[str, object] | None = None,
        gpu: dict[str, object] | None = None,
    ) -> tuple[Path, Path]:
        input_sha256, input_files = self._input_description(instance)
        shared = {"input_sha256": input_sha256, "input_files": input_files}
        return (
            self._write_record("cpu", instance, **shared, **(cpu or {})),
            self._write_record("gpu", instance, **shared, **(gpu or {})),
        )

    def test_builds_deterministic_correctness_only_manifest(self) -> None:
        z_cpu, z_gpu = self._write_pair(
            "z-input", gpu={"energy": -10.0 * (1.0 + 1.0e-12)}
        )
        a_cpu, a_gpu = self._write_pair(
            "a-input", gpu={"density": [0.25 + 1.0e-12, 1.75]}
        )
        output = self.root / "calibration.json"
        paths = [z_gpu, a_cpu, z_cpu, a_gpu]

        manifest, changed = MODULE.build_calibration_manifest(paths, output)

        self.assertTrue(changed)
        self.assertTrue(manifest["passed"])
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(
            [entry["problem_instance"] for entry in manifest["validated_inputs"]],
            ["a-input", "z-input"],
        )
        self.assertEqual(
            [item["backend"] for item in manifest["candidate_artifacts"]],
            ["cpu", "gpu"],
        )
        self.assertEqual(
            manifest["validated_inputs"][0]["solver"], SOLVER
        )
        self.assertEqual(
            manifest["validated_inputs"][0]["reference_value"], -10.0
        )
        self.assertTrue(manifest["scope"]["correctness_only"])
        self.assertFalse(manifest["scope"]["timing_evidence_used"])
        serialized = json.dumps(manifest, sort_keys=True)
        for forbidden in ("wall_time", "solver_time", "speedup"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(json.loads(output.read_text()), manifest)

        before = (output.stat().st_ino, output.stat().st_mtime_ns, output.read_bytes())
        second_manifest, second_changed = MODULE.build_calibration_manifest(
            list(reversed(paths)), output
        )
        after = (output.stat().st_ino, output.stat().st_mtime_ns, output.read_bytes())
        self.assertFalse(second_changed)
        self.assertEqual(second_manifest, manifest)
        self.assertEqual(after, before)

    def test_schema_v3_manifest_binds_family_metadata(self) -> None:
        cpu_path, gpu_path = self._write_pair(
            "v3-input",
            cpu={
                "schema_version": 3,
                "family_id": "n2",
                "molecule": "N2",
                "basis": "6-31G",
            },
            gpu={
                "schema_version": 3,
                "family_id": "n2",
                "molecule": "N2",
                "basis": "6-31G",
            },
        )
        manifest = MODULE.make_calibration_manifest([gpu_path, cpu_path])

        self.assertEqual(manifest["schema_version"], 3)
        entry = manifest["validated_inputs"][0]
        self.assertEqual(entry["family_id"], "n2")
        self.assertEqual(entry["molecule"], "N2")
        self.assertEqual(entry["basis"], "6-31G")
        self.assertEqual(entry["workload"]["family_id"], "n2")

    def test_same_input_supports_multiple_exact_solver_pairs(self) -> None:
        input_sha256, input_files = self._input_description("parameter-grid")
        shared = {
            "input_sha256": input_sha256,
            "input_files": input_files,
            "schema_version": 3,
            "family_id": "n2",
            "molecule": "N2",
            "basis": "6-31G",
        }
        solver_48 = {**SOLVER, "bit_length": 48}
        paths = [
            self._write_record("cpu", "parameter-grid", **shared),
            self._write_record("gpu", "parameter-grid", **shared),
            self._write_record(
                "cpu",
                "parameter-grid",
                **shared,
                solver=solver_48,
                attempt_index=1,
            ),
            self._write_record(
                "gpu",
                "parameter-grid",
                **shared,
                solver=solver_48,
                attempt_index=1,
            ),
        ]

        manifest = MODULE.make_calibration_manifest(list(reversed(paths)))

        self.assertEqual(len(manifest["validated_inputs"]), 2)
        self.assertEqual(
            [entry["solver"]["bit_length"] for entry in manifest["validated_inputs"]],
            [20, 48],
        )
        self.assertEqual(
            {entry["input_sha256"] for entry in manifest["validated_inputs"]},
            {input_sha256},
        )

    def test_schema_v3_pairing_distinguishes_same_label_across_families(self) -> None:
        n2_cpu, n2_gpu = self._write_pair(
            "shared-instance-label",
            cpu={
                "schema_version": 3,
                "family_id": "n2",
                "molecule": "N2",
                "basis": "6-31G",
            },
            gpu={
                "schema_version": 3,
                "family_id": "n2",
                "molecule": "N2",
                "basis": "6-31G",
            },
        )
        h2o_cpu, h2o_gpu = self._write_pair(
            "shared-instance-label",
            cpu={
                "schema_version": 3,
                "family_id": "h2o",
                "molecule": "H2O",
                "basis": "cc-pVDZ",
            },
            gpu={
                "schema_version": 3,
                "family_id": "h2o",
                "molecule": "H2O",
                "basis": "cc-pVDZ",
            },
        )

        manifest = MODULE.make_calibration_manifest(
            [n2_cpu, h2o_gpu, n2_gpu, h2o_cpu]
        )

        self.assertEqual(manifest["schema_version"], 3)
        self.assertEqual(len(manifest["validated_inputs"]), 2)
        self.assertEqual(
            [entry["family_id"] for entry in manifest["validated_inputs"]],
            ["h2o", "n2"],
        )
        self.assertEqual(
            {
                entry["problem_instance"]
                for entry in manifest["validated_inputs"]
            },
            {"shared-instance-label"},
        )

    def test_refuses_mixed_schema_or_v3_metadata_mismatch(self) -> None:
        cpu_path, gpu_path = self._write_pair(
            "mixed-schema",
            cpu={"schema_version": 2},
            gpu={"schema_version": 3},
        )
        with self.assertRaisesRegex(MODULE.CalibrationError, "cannot mix"):
            MODULE.make_calibration_manifest([cpu_path, gpu_path])

        cpu_path, gpu_path = self._write_pair(
            "metadata-mismatch",
            cpu={"schema_version": 3, "molecule": "N2"},
            gpu={"schema_version": 3, "molecule": "Other"},
        )
        with self.assertRaisesRegex(MODULE.CalibrationError, "molecule mismatch"):
            MODULE.make_calibration_manifest([cpu_path, gpu_path])

    def test_refuses_missing_and_duplicate_pairs(self) -> None:
        cpu_path, gpu_path = self._write_pair("pairing")
        with self.assertRaisesRegex(MODULE.CalibrationError, "missing gpu"):
            MODULE.make_calibration_manifest([cpu_path])

        input_sha256, input_files = self._input_description("pairing")
        duplicate_cpu = self._write_record(
            "cpu",
            "pairing",
            input_sha256=input_sha256,
            input_files=input_files,
            attempt_index=1,
        )
        with self.assertRaisesRegex(MODULE.CalibrationError, "duplicate cpu"):
            MODULE.make_calibration_manifest([cpu_path, gpu_path, duplicate_cpu])
        with self.assertRaisesRegex(MODULE.CalibrationError, "duplicate record path"):
            MODULE.make_calibration_manifest([cpu_path, cpu_path])

    def test_refuses_dirty_records_and_tampered_artifacts(self) -> None:
        dirty_cpu, dirty_gpu = self._write_pair("dirty", cpu={"dirty": True})
        with self.assertRaisesRegex(MODULE.CalibrationError, "dirty project"):
            MODULE.make_calibration_manifest([dirty_cpu, dirty_gpu])

        cpu_path, gpu_path = self._write_pair("tampered-log")
        gpu_record = json.loads(gpu_path.read_text())
        Path(gpu_record["run_artifacts"]["stdout"]["path"]).write_bytes(b"tampered\n")
        with self.assertRaisesRegex(
            MODULE.CalibrationError, "(?:size|SHA-256) mismatch"
        ):
            MODULE.make_calibration_manifest([cpu_path, gpu_path])

        cpu_path, gpu_path = self._write_pair("tampered-build")
        self.executables["cpu"].write_bytes(b"tampered executable\n")
        with self.assertRaisesRegex(MODULE.CalibrationError, "build.*mismatch"):
            MODULE.make_calibration_manifest([cpu_path, gpu_path])

    def test_refuses_solver_configuration_and_iteration_mismatches(self) -> None:
        mismatches = (
            (
                "solver",
                {},
                {"solver": {**SOLVER, "block": 11}},
                "missing gpu record",
            ),
            ("config-count", {}, {"n_configurations": 25}, "n_configurations"),
            ("iterations", {}, {"iterations": 8}, "iterations mismatch"),
        )
        for instance, cpu_options, gpu_options, expected in mismatches:
            with self.subTest(instance=instance):
                cpu_path, gpu_path = self._write_pair(
                    instance, cpu=cpu_options, gpu=gpu_options
                )
                with self.assertRaisesRegex(MODULE.CalibrationError, expected):
                    MODULE.make_calibration_manifest([cpu_path, gpu_path])

    def test_refuses_convergence_residual_energy_and_density_failures(self) -> None:
        failures = (
            ("not-converged", {"converged": False}, "did not converge"),
            ("residual", {"residual": 2.0e-8}, "residual.*exceeds"),
            ("energy", {"energy": -9.0}, "energy relative error.*exceeds"),
            ("density", {"density": [0.5, 1.5]}, "density max absolute.*exceeds"),
        )
        for instance, gpu_options, expected in failures:
            with self.subTest(instance=instance):
                cpu_path, gpu_path = self._write_pair(instance, gpu=gpu_options)
                with self.assertRaisesRegex(MODULE.CalibrationError, expected):
                    MODULE.make_calibration_manifest([cpu_path, gpu_path])

    def test_refuses_density_length_or_invalid_orbital_count(self) -> None:
        failures = (
            (
                "cpu-density-length",
                {"density": [2.0]},
                {},
                "density length 1 does not match n_orbitals 2",
            ),
            (
                "gpu-density-length",
                {},
                {"density": [0.25, 0.75, 1.0]},
                "density length 3 does not match n_orbitals 2",
            ),
            (
                "zero-orbitals",
                {},
                {"n_orbitals": 0},
                "n_orbitals must be a positive integer",
            ),
            (
                "boolean-orbitals",
                {"n_orbitals": True},
                {},
                "n_orbitals must be a positive integer",
            ),
            (
                "noninteger-orbitals",
                {},
                {"n_orbitals": 2.0},
                "n_orbitals must be a positive integer",
            ),
        )
        for instance, cpu_options, gpu_options, expected in failures:
            with self.subTest(instance=instance):
                cpu_path, gpu_path = self._write_pair(
                    instance, cpu=cpu_options, gpu=gpu_options
                )
                with self.assertRaisesRegex(MODULE.CalibrationError, expected):
                    MODULE.make_calibration_manifest([cpu_path, gpu_path])

    def test_refuses_incomplete_gpu_monitoring_or_assignment(self) -> None:
        failures = (
            ("gpu-monitor", {"gpu_complete": False}, "GPU monitoring was incomplete"),
            (
                "gpu-process",
                {"gpu_process_observed": False},
                "solver process was not observed",
            ),
            (
                "gpu-assignment",
                {"device_assignment_seen": False},
                "no device assignment evidence",
            ),
            ("gpu-visible", {"visible_device": None}, "no explicit CUDA device"),
        )
        for instance, gpu_options, expected in failures:
            with self.subTest(instance=instance):
                cpu_path, gpu_path = self._write_pair(instance, gpu=gpu_options)
                with self.assertRaisesRegex(MODULE.CalibrationError, expected):
                    MODULE.make_calibration_manifest([cpu_path, gpu_path])

        cpu_path, gpu_path = self._write_pair(
            "cpu-preflight", cpu={"gpu_idle": False}
        )
        with self.assertRaisesRegex(MODULE.CalibrationError, "GPU was not idle"):
            MODULE.make_calibration_manifest([cpu_path, gpu_path])

    def test_refuses_timing_or_noncorrectness_records(self) -> None:
        cpu_path, gpu_path = self._write_pair(
            "pilot-purpose", cpu={"protocol_purpose": "pilot"}
        )
        with self.assertRaisesRegex(MODULE.CalibrationError, "correctness-purpose"):
            MODULE.make_calibration_manifest([cpu_path, gpu_path])

        cpu_path, gpu_path = self._write_pair(
            "timing-evidence", gpu={"timing_eligible": True}
        )
        with self.assertRaisesRegex(MODULE.CalibrationError, "timing evidence"):
            MODULE.make_calibration_manifest([cpu_path, gpu_path])

    def test_refuses_unofficial_upstream(self) -> None:
        cpu_path, gpu_path = self._write_pair(
            "unofficial",
            gpu={"upstream_url": "https://example.invalid/not-amd-sbd"},
        )
        with self.assertRaisesRegex(MODULE.CalibrationError, "upstream URL"):
            MODULE.make_calibration_manifest([cpu_path, gpu_path])


if __name__ == "__main__":
    unittest.main()
