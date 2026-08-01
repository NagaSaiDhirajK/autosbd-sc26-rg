"""Tests for deterministic identities and immutable Stage 2 records."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import tempfile
import unittest

from autosbd.records import (
    ClaimExistsError,
    RecordError,
    RecordExistsError,
    SCHEMA_VERSION,
    TrialClaim,
    canonical_json,
    load_record,
    make_trial_id,
    validate_record,
    write_immutable_json,
)


def make_valid_record(**overrides: object) -> dict[str, object]:
    """Return one complete schema-valid record suitable for record tests."""

    input_sha256 = "c" * 64
    logical_identity = {
        "schema_version": 3,
        "sweep_name": "mock",
        "workload": "fixture-success",
        "family_id": "fixture",
        "molecule": "Fixture",
        "basis": "fixture-basis",
        "backend": "mock",
        "build_id": "mock-build-v1",
        "input_sha256": input_sha256,
        "problem_instance": "fixture-success",
        "repetition": 0,
        "warmup_or_measured": "test",
    }
    logical_trial_id = make_trial_id(logical_identity)
    trial_id = make_trial_id(
        {"logical_trial_id": logical_trial_id, "attempt_index": 0}
    )
    record: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "trial_id": trial_id,
        "logical_trial_id": logical_trial_id,
        "logical_identity": logical_identity,
        "attempt_index": 0,
        "timestamp_utc": "2026-08-01T00:00:00.000000Z",
        "finished_timestamp_utc": "2026-08-01T00:00:00.100000Z",
        "hostname": "autosbd-test-host",
        "project_git_commit": "a" * 40,
        "upstream_url": "https://github.com/AMD-HPC/amd-sbd",
        "upstream_git_commit": "729cfa3a5011fb805eb9e686a7711f6919836dcb",
        "build_id": "mock-build-v1",
        "compiler_and_flags": "CPython mock fixture; no compiled solver",
        "gpu_name": None,
        "driver_version": None,
        "cuda_toolkit_version": None,
        "cpu_model": "test-cpu",
        "physical_cores": 1,
        "problem_family": "mock",
        "problem_instance": "fixture-success",
        "family_id": "fixture",
        "molecule": "Fixture",
        "basis": "fixture-basis",
        "input_sha256": input_sha256,
        "seed": 0,
        "n_orbitals": 36,
        "n_spin_orbitals": 72,
        "n_alpha_strings": 2,
        "n_beta_strings": 2,
        "n_configurations": 4,
        "estimated_work": 4.0,
        "estimated_cache_bytes": 128,
        "backend": "mock",
        "cpu_threads": 1,
        "mpi_ranks": 1,
        "bit_length": 20,
        "shuffle": False,
        "cache_mode": "off",
        "decomposition": {"adet_comm_size": 1, "bdet_comm_size": 1},
        "warmup_or_measured": "test",
        "repetition": 0,
        "command": ["python3", "tests/fixtures/mock_sbd.py", "success"],
        "wall_time_s": 0.1,
        "initialization_time_s": 0.0001,
        "solver_time_s": 0.02,
        "matvec_time_s": 0.005,
        "transfer_time_s": None,
        "iterations": 2,
        "energy_or_eigenvalue": -326.6982536731583,
        "reference_value": -326.6982536731583,
        "relative_error": 0.0,
        "correct": True,
        "peak_host_rss_mb": 12.0,
        "peak_gpu_memory_mb": None,
        "timeout": False,
        "oom": False,
        "exit_code": 0,
        "stdout_log": "logs/test.stdout.log",
        "stderr_log": "logs/test.stderr.log",
        "notes": [],
        "status": "success",
        "failure_kind": None,
        "parse_error": None,
        "skip_reason": None,
        "process_success": True,
        "scientific_success": True,
        "timing_eligible": False,
        "input_files": [
            {
                "path": "tests/fixtures/input.dat",
                "sha256": input_sha256,
                "size_bytes": 4,
            }
        ],
        "environment_overrides": {"OMP_NUM_THREADS": "1"},
        "preflight": {"gpu_required": False},
        "resource_monitoring": {
            "host_complete": True,
            "gpu_complete": None,
            "samples": 1,
        },
    }
    record.update(overrides)
    validate_record(record)
    return record


def as_schema_v2(record: dict[str, object]) -> dict[str, object]:
    """Return the historical schema-v2 shape with self-consistent identities."""

    converted = dict(record)
    converted["schema_version"] = 2
    for field in ("family_id", "molecule", "basis"):
        converted.pop(field)
    identity = dict(converted["logical_identity"])  # type: ignore[arg-type]
    identity["schema_version"] = 2
    for field in ("family_id", "molecule", "basis"):
        identity.pop(field)
    converted["logical_identity"] = identity
    logical_trial_id = make_trial_id(identity)
    converted["logical_trial_id"] = logical_trial_id
    converted["trial_id"] = make_trial_id(
        {"logical_trial_id": logical_trial_id, "attempt_index": 0}
    )
    validate_record(converted)
    return converted


def rehash_schema_v3(record: dict[str, object]) -> None:
    identity = record["logical_identity"]
    assert isinstance(identity, dict)
    logical_trial_id = make_trial_id(identity)
    record["logical_trial_id"] = logical_trial_id
    record["trial_id"] = make_trial_id(
        {
            "logical_trial_id": logical_trial_id,
            "attempt_index": record["attempt_index"],
        }
    )


class TrialIdentityTests(unittest.TestCase):
    def test_canonical_json_and_trial_id_ignore_mapping_key_order(self) -> None:
        first = {
            "backend": "mock",
            "candidate": {"threads": 4, "shuffle": False},
            "inputs": ["alpha", "fcidump"],
        }
        reordered = {
            "inputs": ["alpha", "fcidump"],
            "candidate": {"shuffle": False, "threads": 4},
            "backend": "mock",
        }

        self.assertEqual(canonical_json(first), canonical_json(reordered))
        self.assertEqual(make_trial_id(first), make_trial_id(reordered))

        changed = dict(first)
        changed["backend"] = "cpu"
        self.assertNotEqual(make_trial_id(first), make_trial_id(changed))

    def test_empty_identity_is_rejected(self) -> None:
        with self.assertRaises(RecordError):
            make_trial_id({})


class ImmutableRecordTests(unittest.TestCase):
    def test_v2_rejects_tampered_logical_identity(self) -> None:
        record = as_schema_v2(make_valid_record())
        record["logical_identity"] = {
            **record["logical_identity"],  # type: ignore[arg-type]
            "backend": "cpu",
        }
        with self.assertRaisesRegex(RecordError, "logical_trial_id does not match"):
            validate_record(record)

    def test_v2_rejects_tampered_logical_trial_id(self) -> None:
        record = as_schema_v2(make_valid_record())
        record["logical_trial_id"] = "d" * 64
        with self.assertRaisesRegex(RecordError, "logical_trial_id does not match"):
            validate_record(record)

    def test_v2_rejects_tampered_attempt_index(self) -> None:
        record = as_schema_v2(make_valid_record())
        record["attempt_index"] = 1
        with self.assertRaisesRegex(RecordError, "trial_id does not match"):
            validate_record(record)

    def test_existing_v1_shape_remains_valid_and_loadable(self) -> None:
        record = as_schema_v2(make_valid_record())
        record["schema_version"] = 1
        record.pop("logical_identity")
        record["trial_id"] = make_trial_id(
            {
                "attempt_index": 0,
                "backend": "mock",
                "legacy_identity_shape": True,
            }
        )
        validate_record(record)

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / f"{record['trial_id']}.json"
            write_immutable_json(path, record)
            self.assertEqual(load_record(path), record)

    def test_existing_v2_shape_remains_valid_without_family_metadata(self) -> None:
        record = as_schema_v2(make_valid_record())
        self.assertEqual(record["schema_version"], 2)
        self.assertNotIn("family_id", record)
        validate_record(record)

    def test_v3_requires_and_cross_checks_bound_family_metadata(self) -> None:
        record = make_valid_record()
        self.assertEqual(record["schema_version"], 3)
        self.assertEqual(record["family_id"], "fixture")

        for field in ("family_id", "molecule", "basis"):
            with self.subTest(missing=field):
                missing = dict(record)
                missing.pop(field)
                with self.assertRaisesRegex(RecordError, "Missing required"):
                    validate_record(missing)

        top_level_tamper = dict(record)
        top_level_tamper["molecule"] = "Other"
        with self.assertRaisesRegex(RecordError, "molecule does not match"):
            validate_record(top_level_tamper)

        invalid_slug = dict(record)
        invalid_identity = dict(record["logical_identity"])  # type: ignore[arg-type]
        invalid_identity["family_id"] = "Bad Family"
        invalid_slug["logical_identity"] = invalid_identity
        invalid_slug["family_id"] = "Bad Family"
        rehash_schema_v3(invalid_slug)
        with self.assertRaisesRegex(RecordError, "lowercase ASCII slug"):
            validate_record(invalid_slug)

        wrong_workload = dict(record)
        wrong_identity = dict(record["logical_identity"])  # type: ignore[arg-type]
        wrong_identity["workload"] = "other"
        wrong_workload["logical_identity"] = wrong_identity
        rehash_schema_v3(wrong_workload)
        with self.assertRaisesRegex(RecordError, "problem_instance does not match"):
            validate_record(wrong_workload)

    def test_write_is_immutable_and_preserves_bytes_and_mtime(self) -> None:
        record = make_valid_record()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            path = directory / f"{record['trial_id']}.json"
            write_immutable_json(path, record)

            loaded = load_record(path)
            self.assertEqual(loaded, record)
            original_bytes = path.read_bytes()
            os.utime(path, ns=(1_700_000_000_000_000_000,) * 2)
            original_mtime_ns = path.stat().st_mtime_ns

            replacement = dict(record)
            replacement["notes"] = ["must never replace the original"]
            with self.assertRaises(RecordExistsError):
                write_immutable_json(path, replacement)

            self.assertEqual(path.read_bytes(), original_bytes)
            self.assertEqual(path.stat().st_mtime_ns, original_mtime_ns)
            self.assertEqual(list(directory.glob(f".{path.name}.*.tmp")), [])

    def test_load_rejects_filename_that_does_not_match_trial_id(self) -> None:
        record = make_valid_record()
        wrong_trial_id = "0" * 64
        self.assertNotEqual(wrong_trial_id, record["trial_id"])

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / f"{wrong_trial_id}.json"
            write_immutable_json(path, record)
            with self.assertRaisesRegex(RecordError, "filename does not match"):
                load_record(path)


class TrialClaimTests(unittest.TestCase):
    def test_claim_is_exclusive_and_released_by_context_manager(self) -> None:
        record = make_valid_record()
        with tempfile.TemporaryDirectory() as temporary_directory:
            record_path = Path(temporary_directory) / f"{record['trial_id']}.json"
            first_claim = TrialClaim(record_path, {"trial_id": record["trial_id"]})

            with first_claim:
                self.assertTrue(first_claim.path.is_file())
                payload = json.loads(first_claim.path.read_text(encoding="utf-8"))
                self.assertEqual(payload["trial_id"], record["trial_id"])
                self.assertEqual(payload["pid"], os.getpid())
                self.assertEqual(payload["hostname"], socket.gethostname())
                self.assertIsInstance(payload["process_start_ticks"], int)

                with self.assertRaises(ClaimExistsError):
                    with TrialClaim(record_path, {"trial_id": record["trial_id"]}):
                        self.fail("a second claim unexpectedly acquired the same trial")

                self.assertTrue(first_claim.path.exists())

            self.assertFalse(first_claim.path.exists())
            with TrialClaim(record_path, {"trial_id": record["trial_id"]}) as reacquired:
                self.assertTrue(reacquired.path.exists())
            self.assertFalse(first_claim.path.exists())

    def test_dead_same_host_claim_is_recovered(self) -> None:
        record = make_valid_record()
        with tempfile.TemporaryDirectory() as temporary_directory:
            record_path = Path(temporary_directory) / f"{record['trial_id']}.json"
            claim_path = record_path.with_suffix(record_path.suffix + ".claim")
            claim_path.write_text(
                json.dumps(
                    {
                        "pid": 2_000_000_000,
                        "hostname": socket.gethostname(),
                        "process_start_ticks": 1,
                    }
                ),
                encoding="utf-8",
            )

            with TrialClaim(record_path, {"trial_id": record["trial_id"]}) as recovered:
                payload = json.loads(recovered.path.read_text(encoding="utf-8"))
                self.assertEqual(payload["pid"], os.getpid())

            self.assertFalse(claim_path.exists())

    def test_pid_reuse_mismatch_claim_is_recovered(self) -> None:
        record = make_valid_record()
        own_stat = Path("/proc/self/stat").read_text(encoding="utf-8")
        own_start_ticks = int(own_stat[own_stat.rfind(")") + 1 :].split()[19])
        with tempfile.TemporaryDirectory() as temporary_directory:
            record_path = Path(temporary_directory) / f"{record['trial_id']}.json"
            claim_path = record_path.with_suffix(record_path.suffix + ".claim")
            claim_path.write_text(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "hostname": socket.gethostname(),
                        "process_start_ticks": own_start_ticks + 1,
                    }
                ),
                encoding="utf-8",
            )

            with TrialClaim(record_path, {"trial_id": record["trial_id"]}) as recovered:
                payload = json.loads(recovered.path.read_text(encoding="utf-8"))
                self.assertEqual(payload["process_start_ticks"], own_start_ticks)

            self.assertFalse(claim_path.exists())


if __name__ == "__main__":
    unittest.main()
