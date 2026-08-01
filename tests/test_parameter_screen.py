"""Tests for strict, deterministic Phase C parameter-screen analysis."""

from __future__ import annotations

from copy import deepcopy
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from autosbd.analysis import aggregate_records
from autosbd.parameter_screen import (
    EXPECTED_CANDIDATES,
    EXPECTED_WORKLOADS,
    ParameterScreenError,
    analyze_and_write_parameter_screen,
    build_parameter_screen_analysis,
    write_parameter_screen_outputs,
)
from autosbd.records import make_trial_id, write_immutable_json


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "analyze_parameter_screen.py"


def _record(
    serial: int,
    workload: dict[str, object],
    candidate: dict[str, object],
    phase: str,
) -> dict[str, object]:
    repetition = 0
    candidate_identity = {
        "name": candidate["name"],
        "backend": candidate["backend"],
        "threads": candidate["cpu_threads"],
        "mpi_ranks": 1,
        "build_id": f"{candidate['name']}-build",
        "artifact_sha256": ("a" if candidate["backend"] == "cpu" else "b") * 64,
        "compiler_flags": ["-O3"],
        "compiler_identity": "fixture nvc++ 26.5",
    }
    input_sha = f"{EXPECTED_WORKLOADS.index(workload) + 1:064x}"
    validation_sha = "c" * 64
    command = [
        "diag",
        "--bit_length",
        str(candidate["bit_length"]),
        "--shuffle",
        str(int(candidate["shuffle"])),
    ]
    logical_identity = {
        "schema_version": 3,
        "sweep_name": "phasec-amd-parameter-screen-pilot-v1",
        "workload": workload["problem_instance"],
        "family_id": workload["family_id"],
        "molecule": workload["molecule"],
        "basis": workload["basis"],
        "input_sha256": input_sha,
        "phase": phase,
        "repetition": repetition,
        "candidate": candidate_identity,
        "command": command,
        "environment_overrides": {},
        "harness_sha256": "d" * 64,
        "machine_fingerprint": "e" * 64,
        "project_commit": "f" * 40,
        "project_dirty": False,
        "protocol": {
            "purpose": "pilot",
            "warmups": 1,
            "repetitions": 1,
            "seed": 1729,
            "timeout_s": 300.0,
            "correctness_validated": True,
            "validation_manifest_sha256": validation_sha,
        },
        "reference_source": "fixture",
        "reference_value": -1.0,
        "solver": {
            "method": 0,
            "iteration": 6,
            "block": 10,
            "tolerance": 1.0e-8,
            "max_time": 240.0,
            "bit_length": candidate["bit_length"],
            "shuffle": int(candidate["shuffle"]),
            "carryover_ratio": 0.5,
            "rdm": 0,
            "adet_comm_size": 1,
            "bdet_comm_size": 1,
            "task_comm_size": 1,
        },
        "upstream_commit": "729cfa3a5011fb805eb9e686a7711f6919836dcb",
    }
    logical_trial_id = make_trial_id(logical_identity)
    trial_id = make_trial_id({"logical_trial_id": logical_trial_id, "attempt_index": 0})
    time_base = 1.0 + EXPECTED_WORKLOADS.index(workload) + EXPECTED_CANDIDATES.index(candidate) / 10
    features = {
        "combined_input_sha256": input_sha,
        "n_configurations": workload["n_configurations"],
        "method0_work_proxy": int(workload["n_configurations"]) * 10,
        "fcidump": {"n_orbitals": 18},
        "alpha": {"count": 32},
        "beta": {"count": 32},
    }
    measured = phase == "measured"
    return {
        "schema_version": 3,
        "trial_id": trial_id,
        "logical_trial_id": logical_trial_id,
        "logical_identity": logical_identity,
        "attempt_index": 0,
        "timestamp_utc": f"2026-08-01T00:{serial // 60:02d}:{serial % 60:02d}.000000Z",
        "finished_timestamp_utc": f"2026-08-01T00:{serial // 60:02d}:{serial % 60:02d}.500000Z",
        "hostname": "fixture-host",
        "project_git_commit": "f" * 40,
        "upstream_url": "https://github.com/AMD-HPC/amd-sbd",
        "upstream_git_commit": "729cfa3a5011fb805eb9e686a7711f6919836dcb",
        "build_id": candidate_identity["build_id"],
        "compiler_and_flags": "fixture nvc++ 26.5; -O3",
        "gpu_name": "L4" if candidate["backend"] == "gpu" else None,
        "driver_version": "fixture" if candidate["backend"] == "gpu" else None,
        "cuda_toolkit_version": "fixture" if candidate["backend"] == "gpu" else None,
        "cpu_model": "fixture CPU",
        "physical_cores": 16,
        "problem_family": "phasec-amd-parameter-screen-pilot-v1",
        "problem_instance": workload["problem_instance"],
        "family_id": workload["family_id"],
        "molecule": workload["molecule"],
        "basis": workload["basis"],
        "input_sha256": input_sha,
        "seed": 1729,
        "n_orbitals": 18,
        "n_spin_orbitals": 36,
        "n_alpha_strings": 32,
        "n_beta_strings": 32,
        "n_configurations": workload["n_configurations"],
        "estimated_work": int(workload["n_configurations"]) * 10,
        "estimated_cache_bytes": int(workload["n_configurations"]) * 16,
        "backend": candidate["backend"],
        "cpu_threads": candidate["cpu_threads"],
        "mpi_ranks": 1,
        "bit_length": candidate["bit_length"],
        "shuffle": candidate["shuffle"],
        "cache_mode": "fixture",
        "decomposition": {"adet_comm_size": 1, "bdet_comm_size": 1, "task_comm_size": 1, "h_comm_size": 1},
        "warmup_or_measured": phase,
        "repetition": repetition,
        "command": command,
        "wall_time_s": time_base,
        "initialization_time_s": 0.1,
        "solver_time_s": time_base / 2,
        "matvec_time_s": None,
        "transfer_time_s": None,
        "iterations": 6,
        "energy_or_eigenvalue": -1.0,
        "reference_value": -1.0,
        "relative_error": 0.0,
        "correct": True,
        "peak_host_rss_mb": 10.0,
        "peak_gpu_memory_mb": 64.0 if candidate["backend"] == "gpu" else None,
        "timeout": False,
        "oom": False,
        "exit_code": 0,
        "stdout_log": f"logs/{trial_id}.stdout.log",
        "stderr_log": f"logs/{trial_id}.stderr.log",
        "notes": [],
        "status": "success",
        "failure_kind": None,
        "parse_error": None,
        "skip_reason": None,
        "process_success": True,
        "scientific_success": True,
        "timing_eligible": measured,
        "input_files": [],
        "environment_overrides": {},
        "preflight": {},
        "resource_monitoring": {
            "host_complete": True,
            "gpu_complete": True if candidate["backend"] == "gpu" else None,
            "gpu_process_observed": True if candidate["backend"] == "gpu" else None,
            "samples": 2,
        },
        "project_git_dirty": False,
        "input_integrity": {"unchanged_before_launch": True, "unchanged_after_run": True, "rehash_error": None},
        "validation_evidence": {"required": True, "valid": True, "sha256": validation_sha, "errors": []},
        "protocol": {"purpose": "pilot", "warmups": 1, "repetitions": 1, "timeout_s": 300.0, "correctness_validated": True},
        "input_features": features,
    }


class ParameterScreenTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.raw = self.root / "raw"
        self.raw.mkdir()
        self.aggregate_path = self.root / "aggregate.json"
        self.records: list[dict[str, object]] = []
        serial = 0
        for workload in EXPECTED_WORKLOADS:
            for candidate in EXPECTED_CANDIDATES:
                for phase in ("warmup", "measured"):
                    record = _record(serial, workload, candidate, phase)
                    serial += 1
                    self.records.append(record)
                    write_immutable_json(self.raw / f"{record['trial_id']}.json", record)
        aggregate = aggregate_records(sorted(self.raw.glob("*.json")))
        self.aggregate_path.write_text(
            json.dumps(aggregate, allow_nan=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def test_complete_grid_pairs_summaries_and_no_pruning(self) -> None:
        result = build_parameter_screen_analysis(
            self.aggregate_path, self.raw, repository_root=self.root
        )
        self.assertEqual(len(result["measurements"]), 72)
        self.assertEqual(len(result["paired_effects"]), 108)
        self.assertEqual(
            {row["factor"] for row in result["paired_effects"]},
            {"backend", "bit_length", "shuffle"},
        )
        self.assertEqual(len(result["summaries"]["per_candidate"]), 8)
        self.assertEqual(len(result["summaries"]["per_family_candidate"]), 24)
        self.assertEqual(len(result["summaries"]["per_size_candidate"]), 48)
        self.assertEqual(len(result["summaries"]["per_family_factor"]), 9)
        self.assertFalse(result["analysis_boundary"]["configuration_pruning_performed"])
        self.assertFalse(result["analysis_boundary"]["missing_measurements_imputed"])
        first = result["paired_effects"][0]
        self.assertEqual(first["factor"], "backend")
        self.assertEqual(first["left_level"], "cpu")
        self.assertEqual(first["right_level"], "gpu")
        self.assertEqual(first["wall_winner"], "left")

    def test_atomic_json_csv_are_deterministic_and_complete(self) -> None:
        result = build_parameter_screen_analysis(
            self.aggregate_path, self.raw, repository_root=self.root
        )
        output_json = self.root / "out/parameter.json"
        output_csv = self.root / "out/parameter.csv"
        first = write_parameter_screen_outputs(result, output_json, output_csv)
        first_bytes = (output_json.read_bytes(), output_csv.read_bytes())
        second = write_parameter_screen_outputs(result, output_json, output_csv)
        self.assertTrue(first["json_changed"])
        self.assertTrue(first["csv_changed"])
        self.assertFalse(second["json_changed"])
        self.assertFalse(second["csv_changed"])
        self.assertEqual(first_bytes, (output_json.read_bytes(), output_csv.read_bytes()))
        with output_csv.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 272)
        self.assertEqual(
            {row["row_type"] for row in rows},
            {
                "measurement",
                "paired_effect",
                "candidate_summary",
                "family_candidate_summary",
                "size_candidate_summary",
                "factor_summary",
                "family_factor_summary",
            },
        )

        tampered = deepcopy(result)
        tampered["paired_effects"][0]["wall_winner"] = "right"
        with self.assertRaisesRegex(ParameterScreenError, "recomputation"):
            write_parameter_screen_outputs(
                tampered,
                self.root / "out/tampered.json",
                self.root / "out/tampered.csv",
            )

    def test_tampered_aggregate_and_incomplete_geometry_fail_closed(self) -> None:
        aggregate = json.loads(self.aggregate_path.read_text(encoding="utf-8"))
        aggregate["rows"][0]["times_s"]["wall"] += 1.0
        tampered = self.root / "tampered.json"
        tampered.write_text(json.dumps(aggregate), encoding="utf-8")
        with self.assertRaisesRegex(ParameterScreenError, "recomputation"):
            build_parameter_screen_analysis(tampered, self.raw, repository_root=self.root)

        malformed_records = [deepcopy(record) for record in self.records]
        malformed_records[-1]["repetition"] = 1
        # Exercise the geometry validator directly without weakening file sealing.
        from autosbd.parameter_screen import _validate_and_extract_measurements

        with self.assertRaisesRegex(ParameterScreenError, "geometry"):
            _validate_and_extract_measurements(malformed_records)

    def test_parameter_identity_and_correctness_gate_fail_closed(self) -> None:
        from autosbd.parameter_screen import _validate_and_extract_measurements

        wrong_parameter = [deepcopy(record) for record in self.records]
        wrong_parameter[-1]["bit_length"] = 64
        with self.assertRaisesRegex(ParameterScreenError, "bit_length"):
            _validate_and_extract_measurements(wrong_parameter)

        not_validated = [deepcopy(record) for record in self.records]
        not_validated[-1]["protocol"]["correctness_validated"] = False
        with self.assertRaisesRegex(ParameterScreenError, "predates correctness"):
            _validate_and_extract_measurements(not_validated)

    def test_cli_failure_is_nonzero_and_success_writes_outputs(self) -> None:
        output_json = self.root / "cli.json"
        output_csv = self.root / "cli.csv"
        command = [
            sys.executable,
            str(SCRIPT),
            "--repository-root",
            str(self.root),
            "--aggregate",
            str(self.aggregate_path),
            "--raw-dir",
            str(self.raw),
            "--output-json",
            str(output_json),
            "--output-csv",
            str(output_csv),
        ]
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(output_json.is_file())
        self.assertTrue(output_csv.is_file())

        failed = subprocess.run(
            [*command[: command.index("--aggregate") + 1], str(self.root / "missing.json"), *command[command.index("--raw-dir") :]],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(failed.returncode, 2)
        self.assertIn("parameter-screen analysis failed", failed.stderr)


if __name__ == "__main__":
    unittest.main()
