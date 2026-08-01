from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "prepare_phase_b_workloads.py"
SPEC = importlib.util.spec_from_file_location(
    "prepare_phase_b_workloads_script", SCRIPT_PATH
)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import machinery guard
    raise RuntimeError(f"cannot load {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

PARENTS = {
    "n2": REPOSITORY_ROOT / "external/riken-sbd/data/n2/1em3-alpha.txt",
    "h2o": REPOSITORY_ROOT / "external/riken-sbd/data/h2o/h2o-1em3-alpha.txt",
}
FULL_COUNTS = {"n2": 239, "h2o": 275}
EXPECTED_PREFIX_HASHES = {
    "n2": {
        32: "3d2406670cadd5ba16089fa08af208b469208d3afaf09ff6268aa6bfd2ea7b7d",
        55: "75b771bea9661bb23f98f6e2bdd165e47841cee8e8de91c13959eb40abc54d79",
        100: "bc288d1aa1293c495453c7bb7bf3079aa9d2e03c799715d2835d9a09034b9917",
        174: "89ff6a62b266baf5d449dbc21d728acf318fb5c2f13dfe5e786804033bfe4823",
        239: "73a28f6e6a26b06fbf4accf704f4112dca36ea53fe52ec40ed6379644b218dd2",
    },
    "h2o": {
        32: "6f1fcf262ca0e91cbede71522a4f756cc801a0c7730d2e16552876386f6da58f",
        55: "5e4b39a5043f24f7cdaabbc08de83d9d0b1d7e7bd44d0ee17093d9434de09463",
        100: "e9839cc16b450597bac2d0e1c9e8357d6de0e76b6755aab0d3e73419ab329ce3",
        174: "5cb369df17d90da84c3fb7fb13ff45a490e56281d262c8ae968e235b93c82c10",
        275: "ea94906047a1d081d493066478e9f009c07cb4286541f1781060081205fd5a67",
    },
}


class PreparePhaseBWorkloadsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not MODULE.DEFAULT_INVENTORY.is_file() or not all(
            path.is_file() for path in PARENTS.values()
        ):
            raise unittest.SkipTest("Pinned Phase B inputs are unavailable")

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)
        self.output_directory = self.directory / "derived"

    def test_exact_nested_prefixes_and_combined_strict_manifest(self) -> None:
        outcome = MODULE.prepare_phase_b_workloads(
            output_directory=self.output_directory
        )

        self.assertEqual(outcome["status"], "valid")
        self.assertEqual(outcome["workload_count"], 10)
        self.assertEqual(len(outcome["changed_files"]), 11)
        for family_id, expected_hashes in EXPECTED_PREFIX_HASHES.items():
            parent_payload = PARENTS[family_id].read_bytes()
            parent_lines = parent_payload.splitlines(keepends=True)
            previous = b""
            for count, expected_hash in expected_hashes.items():
                target = (
                    self.output_directory
                    / family_id
                    / f"AlphaDets_n{count:04d}.txt"
                )
                payload = target.read_bytes()
                self.assertEqual(payload, b"".join(parent_lines[:count]))
                self.assertTrue(payload.startswith(previous))
                self.assertEqual(MODULE._sha256(payload), expected_hash)
                previous = payload
            full_path = (
                self.output_directory
                / family_id
                / f"AlphaDets_n{FULL_COUNTS[family_id]:04d}.txt"
            )
            self.assertEqual(full_path.read_bytes(), parent_payload)

        manifest_path = self.output_directory / MODULE.MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(manifest),
            {
                "schema_version",
                "dataset_id",
                "inventory",
                "source_repository",
                "solver_boundary",
                "license",
                "derivation",
                "workloads",
            },
        )
        self.assertEqual(
            manifest["inventory"]["sha256"], MODULE.EXPECTED_INVENTORY_SHA256
        )
        self.assertEqual(manifest["source_repository"]["commit"], MODULE.UPSTREAM_COMMIT)
        self.assertEqual(
            manifest["solver_boundary"]["active_solver_repository"],
            MODULE.ACTIVE_SOLVER_REPOSITORY,
        )
        self.assertEqual(
            manifest["solver_boundary"]["active_solver_commit"],
            MODULE.ACTIVE_SOLVER_COMMIT,
        )
        self.assertFalse(
            manifest["solver_boundary"]["riken_solver_build_run_or_timing_allowed"]
        )
        self.assertEqual(len(manifest["workloads"]), 10)
        for record in manifest["workloads"]:
            count = record["prefix"]["half_determinant_count"]
            self.assertEqual(record["expected_product_configurations"], count * count)
            self.assertEqual(record["family_id"], record["workload_id"].split("-")[0])
            self.assertEqual(record["electronic_structure"]["ms2"], 0)
            self.assertEqual(record["source_and_license"]["license_spdx"], "Apache-2.0")
            self.assertEqual(
                record["output"]["sha256"],
                EXPECTED_PREFIX_HASHES[record["family_id"]][count],
            )
            if record["prefix"]["is_full_official_smallest_list"]:
                self.assertTrue(record["prefix"]["byte_identical_to_parent"])
                self.assertEqual(
                    record["output"]["sha256"],
                    record["parent_determinants"]["sha256"],
                )

    def test_generation_is_changed_only_idempotent_and_check_is_read_only(self) -> None:
        MODULE.prepare_phase_b_workloads(output_directory=self.output_directory)
        paths = sorted(path for path in self.output_directory.rglob("*") if path.is_file())
        before = {
            path.relative_to(self.output_directory).as_posix(): (
                path.read_bytes(),
                path.stat().st_mtime_ns,
            )
            for path in paths
        }

        second = MODULE.prepare_phase_b_workloads(
            output_directory=self.output_directory
        )
        checked = MODULE.prepare_phase_b_workloads(
            output_directory=self.output_directory, check=True
        )
        after = {
            path.relative_to(self.output_directory).as_posix(): (
                path.read_bytes(),
                path.stat().st_mtime_ns,
            )
            for path in paths
        }

        self.assertEqual(second["changed_files"], [])
        self.assertEqual(checked["mode"], "check")
        self.assertEqual(checked["changed_files"], [])
        self.assertEqual(before, after)

    def test_check_rejects_tampered_variant_and_manifest_without_repair(self) -> None:
        MODULE.prepare_phase_b_workloads(output_directory=self.output_directory)
        variant = self.output_directory / "n2" / "AlphaDets_n0055.txt"
        variant.write_bytes(b"tampered\n")
        with self.assertRaisesRegex(MODULE.PreparationError, "differs"):
            MODULE.prepare_phase_b_workloads(
                output_directory=self.output_directory, check=True
            )
        self.assertEqual(variant.read_bytes(), b"tampered\n")

        MODULE.prepare_phase_b_workloads(output_directory=self.output_directory)
        manifest = self.output_directory / MODULE.MANIFEST_NAME
        manifest.write_bytes(manifest.read_bytes() + b" \n")
        with self.assertRaisesRegex(MODULE.PreparationError, "manifest differs"):
            MODULE.prepare_phase_b_workloads(
                output_directory=self.output_directory, check=True
            )
        self.assertTrue(manifest.read_bytes().endswith(b" \n"))

    def test_rejects_inventory_byte_tamper_before_creating_outputs(self) -> None:
        tampered_inventory = self.directory / "inventory.json"
        tampered_inventory.write_bytes(MODULE.DEFAULT_INVENTORY.read_bytes() + b" \n")

        with self.assertRaisesRegex(MODULE.PreparationError, "inventory SHA-256"):
            MODULE.prepare_phase_b_workloads(
                inventory_path=tampered_inventory,
                output_directory=self.output_directory,
            )
        self.assertFalse(self.output_directory.exists())

    def test_generator_rechecks_parent_hash_and_structure(self) -> None:
        real_reader = MODULE._read_stable_regular_file
        n2_parent = PARENTS["n2"].resolve()

        def tampered_reader(path: Path, label: str) -> bytes:
            payload = real_reader(path, label)
            if Path(path).resolve() == n2_parent:
                return b"X" + payload[1:]
            return payload

        with mock.patch.object(
            MODULE, "_read_stable_regular_file", side_effect=tampered_reader
        ):
            with self.assertRaisesRegex(MODULE.PreparationError, "SHA-256 mismatch"):
                MODULE.prepare_phase_b_workloads(output_directory=self.output_directory)
        self.assertFalse(self.output_directory.exists())

        entry = {
            "size_bytes": 4,
            "sha256": MODULE._sha256(b"01X\n"),
            "row_count": 1,
            "string_width": 3,
            "occupied_orbitals": 1,
        }
        with self.assertRaisesRegex(MODULE.PreparationError, "not binary"):
            MODULE._validate_parent_determinants(entry, b"01X\n", "test")

    def test_rejects_unofficial_dirty_wrong_commit_or_wrong_tag_checkout(self) -> None:
        cases = (
            (["https://example.invalid/sbd.git"], "origin mismatch"),
            ([MODULE.UPSTREAM_REPOSITORY, "0" * 40], "commit mismatch"),
            (
                [MODULE.UPSTREAM_REPOSITORY, MODULE.UPSTREAM_COMMIT, "v0.0.0"],
                "tag mismatch",
            ),
            (
                [
                    MODULE.UPSTREAM_REPOSITORY,
                    MODULE.UPSTREAM_COMMIT,
                    MODULE.UPSTREAM_TAG,
                    MODULE.UPSTREAM_COMMIT,
                    " M data/n2/fcidump.txt",
                ],
                "local modifications",
            ),
        )
        for outputs, message in cases:
            with self.subTest(message=message):
                with mock.patch.object(MODULE, "_git_output", side_effect=outputs):
                    with self.assertRaisesRegex(MODULE.PreparationError, message):
                        MODULE.prepare_phase_b_workloads(
                            output_directory=self.output_directory
                        )
                self.assertFalse(self.output_directory.exists())

    def test_refuses_output_inside_upstream_or_outside_project_derived_area(self) -> None:
        forbidden_upstream = MODULE.UPSTREAM_ROOT / "__autosbd_must_not_write"
        with self.assertRaisesRegex(MODULE.PreparationError, "inside pinned upstream"):
            MODULE.prepare_phase_b_workloads(output_directory=forbidden_upstream)
        self.assertFalse(forbidden_upstream.exists())

        forbidden_project = REPOSITORY_ROOT / "reports" / "derived-workloads"
        with self.assertRaisesRegex(MODULE.PreparationError, "under data/derived"):
            MODULE.prepare_phase_b_workloads(output_directory=forbidden_project)
        self.assertFalse(forbidden_project.exists())


if __name__ == "__main__":
    unittest.main()
