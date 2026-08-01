from __future__ import annotations

import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path

from autosbd.config import load_sweep_config
from autosbd.features import extract_input_features


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "reports" / "phasec_parameter_protocol.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PhaseCParameterProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        config_path = ROOT / cls.protocol["correctness_campaign"]["config"]["path"]
        cls.config_path = config_path
        cls.config = load_sweep_config(config_path)

    def test_frozen_scope_and_approval_gate(self) -> None:
        protocol = self.protocol
        self.assertEqual(protocol["schema_version"], 1)
        self.assertEqual(protocol["status"], "frozen_before_correctness")
        self.assertTrue(
            protocol["approval_gate"]["explicit_user_approval_required_before_launch"]
        )
        self.assertEqual(
            protocol["approval_gate"]["status_at_freeze"],
            "awaiting_explicit_phase_c_approval",
        )
        self.assertTrue(protocol["scope"]["official_primary_only"])
        self.assertEqual(
            protocol["scope"]["upstream_git_commit"],
            "729cfa3a5011fb805eb9e686a7711f6919836dcb",
        )
        self.assertIn("no RIKEN executable", protocol["scope"]["riken_role"])

    def test_config_hash_geometry_and_solver_grid_are_frozen(self) -> None:
        expected_hash = self.protocol["correctness_campaign"]["config"]["sha256"]
        self.assertEqual(_sha256(self.config_path), expected_hash)
        templates = self.config.trial_templates(randomize=False)
        self.assertEqual(len(self.config.workloads), 9)
        self.assertEqual(len(self.config.candidates), 8)
        self.assertEqual(len(templates), 72)
        self.assertEqual(len({template.semantic_key for template in templates}), 72)
        self.assertEqual(
            Counter(template.candidate.backend for template in templates),
            {"cpu": 36, "gpu": 36},
        )
        self.assertEqual(
            sorted(
                {
                    (
                        template.candidate.backend,
                        template.solver.bit_length,
                        template.solver.shuffle,
                    )
                    for template in templates
                }
            ),
            [
                ("cpu", 20, 0),
                ("cpu", 20, 1),
                ("cpu", 48, 0),
                ("cpu", 48, 1),
                ("gpu", 20, 0),
                ("gpu", 20, 1),
                ("gpu", 48, 0),
                ("gpu", 48, 1),
            ],
        )
        self.assertEqual(self.config.protocol.warmups, 0)
        self.assertEqual(self.config.protocol.repetitions, 1)
        self.assertEqual(self.config.protocol.timeout_s, 300.0)
        self.assertEqual(self.config.protocol.purpose, "correctness")
        self.assertFalse(self.config.protocol.correctness_validated)

    def test_workload_features_and_references_match_protocol(self) -> None:
        expected = {
            row["name"]: row for row in self.protocol["input_evidence"]["workloads"]
        }
        self.assertEqual(set(expected), {workload.name for workload in self.config.workloads})
        for workload in self.config.workloads:
            with self.subTest(workload=workload.name):
                features = extract_input_features(
                    workload.fcidump,
                    workload.adetfile,
                    workload.bdetfile,
                    max_connectivity_pairs=0,
                )
                row = expected[workload.name]
                self.assertEqual(workload.family_id, row["family_id"])
                self.assertEqual(workload.reference_source, row["reference_source"])
                self.assertEqual(workload.reference_value, row["reference_value"])
                self.assertEqual(features.n_configurations, row["n_configurations"])
                self.assertEqual(features.fcidump.sha256, row["fcidump_sha256"])
                self.assertEqual(features.alpha.sha256, row["alpha_sha256"])
                self.assertEqual(
                    features.combined_input_sha256, row["combined_input_sha256"]
                )

    def test_source_manifest_and_binary_hashes_match(self) -> None:
        for item in self.protocol["source_manifests"].values():
            path = ROOT / item["path"]
            self.assertEqual(_sha256(path), item["sha256"])
        for item in self.protocol["scope"]["binaries"].values():
            path = ROOT / item["path"]
            self.assertEqual(path.stat().st_size, item["size_bytes"])
            self.assertEqual(_sha256(path), item["sha256"])
        semantics = self.protocol["parameter_semantics"]
        source_items = [
            (semantics["bit_length"]["source"]["cache_path"], semantics["bit_length"]["source"]["cache_sha256"]),
            (semantics["bit_length"]["source"]["sample_readme_path"], semantics["bit_length"]["source"]["sample_readme_sha256"]),
            (semantics["shuffle"]["source"]["main_path"], semantics["shuffle"]["source"]["main_sha256"]),
            (semantics["shuffle"]["source"]["readme_path"], semantics["shuffle"]["source"]["readme_sha256"]),
        ]
        for relative, expected_hash in source_items:
            self.assertEqual(_sha256(ROOT / relative), expected_hash)

    def test_record_geometry_and_projection_are_consistent(self) -> None:
        correctness = self.protocol["correctness_campaign"]["expected_records"]
        timing = self.protocol["timing_campaign_after_correctness"]["expected_records"]
        total = self.protocol["total_planned_records"]
        self.assertEqual(correctness, {"measured": 72, "total": 72, "warmup": 0})
        self.assertEqual(timing, {"measured": 72, "total": 144, "warmup": 72})
        self.assertEqual(total["correctness"], correctness["total"])
        self.assertEqual(total["timing_measured"], timing["measured"])
        self.assertEqual(total["timing_warmup"], timing["warmup"])
        self.assertEqual(total["grand_total"], correctness["total"] + timing["total"])
        projection = self.protocol["projection"]
        self.assertAlmostEqual(
            projection["nominal_combined"]["seconds"],
            projection["correctness_only"]["seconds"]
            + projection["timing_only"]["seconds"],
        )
        self.assertGreater(projection["buffer_25_percent"]["minutes"], 10.0)


if __name__ == "__main__":
    unittest.main()
