from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "prepare_workloads.py"
SPEC = importlib.util.spec_from_file_location("prepare_workloads_script", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import machinery guard
    raise RuntimeError(f"cannot load {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SOURCE = (
    REPOSITORY_ROOT
    / "external"
    / "amd-sbd"
    / "samples"
    / "selected_basis_diagonalization"
    / "AlphaDets.txt"
)
FCIDUMP = SOURCE.with_name("fcidump_Fe4S4.txt")
EXPECTED_PREFIX_HASHES = {
    32: "5f2beadb720d61c467a3ee8ee9f127152e1a69b2edcdad3139d74888d5d4cbc8",
    55: "2b296f3011a87e9bf7f9682b8de25e78442ac6bcb47942bf8003ecdeb65d3ef1",
    100: "2722d475430a07b416dce775f7daa5e084aa49f90d27b8cd756ecf45c4b96a8a",
    174: "bad29cfa68e324ae9a63b22bf5d18e86f6766a2f251371ae92ab6080e1c33b67",
    244: "b1aa7e60cfde6adc39f9271bb2c6d8d15774a694e746e66bab44db9842748f68",
}


class PrepareWorkloadsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not SOURCE.is_file() or not FCIDUMP.is_file():
            raise unittest.SkipTest("Pinned AMD Fe4S4 inputs are unavailable")
        cls.source_payload = SOURCE.read_bytes()

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)
        self.output_directory = self.directory / "derived"

    def test_exact_nested_prefixes_and_auditable_manifest(self) -> None:
        outcome = MODULE.prepare_workloads(output_directory=self.output_directory)

        self.assertEqual(outcome["status"], "valid")
        self.assertEqual(
            set(outcome["changed_files"]),
            {
                "AlphaDets_n0032.txt",
                "AlphaDets_n0055.txt",
                "AlphaDets_n0100.txt",
                "AlphaDets_n0174.txt",
                "AlphaDets_n0244.txt",
                "manifest.json",
            },
        )
        source_lines = self.source_payload.splitlines(keepends=True)
        previous = b""
        for size, expected_hash in EXPECTED_PREFIX_HASHES.items():
            path = self.output_directory / f"AlphaDets_n{size:04d}.txt"
            payload = path.read_bytes()
            self.assertEqual(payload, b"".join(source_lines[:size]))
            self.assertTrue(payload.startswith(previous))
            self.assertEqual(MODULE._sha256(payload), expected_hash)
            previous = payload

        manifest = json.loads(
            (self.output_directory / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["upstream"]["commit"], MODULE.UPSTREAM_COMMIT)
        self.assertEqual(
            manifest["upstream"]["source_determinants"]["sha256"],
            MODULE.EXPECTED_SOURCE_SHA256,
        )
        self.assertEqual(
            manifest["upstream"]["companion_fcidump"]["sha256"],
            MODULE.EXPECTED_FCIDUMP_SHA256,
        )
        self.assertFalse(
            manifest["upstream"]["companion_fcidump"]["copied_or_modified"]
        )
        self.assertEqual(
            manifest["dataset_scope"]["variant_type"],
            "derived_determinant_prefix_size",
        )
        self.assertFalse(manifest["dataset_scope"]["distinct_chemical_families"])
        self.assertEqual(manifest["dataset_scope"]["family_count"], 1)
        self.assertEqual(
            [item["output"]["sha256"] for item in manifest["variants"]],
            list(EXPECTED_PREFIX_HASHES.values()),
        )

    def test_generation_is_idempotent_and_check_is_read_only(self) -> None:
        MODULE.prepare_workloads(output_directory=self.output_directory)
        paths = sorted(self.output_directory.iterdir())
        before = {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths
        }

        second = MODULE.prepare_workloads(output_directory=self.output_directory)
        checked = MODULE.prepare_workloads(
            output_directory=self.output_directory, check=True
        )
        after = {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths
        }

        self.assertEqual(second["changed_files"], [])
        self.assertEqual(checked["mode"], "check")
        self.assertEqual(checked["changed_files"], [])
        self.assertEqual(before, after)

    def test_check_rejects_tampered_variant_without_repairing_it(self) -> None:
        MODULE.prepare_workloads(output_directory=self.output_directory)
        target = self.output_directory / "AlphaDets_n0055.txt"
        target.write_bytes(b"tampered\n")

        with self.assertRaisesRegex(MODULE.PreparationError, "differs"):
            MODULE.prepare_workloads(
                output_directory=self.output_directory,
                check=True,
            )
        self.assertEqual(target.read_bytes(), b"tampered\n")

    def test_rejects_unexpected_source_hash_count_and_format(self) -> None:
        with mock.patch.object(MODULE, "EXPECTED_SOURCE_SHA256", "0" * 64):
            with self.assertRaisesRegex(MODULE.PreparationError, "SHA-256"):
                MODULE.prepare_workloads(output_directory=self.output_directory)
        self.assertFalse(self.output_directory.exists())

        short_source = self.directory / "short.txt"
        short_source.write_bytes(b"".join(self.source_payload.splitlines(keepends=True)[:-1]))
        with self.assertRaisesRegex(MODULE.PreparationError, "determinant count"):
            MODULE.prepare_workloads(
                source=short_source,
                output_directory=self.output_directory,
            )

        malformed_source = self.directory / "malformed.txt"
        malformed_source.write_bytes(b"x" + self.source_payload[1:])
        with self.assertRaisesRegex(MODULE.PreparationError, "non-binary"):
            MODULE.prepare_workloads(
                source=malformed_source,
                output_directory=self.output_directory,
            )
        self.assertFalse(self.output_directory.exists())

    def test_rejects_unexpected_fcidump_without_creating_outputs(self) -> None:
        bad_fcidump = self.directory / "FCIDUMP"
        bad_fcidump.write_bytes(FCIDUMP.read_bytes()[:-1])

        with self.assertRaisesRegex(MODULE.PreparationError, "FCIDUMP byte count"):
            MODULE.prepare_workloads(
                fcidump=bad_fcidump,
                output_directory=self.output_directory,
            )
        self.assertFalse(self.output_directory.exists())

    def test_refuses_output_inside_pinned_upstream(self) -> None:
        forbidden = MODULE.SAMPLE_DIRECTORY / "__autosbd_test_must_not_write"
        with self.assertRaisesRegex(MODULE.PreparationError, "pinned upstream"):
            MODULE._validate_output_location(forbidden, SOURCE, FCIDUMP)
        self.assertFalse(forbidden.exists())

    def test_rejects_unofficial_dirty_or_wrong_commit_checkout(self) -> None:
        cases = (
            (
                ["https://example.invalid/not-amd-sbd.git"],
                "origin mismatch",
            ),
            (
                [MODULE.UPSTREAM_REPOSITORY, "0" * 40],
                "commit mismatch",
            ),
            (
                [MODULE.UPSTREAM_REPOSITORY, MODULE.UPSTREAM_COMMIT, " M source"],
                "local modifications",
            ),
        )
        for outputs, message in cases:
            with self.subTest(message=message):
                with mock.patch.object(MODULE, "_git_output", side_effect=outputs):
                    with self.assertRaisesRegex(MODULE.PreparationError, message):
                        MODULE.prepare_workloads(
                            output_directory=self.output_directory,
                        )
                self.assertFalse(self.output_directory.exists())


if __name__ == "__main__":
    unittest.main()
