"""Tests for deterministic, fail-closed timing-result aggregation."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from autosbd.analysis import (
    AnalysisError,
    aggregate_and_write,
    aggregate_records,
    linear_percentile,
    summarize_values,
)
from autosbd.records import make_trial_id, write_immutable_json


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_SCRIPT = REPOSITORY_ROOT / "scripts" / "analyze_results.py"


def make_timing_record(
    serial: int,
    *,
    wall_time_s: float = 2.0,
    solver_time_s: float = 1.0,
    backend: str = "cpu",
    candidate_name: str | None = None,
    cpu_threads: int | None = None,
    phase: str = "measured",
    timing_eligible: bool = True,
    problem_instance: str = "fixture-workload",
    input_sha256: str = "c" * 64,
) -> dict[str, object]:
    """Return one complete schema-v2 timing record."""

    if candidate_name is None:
        candidate_name = f"fixture-{backend}"
    if cpu_threads is None:
        cpu_threads = 1 if backend == "gpu" else 16
    candidate_identity = {
        "name": candidate_name,
        "backend": backend,
        "threads": cpu_threads,
        "mpi_ranks": 1,
        "build_id": f"{candidate_name}-build",
        "artifact_sha256": "d" * 64,
        "compiler_flags": ["-O3"],
        "compiler_identity": "fixture compiler",
    }
    logical_identity = {
        "serial": serial,
        "input_sha256": input_sha256,
        "problem_instance": problem_instance,
        "phase": phase,
        "candidate": candidate_identity,
    }
    logical_trial_id = make_trial_id(logical_identity)
    trial_id = make_trial_id(
        {"logical_trial_id": logical_trial_id, "attempt_index": 0}
    )
    features = {
        "combined_input_sha256": input_sha256,
        "n_configurations": 4,
        "method0_work_proxy": 100,
        "fcidump": {"n_orbitals": 2},
        "alpha": {"count": 2},
        "beta": {"count": 2},
    }
    gpu_monitoring = backend == "gpu"
    return {
        "schema_version": 2,
        "trial_id": trial_id,
        "logical_trial_id": logical_trial_id,
        "logical_identity": logical_identity,
        "attempt_index": 0,
        "timestamp_utc": f"2026-08-01T00:00:{serial:02d}.000000Z",
        "finished_timestamp_utc": f"2026-08-01T00:00:{serial:02d}.500000Z",
        "hostname": "analysis-test-host",
        "project_git_commit": "a" * 40,
        "upstream_url": "https://github.com/AMD-HPC/amd-sbd",
        "upstream_git_commit": "729cfa3a5011fb805eb9e686a7711f6919836dcb",
        "build_id": f"{candidate_name}-build",
        "compiler_and_flags": "fixture compiler; -O3",
        "gpu_name": "fixture-gpu" if backend == "gpu" else None,
        "driver_version": "fixture-driver" if backend == "gpu" else None,
        "cuda_toolkit_version": "fixture-cuda" if backend == "gpu" else None,
        "cpu_model": "fixture-cpu",
        "physical_cores": 16,
        "problem_family": "analysis-fixture",
        "problem_instance": problem_instance,
        "input_sha256": input_sha256,
        "seed": 1729,
        "n_orbitals": 2,
        "n_spin_orbitals": 4,
        "n_alpha_strings": 2,
        "n_beta_strings": 2,
        "n_configurations": 4,
        "estimated_work": 100,
        "estimated_cache_bytes": 128,
        "backend": backend,
        "cpu_threads": cpu_threads,
        "mpi_ranks": 1,
        "bit_length": 20,
        "shuffle": False,
        "cache_mode": "fixture-cache",
        "decomposition": {
            "adet_comm_size": 1,
            "bdet_comm_size": 1,
            "task_comm_size": 1,
            "h_comm_size": 1,
        },
        "warmup_or_measured": phase,
        "repetition": 0,
        "command": ["fixture-sbd", "--serial", str(serial)],
        "wall_time_s": wall_time_s,
        "initialization_time_s": 0.1,
        "solver_time_s": solver_time_s,
        "matvec_time_s": None,
        "transfer_time_s": None,
        "iterations": 2,
        "energy_or_eigenvalue": -1.0,
        "reference_value": -1.0,
        "relative_error": 0.0,
        "correct": True,
        "peak_host_rss_mb": 12.0,
        "peak_gpu_memory_mb": 64.0 if backend == "gpu" else None,
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
        "timing_eligible": timing_eligible,
        "input_files": [],
        "environment_overrides": {},
        "preflight": {},
        "resource_monitoring": {
            "host_complete": True,
            "gpu_complete": True if gpu_monitoring else None,
            "gpu_process_observed": True if gpu_monitoring else None,
            "samples": 2,
        },
        "project_git_dirty": False,
        "input_integrity": {
            "unchanged_before_launch": True,
            "unchanged_after_run": True,
            "rehash_error": None,
        },
        "validation_evidence": {
            "required": True,
            "valid": True,
            "sha256": "e" * 64,
            "errors": [],
        },
        "protocol": {
            "purpose": "pilot",
            "warmups": 1,
            "repetitions": 1,
            "correctness_validated": True,
        },
        "input_features": features,
    }


def make_family_timing_record(
    serial: int,
    *,
    family_id: str,
    molecule: str,
    basis: str,
    wall_time_s: float = 2.0,
    backend: str = "cpu",
    candidate_name: str | None = None,
    problem_instance: str = "shared-workload",
    input_sha256: str = "c" * 64,
) -> dict[str, object]:
    """Return one complete family-aware schema-v3 timing record."""

    record = make_timing_record(
        serial,
        wall_time_s=wall_time_s,
        backend=backend,
        candidate_name=candidate_name,
        problem_instance=problem_instance,
        input_sha256=input_sha256,
    )
    logical_identity = dict(record["logical_identity"])
    logical_identity.update(
        {
            "schema_version": 3,
            "sweep_name": record["problem_family"],
            "workload": problem_instance,
            "family_id": family_id,
            "molecule": molecule,
            "basis": basis,
        }
    )
    logical_trial_id = make_trial_id(logical_identity)
    trial_id = make_trial_id(
        {"logical_trial_id": logical_trial_id, "attempt_index": 0}
    )
    record.update(
        {
            "schema_version": 3,
            "logical_identity": logical_identity,
            "logical_trial_id": logical_trial_id,
            "trial_id": trial_id,
            "family_id": family_id,
            "molecule": molecule,
            "basis": basis,
        }
    )
    return record


class AnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name)

    def write_record(self, record: dict[str, object]) -> Path:
        path = self.root / f"{record['trial_id']}.json"
        write_immutable_json(path, record)
        return path

    def test_invalid_record_and_invalid_timing_shape_fail_closed(self) -> None:
        malformed = self.root / f"{'0' * 64}.json"
        malformed.write_text("{not-json}\n", encoding="utf-8")
        with self.assertRaisesRegex(AnalysisError, "cannot load record"):
            aggregate_records([malformed])

        missing_features = make_timing_record(1)
        missing_features.pop("input_features")
        missing_features_path = self.write_record(missing_features)
        with self.assertRaisesRegex(AnalysisError, "lacks input_features"):
            aggregate_records([missing_features_path])

        legacy = make_timing_record(2)
        legacy["schema_version"] = 1
        legacy.pop("logical_identity")
        legacy["trial_id"] = "f" * 64
        legacy_path = self.write_record(legacy)
        with self.assertRaisesRegex(AnalysisError, "requires schema_version 2"):
            aggregate_records([legacy_path])

    def test_classifies_warmup_ineligible_and_failed_gates(self) -> None:
        warmup = make_timing_record(
            1, phase="warmup", timing_eligible=False
        )
        ineligible = make_timing_record(2, timing_eligible=False)
        invalid_manifest = make_timing_record(3)
        invalid_manifest["validation_evidence"] = {
            "required": True,
            "valid": False,
            "sha256": "e" * 64,
            "errors": ["fixture"],
        }
        incomplete_gpu = make_timing_record(4, backend="gpu")
        incomplete_gpu["resource_monitoring"] = {
            "host_complete": True,
            "gpu_complete": True,
            "gpu_process_observed": False,
            "samples": 2,
        }
        included = make_timing_record(5)
        paths = [
            self.write_record(record)
            for record in (
                warmup,
                ineligible,
                invalid_manifest,
                incomplete_gpu,
                included,
            )
        ]

        analysis = aggregate_records(paths)

        self.assertEqual(
            analysis["record_counts"],
            {"input": 5, "included": 1, "excluded": 4},
        )
        reasons = analysis["exclusion_reason_counts"]
        self.assertEqual(reasons["warmup"], 1)
        self.assertEqual(reasons["timing_ineligible"], 2)
        self.assertEqual(reasons["validation_manifest_invalid"], 1)
        self.assertEqual(reasons["gpu_process_not_observed"], 1)
        self.assertEqual(len(analysis["rows"]), 5)
        included_rows = [row for row in analysis["rows"] if row["included"]]
        self.assertEqual([row["trial_id"] for row in included_rows], [included["trial_id"]])

    def test_n1_n3_statistics_comparisons_and_oracle(self) -> None:
        records = [
            make_timing_record(
                1,
                wall_time_s=9.0,
                solver_time_s=4.5,
                candidate_name="amd-cpu",
            ),
            make_timing_record(
                2,
                wall_time_s=1.0,
                solver_time_s=0.5,
                candidate_name="amd-cpu",
            ),
            make_timing_record(
                3,
                wall_time_s=2.0,
                solver_time_s=1.0,
                candidate_name="amd-cpu",
            ),
            make_timing_record(
                4,
                wall_time_s=1.5,
                solver_time_s=0.75,
                backend="gpu",
                candidate_name="amd-gpu",
            ),
        ]
        paths = [self.write_record(record) for record in records]

        analysis = aggregate_records(list(reversed(paths)))
        groups = {
            group["candidate"]["name"]: group
            for group in analysis["candidate_groups"]
        }
        cpu_wall = groups["amd-cpu"]["wall_time_s"]
        self.assertEqual(
            cpu_wall,
            {
                "count": 3,
                "minimum": 1.0,
                "q1": 1.5,
                "median": 2.0,
                "q3": 5.5,
                "iqr": 4.0,
                "maximum": 9.0,
            },
        )
        gpu_wall = groups["amd-gpu"]["wall_time_s"]
        self.assertEqual(gpu_wall["count"], 1)
        self.assertEqual(gpu_wall["q1"], 1.5)
        self.assertEqual(gpu_wall["median"], 1.5)
        self.assertEqual(gpu_wall["q3"], 1.5)
        self.assertEqual(gpu_wall["iqr"], 0.0)

        workload = analysis["workloads"][0]
        self.assertEqual(workload["oracle"]["minimum"], 1.5)
        self.assertEqual(
            [candidate["name"] for candidate in workload["oracle"]["candidates"]],
            ["amd-gpu"],
        )
        comparison = workload["candidate_comparisons"][0]
        self.assertAlmostEqual(
            comparison["median_wall_ratio_left_over_right"], 2.0 / 1.5
        )
        self.assertEqual(
            analysis["statistics"]["percentile_method"],
            "linear interpolation on ascending values at zero-based position (n - 1) * p",
        )
        self.assertEqual(analysis["schema_version"], 1)
        self.assertNotIn("record_schema_version", analysis)
        self.assertNotIn("family_id", analysis["rows"][0])

    def test_schema3_multifamily_identity_is_preserved_without_collapsing(self) -> None:
        records = [
            make_family_timing_record(
                10,
                family_id="family-a",
                molecule="Molecule A",
                basis="basis-a",
                wall_time_s=4.0,
                candidate_name="amd-cpu",
            ),
            make_family_timing_record(
                11,
                family_id="family-a",
                molecule="Molecule A",
                basis="basis-a",
                wall_time_s=2.0,
                backend="gpu",
                candidate_name="amd-gpu",
            ),
            make_family_timing_record(
                12,
                family_id="family-b",
                molecule="Molecule B",
                basis="basis-b",
                wall_time_s=1.0,
                candidate_name="amd-cpu",
            ),
            make_family_timing_record(
                13,
                family_id="family-b",
                molecule="Molecule B",
                basis="basis-b",
                wall_time_s=3.0,
                backend="gpu",
                candidate_name="amd-gpu",
            ),
        ]
        paths = [self.write_record(record) for record in records]

        analysis = aggregate_records(list(reversed(paths)))

        self.assertEqual(analysis["schema_version"], 2)
        self.assertEqual(analysis["record_schema_version"], 3)
        self.assertEqual(analysis["record_counts"], {"input": 4, "included": 4, "excluded": 0})
        self.assertEqual(
            analysis["grouping_fields"],
            [
                "family_id",
                "molecule",
                "basis",
                "problem_instance",
                "input_sha256",
                "candidate",
            ],
        )
        self.assertEqual(
            [family["family_id"] for family in analysis["families"]],
            ["family-a", "family-b"],
        )
        self.assertEqual(len(analysis["candidate_groups"]), 4)
        self.assertEqual(len(analysis["workloads"]), 2)
        self.assertEqual(
            {workload["family_id"] for workload in analysis["workloads"]},
            {"family-a", "family-b"},
        )
        self.assertTrue(
            all(
                set(("family_id", "molecule", "basis")).issubset(row)
                for row in analysis["rows"]
            )
        )
        self.assertTrue(
            all(
                set(("build_id", "artifact_sha256", "mpi_ranks")).issubset(
                    group["candidate"]
                )
                for group in analysis["candidate_groups"]
            )
        )
        oracle_by_family = {
            workload["family_id"]: workload["oracle"]["candidates"][0]["name"]
            for workload in analysis["workloads"]
        }
        self.assertEqual(
            oracle_by_family,
            {"family-a": "amd-gpu", "family-b": "amd-cpu"},
        )

    def test_schema3_outputs_are_deterministic_and_family_aware(self) -> None:
        paths = [
            self.write_record(
                make_family_timing_record(
                    20,
                    family_id="family-a",
                    molecule="Molecule A",
                    basis="basis-a",
                )
            ),
            self.write_record(
                make_family_timing_record(
                    21,
                    family_id="family-b",
                    molecule="Molecule B",
                    basis="basis-b",
                )
            ),
        ]
        output_json = self.root / "family-aware.json"
        output_csv = self.root / "family-aware.csv"

        first, first_status = aggregate_and_write(
            list(reversed(paths)), output_json, output_csv
        )
        json_bytes = output_json.read_bytes()
        csv_bytes = output_csv.read_bytes()
        second, second_status = aggregate_and_write(paths, output_json, output_csv)

        self.assertEqual(second, first)
        self.assertTrue(first_status["json_changed"])
        self.assertTrue(first_status["csv_changed"])
        self.assertFalse(second_status["json_changed"])
        self.assertFalse(second_status["csv_changed"])
        self.assertEqual(output_json.read_bytes(), json_bytes)
        self.assertEqual(output_csv.read_bytes(), csv_bytes)
        with output_csv.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(
            [rows[0]["family_id"], rows[0]["molecule"], rows[0]["basis"]],
            ["family-a", "Molecule A", "basis-a"],
        )

    def test_rejects_mixed_record_schemas_and_inconsistent_family_contracts(self) -> None:
        legacy = self.write_record(make_timing_record(30))
        family = self.write_record(
            make_family_timing_record(
                31,
                family_id="family-a",
                molecule="Molecule A",
                basis="basis-a",
            )
        )
        with self.assertRaisesRegex(AnalysisError, "homogeneous record schema"):
            aggregate_records([legacy, family])

        inconsistent_metadata = [
            self.write_record(
                make_family_timing_record(
                    32,
                    family_id="shared-family",
                    molecule="Molecule A",
                    basis="basis-a",
                    problem_instance="workload-a",
                )
            ),
            self.write_record(
                make_family_timing_record(
                    33,
                    family_id="shared-family",
                    molecule="Molecule B",
                    basis="basis-a",
                    problem_instance="workload-b",
                )
            ),
        ]
        with self.assertRaisesRegex(AnalysisError, "inconsistent molecule/basis"):
            aggregate_records(inconsistent_metadata)

        inconsistent_hash = [
            self.write_record(
                make_family_timing_record(
                    34,
                    family_id="hash-family",
                    molecule="Molecule H",
                    basis="basis-h",
                    input_sha256="1" * 64,
                )
            ),
            self.write_record(
                make_family_timing_record(
                    35,
                    family_id="hash-family",
                    molecule="Molecule H",
                    basis="basis-h",
                    input_sha256="2" * 64,
                )
            ),
        ]
        with self.assertRaisesRegex(AnalysisError, "inconsistent metadata or input hashes"):
            aggregate_records(inconsistent_hash)


    def test_percentile_validation_and_direct_summary(self) -> None:
        self.assertEqual(linear_percentile([7.0], 0.25), 7.0)
        self.assertEqual(summarize_values([9.0, 1.0, 2.0])["q3"], 5.5)
        with self.assertRaises(AnalysisError):
            linear_percentile([], 0.5)
        with self.assertRaises(AnalysisError):
            linear_percentile([1.0], 2.0)
        with self.assertRaises(AnalysisError):
            summarize_values([True])
        with self.assertRaises(AnalysisError):
            summarize_values([float("inf")])

    def test_rejects_duplicate_explicit_path(self) -> None:
        path = self.write_record(make_timing_record(1))
        with self.assertRaisesRegex(AnalysisError, "duplicate record path"):
            aggregate_records([path, path])
        with self.assertRaisesRegex(AnalysisError, "at least one"):
            aggregate_records([])

    def test_outputs_are_deterministic_atomic_and_changed_only(self) -> None:
        paths = [
            self.write_record(make_timing_record(1, wall_time_s=2.0)),
            self.write_record(
                make_timing_record(
                    2,
                    wall_time_s=1.0,
                    backend="gpu",
                )
            ),
        ]
        output_json = self.root / "nested" / "analysis.json"
        output_csv = self.root / "nested" / "analysis.csv"

        first_analysis, first_status = aggregate_and_write(
            list(reversed(paths)), output_json, output_csv
        )
        self.assertTrue(first_status["json_changed"])
        self.assertTrue(first_status["csv_changed"])
        json_bytes = output_json.read_bytes()
        csv_bytes = output_csv.read_bytes()
        os.utime(output_json, ns=(1_700_000_000_000_000_000,) * 2)
        os.utime(output_csv, ns=(1_700_000_000_000_000_000,) * 2)
        json_mtime = output_json.stat().st_mtime_ns
        csv_mtime = output_csv.stat().st_mtime_ns

        second_analysis, second_status = aggregate_and_write(
            paths, output_json, output_csv
        )
        self.assertEqual(second_analysis, first_analysis)
        self.assertFalse(second_status["json_changed"])
        self.assertFalse(second_status["csv_changed"])
        self.assertEqual(output_json.read_bytes(), json_bytes)
        self.assertEqual(output_csv.read_bytes(), csv_bytes)
        self.assertEqual(output_json.stat().st_mtime_ns, json_mtime)
        self.assertEqual(output_csv.stat().st_mtime_ns, csv_mtime)
        self.assertEqual(json.loads(json_bytes)["record_counts"]["included"], 2)
        with output_csv.open(newline="", encoding="utf-8") as stream:
            csv_rows = list(csv.DictReader(stream))
        self.assertEqual(len(csv_rows), 2)
        self.assertTrue(all(row["input_features_json"] for row in csv_rows))

    def test_cli_reports_counts_and_output_status(self) -> None:
        included = self.write_record(make_timing_record(1))
        warmup = self.write_record(
            make_timing_record(2, phase="warmup", timing_eligible=False)
        )
        output_json = self.root / "cli.json"
        output_csv = self.root / "cli.csv"
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(REPOSITORY_ROOT / "src")
        completed = subprocess.run(
            [
                sys.executable,
                str(ANALYSIS_SCRIPT),
                str(included),
                str(warmup),
                "--output-json",
                str(output_json),
                "--output-csv",
                str(output_csv),
            ],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        status = json.loads(completed.stdout)
        self.assertEqual(status["status"], "ok")
        self.assertEqual(status["input_records"], 2)
        self.assertEqual(status["included_records"], 1)
        self.assertEqual(status["excluded_records"], 1)
        self.assertTrue(output_json.is_file())
        self.assertTrue(output_csv.is_file())


if __name__ == "__main__":
    unittest.main()
