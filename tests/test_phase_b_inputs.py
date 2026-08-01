from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_phase_b_inputs.py"
MANIFEST = ROOT / "reports" / "phase_b_input_inventory.json"
SPEC = importlib.util.spec_from_file_location("validate_phase_b_inputs", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PhaseBInputInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = copy.deepcopy(MODULE.load_manifest(MANIFEST))

    def _write_manifest(self, directory: Path, manifest: object) -> Path:
        path = directory / "inventory.json"
        path.write_text(
            json.dumps(manifest, allow_nan=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def test_pinned_real_inventory_passes(self) -> None:
        result = MODULE.validate_inventory(MANIFEST, ROOT)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["families"], ["h2o", "n2"])
        self.assertEqual(result["artifact_count"], 20)
        self.assertEqual(result["determinant_file_count"], 15)
        self.assertEqual(result["source_commit"], MODULE.EXPECTED_COMMIT)

    def test_hash_tamper_fails_full_validation(self) -> None:
        self.manifest["families"][0]["files"][2]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            path = self._write_manifest(Path(temporary), self.manifest)
            with self.assertRaisesRegex(MODULE.InventoryError, "SHA-256 mismatch"):
                MODULE.validate_inventory(path, ROOT)

    def test_structural_tamper_fails_even_with_matching_size_and_hash(self) -> None:
        entry = self.manifest["families"][0]["files"][2]
        target = ROOT / entry["path"]
        original_payload = target.read_bytes()
        tampered_payload = b"X" + original_payload[1:]
        entry["sha256"] = hashlib.sha256(tampered_payload).hexdigest()
        entry["size_bytes"] = len(tampered_payload)
        original_reader = MODULE._read_stable_file

        def substituted_reader(path: Path) -> bytes:
            if path == target.resolve():
                return tampered_payload
            return original_reader(path)

        with tempfile.TemporaryDirectory() as temporary:
            path = self._write_manifest(Path(temporary), self.manifest)
            with patch.object(MODULE, "_read_stable_file", side_effect=substituted_reader):
                with self.assertRaisesRegex(MODULE.InventoryError, "is not binary"):
                    MODULE.validate_inventory(path, ROOT)

    def test_strict_json_and_closed_schema_reject_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            duplicate = directory / "duplicate.json"
            duplicate.write_text(
                '{"schema_version": 1, "schema_version": 1}\n', encoding="utf-8"
            )
            with self.assertRaisesRegex(MODULE.InventoryError, "duplicate JSON key"):
                MODULE.load_manifest(duplicate)

            floating = directory / "floating.json"
            floating.write_text('{"schema_version": 1.0}\n', encoding="utf-8")
            with self.assertRaisesRegex(MODULE.InventoryError, "floating-point JSON value"):
                MODULE.load_manifest(floating)

            unknown = copy.deepcopy(self.manifest)
            unknown["unreviewed"] = True
            with self.assertRaisesRegex(MODULE.InventoryError, r"unknown=\['unreviewed'\]"):
                MODULE.validate_manifest_schema(unknown)


if __name__ == "__main__":
    unittest.main()
