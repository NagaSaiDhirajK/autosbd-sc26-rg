"""Tests for external family augmentation of immutable Stage 4 evidence."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from autosbd.family_registry import (
    BASIS_STATUS,
    EXPECTED_AGGREGATE_PATH,
    EXPECTED_COMPLETION_PATH,
    EXPECTED_RAW_DIRECTORY,
    FAMILY_ID,
    FamilyRegistryError,
    build_fe4s4_family_registry,
    resolve_family_entry,
    sha256_path,
    validate_family_registry,
    write_family_registry,
)


ROOT = Path(__file__).resolve().parents[1]


class FamilyRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.completion_path = ROOT / EXPECTED_COMPLETION_PATH
        cls.aggregate_path = ROOT / EXPECTED_AGGREGATE_PATH
        cls.raw_dir = ROOT / EXPECTED_RAW_DIRECTORY
        cls.completion = json.loads(cls.completion_path.read_text(encoding="utf-8"))
        cls.registry = build_fe4s4_family_registry(
            cls.completion_path,
            cls.aggregate_path,
            cls.raw_dir,
            repository_root=ROOT,
        )

    def build(self, root: Path = ROOT) -> dict[str, object]:
        return build_fe4s4_family_registry(
            root / EXPECTED_COMPLETION_PATH,
            root / EXPECTED_AGGREGATE_PATH,
            root / EXPECTED_RAW_DIRECTORY,
            repository_root=root,
        )

    def copy_evidence(self, destination: Path) -> None:
        paths = {
            Path(EXPECTED_COMPLETION_PATH),
            Path(EXPECTED_AGGREGATE_PATH),
        }
        for record in self.completion["records"]:
            raw_relative = Path(record["raw_record"]["path"])
            paths.add(raw_relative)
            raw = json.loads((ROOT / raw_relative).read_text(encoding="utf-8"))
            paths.update(Path(item["path"]) for item in raw["input_files"])
        for relative in sorted(paths):
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)

    def test_real_registry_has_five_exact_entries_and_preserves_raw_bytes(self) -> None:
        before = {
            item["trial_id"]: sha256_path(ROOT / item["raw_record"]["path"])
            for item in self.completion["records"]
        }
        registry = self.build()
        after = {
            item["trial_id"]: sha256_path(ROOT / item["raw_record"]["path"])
            for item in self.completion["records"]
        }
        self.assertEqual(before, after)
        self.assertEqual(registry, self.registry)
        self.assertEqual(registry["record_counts"], {
            "workload_entries": 5,
            "raw_records": 48,
        })
        self.assertEqual(len(registry["records"]), 48)
        self.assertEqual(
            [entry["n_configurations"] for entry in registry["workloads"]],
            [1024, 3025, 10000, 30276, 59536],
        )
        self.assertTrue(all(entry["family_id"] == FAMILY_ID for entry in registry["workloads"]))
        self.assertTrue(all(entry["molecule"] == "Fe4S4" for entry in registry["workloads"]))
        self.assertTrue(all(entry["basis"] is None for entry in registry["workloads"]))
        self.assertTrue(
            all(entry["basis_status"] == BASIS_STATUS for entry in registry["workloads"])
        )
        self.assertIsNone(registry["family"]["basis"])
        self.assertEqual(registry["family"]["basis_status"], BASIS_STATUS)
        self.assertFalse(registry["augmentation_contract"]["raw_records_modified"])
        self.assertFalse(registry["augmentation_contract"]["raw_trial_ids_modified"])

    def test_exact_lookup_and_disagreement_paths_fail_closed(self) -> None:
        entry = self.registry["workloads"][0]
        components = entry["components"]
        resolved = resolve_family_entry(
            self.registry,
            problem_instance=entry["problem_instance"],
            input_sha256=entry["input_sha256"],
            fcidump_sha256=components["fcidump"]["sha256"],
            alpha_determinant_sha256=components["alpha_determinants"]["sha256"],
            beta_determinant_sha256=components["beta_determinants"]["sha256"],
            n_configurations=entry["n_configurations"],
        )
        self.assertEqual(resolved["entry_id"], entry["entry_id"])
        with self.assertRaisesRegex(FamilyRegistryError, "instance/hash disagreement"):
            resolve_family_entry(
                self.registry,
                problem_instance=entry["problem_instance"],
                input_sha256="0" * 64,
                fcidump_sha256=components["fcidump"]["sha256"],
                alpha_determinant_sha256=components["alpha_determinants"]["sha256"],
                beta_determinant_sha256=components["beta_determinants"]["sha256"],
                n_configurations=entry["n_configurations"],
            )
        with self.assertRaisesRegex(FamilyRegistryError, "unknown family mapping"):
            resolve_family_entry(
                self.registry,
                problem_instance="unknown-instance",
                input_sha256="0" * 64,
                fcidump_sha256=components["fcidump"]["sha256"],
                alpha_determinant_sha256=components["alpha_determinants"]["sha256"],
                beta_determinant_sha256=components["beta_determinants"]["sha256"],
                n_configurations=entry["n_configurations"],
            )
        with self.assertRaisesRegex(FamilyRegistryError, "component-hash disagreement"):
            resolve_family_entry(
                self.registry,
                problem_instance=entry["problem_instance"],
                input_sha256=entry["input_sha256"],
                fcidump_sha256="0" * 64,
                alpha_determinant_sha256=components["alpha_determinants"]["sha256"],
                beta_determinant_sha256=components["beta_determinants"]["sha256"],
                n_configurations=entry["n_configurations"],
            )

    def test_duplicate_and_ambiguous_registry_mappings_fail(self) -> None:
        duplicate_entry = deepcopy(self.registry)
        duplicate_entry["workloads"].append(deepcopy(duplicate_entry["workloads"][0]))
        duplicate_entry["record_counts"]["workload_entries"] += 1
        duplicate_entry["registry_id"] = self._registry_id(duplicate_entry)
        with self.assertRaisesRegex(FamilyRegistryError, "ambiguous"):
            validate_family_registry(duplicate_entry)

        duplicate_record = deepcopy(self.registry)
        duplicate_record["records"].append(deepcopy(duplicate_record["records"][0]))
        duplicate_record["record_counts"]["raw_records"] += 1
        duplicate_record["registry_id"] = self._registry_id(duplicate_record)
        with self.assertRaisesRegex(FamilyRegistryError, "duplicate registry record"):
            validate_family_registry(duplicate_record)

        tampered_source = deepcopy(self.registry)
        tampered_source["sources"]["stage4_completion"]["sha256"] = "0" * 64
        tampered_source["registry_id"] = self._registry_id(tampered_source)
        with self.assertRaisesRegex(FamilyRegistryError, "source path/SHA/size"):
            validate_family_registry(tampered_source)

    def test_unknown_workload_and_record_fields_fail_after_id_recomputed(self) -> None:
        unknown_workload_field = deepcopy(self.registry)
        unknown_workload_field["workloads"][0]["unregistered_metadata"] = "reject"
        unknown_workload_field["registry_id"] = self._registry_id(
            unknown_workload_field
        )
        with self.assertRaisesRegex(
            FamilyRegistryError, "workload entry fields differ"
        ):
            validate_family_registry(unknown_workload_field)

        unknown_record_field = deepcopy(self.registry)
        unknown_record_field["records"][0]["unregistered_metadata"] = "reject"
        unknown_record_field["registry_id"] = self._registry_id(unknown_record_field)
        with self.assertRaisesRegex(
            FamilyRegistryError, "record mapping fields differ"
        ):
            validate_family_registry(unknown_record_field)

    def test_altered_aggregate_and_raw_bytes_fail_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.copy_evidence(root)
            aggregate = root / EXPECTED_AGGREGATE_PATH
            aggregate.write_bytes(aggregate.read_bytes() + b"\n")
            with self.assertRaisesRegex(FamilyRegistryError, "aggregate SHA-256 mismatch"):
                self.build(root)

        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.copy_evidence(root)
            raw = root / self.completion["records"][0]["raw_record"]["path"]
            before = raw.read_bytes()
            raw.write_bytes(before + b"\n")
            with self.assertRaisesRegex(FamilyRegistryError, "raw record .* size mismatch"):
                self.build(root)
            self.assertEqual(raw.read_bytes(), before + b"\n")

    def test_component_disagreement_between_verified_layers_fails(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.copy_evidence(root)
            aggregate_path = root / EXPECTED_AGGREGATE_PATH
            completion_path = root / EXPECTED_COMPLETION_PATH
            aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
            aggregate["rows"][0]["features"]["alpha"]["sha256"] = "0" * 64
            aggregate_path.write_text(
                json.dumps(aggregate, allow_nan=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            completion = json.loads(completion_path.read_text(encoding="utf-8"))
            completion["source_artifacts"]["aggregate"]["sha256"] = sha256_path(
                aggregate_path
            )
            completion["source_artifacts"]["aggregate"]["size_bytes"] = aggregate_path.stat().st_size
            completion_path.write_text(
                json.dumps(completion, allow_nan=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            # Frozen source hashes reject the altered layers before semantic use.
            with self.assertRaisesRegex(FamilyRegistryError, "completion SHA-256 mismatch"):
                self.build(root)

    def test_atomic_changed_only_check_mode_and_raw_output_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            output = root / "reports" / "registry.json"
            forbidden = root / "results" / "raw"
            forbidden.mkdir(parents=True)
            self.assertTrue(
                write_family_registry(
                    self.registry, output, forbidden_directory=forbidden
                )
            )
            first = output.read_bytes()
            self.assertFalse(
                write_family_registry(
                    self.registry, output, forbidden_directory=forbidden
                )
            )
            self.assertFalse(
                write_family_registry(
                    self.registry,
                    output,
                    check=True,
                    forbidden_directory=forbidden,
                )
            )
            output.write_bytes(first + b" ")
            with self.assertRaisesRegex(FamilyRegistryError, "check failed"):
                write_family_registry(
                    self.registry,
                    output,
                    check=True,
                    forbidden_directory=forbidden,
                )
            with self.assertRaisesRegex(FamilyRegistryError, "results/raw"):
                write_family_registry(
                    self.registry,
                    forbidden / "registry.json",
                    forbidden_directory=forbidden,
                )

    @staticmethod
    def _registry_id(registry: dict[str, object]) -> str:
        value = {key: item for key, item in registry.items() if key != "registry_id"}
        return hashlib.sha256(
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()


if __name__ == "__main__":
    unittest.main()
