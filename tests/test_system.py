"""Focused tests for semantic input and system/preflight provenance."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import autosbd.system as system


SECRET_KEY = "AUTOSBD_TEST_SECRET_TOKEN"
SECRET_VALUE = "must-not-appear-in-provenance-9f6435"


def mapping_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.add(str(key).lower())
            keys.update(mapping_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            keys.update(mapping_keys(nested))
    return keys


class SemanticInputHashTests(unittest.TestCase):
    def test_hash_is_stable_across_paths_and_mapping_insertion_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_root = root / "first"
            second_root = root / "second"
            first_root.mkdir()
            second_root.mkdir()

            first_fcidump = first_root / "FCIDUMP"
            first_alpha = first_root / "AlphaDets.txt"
            second_fcidump = second_root / "renamed-integrals.dat"
            second_alpha = second_root / "renamed-determinants.dat"
            for path in (first_fcidump, second_fcidump):
                path.write_bytes(b"semantic fcidump bytes\n")
            for path in (first_alpha, second_alpha):
                path.write_bytes(b"1010\n0101\n")

            first = system.describe_input_files(
                {"fcidump": first_fcidump, "alpha": first_alpha}, first_root
            )
            second = system.describe_input_files(
                {"alpha": second_alpha, "fcidump": second_fcidump}, second_root
            )

            self.assertEqual([item["role"] for item in first], ["alpha", "fcidump"])
            self.assertEqual([item["role"] for item in second], ["alpha", "fcidump"])
            self.assertNotEqual(
                [item["path"] for item in first], [item["path"] for item in second]
            )
            self.assertEqual(
                system.combined_input_sha256(first),
                system.combined_input_sha256(second),
            )

            second_alpha.write_bytes(b"0101\n1010\n")
            changed = system.describe_input_files(
                {"alpha": second_alpha, "fcidump": second_fcidump}, second_root
            )
            self.assertNotEqual(
                system.combined_input_sha256(first),
                system.combined_input_sha256(changed),
            )

    def test_hash_is_role_sensitive(self) -> None:
        first = [
            {"role": "alpha", "sha256": "a" * 64, "size_bytes": 10},
            {"role": "fcidump", "sha256": "b" * 64, "size_bytes": 20},
        ]
        swapped = [
            {"role": "alpha", "sha256": "b" * 64, "size_bytes": 20},
            {"role": "fcidump", "sha256": "a" * 64, "size_bytes": 10},
        ]
        self.assertNotEqual(
            system.combined_input_sha256(first),
            system.combined_input_sha256(swapped),
        )


class GitStateTests(unittest.TestCase):
    @staticmethod
    def git(repository: Path, *arguments: str) -> None:
        subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )

    def make_repository(self, root: Path, *, tracked_raw_json: bool = False) -> Path:
        repository = root / "repository"
        repository.mkdir()
        self.git(repository, "init", "--quiet")
        self.git(repository, "config", "user.name", "AutoSBD Test")
        self.git(repository, "config", "user.email", "autosbd-test@example.invalid")
        self.git(repository, "remote", "add", "origin", "https://example.invalid/test.git")
        (repository / "seed.txt").write_text("seed\n", encoding="utf-8")
        if tracked_raw_json:
            raw = repository / "results" / "raw"
            raw.mkdir(parents=True)
            (raw / "tracked.json").write_text('{"state":"original"}\n', encoding="utf-8")
        self.git(repository, "add", ".")
        self.git(repository, "commit", "--quiet", "-m", "initial")
        return repository

    def test_optional_filter_ignores_only_untracked_raw_json_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = self.make_repository(Path(temporary_directory))
            raw = repository / "results" / "raw"
            nested = raw / "nested"
            nested.mkdir(parents=True)
            (raw / "direct.json").write_text("{}\n", encoding="utf-8")
            (nested / "record.json").write_text("{}\n", encoding="utf-8")

            self.assertTrue(system.git_state(repository)["dirty"])
            self.assertFalse(
                system.git_state(
                    repository,
                    ignore_untracked_json_under=Path("results/raw"),
                )["dirty"]
            )

    def test_filter_keeps_other_untracked_files_dirty(self) -> None:
        cases = (
            Path("results/raw/record.txt"),
            Path("results/raw/record.JSON"),
            Path("elsewhere/record.json"),
        )
        for relative_path in cases:
            with (
                self.subTest(path=str(relative_path)),
                tempfile.TemporaryDirectory() as temporary_directory,
            ):
                repository = self.make_repository(Path(temporary_directory))
                path = repository / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")

                self.assertTrue(
                    system.git_state(
                        repository,
                        ignore_untracked_json_under=Path("results/raw"),
                    )["dirty"]
                )

    def test_filter_keeps_untracked_symlink_dirty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository = self.make_repository(root)
            raw = repository / "results" / "raw"
            raw.mkdir(parents=True)
            target = root / "target.json"
            target.write_text("{}\n", encoding="utf-8")
            (raw / "record.json").symlink_to(target)

            self.assertTrue(
                system.git_state(
                    repository,
                    ignore_untracked_json_under=Path("results/raw"),
                )["dirty"]
            )

    def test_filter_rejects_directory_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository = self.make_repository(root)
            raw = repository / "results" / "raw"
            raw.mkdir(parents=True)
            (raw / "record.json").write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "inside repository"):
                system.git_state(
                    repository,
                    ignore_untracked_json_under=root / "outside",
                )

    def test_filter_keeps_tracked_raw_json_changes_dirty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = self.make_repository(
                Path(temporary_directory), tracked_raw_json=True
            )
            tracked = repository / "results" / "raw" / "tracked.json"
            tracked.write_text('{"state":"modified"}\n', encoding="utf-8")
            self.assertTrue(
                system.git_state(
                    repository,
                    ignore_untracked_json_under=Path("results/raw"),
                )["dirty"]
            )

            tracked.write_text('{"state":"original"}\n', encoding="utf-8")
            tracked.unlink()
            self.assertTrue(
                system.git_state(
                    repository,
                    ignore_untracked_json_under=Path("results/raw"),
                )["dirty"]
            )


class SystemSnapshotTests(unittest.TestCase):
    def assert_no_environment_secret(self, payload: dict[str, object]) -> None:
        serialized = json.dumps(payload, sort_keys=True)
        self.assertNotIn(SECRET_KEY, serialized)
        self.assertNotIn(SECRET_VALUE, serialized)
        sensitive_fragments = ("password", "secret", "token", "credential", "api_key")
        for key in mapping_keys(payload):
            self.assertFalse(
                any(fragment in key for fragment in sensitive_fragments),
                f"snapshot contains a secret-like key: {key}",
            )

    def test_static_snapshot_has_basic_schema_and_no_secrets(self) -> None:
        fake_gpu = {
            "index": 0,
            "uuid": "GPU-test-uuid",
            "name": "NVIDIA L4",
            "driver_version": "580.173.02",
            "compute_capability": "8.9",
            "memory_total_mib": 23_034.0,
            "memory_used_mib": 0.0,
            "memory_free_mib": 22_564.0,
            "utilization_gpu_pct": 0.0,
            "temperature_c": 34.0,
            "power_draw_w": 16.5,
            "power_limit_w": 72.0,
        }
        with (
            mock.patch.dict(os.environ, {SECRET_KEY: SECRET_VALUE}),
            mock.patch.object(system, "query_gpu", return_value=fake_gpu),
            mock.patch.object(system.socket, "gethostname", return_value="test-host"),
            mock.patch.object(system, "_cpu_model", return_value="test-cpu"),
            mock.patch.object(system, "_physical_core_count", return_value=16),
            mock.patch.object(system.os, "cpu_count", return_value=32),
        ):
            snapshot = system.static_system_snapshot("12.9.41")

        self.assertEqual(
            set(snapshot),
            {
                "hostname",
                "cpu_model",
                "physical_cores",
                "logical_cpus",
                "gpu",
                "cuda_toolkit_version",
                "machine_fingerprint",
            },
        )
        self.assertEqual(snapshot["hostname"], "test-host")
        self.assertEqual(snapshot["physical_cores"], 16)
        self.assertEqual(snapshot["logical_cpus"], 32)
        self.assertEqual(snapshot["gpu"], fake_gpu)
        self.assertRegex(str(snapshot["machine_fingerprint"]), r"^[0-9a-f]{64}$")
        self.assert_no_environment_secret(snapshot)

    def test_dynamic_preflight_has_basic_schema_caps_and_no_secrets(self) -> None:
        fake_gpu = {
            "name": "NVIDIA L4",
            "memory_free_mib": 1_000.0,
            "temperature_c": 34.0,
            "power_draw_w": 16.5,
        }
        host_available = 10_000_000_000
        with (
            mock.patch.dict(os.environ, {SECRET_KEY: SECRET_VALUE}),
            mock.patch.object(system, "query_gpu", return_value=fake_gpu),
            mock.patch.object(system, "query_gpu_processes", return_value=[]),
            mock.patch.object(system, "_mem_available_bytes", return_value=host_available),
            mock.patch.object(system.os, "getloadavg", return_value=(0.25, 0.5, 0.75)),
        ):
            preflight = system.dynamic_preflight()

        self.assertEqual(
            set(preflight),
            {
                "load_average_1m",
                "host_memory_available_bytes",
                "host_memory_cap_bytes",
                "gpu",
                "gpu_compute_processes",
                "gpu_process_query_ok",
                "gpu_idle",
                "gpu_memory_cap_bytes",
                "gpu_memory_policy",
            },
        )
        self.assertEqual(preflight["load_average_1m"], 0.25)
        self.assertEqual(preflight["host_memory_available_bytes"], host_available)
        self.assertEqual(preflight["host_memory_cap_bytes"], int(0.8 * host_available))
        self.assertTrue(preflight["gpu_idle"])
        self.assertTrue(preflight["gpu_process_query_ok"])
        self.assertEqual(preflight["gpu_compute_processes"], [])
        self.assertEqual(
            preflight["gpu_memory_cap_bytes"], int(0.8 * 1_000 * system.MIB)
        )
        self.assertEqual(
            preflight["gpu_memory_policy"],
            "min(20 GiB, 80% of preflight free VRAM)",
        )
        self.assert_no_environment_secret(preflight)

    def test_dynamic_preflight_tolerates_missing_gpu_memory_value(self) -> None:
        fake_gpu = {"name": "NVIDIA L4", "memory_free_mib": None}
        with (
            mock.patch.object(system, "query_gpu", return_value=fake_gpu),
            mock.patch.object(system, "query_gpu_processes", return_value=[]),
            mock.patch.object(system, "_mem_available_bytes", return_value=1_000_000),
            mock.patch.object(system.os, "getloadavg", return_value=(0.0, 0.0, 0.0)),
        ):
            preflight = system.dynamic_preflight()
        self.assertIsNone(preflight["gpu_memory_cap_bytes"])
        self.assertTrue(preflight["gpu_idle"])

    def test_dynamic_preflight_fails_closed_when_process_query_fails(self) -> None:
        fake_gpu = {"name": "NVIDIA L4", "memory_free_mib": 1_000.0}
        with (
            mock.patch.object(system, "query_gpu", return_value=fake_gpu),
            mock.patch.object(system, "query_gpu_processes", return_value=None),
            mock.patch.object(system, "_mem_available_bytes", return_value=1_000_000),
            mock.patch.object(system.os, "getloadavg", return_value=(0.0, 0.0, 0.0)),
        ):
            preflight = system.dynamic_preflight()

        self.assertFalse(preflight["gpu_process_query_ok"])
        self.assertIsNone(preflight["gpu_compute_processes"])
        self.assertIsNone(preflight["gpu_idle"])

    def test_dynamic_preflight_without_gpu_does_not_claim_query_or_idle(self) -> None:
        with (
            mock.patch.object(system, "query_gpu", return_value=None),
            mock.patch.object(system, "query_gpu_processes") as process_query,
            mock.patch.object(system, "_mem_available_bytes", return_value=1_000_000),
            mock.patch.object(system.os, "getloadavg", return_value=(0.0, 0.0, 0.0)),
        ):
            preflight = system.dynamic_preflight()

        process_query.assert_not_called()
        self.assertIsNone(preflight["gpu_process_query_ok"])
        self.assertIsNone(preflight["gpu_compute_processes"])
        self.assertIsNone(preflight["gpu_idle"])


class GpuProcessQueryTests(unittest.TestCase):
    @staticmethod
    def completed(stdout: str, returncode: int = 0) -> object:
        return system.subprocess.CompletedProcess(
            args=["nvidia-smi"], returncode=returncode, stdout=stdout, stderr=""
        )

    def test_successful_empty_query_is_the_only_empty_list_result(self) -> None:
        with mock.patch.object(
            system.subprocess, "run", return_value=self.completed("")
        ):
            self.assertEqual(system.query_gpu_processes(), [])

    def test_successful_rows_are_parsed(self) -> None:
        with mock.patch.object(
            system.subprocess,
            "run",
            return_value=self.completed("1234, /tmp/solver, 87.5\n"),
        ):
            self.assertEqual(
                system.query_gpu_processes(),
                [
                    {
                        "pid": 1234,
                        "process_name": "/tmp/solver",
                        "used_gpu_memory_mib": 87.5,
                    }
                ],
            )

    def test_query_failures_return_none(self) -> None:
        failures = (
            OSError("nvidia-smi unavailable"),
            system.subprocess.TimeoutExpired(["nvidia-smi"], 5),
            self.completed("", returncode=1),
            self.completed("malformed row\n"),
            self.completed("not-a-pid, solver, 10\n"),
            self.completed("123, solver, [Not Supported]\n"),
            self.completed("123, solver, nan\n"),
            self.completed('123, "unterminated, 10\n'),
        )
        for index, failure in enumerate(failures):
            with self.subTest(index=index):
                if isinstance(failure, BaseException):
                    patch = mock.patch.object(
                        system.subprocess, "run", side_effect=failure
                    )
                else:
                    patch = mock.patch.object(
                        system.subprocess, "run", return_value=failure
                    )
                with patch:
                    self.assertIsNone(system.query_gpu_processes())


if __name__ == "__main__":
    unittest.main()
